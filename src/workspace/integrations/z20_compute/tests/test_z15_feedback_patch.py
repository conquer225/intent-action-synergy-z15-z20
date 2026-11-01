import unittest


class PlayerGuardTests(unittest.TestCase):
 def test_existing_player_patch_is_idempotent_and_unknown_versions_are_rejected(self):
  from z20_compute.z15_feedback_patch import patch_signal_audio_guards
  source="a=vision.signal and vision.signal.session.snapshot()\nb=vision.signal and vision.signal.analysis.thread.is_alive()\n"
  fixed=patch_signal_audio_guards(source)
  self.assertIn('and vision.signal.session and',fixed)
  self.assertIn('and vision.signal.analysis and',fixed)
  self.assertEqual(fixed,patch_signal_audio_guards(fixed))
  with self.assertRaisesRegex(ValueError,'player baseline'):patch_signal_audio_guards('unrecognized=1')
