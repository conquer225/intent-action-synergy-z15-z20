"""The menu, control service and boot pins must update and roll back together."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]


class DeviceMenuInstallTests(unittest.TestCase):
    def fixture(self,root):
        spec=importlib.util.spec_from_file_location('menu_fixture',HERE.parent/'eeg_demo/tests/test_install_demo.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        roots,_,_=module.InstallDemoTests().fixture(root)
        bundle=root/'bundle';(bundle/'payload').mkdir(parents=True)
        files={}
        for name in ('system_hdmi.py','system_runtime/guardianloop_system/eye_devices.py',
                     'system_runtime/guardianloop_system/device_link.py'):
            target=roots['media']/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(b'# original\n')
            source=bundle/'payload'/name;source.parent.mkdir(parents=True,exist_ok=True)
            source.write_bytes(b'# revised\n')
            files[name]=dict(source='payload/'+name,before=[hashlib.sha256(target.read_bytes()).hexdigest()],
                             sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        (bundle/'menu-update.json').write_text(json.dumps(dict(format='z15-device-menu-v1',files=files,required={})))
        return roots,bundle

    def test_preview_apply_and_rollback_preserve_configuration_and_pair_pins(self):
        from install_device_menu import plan_update,transaction
        with tempfile.TemporaryDirectory() as folder:
            roots,bundle=self.fixture(Path(folder))
            config=roots['media']/'eye_devices.json';config.write_bytes(b'private unchanged config')
            before={p:p.read_bytes() for r in roots.values() for p in r.rglob('*') if p.is_file()}
            plan=plan_update(roots,bundle)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            backup=transaction.apply_transaction(roots,plan)
            for name in json.loads((bundle/'menu-update.json').read_text())['files']:
                self.assertEqual((roots['media']/name).read_bytes(),b'# revised\n')
            for name,sha in json.loads((roots['media']/'boot-pins.json').read_text())['files'].items():
                self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(),sha)
            self.assertEqual(config.read_bytes(),b'private unchanged config')
            transaction.rollback(roots,backup)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    def test_unknown_installed_revision_is_refused_before_writes(self):
        from install_device_menu import plan_update
        with tempfile.TemporaryDirectory() as folder:
            roots,bundle=self.fixture(Path(folder))
            target=roots['media']/'system_hdmi.py';target.write_bytes(b'# user revision\n')
            before={p:p.read_bytes() for r in roots.values() for p in r.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError,'baseline'):plan_update(roots,bundle)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))

    def test_partial_control_payload_is_refused(self):
        from install_device_menu import plan_update
        with tempfile.TemporaryDirectory() as folder:
            roots,bundle=self.fixture(Path(folder));path=bundle/'menu-update.json'
            row=json.loads(path.read_text());del row['files']['system_runtime/guardianloop_system/device_link.py']
            path.write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError,'Incomplete'):plan_update(roots,bundle)

    def test_tampered_payload_is_refused_and_installed_later_edits_block_rollback(self):
        from install_device_menu import plan_update,transaction
        with tempfile.TemporaryDirectory() as folder:
            roots,bundle=self.fixture(Path(folder))
            payload=bundle/'payload/system_hdmi.py';original=payload.read_bytes();payload.write_bytes(b'# tamper\n')
            with self.assertRaisesRegex(ValueError,'checksum'):plan_update(roots,bundle)
            payload.write_bytes(original)
            backup=transaction.apply_transaction(roots,plan_update(roots,bundle))
            (roots['media']/'system_hdmi.py').write_bytes(b'# later user edit\n')
            with self.assertRaisesRegex(ValueError,'changed'):transaction.rollback(roots,backup)
