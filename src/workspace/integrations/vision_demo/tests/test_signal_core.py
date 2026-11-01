import unittest
import numpy as np
from vision_demo.signal_core import MusicPolicy,normalize_eeg,analyze_audio,SignalPages
class PolicyTests(unittest.TestCase):
 def frame(self,seq=1,label='funny',level='normal',origin='live'):
  return dict(ok=True,origin=origin,source_id='test',seq=seq,fatigue=dict(level=level,score=.1),emotion=dict(raw=label))
 def test_requires_music_visit_two_different_sequences_and_twenty_second_hold(self):
  p=MusicPolicy();f=self.frame()
  self.assertIsNone(p.update(f,0));p.arm()
  self.assertIsNone(p.update(f,1));self.assertIsNone(p.update(f,2))
  self.assertEqual(p.update(self.frame(2),3),'bright')
  self.assertIsNone(p.update(self.frame(3,'horror'),4))
  self.assertIsNone(p.update(self.frame(4,'horror'),5))
  self.assertEqual(p.update(self.frame(5,'horror'),24),'calm')
 def test_severe_priority_expiry_and_source_change_reconfirm(self):
  p=MusicPolicy();p.arm();p.update(self.frame(1,level='severe'),0)
  self.assertEqual(p.update(self.frame(2,level='severe'),1),'calm')
  self.assertIsNone(p.update(dict(ok=False),3))
  self.assertEqual(p.update(dict(ok=False),4.01),'stop')
  self.assertIsNone(p.update(self.frame(3,origin='replay'),5))
  self.assertEqual(p.update(self.frame(4,origin='replay'),6),'bright')
 def test_regressed_sequences_do_not_confirm_or_keep_old_output_live(self):
  p=MusicPolicy();p.arm();p.update(self.frame(3),0)
  self.assertIsNone(p.update(self.frame(2),1))
  self.assertIsNone(p.update(self.frame(3),2))
  self.assertEqual(p.update(self.frame(4),3),'bright')
 def test_same_fatigue_inference_republished_in_new_status_is_not_two_confirmations(self):
  p=MusicPolicy();p.arm()
  f=self.frame(1,level='severe');f['fatigue']['inference_seq']='windowA';p.update(f,0)
  f=self.frame(2,level='severe');f['fatigue']['inference_seq']='windowA';self.assertIsNone(p.update(f,1))
  f=self.frame(3,level='severe');f['fatigue']['inference_seq']='windowB';self.assertEqual(p.update(f,2),'calm')
 def test_music_events_follow_eeg_time_instead_of_machine_uptime(self):
  p=MusicPolicy();p.arm();p.update(dict(self.frame(1),position_seconds=10.),10000.)
  p.update(dict(self.frame(2),position_seconds=11.),10001.)
  self.assertEqual(p.events[-1]['source_position_seconds'],11.)
  p.update(dict(ok=False,position_seconds=15.),10005.)
  self.assertEqual(p.events[-1]['source_position_seconds'],15.)
 def test_four_pages_cycle_and_only_music_page_arms(self):
  s=SignalPages()
  self.assertEqual([s.next() for _ in range(5)],['fatigue','emotion','music','audio','fatigue'])
  self.assertTrue(s.music_armed);s.leave();self.assertFalse(s.music_armed)
class AudioTests(unittest.TestCase):
 def test_stereo_antiphase_does_not_cancel_energy_or_spectrum(self):
  n=np.arange(1024);x=.5*np.sin(2*np.pi*32*n/1024)
  r=analyze_audio(np.stack((x,-x),axis=1),48000)
  self.assertAlmostEqual(r['peak_hz'],1500);self.assertAlmostEqual(r['rms_dbfs'][0],-9.0309,places=3)
  self.assertGreater(r['bands'][1],.99)
  self.assertGreater(max(r['spectrum_dbfs']),-7)
 def test_silence_has_no_peak_and_nonfinite_audio_is_rejected(self):
  r=analyze_audio(np.zeros((1024,2)),48000);self.assertIsNone(r['peak_hz'])
  with self.assertRaises(ValueError):analyze_audio(np.full((1024,2),np.nan),48000)
class EEGAdmissionTests(unittest.TestCase):
 def test_stale_and_wrong_cap_clear_results(self):
  for packet in (dict(stale=True),dict(stale=False,status={},telemetry={'channels':['Cz']})):
   r=normalize_eeg(packet);self.assertFalse(r['ok']);self.assertIsNone(r['fatigue']);self.assertEqual(r['raw'],[])
