"""Process transport parity, overload, stale epochs and shutdown contracts."""
import json
from pathlib import Path
import queue
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from ssvep_async import AsyncSSVEPShadow
from ssvep_shadow import CHANNELS, SSVEPShadow

HERE = Path(__file__).resolve().parent
CONFIG = HERE/'ssvep_causal_protocol.json'
SOS = HERE/'ssvep_candidate_sos.npy'
if not CONFIG.exists():
    CONFIG = HERE.parent/'eeg_apps_z15/ssvep_causal_protocol.json'
    SOS = HERE.parent/'eeg_apps_z15/output/ssvep_causal_20260926/candidate_sos.npy'


class AsyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'async.json'
        self.shadow = AsyncSSVEPShadow(CONFIG, SOS, CHANNELS, source='replay', status_path=self.path)
        self.assertTrue(self.shadow.ready.wait(20))
        self.assertTrue(self.shadow.worker.is_alive())

    def tearDown(self):
        self.shadow.disconnect()
        self.assertFalse(self.shadow.worker.is_alive())
        self.temp.cleanup()

    def wait_processed(self, count):
        deadline = time.monotonic()+10
        while self.shadow.counts[0] < count and time.monotonic() < deadline:
            self.shadow.poll()
            time.sleep(.005)
        self.assertEqual(self.shadow.counts[0], count)
        time.sleep(.03)
        self.shadow.poll()

    def test_transport_numeric_parity_and_warmup_after_gap(self):
        reference = SSVEPShadow(CONFIG, SOS, CHANNELS, source='replay',
                                 status_path=Path(self.temp.name)/'sync.json')
        for i in range(760):
            row = np.zeros(8)
            row[6] = 20*np.sin(2*np.pi*10*i/250)
            row[7] = 18*np.sin(2*np.pi*10*i/250+.3)+np.sin(i*.7)
            reference.packet(row, i%256, now=i/250)
            self.shadow.packet(row, i%256, now=i/250)
            if i%10 == 9:
                self.wait_processed(i+1)
        result = self.shadow.latest
        self.assertEqual(result['state'], 'candidate_only')
        self.assertEqual(result['frequency_hz'], reference.latest['frequency_hz'])
        np.testing.assert_allclose(result['scores'], reference.latest['scores'], atol=1e-12)
        self.assertEqual(self.shadow.skipped, 0)
        epoch = self.shadow.epoch.value
        self.shadow.packet(row, 15, now=4.)
        self.assertGreater(self.shadow.epoch.value, epoch)
        self.assertEqual(self.shadow.latest['state'], 'warmup')
        self.assertIsNone(self.shadow.latest['frequency_hz'])

    def test_overflow_nonblocking_and_late_results_rejected(self):
        start = time.monotonic()
        with patch.object(self.shadow.pending, 'put_nowait', side_effect=queue.Full):
            for i in range(10):
                self.shadow.packet(np.zeros(8), i, now=i/250)
        self.assertLess(time.monotonic()-start, .5)
        self.assertEqual(self.shadow.skipped, 10)
        self.assertEqual(self.shadow.epoch.value, 1)
        self.shadow.results.put((0, dict(state='candidate_only', frequency_hz=10)))
        time.sleep(.05)
        self.shadow.poll()
        self.assertEqual(self.shadow.latest['state'], 'warmup')
        self.assertEqual(self.shadow.rejected_results, 1)

    def test_timeout_death_and_shutdown_clear_candidate(self):
        self.shadow.packet(np.zeros(8), 0, now=0.)
        self.shadow.idle(now=1.)
        self.assertEqual(self.shadow.latest['state'], 'no_data')
        self.shadow.worker.terminate()
        self.shadow.worker.join(2)
        self.shadow.packet(np.zeros(8), 1, now=1.)
        self.assertEqual(self.shadow.latest['state'], 'error')
        self.shadow.disconnect()
        status = json.loads(self.path.read_text())
        self.assertFalse(status['control_enabled'])
        self.assertIsNone(status['frequency_hz'])
        self.assertEqual(status['state'], 'no_data')

    def test_old_live_result_does_not_refresh_timestamp(self):
        self.shadow.source = 'live'
        initial_stamp = self.shadow.latest['updated_monotonic']
        self.shadow.results.put((0, dict(state='candidate_only', valid=True,
            frequency_hz=10, updated_monotonic=time.monotonic()-1, input_age_seconds=0.)))
        time.sleep(.05)
        self.shadow.poll()
        self.assertEqual(self.shadow.rejected_results, 1)
        self.assertEqual(self.shadow.latest['updated_monotonic'], initial_stamp)
        self.assertIsNone(self.shadow.latest['frequency_hz'])


if __name__ == '__main__':
    unittest.main()
