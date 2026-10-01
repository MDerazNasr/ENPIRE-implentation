import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "modal_e1_l40s_monitor.py"


class ModalE1L40SMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text)

    def test_monitor_reconstructs_only_a_function_call_identity(self) -> None:
        self.assertIn("modal.FunctionCall.from_id(function_call_id)", self.text)
        self.assertIn('startswith("fc-")', self.text)
        self.assertNotIn("gpu=", self.text)
        self.assertNotIn("modal.Volume", self.text)
        self.assertNotIn("boto3", self.text)

    def test_monitor_can_poll_or_wait_without_cancelling(self) -> None:
        self.assertIn("call.get(timeout=None if wait else 0)", self.text)
        self.assertIn('"status": "running"', self.text)
        self.assertNotIn(".cancel(", self.text)


if __name__ == "__main__":
    unittest.main()
