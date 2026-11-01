import unittest
import numpy as np
from .seed_gate_policy import GatePolicy
from seed_quality_runtime import SeedQualityRuntime


def weights():
    return {'weight':np.ones((3,180)), 'bias':np.array([-1.,0.,1.]),'classes':np.array([-1,0,1])}


class PolicyTests(unittest.TestCase):
    def calibrated(self, **kwargs):
        r = GatePolicy(weights(), **kwargs)
        for _ in range(6):
            r._accept_feature(np.ones(180))
        return r

    def test_short_gap_preserves_only_baseline(self):
        r = self.calibrated(retain_short_gap=True)
        before = r.mean.copy()
        self.assertTrue(r.gap(4)['baseline_retained'])
        np.testing.assert_array_equal(before,r.mean)
        self.assertEqual(r.accepted_windows,6)
        self.assertTrue(r.warming)
        self.assertIsNone(r.last_prediction)
        self.assertEqual(r.features.pending.shape[1],0)

    def test_long_stale_untrusted_changed_stream_reset(self):
        for mode in ('long','stale','bad','changed','uncalibrated'):
            r = self.calibrated(retain_short_gap=True)
            if mode=='stale': r.clock_seconds += 31
            if mode=='bad': r.feed_block(np.zeros((500,8)))
            if mode=='uncalibrated': r.accepted_windows=4
            self.assertFalse(r.gap(6 if mode=='long' else 4,same_stream=mode!='changed')['baseline_retained'])
            self.assertEqual(r.accepted_windows,0)

    def test_warning_predicts_without_baseline_update(self):
        r = self.calibrated(soft_warning=True)
        old = r.mean.copy()
        r.window_warning=True
        result = r._accept_feature(np.ones(180)*2)
        self.assertTrue(result['valid'])
        self.assertTrue(result['warning'])
        self.assertFalse(result['baseline_updated'])
        np.testing.assert_array_equal(old,r.mean)
        self.assertEqual(r.accepted_windows,6)

    def test_strict_matches_original(self):
        old, new = SeedQualityRuntime(weights()), GatePolicy(weights())
        t=np.arange(160*250)/250
        x=np.stack([20*np.sin(2*np.pi*(9+i*.2)*t+i*.3) for i in range(8)],axis=1)
        x[10000:11000,6:]=0
        for start in range(0,len(x),500):
            self.assertEqual(old.append(x[start:start+500]),new.feed_block(x[start:start+500]))

    def test_nonfinite_forces_reset(self):
        r=self.calibrated(soft_warning=True,retain_short_gap=True)
        self.assertEqual(r.feed_block(np.full((500,8),np.nan))[0]['state'],'reset')
        self.assertEqual(r.accepted_windows,0)

    def test_absolute_fault_still_rejected_under_soft_policy(self):
        r=self.calibrated(soft_warning=True,retain_short_gap=True)
        old=r.mean.copy()
        event=r.feed_block(np.zeros((500,8)))[0]
        self.assertEqual(event['state'],'rejected')
        np.testing.assert_array_equal(old,r.mean)
        self.assertIsNone(r.last_trusted_seconds)

    def test_short_gap_recovery_has_no_old_window(self):
        r=self.calibrated(retain_short_gap=True)
        r.gap(4)
        t=np.arange(14*250)/250
        x=np.stack([20*np.sin(2*np.pi*(9+i*.2)*t+i*.3) for i in range(8)],axis=1)
        predictions=[]
        for start in range(0,len(x),500):
            for event in r.feed_block(x[start:start+500]):
                if event['valid']:predictions.append((start+500)/250)
        self.assertEqual(predictions,[14.])


if __name__=='__main__':
    unittest.main()
