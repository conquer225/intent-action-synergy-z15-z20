"""Private queue contention checks; no real input, PL or actuator output."""
import multiprocessing
import os
import queue
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np


@unittest.skipUnless(os.name == 'posix', 'Private primary worker requires Linux fork')
class PrimaryHandoffTests(unittest.TestCase):
    def test_busy_feeder_accepts_in_order_without_leaking_or_expanding_capacity(self):
        from async_primary import _StagedPrimaryQueue
        pending = _StagedPrimaryQueue(maxsize=32, ctx=multiprocessing.get_context('fork'))
        pending.prepare()
        entered, release = threading.Event(), threading.Event()
        def hold():
            with pending._notempty:
                entered.set()
                release.wait(timeout=2)
        holder = threading.Thread(target=hold)
        holder.start()
        try:
            self.assertTrue(entered.wait(timeout=1))
            before = time.monotonic()
            for index in range(32):
                pending.put_nowait(index)
            for index in range(100):
                with self.assertRaises(queue.Full):
                    pending.put_nowait(32 + index)
            self.assertLess(time.monotonic()-before, .1)
            self.assertEqual(pending._sem.get_value(), 0)
            release.set(); holder.join(timeout=1)
            self.assertEqual([pending.get(timeout=1) for _ in range(32)], list(range(32)))
            self.assertEqual(pending._sem.get_value(), 32)
        finally:
            release.set(); holder.join(timeout=2)
            pending.cancel_join_thread(); pending.close()
        with self.assertRaises(ValueError):
            pending.put_nowait('closed')

    def test_reader_accepts_during_feeder_wait_and_preserves_payload(self):
        from async_primary import AsyncPrimaryWorker
        from test_async_primary import BlockingProcessor, counters
        context = multiprocessing.get_context('fork')
        started, process_release = context.Event(), context.Event()
        process_release.set()
        worker = AsyncPrimaryWorker(BlockingProcessor(started, process_release))
        entered, release = threading.Event(), threading.Event()
        def hold():
            with worker.pending._notempty:
                entered.set(); release.wait(timeout=2)
        holder = threading.Thread(target=hold); holder.start()
        try:
            self.assertTrue(entered.wait(timeout=1))
            raw = np.ones((1, 8))
            before = time.monotonic()
            self.assertTrue(worker.submit(raw, raw, [False], counters(1), before))
            self.assertLess(time.monotonic()-before, .1)
            self.assertIsNone(worker.last_submit_rejection)
            self.assertEqual(worker.stats['handoff_busy'], 0)
            self.assertEqual(worker.stats['queue_full'], 0)
            self.assertEqual(worker.stats['submitted_batches'], 1)
            raw[:] = 99
            release.set(); holder.join(timeout=1)
            replies = []
            deadline = time.monotonic()+2
            while not replies and time.monotonic() < deadline:
                replies = worker.poll()
                time.sleep(.005)
            self.assertEqual(replies[0]['result']['raw'], 1)
            self.assertEqual(replies[0]['epoch'], 0)
        finally:
            release.set(); holder.join(timeout=2); worker.close()
        self.assertFalse(worker.process.is_alive())

    def test_main_full_withdrawal_keeps_explicit_reason_and_calibration(self):
        from test_calibration_main import CalibrationMainTests
        import tempfile
        worker = Mock(calibration_progress=15, calibration_ready=True, identity={}, stats={})
        worker.lag.return_value = 0
        worker.poll.return_value = []
        worker.submit.return_value = False
        worker.last_submit_rejection = 'PRIMARY_WORKER_QUEUE_FULL'
        with tempfile.TemporaryDirectory() as directory, \
                patch('async_primary.AsyncPrimaryWorker', return_value=worker):
            rows = CalibrationMainTests().run_main(directory, 100, async_primary=True)
        withdrawn = [r for r in rows if r.get('reason') == 'PRIMARY_WORKER_QUEUE_FULL']
        self.assertTrue(withdrawn)
        self.assertTrue(all(r['calibration_current'] == 15 and not r['valid'] for r in withdrawn))
        self.assertGreater(worker.invalidate.call_count, 0)

    def test_waiting_old_epoch_is_discarded_before_fresh_payload(self):
        from async_primary import AsyncPrimaryWorker
        from test_async_primary import BlockingProcessor, counters
        context = multiprocessing.get_context('fork')
        started, process_release = context.Event(), context.Event()
        process_release.set()
        worker = AsyncPrimaryWorker(BlockingProcessor(started, process_release))
        entered, release = threading.Event(), threading.Event()
        def hold():
            with worker.pending._notempty:
                entered.set(); release.wait(timeout=2)
        holder = threading.Thread(target=hold); holder.start()
        try:
            self.assertTrue(entered.wait(timeout=1))
            old = np.ones((1, 8))
            self.assertTrue(worker.submit(old, old, [False], counters(1), time.monotonic()))
            worker.invalidate()
            fresh = old * 7
            self.assertTrue(worker.submit(fresh, fresh, [False], counters(2), time.monotonic()))
            release.set(); holder.join(timeout=1)
            replies = []
            deadline = time.monotonic()+2
            while not replies and time.monotonic() < deadline:
                replies = worker.poll()
                time.sleep(.005)
            self.assertEqual(len(replies), 1)
            self.assertEqual(replies[0]['result']['raw'], 7)
            self.assertEqual(replies[0]['epoch'], 1)
            self.assertEqual(worker.calibration_progress, 15)
        finally:
            release.set(); holder.join(timeout=2); worker.close()

    def test_unprepared_offer_and_failed_dispatcher_are_rejected(self):
        from async_primary import _StagedPrimaryQueue
        pending = _StagedPrimaryQueue(maxsize=1, ctx=multiprocessing.get_context('fork'))
        try:
            with self.assertRaisesRegex(RuntimeError, 'not prepared'):
                pending.put_nowait('not prepared')
            self.assertEqual(pending._sem.get_value(), 1)
            pending.prepare()
            pending._dispatch_error = OSError('injected dispatcher failure')
            with self.assertRaisesRegex(RuntimeError, 'dispatcher failed'):
                pending.put_nowait('not accepted')
            self.assertEqual(pending._sem.get_value(), 1)
        finally:
            pending.cancel_join_thread(); pending.close()


if __name__ == '__main__':
    unittest.main()
