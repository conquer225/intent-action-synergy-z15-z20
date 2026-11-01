import unittest
import numpy as np
from z20_compute.training import Dataset,train_mlp


class GroupedTrainingTests(unittest.TestCase):
    def test_repeating_a_source_recording_does_not_reweight_its_class(self):
        rng=np.random.default_rng(8)
        x=rng.normal(size=(9,40));y=np.tile(np.arange(3),3)
        groups=np.array(['recording%d'%i for i in range(9)])
        splits=np.repeat(['train','validation','test'],3)
        original=Dataset(x,y,groups,splits,'independent diagnostic recordings','synthetic')
        # Repeated windows from one recording must retain one recording's weight.
        indices=np.r_[np.arange(9),np.repeat([0,3],8)]
        repeated=Dataset(x[indices],y[indices],groups[indices],splits[indices],original.source,original.source_kind)
        a,_=train_mlp(original,'sound',epochs=5,group_balanced=True)
        b,report=train_mlp(repeated,'sound',epochs=5,group_balanced=True)
        np.testing.assert_allclose(a.mean,b.mean,atol=1e-12)
        for first,second in zip(a.float_parameters,b.float_parameters):np.testing.assert_allclose(first,second,atol=1e-10)
        self.assertEqual(report['weighting'],'equal_class_then_source_recording')


if __name__=='__main__':unittest.main()
