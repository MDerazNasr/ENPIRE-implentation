"""Versioned M6 actor-objective ABI and isolated validation records."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from supervisor.canonical import ContractError, require_safe_relative_path, require_sha256


OBJECTIVE_CONTRACT_VERSION = "m6-actor-objective-v1"
OBJECTIVE_FUNCTION = "combine_actor_objective"
OBJECTIVE_ARGUMENTS = ("actor_loss", "bc_loss", "bc_weight")
OBJECTIVE_RELATIVE_PATH = "supervisor/objectives/actor_objective.py"
MAX_VALIDATOR_OUTPUT_BYTES = 262_144
OBJECTIVE_IMPORT_ROOTS = {"math", "torch"}
OBJECTIVE_CALL_NAMES = {"abs", "float", "max", "min"}
OBJECTIVE_CALL_ATTRIBUTES = {
    "abs",
    "clamp",
    "exp",
    "log",
    "maximum",
    "mean",
    "minimum",
    "nan_to_num",
    "relu",
    "sigmoid",
    "softplus",
    "square",
    "sum",
    "where",
}
OBJECTIVE_FORBIDDEN_CONTROL = (
    ast.Assert,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Await,
    ast.Break,
    ast.Continue,
    ast.Delete,
    ast.For,
    ast.GeneratorExp,
    ast.If,
    ast.IfExp,
    ast.Lambda,
    ast.ListComp,
    ast.DictComp,
    ast.Match,
    ast.SetComp,
    ast.NamedExpr,
    ast.Raise,
    ast.Try,
    ast.While,
    ast.With,
    ast.Yield,
    ast.YieldFrom,
)


class ObjectiveValidationError(ContractError):
    """Raised when an objective validator or its output violates the contract."""


@dataclass(frozen=True)
class ObjectiveSourceIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ObjectiveValidationResult:
    contract_version: str
    plugin_path: str
    source_sha256: str
    static_valid: bool
    loaded: bool
    finite: bool
    gradients_present: bool
    behavior_changed: bool
    reference_values: tuple[float, ...]
    candidate_values: tuple[float, ...]
    reference_gradient: tuple[float, ...]
    candidate_gradient: tuple[float, ...]
    errors: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "ObjectiveValidationResult":
        if not isinstance(value, dict):
            raise ObjectiveValidationError("objective result must be an object")
        expected = {
            "contract_version",
            "plugin_path",
            "source_sha256",
            "static_valid",
            "loaded",
            "finite",
            "gradients_present",
            "behavior_changed",
            "reference_values",
            "candidate_values",
            "reference_gradient",
            "candidate_gradient",
            "errors",
        }
        if set(value) != expected:
            raise ObjectiveValidationError("objective result fields are invalid")
        if value["contract_version"] != OBJECTIVE_CONTRACT_VERSION:
            raise ObjectiveValidationError("objective contract version is unsupported")
        path = require_safe_relative_path(value["plugin_path"], "objective plugin path")
        source_hash = require_sha256(value["source_sha256"], "objective source hash")
        flags = {}
        for name in (
            "static_valid",
            "loaded",
            "finite",
            "gradients_present",
            "behavior_changed",
        ):
            if not isinstance(value[name], bool):
                raise ObjectiveValidationError(f"objective result {name} must be boolean")
            flags[name] = value[name]
        numeric: dict[str, tuple[float, ...]] = {}
        for name in (
            "reference_values",
            "candidate_values",
            "reference_gradient",
            "candidate_gradient",
        ):
            raw = value[name]
            if not isinstance(raw, list):
                raise ObjectiveValidationError(f"objective result {name} must be a list")
            converted = tuple(float(item) for item in raw)
            if not all(math.isfinite(item) for item in converted):
                raise ObjectiveValidationError(f"objective result {name} is non-finite")
            numeric[name] = converted
        errors = value["errors"]
        if not isinstance(errors, list) or not all(
            isinstance(item, str) and item for item in errors
        ):
            raise ObjectiveValidationError("objective result errors are invalid")
        return cls(
            contract_version=OBJECTIVE_CONTRACT_VERSION,
            plugin_path=path,
            source_sha256=source_hash,
            static_valid=flags["static_valid"],
            loaded=flags["loaded"],
            finite=flags["finite"],
            gradients_present=flags["gradients_present"],
            behavior_changed=flags["behavior_changed"],
            reference_values=numeric["reference_values"],
            candidate_values=numeric["candidate_values"],
            reference_gradient=numeric["reference_gradient"],
            candidate_gradient=numeric["candidate_gradient"],
            errors=tuple(errors),
        )

    @property
    def passed(self) -> bool:
        return (
            self.static_valid
            and self.loaded
            and self.finite
            and self.gradients_present
            and not self.errors
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "plugin_path": self.plugin_path,
            "source_sha256": self.source_sha256,
            "static_valid": self.static_valid,
            "loaded": self.loaded,
            "finite": self.finite,
            "gradients_present": self.gradients_present,
            "behavior_changed": self.behavior_changed,
            "reference_values": list(self.reference_values),
            "candidate_values": list(self.candidate_values),
            "reference_gradient": list(self.reference_gradient),
            "candidate_gradient": list(self.candidate_gradient),
            "errors": list(self.errors),
        }


def validate_actor_objective_source(content: bytes) -> tuple[ObjectiveSourceIssue, ...]:
    """Require one import-safe function with the exact M6 ABI."""

    try:
        text = content.decode("utf-8")
        tree = ast.parse(text, filename="actor_objective.py")
    except (UnicodeDecodeError, SyntaxError) as error:
        return (ObjectiveSourceIssue("objective_parse", str(error)),)
    issues: list[ObjectiveSourceIssue] = []
    functions: list[ast.FunctionDef] = []
    for index, statement in enumerate(tree.body):
        if (
            index == 0
            and isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        if isinstance(statement, ast.Import):
            imported = {item.name for item in statement.names}
            if not imported.issubset(OBJECTIVE_IMPORT_ROOTS):
                issues.append(
                    ObjectiveSourceIssue(
                        "objective_import",
                        "objective imports are limited to direct imports of math and torch",
                    )
                )
            continue
        if isinstance(statement, ast.ImportFrom):
            issues.append(
                ObjectiveSourceIssue(
                    "objective_import",
                    "from-imports are forbidden in objective modules",
                )
            )
            continue
        if isinstance(statement, ast.FunctionDef):
            functions.append(statement)
            continue
        issues.append(
            ObjectiveSourceIssue(
                "objective_top_level",
                "objective modules may contain only a docstring, imports, and the ABI function",
            )
        )
    if len(functions) != 1 or functions[0].name != OBJECTIVE_FUNCTION:
        issues.append(
            ObjectiveSourceIssue(
                "objective_function",
                f"objective module must define exactly {OBJECTIVE_FUNCTION!r}",
            )
        )
        return tuple(issues)
    function = functions[0]
    arguments = function.args
    names = tuple(item.arg for item in arguments.posonlyargs + arguments.args)
    if (
        names != OBJECTIVE_ARGUMENTS
        or arguments.vararg is not None
        or arguments.kwarg is not None
        or arguments.kwonlyargs
        or arguments.defaults
        or arguments.kw_defaults
        or function.decorator_list
        or function.returns is not None
    ):
        issues.append(
            ObjectiveSourceIssue(
                "objective_signature",
                "objective ABI requires exactly (actor_loss, bc_loss, bc_weight)",
            )
        )
    for node in ast.walk(function):
        if isinstance(node, ast.FunctionDef) and node is not function:
            issues.append(
                ObjectiveSourceIssue(
                    "objective_helper",
                    "objective functions may not define nested helpers",
                )
            )
            break
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            issues.append(
                ObjectiveSourceIssue(
                    "objective_import",
                    "objective imports must appear at module scope",
                )
            )
            break
        if isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.ClassDef)):
            issues.append(
                ObjectiveSourceIssue(
                    "objective_state",
                    "objective functions may not use global/nonlocal/class/async state",
                )
            )
            break
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            issues.append(
                ObjectiveSourceIssue(
                    "objective_dunder",
                    "objective functions may not access dunder attributes",
                )
            )
            break
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if isinstance(node, ast.Assign):
                targets = node.targets
            else:
                targets = [node.target]
            if not all(isinstance(target, ast.Name) for target in targets):
                issues.append(
                    ObjectiveSourceIssue(
                        "objective_mutation",
                        "objective assignments may only bind local names",
                    )
                )
                break
        if isinstance(node, OBJECTIVE_FORBIDDEN_CONTROL):
            issues.append(
                ObjectiveSourceIssue(
                    "objective_control_flow",
                    "objective functions may not loop, await, raise, or use context managers",
                )
            )
            break
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            allowed = node.func.id in OBJECTIVE_CALL_NAMES
        elif isinstance(node.func, ast.Attribute):
            allowed = node.func.attr in OBJECTIVE_CALL_ATTRIBUTES
        else:
            allowed = False
        if not allowed:
            issues.append(
                ObjectiveSourceIssue(
                    "objective_call",
                    "objective calls must use the approved pure-math allowlist",
                )
            )
            break
    return tuple(issues)


class _Dual:
    def __init__(self, value: float, gradient: Sequence[float]) -> None:
        self.value = float(value)
        self.gradient = tuple(float(item) for item in gradient)

    @staticmethod
    def _coerce(value: Any, size: int) -> "_Dual":
        return value if isinstance(value, _Dual) else _Dual(value, (0.0,) * size)

    def __add__(self, other: Any) -> "_Dual":
        other = self._coerce(other, len(self.gradient))
        return _Dual(
            self.value + other.value,
            tuple(a + b for a, b in zip(self.gradient, other.gradient)),
        )

    __radd__ = __add__

    def __sub__(self, other: Any) -> "_Dual":
        other = self._coerce(other, len(self.gradient))
        return _Dual(
            self.value - other.value,
            tuple(a - b for a, b in zip(self.gradient, other.gradient)),
        )

    def __rsub__(self, other: Any) -> "_Dual":
        return self._coerce(other, len(self.gradient)).__sub__(self)

    def __mul__(self, other: Any) -> "_Dual":
        other = self._coerce(other, len(self.gradient))
        return _Dual(
            self.value * other.value,
            tuple(
                self.value * b + other.value * a
                for a, b in zip(self.gradient, other.gradient)
            ),
        )

    __rmul__ = __mul__

    def __truediv__(self, other: Any) -> "_Dual":
        other = self._coerce(other, len(self.gradient))
        if other.value == 0:
            raise ZeroDivisionError
        denominator = other.value * other.value
        return _Dual(
            self.value / other.value,
            tuple(
                (a * other.value - self.value * b) / denominator
                for a, b in zip(self.gradient, other.gradient)
            ),
        )

    def __neg__(self) -> "_Dual":
        return _Dual(-self.value, tuple(-item for item in self.gradient))


def _reference(actor_loss: Any, bc_loss: Any, bc_weight: Any) -> Any:
    return actor_loss + bc_weight * bc_loss


def evaluate_objective_plugin(
    plugin_path: Path,
    *,
    display_path: str,
    require_behavior_change: bool,
) -> ObjectiveValidationResult:
    """Load and probe one statically constrained plugin in the current process."""

    display = require_safe_relative_path(display_path, "objective plugin path")
    source = plugin_path.read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    issues = validate_actor_objective_source(source)
    errors = [f"{item.code}:{item.message}" for item in issues]
    reference_values: list[float] = []
    candidate_values: list[float] = []
    reference_gradient: tuple[float, ...] = ()
    candidate_gradient: tuple[float, ...] = ()
    loaded = False
    finite = False
    gradients_present = False
    behavior_changed = False
    if not issues:
        try:
            spec = importlib.util.spec_from_file_location(
                f"m6_objective_{source_hash[:12]}", plugin_path
            )
            if spec is None or spec.loader is None:
                raise ObjectiveValidationError("objective module loader is unavailable")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            function = getattr(module, OBJECTIVE_FUNCTION)
            loaded = True
            for actor, bc, weight in ((2.0, 3.0, 0.25), (-1.0, 0.5, 2.0)):
                reference_values.append(float(_reference(actor, bc, weight)))
                candidate_values.append(float(function(actor, bc, weight)))
            dual_inputs = (
                _Dual(2.0, (1, 0, 0)),
                _Dual(3.0, (0, 1, 0)),
                _Dual(0.25, (0, 0, 1)),
            )
            expected = _reference(*dual_inputs)
            actual = function(*dual_inputs)
            if not isinstance(actual, _Dual):
                raise ObjectiveValidationError("objective disconnected required gradients")
            reference_gradient = expected.gradient
            candidate_gradient = actual.gradient
            gradients_present = len(candidate_gradient) == len(OBJECTIVE_ARGUMENTS)
            finite = all(
                math.isfinite(item)
                for item in (
                    *reference_values,
                    *candidate_values,
                    *reference_gradient,
                    *candidate_gradient,
                )
            )
            behavior_changed = (
                tuple(candidate_values) != tuple(reference_values)
                or candidate_gradient != reference_gradient
            )
            if not finite:
                errors.append("objective_nonfinite:objective probe was non-finite")
                candidate_values = [
                    item for item in candidate_values if math.isfinite(item)
                ]
                candidate_gradient = tuple(
                    item for item in candidate_gradient if math.isfinite(item)
                )
            if require_behavior_change and not behavior_changed:
                errors.append("objective_noop:candidate does not change approved behavior")
        except Exception as error:  # candidate code failures become bounded evidence
            errors.append(f"objective_runtime:{type(error).__name__}:{error}")
    return ObjectiveValidationResult(
        contract_version=OBJECTIVE_CONTRACT_VERSION,
        plugin_path=display,
        source_sha256=source_hash,
        static_valid=not issues,
        loaded=loaded,
        finite=finite,
        gradients_present=gradients_present,
        behavior_changed=behavior_changed,
        reference_values=tuple(reference_values),
        candidate_values=tuple(candidate_values),
        reference_gradient=reference_gradient,
        candidate_gradient=candidate_gradient,
        errors=tuple(errors),
    )


class ObjectiveValidationRunner:
    """Call the objective validator in a separate bounded Python process."""

    def __init__(self, *, python_executable: Path, validator_script: Path) -> None:
        self.python_executable = python_executable.resolve()
        self.validator_script = validator_script.resolve()
        if not self.python_executable.is_file() or not self.validator_script.is_file():
            raise ObjectiveValidationError("objective validator executables are missing")

    def argv(
        self,
        plugin_relative_path: str,
        *,
        require_behavior_change: bool,
    ) -> tuple[str, ...]:
        path = require_safe_relative_path(plugin_relative_path, "objective plugin path")
        result = [
            str(self.python_executable),
            str(self.validator_script),
            "--plugin",
            path,
        ]
        if require_behavior_change:
            result.append("--require-behavior-change")
        return tuple(result)

    def validate(
        self,
        *,
        workspace: Path,
        plugin_relative_path: str,
        require_behavior_change: bool,
        timeout_seconds: int = 20,
    ) -> ObjectiveValidationResult:
        completed = subprocess.run(
            self.argv(
                plugin_relative_path,
                require_behavior_change=require_behavior_change,
            ),
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            timeout=timeout_seconds,
            check=False,
        )
        if len(completed.stdout) > MAX_VALIDATOR_OUTPUT_BYTES:
            raise ObjectiveValidationError("objective validator output exceeded its cap")
        try:
            payload = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ObjectiveValidationError(
                "objective validator returned invalid JSON"
            ) from error
        result = ObjectiveValidationResult.from_dict(payload)
        if completed.returncode not in (0, 2):
            raise ObjectiveValidationError(
                f"objective validator exited unexpectedly: {completed.returncode}"
            )
        if (completed.returncode == 0) != result.passed:
            raise ObjectiveValidationError("objective validator status disagrees with result")
        plugin = workspace / plugin_relative_path
        if hashlib.sha256(plugin.read_bytes()).hexdigest() != result.source_sha256:
            raise ObjectiveValidationError("objective changed during validation")
        return result
