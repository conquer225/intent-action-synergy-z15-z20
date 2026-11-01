import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.readiness import verify_baseline, inspect_readiness


class ReadinessTests(unittest.TestCase):
    def test_missing_inputs_are_reported_and_baseline_changes_are_detected(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"source.py").write_bytes(b"original\n")
            record = dict(files=[dict(path="source.py", sha256=hashlib.sha256(b"original\n").hexdigest())])
            self.assertTrue(verify_baseline(root, record)["passed"])
            (root/"source.py").write_bytes(b"changed\n")
            self.assertFalse(verify_baseline(root, record)["passed"])
            result = inspect_readiness(root/"models", root/"calibration.json", {})
            self.assertFalse(result["ready"])
            self.assertEqual(len(result["models"]), 4)
            self.assertTrue(all(not state["ready"] for state in result["models"].values()))


if __name__ == "__main__": unittest.main()
