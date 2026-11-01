import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

HERE=Path(__file__).resolve().parents[1]
PROJECT=HERE.parents[1]


class DeviceMenuReleaseTests(unittest.TestCase):
    def test_archive_supports_recorded_field_sources_and_paired_rollback(self):
        from build_device_menu_release import create_release, dependency_sources
        from install_device_menu import plan_update,transaction
        spec=importlib.util.spec_from_file_location('release_fixture',HERE.parent/'eeg_demo/tests/test_install_demo.py')
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=create_release(root/'menu.zip');bundle=root/'unpacked'
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                hashes=json.loads(z.read('SHA256.json'))
                for name,sha in hashes.items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),sha)
                z.extractall(bundle)
            installed=root/'installed';installed.mkdir();roots,_,_=fixture.InstallDemoTests().fixture(installed)
            sources=dependency_sources()
            sources.update({
                'system_hdmi.py':HERE/'build/eye-audio-fix-20261028/system_hdmi.py',
                'system_runtime/guardianloop_system/device_link.py':HERE/'report/eye_audio_20261028/board-device_link.py',
                'system_runtime/guardianloop_system/eye_devices.py':PROJECT/'local/release_20261025/presentation_release/integrations/eeg_demo/runtime/system_runtime/guardianloop_system/eye_devices.py',
            })
            manifest=json.loads((bundle/'menu-update.json').read_text(encoding='utf-8'))
            for name in manifest['files']:
                if name not in sources:sources[name]=HERE/name
            for name,source in sources.items():
                path=roots['media']/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(source.read_bytes())
            before={p:p.read_bytes() for r in roots.values() for p in r.rglob('*') if p.is_file()}
            plan=plan_update(roots,bundle)
            backup=transaction.apply_transaction(roots,plan)
            self.assertIn(b'service_device_entry',(roots['media']/'system_runtime/guardianloop_system/device_link.py').read_bytes())
            self.assertIn(b'return_pending',(roots['media']/'system_runtime/guardianloop_system/eye_devices.py').read_bytes())
            transaction.rollback(roots,backup)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
