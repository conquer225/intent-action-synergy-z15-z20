import tempfile
import json
import unittest
from pathlib import Path
import numpy as np
from seed_shadow import SeedShadow


class ShadowTests(unittest.TestCase):
    def make_shadow(self, p):
        np.savez(p/'model.npz',weight=np.zeros((3,180)),bias=np.zeros(3),classes=[-1,0,1])
        return SeedShadow(p/'model.npz',('F3','F4','C3','C4','T7','T8','O1','O2'),status_path=p/'status.json')

    def test_verified_short_gap_and_idle(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);s=self.make_shadow(p)
            for _ in range(6):s.runtime._accept_feature(np.ones(180))
            s.packet(np.ones(8),0,now=1,timing_verified=True)
            s.idle(now=2)
            payload=json.loads((p/'status.json').read_text())
            self.assertFalse(payload['valid']);self.assertNotIn('class_id',payload)
            s.packet(np.ones(8),233,now=5.004,timing_verified=True)
            self.assertTrue(s.last_gap['baseline_retained'])
            self.assertEqual(s.runtime.accepted_windows,6)
            self.assertIsNone(s.runtime.last_prediction)
            self.assertEqual(len(s.pending),1)
            self.assertTrue(s.runtime.warming)

    def test_unverified_mismatch_and_long_gap_clear(self):
        for verified,sequence,stamp in [(False,233,5.004),(True,15,5.004),(True,221,7.004)]:
            with tempfile.TemporaryDirectory() as folder:
                s=self.make_shadow(Path(folder))
                for _ in range(6):s.runtime._accept_feature(np.ones(180))
                s.packet(np.ones(8),0,now=1,timing_verified=verified)
                s.packet(np.ones(8),sequence,now=stamp,timing_verified=verified)
                self.assertEqual(s.runtime.accepted_windows,0)
                self.assertFalse(s.last_gap['baseline_retained'])

    def test_warning_updates_mean_without_trust_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            s=self.make_shadow(Path(folder))
            for _ in range(5):s.runtime._accept_feature(np.ones(180))
            stamp=s.runtime.last_trusted_seconds
            s.runtime.clock_seconds+=12;s.runtime.window_warning=True
            event=s.runtime._accept_feature(np.full(180,2.))
            np.testing.assert_allclose(s.runtime.mean,7/6)
            self.assertTrue(event['warning']);self.assertTrue(event['baseline_updated'])
            self.assertEqual(s.runtime.last_trusted_seconds,stamp)
            s.publish(event)
            payload=json.loads(s.path.read_text())
            self.assertTrue(payload['shadow']);self.assertTrue(payload['warning'])
            self.assertEqual(payload['policy_version'],'seed-soft-update-short-gap-v1')

    def test_gap_timeout_and_wrap(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            np.savez(p/'model.npz',weight=np.zeros((3,180)),bias=np.zeros(3),classes=[-1,0,1])
            s=SeedShadow(p/'model.npz',('F3','F4','C3','C4','T7','T8','O1','O2'),status_path=p/'status.json')
            s.packet(np.ones(8),255,now=1)
            s.packet(np.ones(8),0,now=1.004)
            self.assertEqual(s.gaps,0)
            s.runtime._accept_feature(np.ones(180))
            s.packet(np.ones(8),3,now=1.008)
            self.assertEqual(s.runtime.accepted_windows,0)
            self.assertEqual(len(s.pending),1)
            s.packet(np.ones(8),4,now=8)
            self.assertEqual(s.gaps,2)
            s.packet(np.ones(8),5,malformed=True,now=8.004)
            self.assertEqual(len(s.pending),0)


if __name__=='__main__':
    unittest.main()
