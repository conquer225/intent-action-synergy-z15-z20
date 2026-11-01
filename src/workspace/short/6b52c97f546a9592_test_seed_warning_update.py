import unittest
import numpy as np
from .seed_warning_update_ablation import UpdatingWarningPolicy


class WarningUpdateTests(unittest.TestCase):
    def test_score_precedes_update_and_warning_does_not_grant_trust(self):
        w={'weight':np.ones((3,180)),'bias':np.array([-1.,0.,1.]),'classes':np.array([-1,0,1])}
        r=UpdatingWarningPolicy(w,soft_warning=True,retain_short_gap=True)
        for _ in range(5):r._accept_feature(np.ones(180))
        stamp=r.last_trusted_seconds
        r.clock_seconds+=12
        r.window_warning=True
        e=r._accept_feature(np.ones(180)*2)
        np.testing.assert_allclose(e['scores'],[179,180,181])
        np.testing.assert_allclose(r.mean,7/6)
        self.assertTrue(e['warning'])
        self.assertTrue(e['baseline_updated'])
        self.assertEqual(r.last_trusted_seconds,stamp)
        self.assertEqual(r.accepted_windows,6)


if __name__=='__main__':unittest.main()
