import json
import tempfile
import unittest
import zipfile
import sys
import os
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_bundle import create_bundle


class BundleTests(unittest.TestCase):
    def test_source_package_has_entry_point_baseline_and_no_fake_boot_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = create_bundle(Path(directory)/"offline.zip")
            with zipfile.ZipFile(path) as package:
                self.assertIsNone(package.testzip())
                self.assertIn("z20_compute/__main__.py", package.namelist())
                self.assertIn("verify_stereo_boot.py", package.namelist())
                self.assertIn("legacy/seed_shadow_weights.npz", package.namelist())
                self.assertFalse(any(name.lower().endswith((".bit", "boot.bin")) for name in package.namelist()))
                manifest = json.loads(package.read("manifest.json"))
                self.assertFalse(manifest["board_executed"])
                self.assertEqual(manifest["kind"], "offline-source-and-hls-ip")
                extracted = Path(directory)/"unpacked"
                package.extractall(extracted)
            result = subprocess.run([sys.executable, "-c",
                "from z20_compute.legacy_eeg import LegacyEEGFeatures; LegacyEEGFeatures(); print('BUNDLE_IMPORT_PASS')"],
                cwd=extracted, env=dict(os.environ, PYTHONPATH=str(extracted)), capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("BUNDLE_IMPORT_PASS", result.stdout)


if __name__ == "__main__": unittest.main()
