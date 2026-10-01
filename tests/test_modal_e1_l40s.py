import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "modal_e1_l40s.py"


class ModalE1L40SContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text)

    def test_frozen_steps_and_hashes_are_present(self) -> None:
        for step in (250, 500, 1000, 2000):
            self.assertIn(f"{step}:", self.text)
        self.assertGreaterEqual(self.text.count('"version_id":'), 4)
        self.assertGreaterEqual(self.text.count('"sha256":'), 4)

    def test_paid_boundary_is_bounded_and_retry_free(self) -> None:
        self.assertIn('GPU = "L40S"', self.text)
        self.assertIn("FUNCTION_TIMEOUT_SECONDS = 7200", self.text)
        self.assertIn('MAX_GPU_RUNTIME_COST_USD = "3.902400"', self.text)
        self.assertIn("ephemeral_disk=512 * 1024", self.text)
        self.assertIn('BASE_IMAGE_ID = "im-66ku0dbczWNQDgPWv97XNc"', self.text)
        self.assertIn("modal.Image.from_id(BASE_IMAGE_ID)", self.text)
        self.assertIn('.pip_install("modal==1.5.4", "boto3==1.40.45")', self.text)
        self.assertIn("retries=0", self.text)
        self.assertIn("single_use_containers=True", self.text)

    def test_entrypoint_launches_detached_function_call(self) -> None:
        self.assertIn("acknowledge_detached_run: bool = False", self.text)
        self.assertIn("if not acknowledge_detached_run:", self.text)
        self.assertIn("call = evaluate.spawn(step)", self.text)
        self.assertIn('"function_call_id": call.object_id', self.text)
        self.assertNotIn("evaluate.remote(step)", self.text)

    def test_no_arbitrary_remote_command_or_selection(self) -> None:
        self.assertNotIn("shell=True", self.text)
        self.assertNotIn("g0_e1_baseline", self.text)
        self.assertIn("development checkpoint evaluation only; no selection or promotion", self.text)


if __name__ == "__main__":
    unittest.main()
