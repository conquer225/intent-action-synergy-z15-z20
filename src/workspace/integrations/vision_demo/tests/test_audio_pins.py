import hashlib,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'eeg_demo/runtime'))
from patch_media import patch_audio
class AudioPairPinTests(unittest.TestCase):
    def test_audio_accepts_only_new_verified_hardware_pair(self):
        original=(ROOT.parent/'eeg_demo/runtime/page_audio.py').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            bit=Path(tmp)/'new.bit';hwh=bit.with_suffix('.hwh');asset=Path(tmp)/'asset.wav'
            bit.write_bytes(b'new bit');hwh.write_bytes(b'new hwh');asset.write_bytes(b'asset')
            digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            code=patch_audio(original,digest(bit),digest(hwh));module=types.ModuleType('vision_audio_pins');exec(compile(code,'page_audio.py','exec'),module.__dict__)
            row=dict(path=str(asset),sha256=digest(asset));config=dict(player=row,music=row,phrases={},videos={},volume_percent=40)
            with patch.object(module,'PcmSession'),patch.object(module,'PageAudio',return_value='ok'):
                self.assertEqual(module.create_page_audio(config,bit),'ok')
                bit.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'Verified audio artifact changed'):module.create_page_audio(config,bit)
if __name__=='__main__':unittest.main()
