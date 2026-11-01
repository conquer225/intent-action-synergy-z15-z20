"""Actual controller choices + a real non-hardware subprocess, not mocked playback."""
from pathlib import Path
import sys
import tempfile
import time
import unittest
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from guardianloop_system.core import SystemController
from audio_session import PcmSession
from page_audio import PageAudio, create_page_audio


class PageAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        paths = []
        for name in ('water','help','music','video','second'):
            path = self.root/(name+'.wav')
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000)
                wav.writeframes(b'\x10\x00\xf0\xff'*(48000*4))
            paths.append(path)
        self.water,self.help,self.music,self.video,self.second = paths
        session = PcmSession([sys.executable,str(Path(__file__).parent/'sim/pcm_player_process_stub.py')])
        self.audio = PageAudio(session,{0:self.water,2:self.help},self.music,{'v':self.video,'second':self.second})
        self.addCleanup(self.audio.close)
        self.controller = SystemController(10.)
        self.now = 10.
        self.ready()

    def ready(self):
        self.controller.presented(self.controller.page_id,self.now)
        self.now += 1.3

    def choose(self, region):
        self.assertTrue(self.controller.choose(region,self.now))
        self.ready()

    def wait(self, predicate):
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            view = self.audio.snapshot()
            if predicate(view):
                return view
            time.sleep(.01)
        self.fail('Audio state did not settle: '+str(self.audio.snapshot()))

    def feeding(self):
        return self.wait(lambda v:v['player']['phase']=='feeding')

    def test_speech_once_per_new_selection_and_switch_to_help(self):
        self.choose(1)
        self.audio.service(self.controller)
        self.assertIsNone(self.audio.snapshot()['player']['pid'])
        self.choose(0)
        self.audio.service(self.controller)
        first = self.feeding()
        for _ in range(30):
            self.audio.service(self.controller)
        self.assertEqual(self.audio.snapshot()['player']['revision'],first['player']['revision'])
        self.choose(2)
        self.audio.service(self.controller)
        view = self.wait(lambda v:v['player'].get('source')==str(self.help) and v['player']['phase']=='feeding')
        self.assertGreater(view['player']['revision'],first['player']['revision'])

    def test_deliberate_repeat_same_phrase_is_allowed(self):
        self.choose(1);self.choose(0)
        self.audio.service(self.controller);first = self.feeding()
        self.choose(0)
        self.audio.service(self.controller)
        self.wait(lambda v:v['player']['revision']>first['player']['revision'] and v['player']['phase']=='feeding')

    def test_leaving_speech_and_returning_does_not_replay_old_phrase(self):
        self.choose(1);self.choose(0)
        self.audio.service(self.controller);self.feeding()
        old = self.audio.session.process
        self.choose(1);self.audio.service(self.controller)
        self.wait(lambda v:v['player']['pid'] is None)
        self.assertIsNotNone(old.poll())
        self.choose(1);self.audio.service(self.controller)
        self.assertIsNone(self.audio.snapshot()['kind'])

    def test_music_entry_and_leave_use_the_existing_menu(self):
        self.choose(2);self.choose(2)
        self.audio.service(self.controller)
        view = self.feeding()
        self.assertEqual(view['player']['source'],str(self.music))
        self.assertEqual(view['volume_percent'],40)
        self.choose(1);self.audio.service(self.controller)
        self.wait(lambda v:v['player']['pid'] is None)

    def test_video_pause_resume_loop_and_switch_positions(self):
        self.choose(2);self.choose(0)
        self.audio.service(self.controller,'v',1.25,True)
        first = self.feeding()
        self.assertEqual(first['player']['position_frames_estimate'],60000)
        self.audio.service(self.controller,'v',1.5,False)
        self.wait(lambda v:v['player']['pid'] is None)
        self.audio.service(self.controller,'v',1.5,True)
        resumed = self.feeding()
        self.assertEqual(resumed['player']['position_frames_estimate'],72000)
        self.audio.service(self.controller,'v',.05,True)
        looped = self.wait(lambda v:v['player']['revision']>resumed['player']['revision'] and v['player']['phase']=='feeding')
        self.assertEqual(looped['player']['position_frames_estimate'],2400)
        self.audio.service(self.controller,'second',0,True)
        self.wait(lambda v:v['player'].get('source')==str(self.second) and v['player']['phase']=='feeding')

    def test_calibration_blocks_and_discards_delayed_speech(self):
        self.choose(1);self.choose(0)
        self.audio.service(self.controller,blocked=True)
        self.audio.service(self.controller,blocked=False)
        self.assertIsNone(self.audio.snapshot()['kind'])
        self.choose(2);self.audio.service(self.controller);self.feeding()
        self.audio.service(self.controller,blocked=True)
        self.wait(lambda v:v['player']['pid'] is None)

    def test_volume_validation_and_change_does_not_inflate_position(self):
        self.choose(2);self.choose(0)
        self.audio.service(self.controller,'v',1,True);first = self.feeding()
        for invalid in (-1,101,True,20.5,'40'):
            with self.assertRaises(ValueError):self.audio.set_volume(invalid)
        self.audio.set_volume(25)
        self.audio.service(self.controller,'v',1.1,True)
        view = self.wait(lambda v:v['player']['revision']>first['player']['revision'] and v['player']['phase']=='feeding')
        self.assertEqual(view['volume_percent'],25)
        self.assertEqual(view['player']['position_frames_estimate'],52800)
        self.assertFalse(view['speaker_latency_measured'])

    def test_missing_track_or_audio_eof_is_explicit(self):
        self.choose(2);self.choose(0)
        row = self.audio.service(self.controller,'missing',0,True)
        self.assertEqual(row['reason'],'video_has_no_prepared_audio')
        self.audio.service(self.controller,'v',0,True);self.feeding()
        row = self.audio.service(self.controller,'v',4,True)
        self.assertEqual(row['reason'],'audio_finished_before_video')
        self.wait(lambda v:v['player']['pid'] is None)

    def test_old_or_changed_bit_cannot_enable_pcm_backend(self):
        bit = self.root/'eye_wifi.bit'
        bit.write_bytes(b'not the verified audio candidate')
        bit.with_suffix('.hwh').write_bytes(b'old register map')
        record=dict(path=str(self.water),sha256='unverified')
        config=dict(player=record,music=record,phrases={'0':record,'2':record},videos={})
        with self.assertRaisesRegex(ValueError,'Verified audio artifact changed'):
            create_page_audio(config,bit)


if __name__ == '__main__':
    unittest.main()
