"""Private IPC candidate: Linux pipes only, no USB or hardware access."""
import os
import time
import unittest
from unittest.mock import patch

from test_cyton_reader_faults import ReaderFaultTests


@unittest.skipUnless(os.name == 'posix', 'Reader requires Linux fork')
class BatchedReaderFaultTests(ReaderFaultTests):
    def setUp(self):
        import cyton_guardianloop as live
        original = live.packets

        def batched(*args, **kwargs):
            # The inherited one-slot overflow test needs room for one batch.
            kwargs['queue_capacity'] = max(10, kwargs.get('queue_capacity', 8192))
            return original(*args, **kwargs, reader_batch_samples=10)

        wrapper = patch.object(live, 'packets', batched)
        wrapper.start()
        self.addCleanup(wrapper.stop)

    def test_short_read_flushes_without_waiting_for_ten_samples(self):
        from cyton_guardianloop import packets
        r, w = os.pipe()
        os.write(w, self.frame(41)+self.frame(42))
        reader = packets(r, 1, with_timing=True)
        try:
            started = time.monotonic()
            first, second = next(reader), next(reader)
            self.assertLess(time.monotonic()-started, .5)
            self.assertEqual([first[0][1], second[0][1]], [41, 42])
            self.assertEqual(first[2], second[2])
        finally:
            reader.close(); os.close(r); os.close(w)

    def test_short_serial_reads_do_not_shrink_candidate_packet_capacity(self):
        import multiprocessing
        from cyton_guardianloop import packets, CytonReaderError
        from cyton_reader_sink import ReaderPacketSink
        sink = ReaderPacketSink(multiprocessing.get_context('spawn'), capacity=128, batch_samples=10)
        r, w = os.pipe()
        frames = [self.frame(i) for i in range(80)]
        os.write(w, b''.join(frames)); os.close(w)
        reader = packets(r, 2, packet_sinks=(sink,), read_chunk=lambda fd, size: os.read(fd, min(size, 66)))
        try:
            self.assertEqual([next(reader)[0] for _ in frames], frames)
            with self.assertRaises(CytonReaderError):
                next(reader)
            rows = []
            while len(rows) < len(frames):
                rows.extend(sink.pending.get(timeout=.5))
            self.assertEqual([row[0] for row in rows], list(range(1, 81)))
            self.assertEqual([row[1] for row in rows], frames)
        finally:
            reader.close(); sink.close(); os.close(r)

    def test_partial_candidate_batch_is_flushed_on_idle_and_eof(self):
        import multiprocessing
        from cyton_guardianloop import packets, CytonReaderError
        from cyton_reader_sink import ReaderPacketSink
        for eof in (False, True):
            sink = ReaderPacketSink(multiprocessing.get_context('spawn'), batch_samples=10)
            r, w = os.pipe()
            os.write(w, self.frame(41)+self.frame(42))
            if eof:
                os.close(w)
            reader = packets(r, 1, packet_sinks=(sink,))
            try:
                next(reader); next(reader)
                if eof:
                    with self.assertRaises(CytonReaderError):
                        next(reader)
                rows = sink.pending.get(timeout=.2)
                self.assertEqual([row[0] for row in rows], [1, 2])
                self.assertEqual([row[1][1] for row in rows], [41, 42])
            finally:
                reader.close(); sink.close(); os.close(r)
                if not eof:
                    os.close(w)

    def test_queue_overflow_is_not_reported_as_serial_io(self):
        from cyton_guardianloop import CytonReaderError, packets
        r, w = os.pipe()
        os.write(w, b''.join(self.frame(i) for i in range(200)))
        reader = packets(r, 1, queue_capacity=10)
        try:
            with self.assertRaises(CytonReaderError) as caught:
                # A terminal fault may precede even the first buffered packet.
                next(reader)
                time.sleep(.1)
                for _ in range(200):
                    next(reader)
            self.assertEqual(caught.exception.report['kind'], 'queue_full')
            self.assertGreaterEqual(caught.exception.report['packets_queued'], 10)
        finally:
            reader.close(); os.close(r); os.close(w)

    def test_terminal_failure_interrupts_an_already_unpacked_batch(self):
        from cyton_guardianloop import CytonReaderError, packets
        r, w = os.pipe()
        os.write(w, b''.join(self.frame(i) for i in range(10)))
        reader = packets(r, 1, queue_capacity=10)
        try:
            self.assertEqual(next(reader)[0][1], 0)
            os.write(w, b''.join(self.frame(i % 256) for i in range(10, 210)))
            time.sleep(.2)
            with self.assertRaises(CytonReaderError) as caught:
                next(reader)
            self.assertEqual(caught.exception.report['kind'], 'queue_full')
        finally:
            reader.close(); os.close(r); os.close(w)

    def test_packet_flags_and_timestamp_are_not_rewritten(self):
        from cyton_guardianloop import CytonReaderError, packets
        r, w = os.pipe()
        frames = [self.frame(i % 256) for i in range(203)]
        os.write(w, b'bad'+b''.join(frames[:13])+b'noise'+b''.join(frames[13:]))
        os.close(w)
        reader = packets(r, 2, with_timing=True)
        try:
            rows = [next(reader) for _ in frames]
            self.assertEqual([row[0] for row in rows], frames)
            self.assertEqual(rows[0][1], 3)
            self.assertEqual(rows[13][1], 5)
            self.assertEqual(sum(row[1] for row in rows), 8)
            self.assertTrue(all(a[2] <= b[2] for a, b in zip(rows, rows[1:])))
            with self.assertRaises(CytonReaderError) as caught:
                next(reader)
            report = caught.exception.report
            self.assertEqual(report['packets_queued'], 203)
            self.assertLessEqual(report['queue_dispatches'], 22)
        finally:
            reader.close(); os.close(r)

    def test_cli_cannot_enable_batching_on_a_live_port(self):
        import sys
        import cyton_guardianloop as live
        for flags in ([], ['--isolated-primary-worker'],
                      ['--port', '/dev/null']):
            with patch.object(sys, 'argv', ['test', '--isolated-reader-batch', *flags]):
                with patch.object(live.os, 'open', side_effect=AssertionError('hardware opened')):
                    with self.assertRaises(SystemExit) as caught:
                        live.main()
            self.assertEqual(caught.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
