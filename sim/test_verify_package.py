"""Public CLI checks for delivery integrity, including unlisted payloads."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "build/verify_package.py"


class PackageChecks(unittest.TestCase):
    def fixture(self, folder):
        root = Path(folder) / "package"
        for name in ("src", "sim", "build", "board", "data", "skill", "report"):
            (root / name).mkdir(parents=True)
        raw = b"pinned source\n"
        (root / "src/payload.txt").write_bytes(raw)
        (root / "README.md").write_text("fixture", encoding="utf-8")
        (root / "report/source_manifest.json").write_text(json.dumps({
            "schema_version": 1, "entries": [{"runtime_path": "src/PAYLOAD.txt",
            "package_path": "src/payload.txt", "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}]}), encoding="utf-8")
        self.pin(root)
        return root

    def pin(self, root):
        lines = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name != "sha256sums.txt":
                lines.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " +
                             path.relative_to(root).as_posix() + "\n")
        (root / "sha256sums.txt").write_text("".join(lines), encoding="ascii")

    def run_check(self, root):
        return subprocess.run([sys.executable, "-X", "utf8", "-B", str(SCRIPT),
            "--package", str(root)], capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_complete_delivery_passes_without_board_access(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_check(self.fixture(folder))
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["passed"])
            self.assertFalse(report["board_executed"])
            self.assertEqual(report["verified_source_files"], 1)

    def test_changed_or_unlisted_payload_fails(self):
        for fault in ("changed", "unlisted", "invalid_name"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                root = self.fixture(folder)
                if fault == "changed":
                    (root / "src/payload.txt").write_bytes(b"different")
                else:
                    (root / ("extra.txt" if fault == "unlisted" else "Bad Name.txt")).write_text("x")
                    if fault == "invalid_name":
                        self.pin(root)
                result = self.run_check(root)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(json.loads(result.stdout)["passed"])

    def test_hash_valid_long_member_is_rejected_for_windows_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            payload = root / "src" / ("a" * 60) / ("b" * 60) / "payload.txt"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"extra but correctly pinned\n")
            self.pin(root)
            result = self.run_check(root)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Windows ZIP", json.loads(result.stdout)["error"])

    def test_git_checkout_metadata_preserves_package_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            (root / ".git/objects").mkdir(parents=True)
            (root / ".git/HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
            (root / ".git/objects/untracked-object").write_bytes(b"git metadata")
            (root / ".gitignore").write_text("__pycache__/\nprivate/\n", encoding="ascii")
            (root / ".gitattributes").write_text("* -text\n", encoding="ascii")
            self.pin(root)
            # Git metadata is deliberately outside the pinned submission files.
            lines = (root / "sha256sums.txt").read_text(encoding="ascii").splitlines(True)
            (root / "sha256sums.txt").write_text("".join(line for line in lines
                if not line.split("  ", 1)[1].startswith(".git/")), encoding="ascii")
            result = self.run_check(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
