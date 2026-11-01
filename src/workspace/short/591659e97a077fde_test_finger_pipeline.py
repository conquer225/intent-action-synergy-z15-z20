"""Small deterministic tests for native triggers and a non-actuating policy."""
import unittest
from pathlib import Path
import tempfile
import numpy as np
from mi_finger_data import transitions, validate_events
from dexterous_hand_policy import Evidence, HandProposalPolicy, Limits


class Triggers(unittest.TestCase):
    def test_transitions(self):
        rows = transitions(np.array([0,0,2,2,3,3,3]),2)
        self.assertEqual([r['code'] for r in rows],[0,2,3])
        self.assertEqual(rows[-1]['duration_seconds'],1.5)
        self.assertEqual(rows[-1]['stop_sample'],7)

    def test_corrected_sample_times_and_corrupted_codes(self):
        native=np.r_[np.zeros(4,dtype=int),np.ones(4,dtype=int),np.full(8,3)]
        rows=np.column_stack((np.arange(4,16)/16,np.zeros(12),native[4:]))
        with tempfile.TemporaryDirectory(prefix='finger-event-test-') as folder:
            path=Path(folder)/'events.tsv'
            np.savetxt(path,rows,delimiter='\t',header='onset\tduration\ttrial_type',comments='')
            result=validate_events(path,native,4)
            self.assertEqual(result['onset_multiplier'],4)
            self.assertEqual(result['rows'],12)
            rows[-1,2]=7
            np.savetxt(path,rows,delimiter='\t',header='onset\tduration\ttrial_type',comments='')
            with self.assertRaises(ValueError): validate_events(path,native,4)

    def test_repeated_sample_indexes_rejected(self):
        native=np.r_[np.zeros(4,dtype=int),np.full(12,3)]
        rows=np.column_stack((np.arange(4,16)/16,np.zeros(12),native[4:]))
        rows[5,0]=rows[4,0]
        with tempfile.TemporaryDirectory(prefix='finger-event-test-') as folder:
            path=Path(folder)/'events.tsv'
            np.savetxt(path,rows,delimiter='\t',header='onset\tduration\ttrial_type',comments='')
            with self.assertRaises(ValueError): validate_events(path,native,4)

    def test_short_zero_padding_not_hidden_nonzero_marker(self):
        native=np.r_[np.zeros(4,dtype=int),np.full(12,3),np.zeros(2,dtype=int)]
        rows=np.column_stack((np.arange(4,16)/16,np.zeros(12),native[4:16]))
        with tempfile.TemporaryDirectory(prefix='finger-event-test-') as folder:
            path=Path(folder)/'events.tsv'
            np.savetxt(path,rows,delimiter='\t',header='onset\tduration\ttrial_type',comments='')
            self.assertEqual(validate_events(path,native,4)['trailing_zero_marker_samples_outside_events'],2)
            native[-1]=3
            with self.assertRaises(ValueError): validate_events(path,native,4)


class Policy(unittest.TestCase):
    def event(self,a,b,**kwargs):
        fields = dict(window_start=a,window_end=b,probabilities=(.9,.025,.025,.025,.025),
                      transport_ok=True,quality_ok=True,cue_active=True,model_validated=True)
        fields.update(kwargs); return Evidence(**fields)

    def test_default_cannot_arm(self):
        policy = HandProposalPolicy()
        self.assertEqual(policy.arm()['state'],'DISARMED')
        self.assertFalse(policy.observe(self.event(0,2),2)['control_enabled'])

    def test_two_separate_windows_propose_only(self):
        policy=HandProposalPolicy(simulation=True); policy.arm()
        self.assertEqual(policy.observe(self.event(0,2),2)['state'],'PENDING')
        value=policy.observe(self.event(2,4),4)
        self.assertEqual(value['finger'],'thumb'); self.assertFalse(value['control_enabled'])
        self.assertTrue(value['dry_run']); self.assertEqual(value['action_budget_ms'],250)

    def test_overlap_does_not_count(self):
        policy=HandProposalPolicy(simulation=True); policy.arm()
        policy.observe(self.event(0,2),2)
        self.assertEqual(policy.observe(self.event(1,3),3)['reason'],'overlapping_or_repeated_window')
        self.assertEqual(policy.count,1)

    def test_hard_faults_require_rearm(self):
        for change in (dict(transport_ok=False),dict(quality_ok=False),dict(cue_active=False),dict(model_validated=False)):
            with self.subTest(change=change):
                policy=HandProposalPolicy(simulation=True); policy.arm()
                self.assertEqual(policy.observe(self.event(0,2,**change),2)['kind'],'STOP_PROPOSAL')
                self.assertEqual(policy.observe(self.event(2,4),4)['state'],'DISARMED')

    def test_stale_future_nan_rejected(self):
        for event,now in ((self.event(0,2),3),(self.event(0,2),1),(self.event(0,float('nan')),2)):
            policy=HandProposalPolicy(simulation=True); policy.arm()
            self.assertEqual(policy.observe(event,now)['kind'],'STOP_PROPOSAL')

    def test_bad_probability_rejected(self):
        policy=HandProposalPolicy(simulation=True); policy.arm()
        self.assertEqual(policy.observe(self.event(0,2,probabilities=(1,1,0,0,0)),2)['kind'],'STOP_PROPOSAL')

    def test_uncertainty_clears_vote(self):
        policy=HandProposalPolicy(simulation=True); policy.arm()
        policy.observe(self.event(0,2),2)
        self.assertEqual(policy.observe(self.event(2,4,probabilities=(.4,.3,.1,.1,.1)),4)['reason'],'uncertain')
        self.assertEqual(policy.count,0)

    def test_limits_and_stop(self):
        with self.assertRaises(ValueError): Limits(action_budget_ms=500)
        policy=HandProposalPolicy(simulation=True); policy.arm(); policy.stop('emergency')
        self.assertEqual(policy.state,'DISARMED')

    def test_no_new_samples_timeout(self):
        policy=HandProposalPolicy(simulation=True); policy.arm()
        policy.observe(self.event(0,2),2)
        self.assertEqual(policy.tick(5)['reason'],'input_silence')

    def test_cooldown_prevents_rapid_proposals(self):
        policy=HandProposalPolicy(simulation=True,limits=Limits(cooldown=5)); policy.arm()
        policy.observe(self.event(0,2),2); policy.observe(self.event(2,4),4)
        self.assertEqual(policy.observe(self.event(4,6),6)['reason'],'rate_limited')


if __name__=='__main__': unittest.main()
