import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('ble_package', Path(__file__).resolve().parents[1] / 'package_delivery.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackageTests(unittest.TestCase):
    def test_preserves_baseline_and_omits_private_build_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / 'base.zip'
            with zipfile.ZipFile(base, 'w') as z:
                z.writestr('original/control.py', b'original\x00payload')
            source = root / 'source'
            (source / 'firmware' / 'MultiControlS3').mkdir(parents=True)
            (source / 'README.md').write_text('wiring', encoding='utf-8')
            (source / 'ble_compat.py').write_text('MTU compatibility overlay', encoding='utf-8')
            (source / 'firmware' / 'MultiControlS3' / 'PendulumLink.cpp').write_text('public', encoding='utf-8')
            (source / 'firmware' / 'MultiControlS3' / 'WifiConfig.h').write_text('private-password', encoding='utf-8')
            (source / 'firmware' / 'MultiControlS3' / 'private.bin').write_bytes(b'private-password')
            out = root / 'out.zip'
            module.package(base, out, source)
            with zipfile.ZipFile(out) as z:
                self.assertEqual(z.read('original/control.py'), b'original\x00payload')
                self.assertEqual(z.read('pendulum_ble_update/firmware/MultiControlS3/PendulumLink.cpp'), b'public')
                self.assertEqual(z.read('pendulum_ble_update/ble_compat.py'), b'MTU compatibility overlay')
                self.assertFalse(any(n.endswith(('WifiConfig.h', 'private.bin')) for n in z.namelist()))


if __name__ == '__main__':
    unittest.main()
