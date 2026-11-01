import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('debug_hold_installer',ROOT/'install_debug_hold.py')
update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)
import test_install_demo as fixtures
install=fixtures.install


class DebugHoldInstallTests(unittest.TestCase):
    def test_mode_update_keeps_target_pins_and_exact_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            roots,_,_=fixtures.InstallDemoTests().fixture(Path(tmp))
            manifest=json.loads((ROOT/'debug_hold_manifest.json').read_text())
            for row in manifest['files']:
                source=ROOT/row['baseline_source']
                target=roots['media']/row['name'];target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
                self.assertEqual(install.digest(target),row['before'])
            path=roots['media']/'eye_devices.json'
            original=b'{"version":1,"s3_host":"192.168.50.45","s3_port":9000}\n'
            path.write_bytes(original)
            plan=update.plan_update(roots,True)
            backup=install.apply_transaction(roots,plan)
            config=json.loads(path.read_text())
            self.assertTrue(config['debug_hold'])
            self.assertEqual(config['s3_host'],'192.168.50.45')
            pins=json.loads((roots['media']/'boot-pins.json').read_text())
            self.assertEqual(pins['files'][str(path)],install.digest(path))
            normal=update.plan_update(roots,False)
            self.assertFalse(json.loads(normal[('media','eye_devices.json')])['debug_hold'])
            install.rollback(roots,backup)
            self.assertEqual(path.read_bytes(),original)


if __name__=='__main__':unittest.main()
