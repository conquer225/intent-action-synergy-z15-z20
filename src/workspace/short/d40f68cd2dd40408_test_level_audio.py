from pathlib import Path
import hashlib
import math
import tempfile
import unittest
import wave

import numpy as np

from level_audio import level, measure


class LevelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def wav(self, name, samples, rate=48000):
        path = self.root/name
        with wave.open(str(path),'wb') as wav:
            wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(rate)
            wav.writeframes(np.asarray(samples,dtype='<i2').tobytes())
        return path

    def test_quiet_stereo_gains_are_equal_and_source_preserved(self):
        samples = np.tile(np.array([[500,-250],[-500,250]],dtype='<i2'),(30001,1))
        src = self.wav('quiet.wav',samples)
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        result = level(src,self.root/'leveled.wav')
        self.assertEqual(result['after']['frames'],len(samples))
        self.assertAlmostEqual(result['after']['rms_dbfs'],-23,delta=.01)
        self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),digest)
        with wave.open(str(self.root/'leveled.wav'),'rb') as w:
            actual = np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').reshape(-1,2)
        gain = 10**(result['gain_db']/20)
        np.testing.assert_array_equal(actual,np.rint(samples.astype(float)*gain).astype('<i2'))
        self.assertFalse(result['hardware_opened'])

    def test_sparse_peaks_are_limited_without_clipping(self):
        samples = np.zeros((60000,2),dtype='<i2')
        samples[100] = [-32768,32767]
        src = self.wav('peaks.wav',samples)
        result = level(src,self.root/'safe.wav')
        self.assertLess(result['gain_db'],0)
        self.assertLessEqual(result['after']['peak'],math.floor(32767*10**(-3/20)))

    def test_existing_output_is_preserved(self):
        src = self.wav('in.wav',[[50,-50]]*100)
        output = self.root/'existing.wav'
        output.write_bytes(b'keep this')
        with self.assertRaises(FileExistsError):
            level(src,output)
        self.assertEqual(output.read_bytes(),b'keep this')

    def test_silence_bad_format_and_truncation_do_not_publish(self):
        silence = self.wav('zero.wav',[[0,0]]*100)
        wrong = self.wav('rate.wav',[[100,100]]*100,44100)
        short = self.wav('short.wav',[[100,100]]*100)
        short.write_bytes(short.read_bytes()[:-20])
        for src in (silence,wrong,short):
            with self.assertRaises(ValueError):
                level(src,self.root/'invalid.wav')
            self.assertFalse((self.root/'invalid.wav').exists())

    def test_gain_bound_for_nearly_silent_input(self):
        src = self.wav('tiny.wav',[[1,-1]]*1000)
        result = level(src,self.root/'tiny-safe.wav')
        self.assertLessEqual(result['gain_db'],30)
        self.assertEqual(measure(self.root/'tiny-safe.wav')['peak'],32)


if __name__ == '__main__':
    unittest.main()
