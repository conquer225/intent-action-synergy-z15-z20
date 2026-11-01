import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.audio import spectrum, sound_features, DacOutput


class AudioTests(unittest.TestCase):
    def test_filtered_audio_preserves_delay_line_across_blocks(self):
        output = DacOutput()
        first = output.audio([0., 0., .5], fir=[.5, .5])
        second = output.audio([0., 0., 0.], fir=[.5, .5])
        self.assertEqual(first.codes.tolist(), [128, 128, 160])
        self.assertEqual(second.codes.tolist(), [160, 128, 128])

    def test_known_tone_peak_and_audio_spectrum_switch(self):
        rate = 16000
        tone = .5*np.sin(2*np.pi*1000*np.arange(rate)/rate)
        frequencies, amplitudes = spectrum(tone[:1024], rate)
        self.assertAlmostEqual(frequencies[np.argmax(amplitudes)], 1000)
        self.assertAlmostEqual(float(amplitudes.max()), .5, places=4)
        self.assertEqual(sound_features(tone, rate).shape, (40,))
        with self.assertRaises(ValueError):
            sound_features(np.zeros(rate), rate)
        output = DacOutput()
        audio = output.audio(np.array([-1., 0., 1.]), rate)
        self.assertEqual(audio.codes.tolist(), [0, 128, 255])
        scan = output.scan(amplitudes, rate, 1024)
        original = scan.codes.copy()
        amplitudes[:] = 0
        np.testing.assert_array_equal(scan.codes, original)
        self.assertEqual(np.flatnonzero(scan.sync).tolist(), [0])
        self.assertEqual(scan.mode, "spectrum")
        self.assertEqual(output.audio(np.zeros(3), rate).mode, "audio")


if __name__ == "__main__":
    unittest.main()
