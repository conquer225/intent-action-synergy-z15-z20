import unittest
import numpy as np
from z20_compute.visual_audio import SequentialSpectrum


class SpectrumTests(unittest.TestCase):
    def test_time_windows_follow_the_recording_instead_of_repeating_its_mean(self):
        t=np.arange(16000)/16000.
        pcm=np.where(t<.5,np.sin(2*np.pi*500*t),np.sin(2*np.pi*3000*t))*.5
        spectrum=SequentialSpectrum(pcm,source='recorded:test',started=10.)
        first=spectrum.at(10.1);second=spectrum.at(10.7)
        self.assertEqual(first['peak_frequency_hz'],500.)
        self.assertEqual(second['peak_frequency_hz'],3000.)
        self.assertEqual(first['sample_offset'],1600)
        self.assertEqual(second['window_sequence'],14)
        self.assertEqual(len(second['band_values']),64)
        self.assertFalse(second['playback_started'])
