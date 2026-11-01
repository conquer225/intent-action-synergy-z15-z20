import unittest

from mi_rms_comparison import metric_rows, aggregate, np


class RMSMetricsTests(unittest.TestCase):
    def test_one_class_collapse_is_chance_balanced_accuracy(self):
        row=metric_rows(np.array([0,1,0,1]),np.tile([1.,0.],(4,1)))
        self.assertEqual(row['balanced_accuracy'],.5)
        self.assertEqual(row['confusion_matrix'],[[2,0],[2,0]])
        self.assertEqual(row['left_fraction'],1)

    def test_person_and_seed_units_not_logit_ensemble(self):
        labels=np.array([0,1,0,1])
        outcomes=[np.array([[6,0],[0,6],[6,0],[0,6]]),
                  np.tile([1,0],(4,1)),np.array([[0,1],[1,0],[0,1],[1,0]])]
        rows=[]
        for person in (1,2):
            row={'subject':person,'windows':4,'baseline':{},'shared_rms':{}}
            for method in ('baseline','shared_rms'):
                for seed,scores in zip((42,43,44),outcomes):
                    row[method][str(seed)]=[{'amplitude_factor':f,**metric_rows(labels,scores),
                                            'agreement_with_clean':1.} for f in (1,.125,.03125)]
            rows.append(row)
        metrics,comparison=aggregate(rows,[42,43,44],[1,.125,.03125],{'seed':42,'draws':1000})
        self.assertEqual(metrics['baseline'][0]['mean_person_ba'],.5)
        self.assertEqual(comparison['paired_person95_ci'],[0,0])
        self.assertEqual(comparison['people_tied'],2)
        ensemble=metric_rows(labels,np.mean(outcomes,axis=0))
        self.assertEqual(ensemble['balanced_accuracy'],1)

    def test_paired_resampling_uses_people(self):
        rows=[]
        for person,count in ((1,4),(2,400)):
            row={'subject':person,'windows':count,'baseline':{},'shared_rms':{}}
            for method,ba in (('baseline',.5),('shared_rms',1.)):
                for seed in (42,43,44):
                    row[method][str(seed)]=[{'balanced_accuracy':ba,'macro_f1':ba,'left_fraction':.5,
                        'agreement_with_clean':1.,'amplitude_factor':factor,'confusion_matrix':[[2,0],[0,2]]}
                        for factor in (1,.125,.03125)]
            rows.append(row)
        _,comparison=aggregate(rows,[42,43,44],[1,.125,.03125],{'seed':42,'draws':1000})
        self.assertEqual(comparison['mean_ba_gain'],.5)
        self.assertEqual(comparison['paired_person95_ci'],[.5,.5])


if __name__=='__main__': unittest.main()
