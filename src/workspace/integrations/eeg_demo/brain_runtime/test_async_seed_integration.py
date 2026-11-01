"""Real spawned worker fault tests; no USB device or live service is opened."""

import json
from pathlib import Path
import tempfile
import time
import unittest

import numpy as np

from async_seed_candidate import AsyncSeedShadow, BATCH_SAMPLES
from seed_quality_runtime import CHANNELS


WEIGHTS = (Path(__file__).resolve().parents[1] /
           'eeg_apps_z15/output/board_pipeline_profile_20260926/stage/seed_shadow_weights.npz')
if not WEIGHTS.exists():
    WEIGHTS = Path(__file__).with_name('seed_shadow_weights.npz')


def wait_for_status(path, predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists():
            status = json.loads(path.read_text(encoding='utf-8'))
            if predicate(status):
                return status
        time.sleep(.02)
    raise AssertionError('Expected isolated status was not published')


def wait_for_change(path, previous_mtime, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.stat().st_mtime_ns != previous_mtime:
            return json.loads(path.read_text(encoding='utf-8'))
        time.sleep(.02)
    raise AssertionError('Isolated worker did not update the status')


class SpawnedWorkerFaultTest(unittest.TestCase):
    def test_live_page_pause_keeps_worker_and_resumes_with_fresh_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);page=root/'page.json';status=root/'shadow.json'
            page.write_text(json.dumps(dict(page='video',mode='live_readonly_hdmi',
                physical_output_enabled=False,updated_monotonic=time.monotonic())))
            shadow=AsyncSeedShadow(WEIGHTS,CHANNELS,status_path=status,source='live',page_policy_path=page,
                                   standalone_enabled=True)
            try:
                result=wait_for_status(status,lambda s:(s.get('last_gap') or {}).get('reason')=='page_task_suspended')
                self.assertFalse(result['valid']);self.assertEqual(result['source'],'live')
                for i in range(BATCH_SAMPLES):shadow.packet(np.ones(8),i)
                self.assertFalse(shadow.pending)
                self.assertTrue(shadow.worker.is_alive())
                page.unlink()
                result=wait_for_status(status,lambda s:(s.get('last_gap') or {}).get('reason')=='page_task_resumed')
                self.assertFalse(result['valid'])
                self.assertEqual(result['accepted_windows'],0)
                self.assertTrue(shadow.worker.is_alive())
            finally:shadow.disconnect('test_complete')

    def test_expired_batch_resets_without_prediction(self):
        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / 'shadow.json'
            shadow = AsyncSeedShadow(WEIGHTS, CHANNELS, status_path=status_path)
            try:
                initial_mtime = status_path.stat().st_mtime_ns
                old = time.monotonic() - 2
                for sequence in range(BATCH_SAMPLES):
                    shadow.packet(np.ones(8), sequence, now=old + sequence / 250,
                                  timing_verified=True)
                status = wait_for_change(status_path, initial_mtime)
                self.assertEqual(status['reason'], 'shadow_input_expired')
                self.assertFalse(status['valid'])
                self.assertEqual(status['accepted_windows'], 0)
            finally:
                shadow.disconnect('test_complete')

    def test_dead_worker_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / 'shadow.json'
            shadow = AsyncSeedShadow(WEIGHTS, CHANNELS, status_path=status_path)
            shadow.worker.terminate()
            shadow.worker.join(timeout=2)
            try:
                shadow.idle()
                status = wait_for_status(
                    status_path,
                    lambda s: s.get('reason') == 'isolated_seed_worker_stopped')
                self.assertEqual(status['state'], 'error')
                self.assertFalse(status['valid'])
                with self.assertRaisesRegex(ValueError, 'worker unavailable'):
                    shadow.packet(np.ones(8), 0)
            finally:
                shadow.disconnect('test_complete')


if __name__ == '__main__':
    unittest.main()
