import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('install_patch',ROOT/'legacy_eye_install.py')
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)


class InstallTests(unittest.TestCase):
    def fixture(self,root):
        manifest={'files':{'media_player.py':{'before':hashlib.sha256(b'old').hexdigest(),
                                            'after':hashlib.sha256(b'new').hexdigest()},
                           'system_runtime/new.py':{'before':None,'after':hashlib.sha256(b'added').hexdigest()}},
                  'required':{}}
        payload=root/'payload';payload.mkdir();(payload/'media_player.py').write_bytes(b'new')
        (payload/'system_runtime').mkdir();(payload/'system_runtime/new.py').write_bytes(b'added')
        target=root/'installed';target.mkdir();(target/'media_player.py').write_bytes(b'old')
        return manifest,payload,target

    def test_preview_apply_and_rollback_preserve_unrelated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest,payload,target=self.fixture(Path(folder))
            (target/'ratings.json').write_bytes(b'keep')
            install.apply_patch(target,payload,manifest,'192.168.4.2',apply=False)
            self.assertEqual((target/'media_player.py').read_bytes(),b'old')
            backup=install.apply_patch(target,payload,manifest,'192.168.4.2',apply=True)
            self.assertEqual((target/'media_player.py').read_bytes(),b'new')
            self.assertEqual(json.loads((target/'eye_devices.json').read_text())['s3_host'],'192.168.4.2')
            install.rollback(target,backup)
            self.assertEqual((target/'media_player.py').read_bytes(),b'old')
            self.assertFalse((target/'eye_devices.json').exists())
            self.assertFalse((target/'system_runtime/new.py').exists())
            self.assertEqual((target/'ratings.json').read_bytes(),b'keep')

    def test_foreign_runtime_refused_before_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest,payload,target=self.fixture(Path(folder))
            (target/'media_player.py').write_bytes(b'newer user version')
            with self.assertRaisesRegex(ValueError,'baseline'):
                install.apply_patch(target,payload,manifest,'192.168.4.2',apply=True)
            self.assertFalse((target/'eye_devices.json').exists())

    def test_rollback_refuses_later_user_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest,payload,target=self.fixture(Path(folder))
            backup=install.apply_patch(target,payload,manifest,'192.168.4.2',apply=True)
            (target/'media_player.py').write_bytes(b'user edit')
            with self.assertRaisesRegex(ValueError,'changed'):
                install.rollback(target,backup)
            self.assertEqual((target/'media_player.py').read_bytes(),b'user edit')

    def test_boot_hash_pins_are_updated_and_restored_with_the_patch(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest,payload,target=self.fixture(Path(folder))
            pins={'files':{str(target/'media_player.py'):hashlib.sha256(b'old').hexdigest()},
                  'manifest_sha256':'unchanged formal release'}
            original=json.dumps(pins).encode();(target/'boot-pins.json').write_bytes(original)
            backup=install.apply_patch(target,payload,manifest,'192.168.4.2',apply=True)
            updated=json.loads((target/'boot-pins.json').read_text())
            self.assertEqual(updated['files'][str(target/'media_player.py')],hashlib.sha256(b'new').hexdigest())
            self.assertIn(str(target/'eye_devices.json'),updated['files'])
            self.assertEqual(updated['manifest_sha256'],'unchanged formal release')
            install.rollback(target,backup)
            self.assertEqual((target/'boot-pins.json').read_bytes(),original)


if __name__=='__main__':unittest.main()
