import unittest

import numpy as np
import torch

from cho2017_features import trial_statistics
from mi_model_comparison import waveform_and_statistics, fold_indices, checked_protocol
from mi_comparison_models import (split_people, EEGNetSmall, channel_scaler, normalized_tensor,
                                  network_logits, fit_selected_fb, selected_fb_scores, mean_person_ba,
                                  train_network)
from mi_spatial_development import fit as fit_spatial

class ModelComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol,cls.original,cls.people=checked_protocol()
        torch.set_num_threads(2)

    def test_all_folds_have_fixed_disjoint_people(self):
        for target in self.people:
            fitting,validation=split_people(self.people,target)
            self.assertEqual((len(fitting),len(validation)),(26,3))
            self.assertFalse(set(fitting)&set(validation))
            self.assertNotIn(target,fitting+validation)
            self.assertEqual(set(fitting+validation+[target]),set(self.people))
            self.assertEqual(split_people(list(reversed(self.people)),target),(fitting,validation))

    def test_scope_rejects_extra_people(self):
        with self.assertRaises(ValueError):split_people(self.people+[6],1)
        with self.assertRaises(ValueError):split_people(self.people,6)

    def test_target_prefix_is_never_scored(self):
        subjects=np.repeat(self.people,80);order=np.tile(np.arange(80),30)
        fitting,validation=split_people(self.people,1)
        a,b,c=fold_indices(subjects,order,{'target':1,'fit_people':fitting,'validation_people':validation})
        self.assertEqual((len(a),len(b),len(c)),(26*80,3*80,20))
        self.assertTrue((order[c]>=60).all())

    def test_waveform_statistics_match_existing_path(self):
        samples=np.random.default_rng(1).normal(size=(3584,8))
        wave,*actual=waveform_and_statistics(samples,1023,self.original)
        for value,expected in zip(actual,trial_statistics(samples,1023,self.original)):
            np.testing.assert_array_equal(value,expected)
        self.assertEqual(wave.shape,(8,500))
        self.assertEqual(wave.dtype,np.float32)

    def test_future_cannot_change_task_waveform(self):
        samples=np.random.default_rng(2).normal(size=(3584,8))
        expected=waveform_and_statistics(samples,1023,self.original)[0]
        samples[2400:]+=1e6
        np.testing.assert_array_equal(expected,waveform_and_statistics(samples,1023,self.original)[0])

    def test_scaler_uses_only_passed_training(self):
        rng=np.random.default_rng(3);fit=rng.normal(size=(20,8,500)).astype(np.float32)
        mean,scale=channel_scaler(fit)
        target=np.full((5,8,500),1e5,dtype=np.float32)
        normalized_tensor(target,mean,scale,'cpu')
        np.testing.assert_array_equal((mean,scale),channel_scaler(fit))

    def test_eegnet_shape_constraints_and_frozen_bn(self):
        model=EEGNetSmall(self.protocol['eegnet'])
        with torch.no_grad():
            model.block1[1].weight.fill_(9);model.dense.weight.fill_(9)
        model.constrain()
        self.assertLessEqual(float(model.block1[1].weight.flatten(1).norm(dim=1).max().detach()),1.000001)
        self.assertLessEqual(float(model.dense.weight.norm(dim=1).max().detach()),.250001)
        before={k:v.clone() for k,v in model.state_dict().items()}
        logits=network_logits(model,torch.randn(3,1,8,500))
        self.assertEqual(logits.shape,(3,2));self.assertTrue(np.isfinite(logits).all())
        for key,value in model.state_dict().items():torch.testing.assert_close(value,before[key],rtol=0,atol=0)
        self.assertEqual(sum(p.numel() for p in model.parameters()),2226)
        with self.assertRaises(ValueError):model(torch.randn(1,1,3,500))

    def test_selected_fb_reproducible_and_portable(self):
        rng=np.random.default_rng(4)
        raw=rng.normal(size=(80,7,8,8));cov=raw@raw.transpose(0,1,3,2)
        cov/=np.trace(cov,axis1=2,axis2=3)[:,:,None,None]
        labels=np.arange(80)%2
        filters=fit_spatial(cov,labels,'FBCSP_LDA')[0]
        first=fit_selected_fb(cov,labels,filters,self.protocol['fbcsp_selection'])
        second=fit_selected_fb(cov,labels,filters,self.protocol['fbcsp_selection'])
        np.testing.assert_array_equal(first.selected_positions,second.selected_positions)
        self.assertEqual(first.scaler.mean_.shape,(6,))
        pred,score,error=selected_fb_scores(cov,first)
        self.assertEqual(len(pred),80);self.assertLess(error,1e-10)

    def test_selection_sees_no_validation_or_target_labels(self):
        rng=np.random.default_rng(5);raw=rng.normal(size=(60,7,8,8))
        cov=raw@raw.transpose(0,1,3,2);cov/=np.trace(cov,axis1=2,axis2=3)[:,:,None,None]
        labels=np.arange(60)%2;train=np.arange(40)
        filters=fit_spatial(cov[train],labels[train],'FBCSP_LDA')[0]
        first=fit_selected_fb(cov[train],labels[train],filters,self.protocol['fbcsp_selection'])
        labels[40:]=1-labels[40:];cov[40:]*=100
        second=fit_selected_fb(cov[train],labels[train],filters,self.protocol['fbcsp_selection'])
        np.testing.assert_array_equal(first.filters,second.filters)
        np.testing.assert_array_equal(first.band_mutual_information,second.band_mutual_information)
        np.testing.assert_array_equal(first.classifier.coef_,second.classifier.coef_)

    def test_two_seed_runs_reproduce_on_synthetic_data(self):
        config={**self.protocol['eegnet'],'epochs_max':2}
        rng=np.random.default_rng(6)
        x=torch.from_numpy(rng.normal(size=(20,1,8,500)).astype(np.float32))
        y=np.arange(20)%2;people=np.repeat([1,2],10)
        torch.use_deterministic_algorithms(True)
        a,ha=train_network(x,y,x,y,people,config,42,'cpu')
        b,hb=train_network(x,y,x,y,people,config,42,'cpu')
        np.testing.assert_array_equal(network_logits(a,x),network_logits(b,x))
        self.assertEqual(ha['best_epoch'],hb['best_epoch'])
        self.assertEqual(ha['history'],hb['history'])

    def test_validation_metric_is_equal_person_not_pooled(self):
        labels=np.array([0,1]+[0,1]*4);people=np.array([1,1]+[2]*8)
        pred=np.array([0,1]+[1,0]*4)
        self.assertEqual(mean_person_ba(labels,pred,people),.5)


if __name__=='__main__':unittest.main()
