import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from build_headless_release import create_release
from z20_compute.release import verify_release,server_command


class ReleaseTests(unittest.TestCase):
    def test_independent_bundle_hashes_dependencies_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=create_release(root/'release.zip')
            with zipfile.ZipFile(archive) as package:
                self.assertIsNone(package.testzip());package.extractall(root/'extracted')
            folder=root/'extracted';report=verify_release(folder)
            self.assertGreater(report['verified_files'],350)
            self.assertTrue((folder/'media/photos/gallery.json').is_file())
            self.assertTrue((folder/'assets/display/libz20_stereo.so').is_file())
            (folder/'z20_compute/protocol.py').write_text('tampered')
            with self.assertRaises(ValueError):verify_release(folder)

    def test_launcher_has_no_audio_or_control_command_and_rejects_s3_port(self):
        config=dict(bind='127.0.0.1',data_port=9020,http_port=9021,backend='ps',pipeline=False,
                    hdmi=False,keys=False,calibration=None,record_pairs=None,autostart=False,actuator_control=False)
        command=server_command(Path('.'),config)
        self.assertIn('z20_compute.headless_server',command)
        self.assertNotIn('--sound-root',command)
        for change in [dict(data_port=9000),dict(autostart=True),dict(actuator_control=True),dict(backend='shell command')]:
            with self.subTest(change=change),self.assertRaises(ValueError):server_command(Path('.'),dict(config,**change))


if __name__=='__main__':unittest.main()
