import copy
import unittest

from supervisor.e2_acceptance import E2AcceptanceError, verify_e2_identity
from supervisor.objective_validation import OBJECTIVE_CONTRACT_VERSION


OBJECTIVE_HASH = "a" * 64


def records():
    plan = {
        "objective_sha256": OBJECTIVE_HASH,
        "objective_contract_version": OBJECTIVE_CONTRACT_VERSION,
        "logical_rlinf_command": [f"objective.sha256={OBJECTIVE_HASH}"],
        "execution_argv": ["--objective-sha256", OBJECTIVE_HASH],
    }
    manifest = {
        "objective_sha256": OBJECTIVE_HASH,
        "objective_contract_version": OBJECTIVE_CONTRACT_VERSION,
        "objective_validation": {
            "source_sha256": OBJECTIVE_HASH,
            "behavior_changed": True,
            "errors": [],
        },
    }
    runtime = {
        "objective_sha256": OBJECTIVE_HASH,
        "attachment": {
            "objective_sha256": OBJECTIVE_HASH,
            "objective_contract_version": OBJECTIVE_CONTRACT_VERSION,
        },
    }
    evidence = {
        "artifacts": [{"kind": "actor-objective", "sha256": OBJECTIVE_HASH}]
    }
    return plan, manifest, runtime, evidence


class E2AcceptanceTests(unittest.TestCase):
    def test_exact_identity_passes_every_boundary(self):
        plan, manifest, runtime, evidence = records()
        checks = verify_e2_identity(
            objective_sha256=OBJECTIVE_HASH,
            plan=plan,
            manifest=manifest,
            runtime=runtime,
            evidence=evidence,
        )
        self.assertTrue(all(checks.values()))

    def test_each_identity_boundary_fails_closed(self):
        mutations = {
            "plan": lambda p, _m, _r, _e: p.update(objective_sha256="b" * 64),
            "command": lambda p, _m, _r, _e: p.update(logical_rlinf_command=[]),
            "manifest": lambda _p, m, _r, _e: m.update(objective_sha256="b" * 64),
            "runtime": lambda _p, _m, r, _e: r.update(objective_sha256="b" * 64),
            "evidence": lambda _p, _m, _r, e: e.update(artifacts=[]),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                values = [copy.deepcopy(item) for item in records()]
                mutate(*values)
                with self.assertRaises(E2AcceptanceError):
                    verify_e2_identity(
                        objective_sha256=OBJECTIVE_HASH,
                        plan=values[0],
                        manifest=values[1],
                        runtime=values[2],
                        evidence=values[3],
                    )


if __name__ == "__main__":
    unittest.main()
