from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from supervisor.attempts import ProposalAttemptController
from supervisor.canonical import ContractError, fingerprint
from supervisor.context import build_context
from supervisor.contracts import CampaignSpec
from supervisor.proposals import AttemptStatus
from supervisor.provider_contract import frozen_contract
from supervisor.providers import (
    ClaudeCliProvider,
    FakeProposalProvider,
    ProcessResult,
    ProviderCallResult,
    ProviderError,
    ProviderTimeout,
    sanitized_environment,
)
from tests.test_supervisor_context import context_kwargs
from tests.test_supervisor_proposals import (
    BASE_COMMIT,
    config_campaign_data,
    config_proposal_data,
)


STARTED = "2026-08-04T12:00:00Z"
COMPLETED = "2026-08-04T12:00:01Z"


class RecordingTransport:
    def __init__(self, result: ProcessResult | Exception) -> None:
        self.result = result
        self.calls: list[dict] = []

    def run(
        self,
        argv,
        *,
        input_text,
        cwd,
        environment,
        timeout_seconds,
    ) -> ProcessResult:
        self.calls.append(
            {
                "argv": tuple(argv),
                "input_text": input_text,
                "cwd": cwd,
                "environment": dict(environment),
                "timeout_seconds": timeout_seconds,
            }
        )
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FixedClock:
    def __init__(self) -> None:
        self.values = iter(
            [
                datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 8, 4, 12, 0, 1, tzinfo=timezone.utc),
            ]
        )

    def __call__(self):
        return next(self.values)


def provider_result(payload: dict, *, cost: str = "0.2") -> ProviderCallResult:
    return ProviderCallResult(
        provider="fake-provider",
        model="opus",
        started_at=STARTED,
        completed_at=COMPLETED,
        response_hash=fingerprint(payload),
        proposal_payload=payload,
        reported_cost_usd=cost,
        input_tokens=100,
        output_tokens=50,
    )


def campaign_and_context():
    campaign = CampaignSpec.from_dict(config_campaign_data())
    context = build_context(campaign, **context_kwargs())
    return campaign, context


class ClaudeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)
        self.campaign, self.context = campaign_and_context()

    def provider(self, envelope: dict, *, return_code: int = 0):
        transport = RecordingTransport(
            ProcessResult(
                return_code=return_code,
                stdout=json.dumps(envelope),
                stderr="failure detail" if return_code else "",
                elapsed_seconds=0.1,
            )
        )
        provider = ClaudeCliProvider(
            executable=Path(sys.executable),
            working_directory=self.cwd,
            transport=transport,
            environment={
                "PATH": "/usr/bin",
                "ANTHROPIC_API_KEY": "not-recorded-in-context",
                "UNRELATED_SECRET": "must-not-pass",
            },
            clock=FixedClock(),
        )
        return provider, transport

    def test_cli_uses_stdin_structured_schema_and_no_tools(self) -> None:
        envelope = {
            "is_error": False,
            "structured_output": config_proposal_data(),
            "total_cost_usd": 0.2,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        provider, transport = self.provider(envelope)
        result = provider.generate(
            self.context,
            model="opus",
            max_budget_usd="1",
            timeout_seconds=600,
        )
        call = transport.calls[0]
        argv = call["argv"]
        for flag in (
            "--print",
            "--bare",
            "--safe-mode",
            "--disable-slash-commands",
            "--no-chrome",
            "--json-schema",
            "--no-session-persistence",
            "--permission-mode",
            "--max-budget-usd",
            "--system-prompt",
        ):
            self.assertIn(flag, argv)
        tools_index = argv.index("--tools")
        self.assertEqual(argv[tools_index + 1], "")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(call["input_text"], self.context.rendered_prompt)
        self.assertNotIn("UNRELATED_SECRET", call["environment"])
        self.assertIn("ANTHROPIC_API_KEY", call["environment"])
        self.assertNotIn("not-recorded-in-context", call["input_text"])
        self.assertEqual(result.reported_cost_usd, "0.2")
        self.assertEqual(result.proposal_payload, config_proposal_data())
        self.assertEqual(result.input_tokens, 100)

    def test_direct_backend_environment_is_least_authority(self) -> None:
        source = {
            "PATH": "/usr/bin",
            "LANG": "C.UTF-8",
            "ANTHROPIC_API_KEY": "direct-secret",
            "ANTHROPIC_BASE_URL": "https://unapproved.invalid",
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_ACCESS_KEY_ID": "cloud-secret",
            "GOOGLE_APPLICATION_CREDENTIALS": "/secret.json",
            "UNRELATED_SECRET": "other-secret",
        }
        self.assertEqual(
            sanitized_environment(source),
            {
                "PATH": "/usr/bin",
                "LANG": "C.UTF-8",
                "ANTHROPIC_API_KEY": "direct-secret",
            },
        )
        with self.assertRaisesRegex(ContractError, "unsupported.*backend"):
            sanitized_environment(source, backend="bedrock")

    def test_explicit_empty_environment_does_not_inherit_process_secrets(self) -> None:
        provider = ClaudeCliProvider(
            executable=Path(sys.executable),
            working_directory=self.cwd,
            environment={},
        )
        self.assertEqual(provider.environment, {})

    def test_c0_contract_is_exact_and_does_not_use_a_moving_model_alias(self) -> None:
        contract = frozen_contract()
        self.assertEqual(contract["provider"], "claude-cli")
        self.assertEqual(contract["model"], "claude-opus-5")
        self.assertNotIn(contract["model"], {"opus", "sonnet", "haiku"})
        self.assertEqual(contract["timeout_seconds"], 600)
        self.assertEqual(contract["max_total_cost_usd"], "0.5")
        self.assertEqual(contract["max_attempts"], 2)
        self.assertEqual(
            contract["allowed_environment_names"],
            ["ANTHROPIC_API_KEY", "LANG", "LC_ALL", "PATH", "TMPDIR"],
        )

    def test_result_string_envelope_is_supported(self) -> None:
        provider, _ = self.provider(
            {"result": json.dumps(config_proposal_data()), "total_cost_usd": "0"}
        )
        result = provider.generate(
            self.context,
            model="opus",
            max_budget_usd="1",
            timeout_seconds=10,
        )
        self.assertEqual(result.proposal_payload, config_proposal_data())

    def test_repair_feedback_is_bounded_and_keeps_original_context(self) -> None:
        provider, transport = self.provider(
            {"structured_output": config_proposal_data(), "total_cost_usd": "0"}
        )
        provider.generate(
            self.context,
            model="opus",
            max_budget_usd="1",
            timeout_seconds=10,
            repair_feedback='{"validation_errors":["fix bounds"]}',
        )
        prompt = transport.calls[0]["input_text"]
        self.assertTrue(prompt.startswith(self.context.rendered_prompt))
        self.assertIn("<repair_request>", prompt)
        with self.assertRaisesRegex(ContractError, "repair feedback"):
            provider.generate(
                self.context,
                model="opus",
                max_budget_usd="1",
                timeout_seconds=10,
                repair_feedback="x" * 16_385,
            )

    def test_malformed_failure_and_oversized_envelopes_are_rejected(self) -> None:
        cases = [
            (ProcessResult(0, "not json", "", 0.1), "not JSON"),
            (ProcessResult(0, json.dumps({"other": 1}), "", 0.1), "proposal object"),
            (ProcessResult(1, "{}", "failure", 0.1), "exited with 1"),
            (ProcessResult(0, "x" * 1_048_577, "", 0.1), "one-MiB"),
            (ProcessResult(0, '{"structured_output":NaN}', "", 0.1), "not JSON"),
        ]
        for process_result, message in cases:
            with self.subTest(message=message):
                provider = ClaudeCliProvider(
                    executable=Path(sys.executable),
                    working_directory=self.cwd,
                    transport=RecordingTransport(process_result),
                    clock=FixedClock(),
                )
                with self.assertRaisesRegex(ProviderError, message):
                    provider.generate(
                        self.context,
                        model="opus",
                        max_budget_usd="1",
                        timeout_seconds=10,
                    )

    def test_timeout_is_propagated_without_a_real_call(self) -> None:
        provider = ClaudeCliProvider(
            executable=Path(sys.executable),
            working_directory=self.cwd,
            transport=RecordingTransport(ProviderTimeout("timed out")),
            clock=FixedClock(),
        )
        with self.assertRaises(ProviderTimeout):
            provider.generate(
                self.context,
                model="opus",
                max_budget_usd="1",
                timeout_seconds=10,
            )


class AttemptControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.campaign, self.context = campaign_and_context()
        self.clock = lambda: datetime(2026, 8, 4, 12, tzinfo=timezone.utc)

    def controller(self, provider, *, budget="1", context=None):
        return ProposalAttemptController(
            campaign=self.campaign,
            context=context or self.context,
            incumbent_commit=BASE_COMMIT,
            provider=provider,
            model="opus",
            proposal_slot_id="slot-1",
            max_total_cost_usd=budget,
            timeout_seconds=600,
            clock=self.clock,
        )

    def test_valid_initial_proposal_is_accepted_once(self) -> None:
        provider = FakeProposalProvider([provider_result(config_proposal_data())])
        session = self.controller(provider).run()
        self.assertTrue(session.accepted)
        self.assertEqual(len(session.attempts), 1)
        self.assertEqual(session.attempts[0].status, AttemptStatus.ACCEPTED)
        self.assertEqual(session.total_cost_usd, "0.2")
        self.assertEqual(len(session.fingerprint()), 64)
        self.assertIsNone(provider.calls[0]["repair_feedback"])

    def test_invalid_initial_gets_one_repair_with_remaining_budget(self) -> None:
        invalid = config_proposal_data()
        invalid["config_overrides"] = {"actor.optim.lr": 1.0}
        provider = FakeProposalProvider(
            [
                provider_result(invalid, cost="0.2"),
                provider_result(config_proposal_data(), cost="0.3"),
            ]
        )
        session = self.controller(provider).run()
        self.assertTrue(session.accepted)
        self.assertEqual(
            [attempt.status for attempt in session.attempts],
            [AttemptStatus.INVALID, AttemptStatus.ACCEPTED],
        )
        self.assertEqual(provider.calls[0]["max_budget_usd"], "1")
        self.assertEqual(provider.calls[1]["max_budget_usd"], "0.8")
        self.assertIn("outside approved bounds", provider.calls[1]["repair_feedback"])
        self.assertEqual(session.total_cost_usd, "0.5")

    def test_two_invalid_attempts_end_rejected(self) -> None:
        invalid = config_proposal_data()
        invalid["changed_paths"] = ["agent/d1_rules.py"]
        provider = FakeProposalProvider(
            [provider_result(invalid), provider_result(copy.deepcopy(invalid))]
        )
        session = self.controller(provider).run()
        self.assertFalse(session.accepted)
        self.assertEqual(len(session.attempts), 2)
        self.assertTrue(all(item.status == AttemptStatus.INVALID for item in session.attempts))
        self.assertEqual(len(provider.calls), 2)

    def test_timeout_and_provider_errors_do_not_trigger_repair(self) -> None:
        for failure, status in (
            (ProviderTimeout("timed out"), AttemptStatus.TIMEOUT),
            (ProviderError("bad envelope"), AttemptStatus.PROVIDER_ERROR),
        ):
            with self.subTest(status=status):
                provider = FakeProposalProvider([failure, provider_result(config_proposal_data())])
                session = self.controller(provider).run()
                self.assertFalse(session.accepted)
                self.assertEqual(len(provider.calls), 1)
                self.assertEqual(session.attempts[0].status, status)

    def test_reported_cost_over_remaining_budget_stops_session(self) -> None:
        provider = FakeProposalProvider(
            [provider_result(config_proposal_data(), cost="1.01")]
        )
        session = self.controller(provider).run()
        self.assertFalse(session.accepted)
        self.assertEqual(session.attempts[0].status, AttemptStatus.BUDGET_EXCEEDED)
        self.assertEqual(session.total_cost_usd, "1.01")
        self.assertEqual(len(provider.calls), 1)

    def test_context_must_match_campaign_and_incumbent(self) -> None:
        changed_data = config_campaign_data()
        changed_data["research_question"] += " changed"
        changed_campaign = CampaignSpec.from_dict(changed_data)
        with self.assertRaisesRegex(ContractError, "context does not match campaign"):
            ProposalAttemptController(
                campaign=changed_campaign,
                context=self.context,
                incumbent_commit=BASE_COMMIT,
                provider=FakeProposalProvider([]),
                model="opus",
                proposal_slot_id="slot-1",
                max_total_cost_usd="1",
                clock=self.clock,
            )

    def test_provider_result_identity_mismatch_is_rejected_without_repair(self) -> None:
        wrong = ProviderCallResult(
            provider="different-provider",
            model="opus",
            started_at=STARTED,
            completed_at=COMPLETED,
            response_hash="a" * 64,
            proposal_payload=config_proposal_data(),
            reported_cost_usd="0",
            input_tokens=1,
            output_tokens=1,
        )
        provider = FakeProposalProvider([wrong, provider_result(config_proposal_data())])
        session = self.controller(provider).run()
        self.assertFalse(session.accepted)
        self.assertEqual(session.attempts[0].status, AttemptStatus.PROVIDER_ERROR)
        self.assertEqual(len(provider.calls), 1)

    def test_unsupported_provider_result_is_audited_without_repair(self) -> None:
        provider = FakeProposalProvider([])
        provider._responses.append(object())  # type: ignore[arg-type]
        session = self.controller(provider).run()
        self.assertFalse(session.accepted)
        self.assertEqual(session.attempts[0].status, AttemptStatus.PROVIDER_ERROR)
        self.assertIn(
            "unsupported result type", session.attempts[0].validation_errors[0]
        )
        self.assertEqual(len(provider.calls), 1)


if __name__ == "__main__":
    unittest.main()
