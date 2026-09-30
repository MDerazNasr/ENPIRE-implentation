import ast
import json
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "modal_e1_l40s.py"
COLLISION_RECEIPT = (
    ROOT
    / "results"
    / "agent-supervisor"
    / "g0"
    / "e1-modal-l40s-step-250-retry-collision-v1.json"
)


class E1ModalCreateOnlyTests(unittest.TestCase):
    def test_collision_gate_precedes_checkpoint_download(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        ast.parse(text)
        function = text[text.index("def evaluate(step: int)") :]
        self.assertLess(
            function.index("if run_dir.exists() or receipt_path.exists()"),
            function.index("download = _download(step, checkpoint)"),
        )

    def test_retry_evidence_uses_new_create_only_paths(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("RUN_REVISION = 2", text)
        self.assertIn('f"g0-e1-l40s-step-{step}-v{RUN_REVISION}"', text)
        self.assertIn('f"step-{step}-v{RUN_REVISION}-terminal.json"', text)
        self.assertIn('receipt_path.open("x", encoding="utf-8")', text)

    def test_collision_receipt_is_canonical_and_non_authorizing(self) -> None:
        envelope = json.loads(COLLISION_RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(set(envelope), {"payload", "sha256"})
        self.assertEqual(fingerprint(envelope["payload"]), envelope["sha256"])
        payload = envelope["payload"]
        self.assertTrue(all(value is False for value in payload["authority"].values()))
        self.assertTrue(payload["failure"]["failed_closed"])
        self.assertFalse(payload["failure"]["evaluation_runner_started"])
        self.assertEqual(payload["failure"]["simulator_steps"], 0)


if __name__ == "__main__":
    unittest.main()
