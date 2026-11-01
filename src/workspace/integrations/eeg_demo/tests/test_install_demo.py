import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('install_demo',ROOT/'install_demo.py')
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)


class InstallDemoTests(unittest.TestCase):
    def fixture(self,root):
        roots={name:root/name for name in ('media','brain','eye')}
        for p in roots.values():p.mkdir()
        old=b'old';new=b'new';model=b'frozen model'
        for group,name,data in [('media','media_player.py',old),('brain','model.bin',model),('brain','math.py',old),('eye','src/coexist_guard.py',b"PRIMARY_MANIFEST = 'OLD'\nEXPECTED_MANIFEST = 'historical'\n")]:
            p=roots[group]/name;p.parent.mkdir(exist_ok=True);p.write_bytes(data)
        manifest={'release_id':'old','channels':['F3','F4','C3','C4','T7','T8','O1','O2'],'files':{'math.py':install.digest(roots['brain']/'math.py'),'model.bin':install.digest(roots['brain']/'model.bin')}}
        encoded=json.dumps(manifest).encode();sha=hashlib.sha256(encoded).hexdigest()
        (roots['brain']/'release_manifest.json').write_bytes(encoded)
        guard=roots['eye']/'src/coexist_guard.py';guard.write_text(guard.read_text().replace('OLD',sha))
        (roots['media']/'state.json').write_text(json.dumps({'formal_hashes':manifest['files'],'other':'kept'}))
        pins={'files':{str(roots['brain']/'math.py'):manifest['files']['math.py'],str(guard):install.digest(guard)},'manifest_sha256':sha}
        (roots['media']/'boot-pins.json').write_text(json.dumps(pins))
        payload={('brain','math.py'):new,('brain','processing_diagnostics.py'):b'new diagnostics',('media','media_player.py'):new}
        expected={key:install.digest(roots[key[0]]/key[1]) for key in payload}
        return roots,payload,expected

    def test_install_updates_every_integrity_reference_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            roots,payload,expected=self.fixture(Path(directory));before={str(p):p.read_bytes() for parent in roots.values() for p in parent.rglob('*') if p.is_file()}
            plan=install.prepare(roots,payload,expected);backup=install.apply_transaction(roots,plan)
            release=json.loads((roots['brain']/'release_manifest.json').read_text());sha=install.digest(roots['brain']/'release_manifest.json')
            self.assertEqual(release['files']['math.py'],hashlib.sha256(b'new').hexdigest())
            self.assertEqual(release['files']['model.bin'],hashlib.sha256(b'frozen model').hexdigest())
            self.assertIn(sha,(roots['eye']/'src/coexist_guard.py').read_text())
            self.assertEqual(json.loads((roots['media']/'state.json').read_text())['formal_hashes'],release['files'])
            self.assertEqual(json.loads((roots['media']/'boot-pins.json').read_text())['manifest_sha256'],sha)
            # hdmi_boot rewrites state.json on every boot; its original boundary is unpinned.
            self.assertNotIn(str(roots['media']/'state.json'),json.loads((roots['media']/'boot-pins.json').read_text())['files'])
            install.rollback(roots,backup)
            self.assertTrue(all(Path(name).read_bytes()==data for name,data in before.items()))
            self.assertFalse((roots['brain']/'processing_diagnostics.py').exists())

    def test_unknown_source_or_changed_model_rejected_before_any_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            roots,payload,expected=self.fixture(Path(directory));(roots['brain']/'model.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Release checksum'):
                install.prepare(roots,payload,expected)
            self.assertEqual((roots['media']/'media_player.py').read_bytes(),b'old')

    def test_later_edits_block_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            roots,payload,expected=self.fixture(Path(directory));backup=install.apply_transaction(roots,install.prepare(roots,payload,expected))
            (roots['brain']/'math.py').write_bytes(b'user edits')
            with self.assertRaisesRegex(ValueError,'changed'):install.rollback(roots,backup)

    def test_failed_write_restores_already_replaced_files(self):
        with tempfile.TemporaryDirectory() as directory:
            roots,payload,expected=self.fixture(Path(directory));plan=install.prepare(roots,payload,expected)
            original=install.atomic;calls=[0]
            def fail_once(path,data):
                calls[0]+=1
                if calls[0]==2:raise OSError('injected storage failure')
                original(path,data)
            with patch.object(install,'atomic',side_effect=fail_once):
                with self.assertRaisesRegex(OSError,'storage'):install.apply_transaction(roots,plan)
            self.assertEqual((roots['brain']/'math.py').read_bytes(),b'old')
            self.assertFalse((roots['brain']/'processing_diagnostics.py').exists())


if __name__=='__main__':unittest.main()
