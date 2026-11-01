import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from guardianloop_system.core import SystemController
from guardianloop_system.live_inputs import BrainInputs
from historical_inputs import HistoricalInputs, SOURCE


class HistoricalTests(unittest.TestCase):
    def setUp(self):
        self.now=10.
        with patch('historical_inputs.ReplayBridge'):
            self.inputs=HistoricalInputs(Path('private'), clock=lambda:self.now)
        self.inputs.stop.set();self.inputs.thread.join();self.addCleanup(self.inputs.close)
        self.controller=SystemController(self.now)

    def put(self, **changes):
        row=dict(source=SOURCE,current_wearer=False,physical_output_enabled=False,
            updated_monotonic=self.now,processed_samples=2500,
            fatigue=dict(seq=1,valid=True,level='normal',source=SOURCE,
                emotion=dict(valid=True,label='calm',source=SOURCE)))
        row.update(changes);self.inputs.rows['status']=(row,self.now,0,None)

    def test_real_adapter_is_unchanged_and_replay_remains_explicit(self):
        self.put();view=self.inputs.apply(self.controller,self.now)
        self.assertEqual(view['state'],'replay');self.assertEqual(view['source'],SOURCE)
        self.assertFalse(view['current_wearer']);self.assertFalse(view['physical_output_enabled'])
        self.assertEqual(self.controller.monitor_labels['fatigue']['source'],SOURCE)
        self.assertIsNot(BrainInputs,HistoricalInputs)

    def test_replay_never_becomes_live_or_direction_even_if_input_contains_accepted(self):
        self.put();self.controller._enter('drive',self.now);self.controller.direction_armed=True
        self.inputs.rows['ssvep-hdmi']=(dict(source='replay',state_owner='isolated_replay',accepted=True),self.now,0,None)
        view=self.inputs.apply(self.controller,self.now)
        self.assertEqual(view['ssvep_hdmi'],{});self.assertEqual(self.controller.direction,'stop')

    def test_finished_or_expired_recording_does_not_hold_monitoring_results(self):
        self.put();self.inputs.apply(self.controller,self.now)
        self.now+=11;view=self.inputs.apply(self.controller,self.now)
        self.assertFalse(view['connected']);self.assertFalse(view['fatigue']['valid'])
        self.assertFalse(self.controller.monitor_labels)

    def test_mislabeled_current_wearer_response_is_rejected(self):
        self.put(current_wearer=True)
        self.assertFalse(self.inputs.snapshot(self.now)['connected'])
        self.put(source='live')
        self.assertFalse(self.inputs.snapshot(self.now)['connected'])


if __name__=='__main__':unittest.main()
