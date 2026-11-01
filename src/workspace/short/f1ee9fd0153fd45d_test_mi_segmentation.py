import unittest

from mi_segmentation import SourceSegments, train_augmented
from mi_comparison_models import network_logits, torch
import numpy as np
from mi_segmentation_experiment import read_json, PROTOCOL, HERE, paired_summary


class SegmentationTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        self.people = np.repeat([1,2,3],6)
        self.labels = np.tile([0,0,0,1,1,1],3)
        self.x = torch.arange(18*8*500,dtype=torch.float32).reshape(18,1,8,500)

    def test_same_person_class_and_all_electrodes_per_segment(self):
        builder = SourceSegments(self.labels,self.people,'cpu',42)
        anchors = torch.arange(18)
        actual, donors = builder.reconstruct(self.x,anchors)
        donors = donors.numpy()
        np.testing.assert_array_equal(self.labels[donors],np.repeat(self.labels[:,None],8,axis=1))
        np.testing.assert_array_equal(self.people[donors],np.repeat(self.people[:,None],8,axis=1))
        for segment,(start,stop) in enumerate(zip(builder.boundaries[:-1],builder.boundaries[1:])):
            torch.testing.assert_close(actual[...,start:stop],self.x[donors[:,segment],...,start:stop],rtol=0,atol=0)
        self.assertEqual(builder.boundaries,[0,62,125,187,250,312,375,437,500])
        self.assertTrue(torch.isfinite(actual).all())

    def test_repeatable_independent_random_stream(self):
        anchors = torch.arange(18)
        a = SourceSegments(self.labels,self.people,'cpu',43)
        b = SourceSegments(self.labels,self.people,'cpu',43)
        torch.manual_seed(1);first,donors1 = a.reconstruct(self.x,anchors)
        torch.manual_seed(100);second,donors2 = b.reconstruct(self.x,anchors)
        torch.testing.assert_close(first,second,rtol=0,atol=0)
        torch.testing.assert_close(donors1,donors2,rtol=0,atol=0)

    def test_reject_extra_tensor_or_wrong_shape(self):
        builder = SourceSegments(self.labels,self.people,'cpu',42)
        with self.assertRaises(ValueError):builder.reconstruct(torch.ones(19,1,8,500),torch.arange(18))
        with self.assertRaises(ValueError):SourceSegments(self.labels,self.people,'cpu',42,segments=7)

    def test_pool_contains_only_passed_fitting_rows(self):
        selected = np.arange(6,18)
        builder = SourceSegments(self.labels[selected],self.people[selected],'cpu',42)
        _, donors = builder.reconstruct(self.x[selected],torch.arange(12))
        actual_people = self.people[selected][donors.numpy()]
        self.assertNotIn(1,actual_people)
        self.assertTrue(np.isin(actual_people,[2,3]).all())

    def test_training_is_repeatable_and_budget_counted(self):
        config = read_json(HERE/'mi_model_comparison_protocol.json')['eegnet']
        config = {**config,'epochs_max':2,'batch_size':6}
        values = self.x/float(self.x.max())
        args = (values,self.labels,self.people,values,self.labels,self.people,config,42,'cpu')
        first,history = train_augmented(*args)
        second,other = train_augmented(*args)
        np.testing.assert_array_equal(network_logits(first,values),network_logits(second,values))
        self.assertEqual(history['history'],other['history'])
        self.assertEqual(history['parameter_count'],2226)
        self.assertEqual(history['optimizer_updates'],6)
        self.assertEqual(history['synthetic_rows_seen'],36)
        self.assertEqual(history['real_rows_seen'],36)

    def test_frozen_protocol_is_one_comparison_only(self):
        protocol = read_json(PROTOCOL)
        self.assertEqual(protocol['channels'],['F3','F4','C3','C4','T7','T8','O1','O2'])
        self.assertEqual(protocol['seeds'],[42,43,44])
        self.assertEqual(protocol['bootstrap']['comparison_count_this_round'],1)
        self.assertFalse(protocol['augmentation']['validation_or_target_donors'])

    def test_paired_comparison_checks_person_identity(self):
        ref = [{'subject':1,'balanced_accuracy':.6},{'subject':2,'balanced_accuracy':.7}]
        with self.assertRaises(ValueError):paired_summary(ref,ref[::-1],{'seed':42,'draws':100})
        comparison = paired_summary(ref,ref,{'seed':42,'draws':100})
        self.assertEqual(comparison['mean_ba_gain'],0)
        self.assertEqual(comparison['paired_95_ci'],[0,0])


if __name__ == '__main__':unittest.main()
