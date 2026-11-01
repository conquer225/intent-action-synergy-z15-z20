import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


class AdapterBundleTests(unittest.TestCase):
    def test_independent_package_imports_and_preflight_detects_original_changes(self):
        from build_z15_adapter import create_bundle
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            archive=create_bundle(root/'adapter.zip')
            with zipfile.ZipFile(archive) as bundle:
                self.assertIsNone(bundle.testzip());bundle.extractall(root/'unpacked')
            command=[sys.executable,'-c',
                'import sys;from z20_compute.z15_preflight import check;from z20_compute.z15_feature_tap import FeatureTap;'
                'from z20_compute.z15_client import ReconnectingFeatures;'
                'assert "scipy" not in sys.modules;'
                'r=check("reference_original","original_hashes.json");assert r["passed"],r']
            result=subprocess.run(command,cwd=root/'unpacked',capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            target=root/'unpacked/reference_original/seed_shadow_weights.npz'
            target.write_bytes(b'changed')
            command[-1]='from z20_compute.z15_preflight import check;r=check("reference_original","original_hashes.json");assert not r["passed"] and "seed_shadow_weights.npz" in r["changed"]'
            result=subprocess.run(command,cwd=root/'unpacked',capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
