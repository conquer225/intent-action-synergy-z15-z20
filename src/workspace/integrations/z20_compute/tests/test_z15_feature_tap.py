import unittest
import numpy as np


class TapTests(unittest.TestCase):
    def test_auxiliary_reference_format_failure_preserves_original_output(self):
        from z20_compute.z15_feature_tap import FeatureTap
        class Publisher:
            def offer_features(self,*args,**kwargs):raise AssertionError('malformed reference must not publish')
        class Fatigue:
            model=object()
            def _predict(self,values):return .42
        fatigue=Fatigue();tap=FeatureTap(Publisher(),source='recorded:test');tap.attach(fatigue=fatigue)
        try:
            self.assertEqual(fatigue._predict(np.ones(20)),.42)
            self.assertEqual(tap.dropped,1)
        finally:tap.close()

    def test_original_methods_keep_their_results_and_features_are_tapped_before_mean_update(self):
        from z20_compute.z15_feature_tap import FeatureTap
        class Emotion:
            def __init__(self): self.mean=np.full(180,2.); self.accepted_windows=5
            def _accept_feature(self, feature):
                self.mean += 10; self.accepted_windows += 1
                self.output={'state':'prediction','class_id':-1}
                return self.output
        class Fatigue:
            def _predict(self, values): self.output=.42; return self.output
        class Publisher:
            def __init__(self): self.records=[]
            def offer_features(self,*args,**kwargs): self.records.append((args,kwargs));return True
        emotion, fatigue, publisher=Emotion(), Fatigue(), Publisher()
        before_emotion=set(emotion.__dict__); before_fatigue=set(fatigue.__dict__)
        tap=FeatureTap(publisher,source='live:Z15')
        tap.attach(emotion=emotion,fatigue=fatigue)
        self.assertIs(emotion._accept_feature(np.full(180,3.)),emotion.output)
        self.assertEqual(fatigue._predict(np.arange(20)),.42)
        first,second=publisher.records
        self.assertEqual(first[0][0],'emotion')
        np.testing.assert_array_equal(first[0][1],np.ones(180))
        self.assertEqual(second[0][0],'fatigue')
        self.assertEqual(first[1]['source'],'live:Z15')
        tap.close()
        self.assertNotIn('_accept_feature',emotion.__dict__)
        self.assertNotIn('_predict',fatigue.__dict__)

    def test_failed_auxiliary_publish_cannot_break_original_classifier(self):
        from z20_compute.z15_feature_tap import FeatureTap
        class Publisher:
            def offer_features(self,*args,**kwargs): raise OSError('link down')
        class Fatigue:
            def _predict(self,values): return .123
        fatigue=Fatigue();tap=FeatureTap(Publisher(),source='recorded:test');tap.attach(fatigue=fatigue)
        self.assertEqual(fatigue._predict(np.ones(20)),.123)
        self.assertEqual(tap.dropped,1)
        tap.close()


if __name__=='__main__':unittest.main()
