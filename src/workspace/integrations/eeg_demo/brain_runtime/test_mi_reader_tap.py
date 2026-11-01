"""Reader fan-out tests; no electrodes or serial device are opened."""
import multiprocessing
import queue
import threading
import unittest
from unittest.mock import Mock

import numpy as np

from mi_acquisition import MIAcquisition, ReaderPacketSink, _forward_reader_packets
from mi_cued import CuedMISession
import test_mi_cued as fixture


class ReaderTapTests(unittest.TestCase):
    def test_full_tap_drops_without_blocking_and_keeps_loss_ordinal(self):
        sink = ReaderPacketSink(multiprocessing.get_context('spawn'), capacity=1)
        try:
            self.assertTrue(sink.offer(b'first', 0, 1.))
            for _ in range(256):
                self.assertFalse(sink.offer(b'dropped', 0, 1.))
            self.assertEqual(sink.pending.get(timeout=2), (1, b'first', 0, 1.))
            self.assertTrue(sink.offer(b'next', 0, 2.))
            self.assertEqual(sink.pending.get(timeout=2), (258, b'next', 0, 2.))
        finally:
            sink.close()

    def test_forwarder_preserves_receive_time_counts_and_gain(self):
        pending = queue.Queue()
        pending.put((1, b'\xa0\x00', 0, 100.))
        pending.put((258, b'\xa0\x01', 0, 100.004))
        stopped = threading.Event()
        adapter = Mock()
        adapter.packet.side_effect = lambda *a, **kw: stopped.set() if a[1] == 1 else None
        values = np.arange(8, dtype=np.int32)
        _forward_reader_packets(pending, adapter, lambda _: values, .022, stopped)
        self.assertEqual(adapter.packet.call_count, 2)
        first, second = adapter.packet.call_args_list
        np.testing.assert_array_equal(first.args[0], values)
        self.assertEqual(first.kwargs, dict(received_at=100., microvolts_per_count=.022))
        self.assertEqual(second.kwargs['received_at'], 100.004)
        adapter.interrupt.assert_called_once_with('mi_reader_queue_gap')

    def test_filter_values_equal_original_adapter(self):
        clock = fixture.Clock()
        session = CuedMISession(fixture.Model(), source='replay', clock=clock)
        reference = CuedMISession(fixture.Model(), source='replay', clock=clock)
        adapter = MIAcquisition(session)
        pending = queue.Queue()
        stopped = threading.Event()
        counts = np.rint(1000 * np.sin(np.arange(50)[:, None] * np.arange(8, 16) / 250)).astype(np.int32)
        for i in range(50):
            pending.put((i+1, bytes((0xa0, i)), 0, clock()))
        original = adapter.packet
        def receive(values, seq, malformed, **kw):
            original(values, seq, malformed, **kw)
            if seq == 49:
                stopped.set()
        adapter.packet = receive
        try:
            _forward_reader_packets(pending, adapter, lambda p: counts[p[1]], .022, stopped)
            adapter.pending.join()
            reference.feed(counts.astype(np.float64)*.022, np.arange(50), received_monotonic=clock())
            np.testing.assert_array_equal(session.raw, reference.raw)
            np.testing.assert_array_equal(session.filtered, reference.filtered)
        finally:
            adapter.close()

    def test_decoder_error_withdraws_and_stops_forwarder(self):
        pending = queue.Queue()
        pending.put((1, b'bad', 0, 100.))
        adapter = Mock()
        def decoder(_packet):
            raise ValueError('invalid fixture packet')
        _forward_reader_packets(pending, adapter, decoder, 1., threading.Event())
        self.assertIn('invalid fixture packet', adapter.error)
        adapter.interrupt.assert_called_once_with('mi_reader_tap_error')
        adapter.packet.assert_not_called()


if __name__ == '__main__':
    unittest.main()
