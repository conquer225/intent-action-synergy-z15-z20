from pathlib import Path
import tempfile
import unittest
import wave
import subprocess
import sys
import numpy as np


class AudioFileTests(unittest.TestCase):
    def test_minimal_board_python_does_not_require_wave_stdlib_package(self):
        result=subprocess.run([sys.executable,'-c','''
import builtins
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name in ('wave','scipy'):raise ImportError('absent in minimal board image')
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from z20_compute.audio_file import read_pcm
'''],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_file_features_and_fft_share_pcm_without_playback(self):
        from z20_compute.audio_file import analyze_file
        from z20_compute.audio import sound_features
        from types import SimpleNamespace
        class Model:
            version='test-model'
            def predict(self, features, *, backend):
                self.features=features
                return SimpleNamespace(valid=True,class_id=1,scores=np.array([0.,2.,1.]),
                    state='prediction',model_version=self.version,backend='test_adapter')
        model=Model()
        pcm=np.rint(np.sin(2*np.pi*1000*np.arange(16000)/16000)*12000).astype('<i2')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'tone.wav'
            with wave.open(str(path),'wb') as output:
                output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000);output.writeframes(pcm.tobytes())
            result=analyze_file(path,model)
            np.testing.assert_array_equal(model.features,sound_features(pcm.astype(float)/32768))
            self.assertEqual(result['analysis']['peak_frequency_hz'],1000.)
            self.assertEqual(result['class_id'],1)
            self.assertEqual(len(result['analysis']['waveform_minmax']),160)
            self.assertFalse(result['playback_started'])

    def test_silence_never_calls_classifier(self):
        from z20_compute.audio_file import analyze_file
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'silence.wav'
            with wave.open(str(path),'wb') as output:
                output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000);output.writeframes(bytes(32000))
            result=analyze_file(path,object())
            self.assertFalse(result['valid']);self.assertIsNone(result['class_id'])
            self.assertEqual(result['state'],'silence')


if __name__=='__main__':unittest.main()
