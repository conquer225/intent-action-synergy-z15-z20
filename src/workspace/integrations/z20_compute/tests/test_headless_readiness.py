from types import SimpleNamespace
import unittest


class ReadinessTests(unittest.TestCase):
    def test_one_missing_model_does_not_disable_other_enabled_tasks(self):
        from z20_compute.headless_readiness import load_enabled_models
        def load(path):
            if path.name=='fatigue':raise FileNotFoundError('absent')
            return SimpleNamespace(task=path.name,version='v1',source_kind='public',deployable=True)
        models,states=load_enabled_models('/models',tasks=('emotion','fatigue'),loader=load)
        self.assertEqual(set(models),{'emotion'})
        self.assertTrue(states['emotion']['operational']);self.assertFalse(states['fatigue']['operational'])
        self.assertNotIn('face',states)

    def test_teacher_candidate_is_explicit_and_does_not_claim_real_recording_training(self):
        from z20_compute.headless_readiness import load_enabled_models
        def load(path):return SimpleNamespace(task='fatigue',version='teacher-v1',source_kind='synthetic',deployable=False)
        models,states=load_enabled_models('/models',tasks=('fatigue',),loader=load)
        self.assertTrue(states['fatigue']['operational'])
        self.assertEqual(states['fatigue']['state'],'teacher_candidate')
        self.assertEqual(states['fatigue']['source_kind'],'synthetic')


if __name__=='__main__':unittest.main()
