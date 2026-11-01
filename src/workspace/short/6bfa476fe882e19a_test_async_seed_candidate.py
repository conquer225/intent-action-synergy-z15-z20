"""Fail-closed behavior of the isolated SEED worker's bounded input lane."""

import queue
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from async_seed_candidate import AsyncSeedShadow, BATCH_SAMPLES, batch_expired


class AlwaysFull:
    def put_nowait(self, _):
        raise queue.Full


class AliveWorker:
    def is_alive(self):
        return True


class Flag:
    def __init__(self):
        self.value = False

    def set(self):
        self.value = True


class AsyncSeedCandidateTest(unittest.TestCase):
    def test_unknown_source_and_live_audit_are_rejected_before_spawning(self):
        for options in ({'source':'unknown'}, {'source':'live','audit_path':'audit.jsonl'}):
            with self.assertRaisesRegex(ValueError, 'source/audit'):
                AsyncSeedShadow('model.npz', (), status_path='status.json', **options)

    def test_status_keeps_explicit_source_and_invalidates_old_result(self):
        with tempfile.TemporaryDirectory() as directory:
            shadow=AsyncSeedShadow.__new__(AsyncSeedShadow)
            shadow.path=Path(directory)/'status.json'
            for source in ('live','replay'):
                shadow.source=source
                shadow.publish({'state':'no_data','valid':False,'reason':'queue_overflow'})
                result=json.loads(shadow.path.read_text())
                self.assertEqual(result['source'],source)
                self.assertFalse(result['valid'])
                self.assertNotIn('class_id',result)

    def test_disconnect_is_idempotent_and_does_not_join_a_full_feeder(self):
        from unittest.mock import Mock
        shadow=AsyncSeedShadow.__new__(AsyncSeedShadow)
        shadow.closed=False;shadow.pending=[];shadow.failed=False
        shadow.worker=Mock();shadow.worker.is_alive.return_value=False
        shadow.work=Mock();shadow.abort=Mock();shadow.publish=Mock()
        shadow.disconnect('test_stop');shadow.disconnect('test_stop')
        shadow.work.cancel_join_thread.assert_called_once()
        shadow.work.close.assert_called_once()
        shadow.publish.assert_called_once_with({'state':'no_data','valid':False,'reason':'test_stop'})

    def test_expiry_boundary(self):
        self.assertFalse(batch_expired(10.0, 10.5))
        self.assertTrue(batch_expired(10.0, 10.500001))
        for stamp,now in ((11.,10.),(float('nan'),10.),(10.,float('inf'))):
            self.assertTrue(batch_expired(stamp,now))
    def test_full_queue_invalidates_without_waiting_or_silent_drop(self):
        shadow = AsyncSeedShadow.__new__(AsyncSeedShadow)
        shadow.work = AlwaysFull()
        shadow.worker = AliveWorker()
        shadow.abort = Flag()
        shadow.failed = False
        shadow.pending = []
        shadow.lease = None
        sample = np.zeros(8)
        for index in range(BATCH_SAMPLES - 1):
            self.assertEqual(shadow.packet(sample, index, now=index / 250), [])
        with self.assertRaisesRegex(ValueError, 'queue full'):
            shadow.packet(sample, BATCH_SAMPLES - 1, now=(BATCH_SAMPLES - 1) / 250)
        self.assertTrue(shadow.failed)
        self.assertTrue(shadow.abort.value)
        with self.assertRaisesRegex(ValueError, 'worker unavailable'):
            shadow.packet(sample, BATCH_SAMPLES, now=BATCH_SAMPLES / 250)


if __name__ == '__main__':
    unittest.main()
