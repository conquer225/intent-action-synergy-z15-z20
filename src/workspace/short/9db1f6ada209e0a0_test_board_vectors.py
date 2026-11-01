"""Host-only vector and verifier format tests; never opens the Z15 device."""
import contextlib
import io
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import numpy as np
from prepare_board_vectors import prepare, MAGIC, FixedSOS, SOS


class VectorTests(unittest.TestCase):
    def test_continuous_golden_and_determinism(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with contextlib.redirect_stdout(io.StringIO()):
                a = prepare(root / 'a', frames=30)
                prepare(root / 'b', frames=30)
            data = (root / 'a/golden_frames.bin').read_bytes()
            self.assertEqual(data, (root / 'b/golden_frames.bin').read_bytes())
            self.assertEqual(struct.unpack_from('<8sII', data), (MAGIC, 1, 30))
            words = np.frombuffer(data, dtype='<i8', offset=16).reshape(30, 2, 10, 8)
            expected = FixedSOS(np.load(SOS)).process_quantized(words[:, 0].reshape(-1, 8))
            np.testing.assert_array_equal(expected, words[:, 1].reshape(-1, 8))
            self.assertTrue(a['split_continuous_parity'])
            self.assertEqual(a['saturations'], 0)

    def test_invalid_frame_count(self):
        for frames in (0, 1, 10001):
            with self.assertRaises(ValueError):
                prepare(Path('unused'), frames=frames)

    def test_c_verifier_rejects_malformed_input(self):
        # C host binary is built explicitly beforehand. Use WSL to run it.
        fixture = struct.pack('<8sII', MAGIC, 1, 2) + bytes(2 * 1280)
        variants = {
            'valid': (fixture, 0),
            'magic': (b'BROKEN00' + fixture[8:], 1),
            'version': (fixture[:8] + struct.pack('<I', 2) + fixture[12:], 1),
            'truncated': (fixture[:-1], 1),
            'trailing': (fixture + b'X', 1),
            'signed40': (fixture[:16] + struct.pack('<q', 1 << 39) + fixture[24:], 1),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, (data, code) in variants.items():
                path = Path(temp, name + '.bin')
                path.write_bytes(data)
                converted = subprocess.check_output(['wsl', '--exec', 'wslpath', '-a', str(path)], text=True).strip()
                result = subprocess.run(['wsl', '--exec', '/tmp/gldma_board_check_host',
                                         '--check-vectors', converted], capture_output=True, text=True)
                self.assertEqual(result.returncode, code, (name, result.stdout, result.stderr))
                if code == 0:
                    self.assertIn('no device opened', result.stdout)


if __name__ == '__main__':
    unittest.main()
