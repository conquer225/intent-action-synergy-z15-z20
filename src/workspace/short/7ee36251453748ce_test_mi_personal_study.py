import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from mi_personal_study import PersonalReadout, PersonalStudySession


class BaseModel:
    def features(self, waves):
        return np.tile(np.linspace(0, 1, 240), (len(waves), 1)) + waves.mean() * .001

    def score_features(self, features):
        return np.tile([1., -1.], (len(features), 1))


class Clock:
    value = 10.
    def __call__(self):
        return self.value


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Clock()
        self.session = PersonalStudySession(BaseModel(), directory=Path(self.temp.name) / 'study', clock=self.clock)
        self.count = 0

    def feed(self, n=750, gain=10):
        for i in range(0, n, 100):
            rows = np.arange(self.count, self.count + min(100, n-i))
            waves = gain * np.sin(2*np.pi*rows[:, None] / 250 * np.arange(8, 16)[None])
            self.clock.value += len(rows)/250
            self.session.feed(waves, rows % 256)
            self.count += len(rows)
            if self.session.trial and self.session.trial['state'] == 'active':
                self.session.command(dict(action='heartbeat', id=self.session.trial['id']))

    def begin(self, phase='calibration'):
        self.feed()
        self.session.command(dict(action='study_begin', phase=phase))

    def trial(self, gain=10):
        s = self.session.command(dict(action='study_next'))
        self.session.command(dict(action='presented', id=s['id'], browser_onset_ms=1, browser_send_ms=2))
        self.feed(750, gain=gain)
        result = self.session.trial['result']
        self.session.command(dict(action='study_finish', id=s['id']))
        return result

    def test_order_is_balanced_prediction_not_cue_and_hidden(self):
        self.begin()
        self.assertEqual(self.session.order.count('right'), 6)
        self.assertEqual(self.session.order.count('left'), 6)
        for _ in range(12):
            r = self.trial()
            self.assertEqual(r['label'], 'left')
            self.assertIsNone(self.session.snapshot()['result'])
        self.assertTrue(self.session.snapshot()['study']['personal_fitted'])
        self.assertEqual(self.session.virtual_hand['command_count'], 0)
        data = np.load(self.session.directory/'calibration/trial-01.npz')
        self.assertEqual(data['filtered'].shape, (500, 8))
        self.assertEqual(data['sensor_uv'].shape, (750, 8))
        self.assertEqual(len(data['sequences']), 750)
        data.close()

    def test_confirmation_does_not_fit_and_cannot_be_reused(self):
        self.begin()
        for _ in range(12): self.trial()
        before = (self.session.directory/'personal_readout.npz').read_bytes()
        self.session.command(dict(action='study_begin', phase='confirmation'))
        for _ in range(12): self.trial()
        self.assertEqual(before, (self.session.directory/'personal_readout.npz').read_bytes())
        self.assertEqual(self.session.completed['confirmation']['attempted'], 12)
        with self.assertRaises(ValueError): self.session.command(dict(action='study_begin', phase='confirmation'))

    def test_refuse_no_data_and_confirmation_without_fit(self):
        with self.assertRaises(ValueError): self.session.command(dict(action='study_begin', phase='calibration'))
        self.feed()
        with self.assertRaises(ValueError): self.session.command(dict(action='study_begin', phase='confirmation'))
        with self.assertRaises(ValueError): self.session.command(dict(action='start', target='right', virtual_control=True))

    def test_rejections_retained_and_insufficient_quality_not_fitted(self):
        self.begin()
        for _ in range(12): self.trial(gain=1000)
        report = self.session.completed['calibration']
        self.assertEqual(report['status'], 'insufficient_quality_no_fit')
        self.assertEqual(report['rejected'], 12)
        self.assertEqual(len(list((self.session.directory/'calibration').glob('trial-*.npz'))), 12)

    def test_old_finish_id_refused_and_abort_saved(self):
        self.begin()
        state = self.session.command(dict(action='study_next'))
        with self.assertRaises(ValueError): self.session.command(dict(action='study_finish', id='old'))
        self.session.command(dict(action='study_abort'))
        self.assertEqual(self.session.completed['calibration']['status'], 'aborted')
        self.assertFalse(self.session.records[0]['accepted'])
        with self.assertRaises(ValueError): self.session.command(dict(action='study_begin', phase='calibration'))

    def test_disconnect_keeps_partial_sensor_trace_and_rejects(self):
        self.begin()
        state = self.session.command(dict(action='study_next'))
        self.session.command(dict(action='presented', id=state['id'], browser_onset_ms=1, browser_send_ms=2))
        self.feed(200)
        self.session.disconnect()
        self.session.command(dict(action='study_finish', id=state['id']))
        data = np.load(self.session.directory/'calibration/trial-01.npz')
        self.assertEqual(len(data['sensor_uv']), 200)
        self.assertFalse(json.loads(str(data['metadata']))['accepted'])
        data.close()

    def test_personal_readout_fit_only_once(self):
        rng = np.random.default_rng(1)
        readout = PersonalReadout()
        features = rng.normal(size=(12, 240))
        labels = np.array([-1, 1]*6)
        readout.fit(features, labels)
        self.assertTrue(np.array_equal(readout.logits(features).argmax(1), (labels+1)//2))
        with self.assertRaises(ValueError): readout.fit(features, labels)


if __name__ == '__main__':
    unittest.main()
