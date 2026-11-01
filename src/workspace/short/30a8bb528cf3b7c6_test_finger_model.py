"""Shape, source-only scaling and person isolation tests; no real EEG scoring."""
import unittest
import torch
import numpy as np
import json
from mi_finger_baseline import FingerEEGNet, split_people, person_ba, metrics
from mi_finger_data import RUN
from mi_comparison_models import channel_scaler, normalized_tensor


class FingerModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(4)
        cls.protocol=json.loads((RUN/'protocol.json').read_text(encoding='utf-8'))

    def test_all_splits_disjoint(self):
        p=self.protocol
        for target in p['development_people']:
            fit,val=split_people(p,target)
            self.assertEqual(len(fit),12); self.assertEqual(len(val),3)
            self.assertFalse(set(fit)&set(val)); self.assertNotIn(target,fit+val)
            self.assertFalse(set(fit+val+[target])&set(p['confirmation_people']))

    def test_five_logits_loss_and_norm(self):
        model=FingerEEGNet(self.protocol['eegnet'])
        x=torch.randn(5,1,8,500); logits=model(x)
        self.assertEqual(tuple(logits.shape),(5,5))
        loss=torch.nn.functional.cross_entropy(logits,torch.arange(5)); loss.backward()
        model.constrain()
        self.assertTrue(torch.all(model.dense.weight.norm(dim=1)<=.250001))
        self.assertTrue(torch.all(model.block1[1].weight.flatten(1).norm(dim=1)<=1.000001))

    def test_scaling_fit_not_affected_by_target(self):
        source=np.random.default_rng(42).normal(size=(10,8,500)).astype(np.float32)
        mean,scale=channel_scaler(source)
        expected_mean,expected_scale=mean.copy(),scale.copy()
        target=np.full((2,8,500),1000,dtype=np.float32)
        result=normalized_tensor(target,mean,scale,torch.device('cpu'))
        self.assertEqual(tuple(result.shape),(2,1,8,500))
        np.testing.assert_array_equal(mean,expected_mean); np.testing.assert_array_equal(scale,expected_scale)
        with self.assertRaises(ValueError): channel_scaler(np.zeros((2,8,500)))

    def test_balanced_accuracy_not_majority_accuracy(self):
        labels=np.r_[np.zeros(50,dtype=int),[1,2,3,4]]; guess=np.zeros(len(labels),dtype=int)
        self.assertAlmostEqual(metrics(labels,guess)['balanced_accuracy'],.2)
        self.assertAlmostEqual(person_ba(labels,guess,np.array(['p']*len(labels))),.2)
        with self.assertRaises(ValueError): metrics(np.array([0,1]),np.array([0,1]))


if __name__=='__main__': unittest.main()
