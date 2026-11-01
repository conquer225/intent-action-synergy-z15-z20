import inspect
import unittest
from mi_person_transfer_diagnostic import personal_indices, balanced_subset, features
from mi_comparison_models import EEGNetSmall, torch
import numpy as np
from mi_model_comparison import read_json, PROTOCOL


class PersonTransferTests(unittest.TestCase):
    def test_chronology_and_disjoint(self):
        people=np.repeat([1,2],200)
        order=np.tile(np.arange(200),2)
        fit,val,test=personal_indices(people,order,1)
        self.assertEqual((len(fit),len(val),len(test)),(80,40,80))
        self.assertLess(order[fit].max(),order[val].min())
        self.assertLess(order[val].max(),order[test].min())
        self.assertFalse(set(fit)&set(test))
        self.assertFalse(set(val)&set(test))
        np.testing.assert_array_equal(people[test],1)

    def test_240_trial_person(self):
        fit,val,test=personal_indices(np.ones(240),np.arange(240),1)
        self.assertEqual(len(test),120)

    def test_incomplete_person_rejected(self):
        with self.assertRaises(ValueError):
            personal_indices(np.ones(180),np.arange(180),1)

    def test_matched_budget_balance_people(self):
        people=np.repeat(np.arange(26),200)
        labels=np.tile(np.arange(200)%2,26)
        selected=balanced_subset(labels,people,np.arange(len(labels)),40,np.random.default_rng(42))
        self.assertEqual(len(set(selected)),80)
        np.testing.assert_array_equal(np.bincount(labels[selected]),[40,40])
        for label in (0,1):
            counts=np.bincount(people[selected[labels[selected]==label]],minlength=26)
            self.assertEqual(set(counts),{1,2})

    def test_matched_validation_both_classes_per_person(self):
        people=np.repeat(np.arange(3),200)
        labels=np.tile(np.arange(200)%2,3)
        selected=balanced_subset(labels,people,np.arange(600),20,np.random.default_rng(42))
        for person in range(3):
            self.assertEqual(set(labels[selected[people[selected]==person]]),{0,1})

    def test_repeat_sampling_deterministic(self):
        people=np.repeat(np.arange(3),200)
        labels=np.tile(np.arange(200)%2,3)
        a=balanced_subset(labels,people,np.arange(600),20,np.random.default_rng(42))
        b=balanced_subset(labels,people,np.arange(600),20,np.random.default_rng(42))
        np.testing.assert_array_equal(a,b)

    def test_eligible_excludes_target(self):
        people=np.repeat(np.arange(4),200)
        labels=np.tile(np.arange(200)%2,4)
        eligible=np.flatnonzero(people!=3)
        selected=balanced_subset(labels,people,eligible,20,np.random.default_rng(42))
        self.assertNotIn(3,people[selected])

    def test_short_class_rejected(self):
        with self.assertRaises(ValueError):
            balanced_subset(np.zeros(10,dtype=int),np.ones(10,dtype=int),np.arange(10),3,np.random.default_rng(42))

    def test_duplicate_eligible_rejected(self):
        with self.assertRaises(ValueError):
            balanced_subset(np.arange(10)%2,np.ones(10),np.array([0,0,1,2,3,4]),3,np.random.default_rng(42))

    def test_features_frozen_deterministic_and_dense_independent(self):
        torch.set_num_threads(2)
        model=EEGNetSmall(read_json(PROTOCOL)['eegnet'])
        x=torch.randn(4,1,8,500)
        state={key:value.clone() for key,value in model.state_dict().items()}
        before=torch.get_rng_state().clone()
        a=features(model,x)
        np.testing.assert_array_equal(a,features(model,x))
        self.assertEqual(a.shape,(4,240))
        torch.testing.assert_close(before,torch.get_rng_state(),rtol=0,atol=0)
        for key,value in model.state_dict().items():
            torch.testing.assert_close(value,state[key],rtol=0,atol=0)
        with torch.no_grad():
            model.dense.weight.add_(100)
        np.testing.assert_array_equal(a,features(model,x))

    def test_feature_api_has_no_labels(self):
        self.assertEqual(list(inspect.signature(features).parameters),['model','x'])


if __name__=='__main__':
    unittest.main()
