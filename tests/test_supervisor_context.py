from __future__ import annotations

import unittest

from supervisor.context import (
    MAX_EXCERPTS,
    ContextRejected,
    PriorTrialSummary,
    SourceExcerpt,
    build_context,
)
from supervisor.contracts import CampaignSpec
from tests.test_supervisor_proposals import BASE_COMMIT, config_campaign_data


def context_kwargs() -> dict:
    return {
        "incumbent_commit": BASE_COMMIT,
        "immutable_boundaries": [
            "Do not edit the base VLA or canonical RLinf.",
            "Do not change reset IDs, success definitions, or evaluator code.",
        ],
        "metric_definitions": {
            "eval/success_once": "Primary fixed-reset success endpoint.",
            "sac/actor_loss": "Diagnostic only; cannot independently promote.",
        },
        "baseline_summary": "Control B completed with fixed reset evidence.",
        "prior_trials": [
            PriorTrialSummary.create(
                trial_id="control-b-seed-2026",
                decision="revert",
                summary="No promotion; preserved as baseline evidence.",
                metrics={"eval/success_once": 0.25},
            )
        ],
        "excerpts": [
            SourceExcerpt.create(
                excerpt_id="actor-config",
                kind="source",
                title="Allowlisted actor configuration",
                content="actor.optim.lr: 0.0001",
            )
        ],
        "delta_summary": "No candidate delta has been applied.",
    }


class ContextBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.campaign = CampaignSpec.from_dict(config_campaign_data())

    def test_context_is_deterministic_and_hashes_sources(self) -> None:
        first = build_context(self.campaign, **context_kwargs())
        reordered = context_kwargs()
        reordered["metric_definitions"] = {
            key: reordered["metric_definitions"][key]
            for key in reversed(reordered["metric_definitions"])
        }
        second = build_context(self.campaign, **reordered)
        self.assertEqual(first.context_hash, second.context_hash)
        self.assertEqual(first.rendered_prompt, second.rendered_prompt)
        self.assertEqual(len(first.excerpt_hashes), 1)
        self.assertIn("untrusted evidence", first.rendered_prompt)
        self.assertLessEqual(first.byte_count, 65_536)

    def test_context_changes_with_incumbent(self) -> None:
        first = build_context(self.campaign, **context_kwargs())
        changed = context_kwargs()
        changed["incumbent_commit"] = "b" * 40
        second = build_context(self.campaign, **changed)
        self.assertNotEqual(first.context_hash, second.context_hash)

    def test_secret_patterns_are_rejected_without_echoing_secret(self) -> None:
        secrets = [
            "-----BEGIN OPENSSH PRIVATE KEY-----\nsecret",
            "Authorization: Bearer abc123",
            "WANDB_API_KEY=abc123",
            "password: hunter2",
        ]
        for secret in secrets:
            with self.subTest(secret=secret):
                kwargs = context_kwargs()
                kwargs["baseline_summary"] = secret
                with self.assertRaises(ContextRejected) as caught:
                    build_context(self.campaign, **kwargs)
                self.assertNotIn("abc123", str(caught.exception))
                self.assertNotIn("hunter2", str(caught.exception))

    def test_raw_log_kind_and_oversized_excerpt_are_rejected(self) -> None:
        with self.assertRaisesRegex(ContextRejected, "excerpt kind"):
            SourceExcerpt.create(
                excerpt_id="raw",
                kind="raw_log",
                title="Raw log",
                content="unbounded output",
            )
        with self.assertRaisesRegex(ContextRejected, "UTF-8 bytes"):
            SourceExcerpt.create(
                excerpt_id="large",
                kind="source",
                title="Large",
                content="é" * 9_000,
            )

    def test_excerpt_and_total_context_limits_fail_closed(self) -> None:
        kwargs = context_kwargs()
        kwargs["excerpts"] = [
            SourceExcerpt.create(
                excerpt_id=f"excerpt-{index}",
                kind="source",
                title=f"Excerpt {index}",
                content="small",
            )
            for index in range(MAX_EXCERPTS + 1)
        ]
        with self.assertRaisesRegex(ContextRejected, "more than"):
            build_context(self.campaign, **kwargs)

        kwargs = context_kwargs()
        kwargs["baseline_summary"] = "b" * 16_000
        kwargs["excerpts"] = [
            SourceExcerpt.create(
                excerpt_id=f"excerpt-{index}",
                kind="source",
                title=f"Excerpt {index}",
                content="x" * 8_000,
            )
            for index in range(7)
        ]
        with self.assertRaisesRegex(ContextRejected, "rendered context"):
            build_context(self.campaign, **kwargs)

    def test_prior_metrics_must_be_finite_and_summaries_are_bounded(self) -> None:
        with self.assertRaisesRegex(ContextRejected, "finite"):
            PriorTrialSummary.create(
                trial_id="bad",
                decision="failed",
                summary="Non-finite result.",
                metrics={"loss": float("nan")},
            )
        with self.assertRaisesRegex(ContextRejected, "must be an object"):
            PriorTrialSummary.create(
                trial_id="bad-metrics",
                decision="failed",
                summary="Malformed provider fixture.",
                metrics=[],  # type: ignore[arg-type]
            )

    def test_context_collections_reject_wrong_record_types(self) -> None:
        kwargs = context_kwargs()
        kwargs["prior_trials"] = ["not-a-summary"]
        with self.assertRaisesRegex(ContextRejected, "PriorTrialSummary"):
            build_context(self.campaign, **kwargs)

        kwargs = context_kwargs()
        kwargs["excerpts"] = ["raw text"]
        with self.assertRaisesRegex(ContextRejected, "SourceExcerpt"):
            build_context(self.campaign, **kwargs)

    def test_duplicate_evidence_ids_and_missing_required_sections_are_rejected(self) -> None:
        kwargs = context_kwargs()
        kwargs["excerpts"] = [kwargs["excerpts"][0], kwargs["excerpts"][0]]
        with self.assertRaisesRegex(ContextRejected, "excerpt IDs"):
            build_context(self.campaign, **kwargs)

        kwargs = context_kwargs()
        kwargs["immutable_boundaries"] = []
        with self.assertRaisesRegex(ContextRejected, "immutable boundaries"):
            build_context(self.campaign, **kwargs)


if __name__ == "__main__":
    unittest.main()
