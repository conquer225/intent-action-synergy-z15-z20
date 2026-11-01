"""Offline-only tests; no invocation of --play or access to the FPGA."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.exe=os.environ['GL_PCM_PLAYER']
        self.input=self.root/'stereo.wav'
        self.frames=[(32767,-32768),(-12345,23456),(1,-1),(0,0)]*800
        self.make_wave(self.input,48000,self.frames)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def make_wave(path,rate,frames):
        with wave.open(str(path),'wb') as out:
            out.setnchannels(2);out.setsampwidth(2);out.setframerate(rate)
            out.writeframes(b''.join(struct.pack('<hh',l,r) for l,r in frames))

    def run_player(self,*args):
        return subprocess.run([self.exe,*map(str,args)],capture_output=True,text=True,timeout=10)

    def test_inspect_and_volume_render(self):
        original=hashlib.sha256(self.input.read_bytes()).hexdigest()
        r=self.run_player('--inspect',self.input)
        self.assertEqual(r.returncode,0,r.stderr)
        result=json.loads(r.stdout)
        self.assertEqual(result['frames'],len(self.frames))
        self.assertEqual(result['rate'],48000)
        self.assertFalse(result['hardware_opened'])
        for volume in [0,25,100]:
            target=self.root/(str(volume)+'.pcm')
            r=self.run_player('--render',self.input,target,'--volume',volume)
            self.assertEqual(r.returncode,0,r.stderr)
            expected=b''.join(struct.pack('<hh',int(l*volume/100),int(right*volume/100)) for l,right in self.frames)
            self.assertEqual(target.read_bytes(),expected)
        self.assertEqual(hashlib.sha256(self.input.read_bytes()).hexdigest(),original)

    def test_output_not_overwritten(self):
        target=self.root/'existing.pcm';target.write_bytes(b'preserve existing data')
        r=self.run_player('--render',self.input,target)
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(target.read_bytes(),b'preserve existing data')

    def test_reject_wrong_rate_bad_file_and_url(self):
        wrong=self.root/'wrong.wav';self.make_wave(wrong,44100,self.frames)
        bad=self.root/'bad.wav';bad.write_bytes(b'not an audio stream')
        for source in [wrong,bad,'http://example.invalid/audio.wav']:
            r=self.run_player('--inspect',source)
            self.assertNotEqual(r.returncode,0)

    def test_empty_input_and_invalid_volume(self):
        empty=self.root/'empty.wav';self.make_wave(empty,48000,[])
        target=self.root/'partial.pcm'
        r=self.run_player('--render',empty,target)
        self.assertNotEqual(r.returncode,0)
        self.assertFalse(target.exists())
        for volume in ['-1','101','hello','10junk']:
            r=self.run_player('--render',self.input,target,'--volume',volume)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse(target.exists())

    def test_video_resume_at_exact_sample(self):
        for offset in [1,511,512,513,len(self.frames)-1]:
            target=self.root/('offset'+str(offset)+'.pcm')
            r=self.run_player('--render',self.input,target,'--volume',100,'--start-frame',offset)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads(r.stdout)['start_frame'],offset)
            self.assertEqual(json.loads(r.stdout)['frames'],len(self.frames)-offset)
            self.assertEqual(target.read_bytes(),b''.join(struct.pack('<hh',l,right) for l,right in self.frames[offset:]))

    def test_reject_start_after_end_and_invalid_options(self):
        target=self.root/'invalid.pcm'
        for options in [('--start-frame',len(self.frames)),('--start-frame',len(self.frames)+1),
                        ('--start-frame',-1),('--start-frame','1.5'),('--start-frame',600*48000),
                        ('--volume',10,'--volume',20),('--start-frame',1,'--start-frame',2),('--unknown',1)]:
            r=self.run_player('--render',self.input,target,*options)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse(target.exists())


if __name__=='__main__':
    unittest.main()
