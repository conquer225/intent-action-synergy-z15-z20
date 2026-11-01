"""Run the actual offline decoder against generated PCM fixtures; no audio device."""
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave


@unittest.skipUnless(os.environ.get('GL_AUDIO_PREPARER'), 'Requires board-compiled prepare_audio')
class AudioCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.binary = os.environ['GL_AUDIO_PREPARER']

    def source(self, rate, channels):
        path = self.root / ('input-%d-%d.wav' % (rate, channels))
        frames = bytearray()
        for i in range(rate):
            value = int(10000 * math.sin(2 * math.pi * 440 * i / rate))
            frames.extend(struct.pack('<' + 'h' * channels, *([value] * channels)))
        with wave.open(str(path), 'wb') as f:
            f.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
            f.writeframes(frames)
        return path

    def convert(self, source, output):
        return subprocess.run([self.binary, str(source), str(output)], capture_output=True,
                              text=True, timeout=15)

    def test_actual_resampling_duration_signal_and_source_preservation(self):
        for rate, channels in ((22050, 1), (44100, 2), (48000, 2)):
            with self.subTest(rate=rate, channels=channels):
                source = self.source(rate, channels)
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                output = self.root / ('output-%d-%d.wav' % (rate, channels))
                result = self.convert(source, output)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertFalse(report['audio_output'])
                self.assertEqual(report['timestamp_discontinuities'], 0)
                self.assertAlmostEqual(report['duration_seconds'], 1., places=4)
                with wave.open(str(output), 'rb') as f:
                    self.assertEqual((f.getframerate(), f.getnchannels(), f.getsampwidth()), (48000, 2, 2))
                    self.assertEqual(f.getnframes(), 48000)
                    values = struct.unpack('<' + 'h' * (48000 * 2), f.readframes(48000))
                self.assertGreater(max(values), 6000)
                left = values[0::2]
                crossings = sum(a <= 0 < b for a, b in zip(left, left[1:]))
                self.assertTrue(438 <= crossings <= 442, crossings)
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)

    def test_existing_output_is_never_overwritten_or_removed(self):
        source = self.source(48000, 1)
        output = self.root / 'existing.wav'
        output.write_bytes(b'user-data')
        self.assertNotEqual(self.convert(source, output).returncode, 0)
        self.assertEqual(output.read_bytes(), b'user-data')

    def test_invalid_input_leaves_no_ready_output(self):
        source = self.root / 'invalid.mp4'
        source.write_bytes(b'not an audio stream')
        output = self.root / 'invalid.wav'
        self.assertNotEqual(self.convert(source, output).returncode, 0)
        self.assertFalse(output.exists())

    def test_nonlocal_input_is_rejected_without_network_access(self):
        output = self.root / 'remote.wav'
        result = self.convert('http://127.0.0.1:1/not-a-local-file', output)
        self.assertEqual(result.returncode, 2)
        self.assertIn('local regular file', result.stderr)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
