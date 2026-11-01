"""Public CLI tests for byte-preserving workspace restoration."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "build/restore_workspace.py"


class RestoreTests(unittest.TestCase):
    def fixture(self, folder):
        package = Path(folder) / "package"
        (package / "src/workspace").mkdir(parents=True)
        (package / "report").mkdir()
        raw = b"Content-pinned payload\r\n"
        (package / "src/workspace/start_board.sh").write_bytes(raw)
        entry = {"package_path": "src/workspace/start_board.sh",
                 "runtime_path": "integrations/demo/START_BOARD.sh",
                 "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        self.manifest(package, [entry])
        return package, entry, raw

    def manifest(self, package, entries):
        (package / "report/source_manifest.json").write_text(
            json.dumps({"schema_version": 1, "entries": entries}), encoding="utf-8")

    def run_restore(self, package, target):
        result = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), "--package", str(package),
                                 "--output", str(target)], capture_output=True,
                                text=True, encoding="utf-8", timeout=30)
        return result, json.loads(result.stdout) if result.stdout.strip() else None

    def test_restores_original_case_and_exact_bytes_into_a_new_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            package, _, raw = self.fixture(folder)
            target = Path(folder) / "restored with spaces"
            result, report = self.run_restore(package, target)
            self.assertEqual(result.returncode, 0, result.stderr)
            restored = target / "integrations/demo/START_BOARD.sh"
            self.assertEqual(restored.read_bytes(), raw)
            self.assertEqual(restored.name, "START_BOARD.sh")
            self.assertEqual(report["restored_files"], 1)
            self.assertFalse(report["board_executed"])

    def test_hash_failure_rejects_before_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            package, _, _ = self.fixture(folder)
            (package / "src/workspace/start_board.sh").write_bytes(b"corrupt")
            target = Path(folder) / "new"
            result, report = self.run_restore(package, target)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(target.exists())
            self.assertIn("sha256", report["error"])

    def test_path_escape_and_existing_target_are_rejected_without_overwrite(self):
        for fault in ("source_escape", "runtime_escape", "existing"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                package, entry, _ = self.fixture(folder)
                target = Path(folder) / "new"
                if fault == "source_escape":
                    entry["package_path"] = "../outside"
                elif fault == "runtime_escape":
                    entry["runtime_path"] = "../outside"
                else:
                    target.mkdir()
                    (target / "keep.txt").write_text("keep", encoding="utf-8")
                self.manifest(package, [entry])
                result, _ = self.run_restore(package, target)
                self.assertEqual(result.returncode, 1, result.stderr)
                if fault == "existing":
                    self.assertEqual((target / "keep.txt").read_text(), "keep")
                else:
                    self.assertFalse(target.exists())
                self.assertFalse((Path(folder) / "outside").exists())


if __name__ == "__main__":
    unittest.main()
