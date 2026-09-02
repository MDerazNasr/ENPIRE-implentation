from __future__ import annotations

import unittest

from supervisor.toy_policy import (
    SUCCESS_RADIUS,
    ToyPolicyError,
    TrainingConfig,
    evaluate_policy,
    make_resets,
    train_policy,
)


class ToyPolicyTests(unittest.TestCase):
    def test_training_is_deterministic_and_records_real_trajectories(self) -> None:
        config = TrainingConfig(exploration_std=0.35)
        first = train_policy(config, 202)
        second = train_policy(config, 202)
        self.assertEqual(first.to_dict(), second.to_dict())
        metrics, episodes = evaluate_policy(first.policy, make_resets(424_242, 32))
        self.assertEqual(metrics.episode_count, 32)
        self.assertEqual(len(episodes), 32)
        self.assertTrue(all(len(episode.path) >= 2 for episode in episodes))
        self.assertTrue(
            all(
                episode.final_distance <= SUCCESS_RADIUS
                for episode in episodes
                if episode.success
            )
        )

    def test_agent_candidate_consistently_improves_paired_seeds(self) -> None:
        resets = make_resets(424_242, 256)
        control = TrainingConfig(exploration_std=0.01)
        candidate = TrainingConfig(exploration_std=0.35)
        for seed in (101, 202, 303):
            control_metrics, _ = evaluate_policy(
                train_policy(control, seed).policy, resets
            )
            candidate_metrics, _ = evaluate_policy(
                train_policy(candidate, seed).policy, resets
            )
            self.assertGreaterEqual(
                candidate_metrics.success_rate - control_metrics.success_rate,
                0.80,
            )
            self.assertLess(
                candidate_metrics.mean_final_distance,
                control_metrics.mean_final_distance,
            )

    def test_training_config_rejects_unknown_or_unsafe_values(self) -> None:
        with self.assertRaises(ToyPolicyError):
            TrainingConfig.from_dict({"exploration_std": 0.35})
        raw = TrainingConfig(exploration_std=0.35).to_dict()
        raw["exploration_std"] = 1.5
        with self.assertRaises(ToyPolicyError):
            TrainingConfig.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
