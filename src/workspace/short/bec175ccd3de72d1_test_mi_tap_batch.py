"""Grouped MI tap keeps the original adapter, clock and inference semantics."""
import multiprocessing
import os
import queue
import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np

from cyton_reader_sink import ReaderPacketSink, decode_eeg_counts
from mi_acquisition import MIAcquisition, MICandidateRuntime, _forward_reader_packets
from mi_features import CHANNELS
from mi_rms_live_virtual import RMSVirtualSession
from test_mi_cued import Clock, Model


class MITapBatchTests(unittest.TestCase):
    def test_group_payload_is_owned_and_short_group_flushes(self):
        sink = ReaderPacketSink(multiprocessing.get_context('spawn'), batch_samples=10)
        try:
            for i in range(3):
                self.assertTrue(sink.offer(bytes((i,)), i, 100+i*.004))
            self.assertTrue(sink.flush())
            sink.offer(b'next', 0, 101.)
            value = sink.pending.get(timeout=2)
            self.assertEqual(value, tuple((i+1, bytes((i,)), i, 100+i*.004) for i in range(3)))
            self.assertEqual(sink.batch, [(4, b'next', 0, 101.)])
        finally:
            sink.close()

    def test_overflow_is_nonblocking_and_ordinal_exposes_whole_group_loss(self):
        sink = ReaderPacketSink(multiprocessing.get_context('spawn'), capacity=10, batch_samples=10)
        try:
            for _ in range(10):
                self.assertTrue(sink.offer(b'first', 0, 100.))
            for i in range(256):
                accepted = sink.offer(b'lost', 0, 100.)
                if (i+1) % 10 == 0:
                    self.assertFalse(accepted)
            self.assertFalse(sink.flush())
            self.assertEqual([v[0] for v in sink.pending.get(timeout=2)], list(range(1,11)))
            sink.offer(b'next', 0, 101.); sink.flush()
            self.assertEqual(sink.pending.get(timeout=2)[0][0], 267)
        finally:
            sink.close()

    def test_forwarder_preserves_gain_time_flags_and_checks_gap_within_group(self):
        pending = queue.Queue()
        pending.put(((1, b'\xa0\x00', 0, 100.), (258, b'\xa0\x01', 3, 100.004)))
        stopped, adapter = threading.Event(), Mock()
        adapter.packet.side_effect = lambda *a, **kw: stopped.set() if a[1] == 1 else None
        values = np.arange(8, dtype=np.int32)
        _forward_reader_packets(pending, adapter, lambda p: values, .022, stopped, 10)
        self.assertEqual(adapter.packet.call_count, 2)
        first, last = adapter.packet.call_args_list
        np.testing.assert_array_equal(first.args[0], values)
        self.assertEqual(last.args[2], 3)
        self.assertEqual(last.kwargs, dict(received_at=100.004, microvolts_per_count=.022))
        adapter.interrupt.assert_called_once_with('mi_reader_queue_gap')

    def test_idle_trial_inference_and_bad_quality_equal_single_packet_adapter(self):
        clock = Clock()
        sessions = [RMSVirtualSession(Model(), source='replay', clock=clock) for _ in range(2)]
        adapters = [MIAcquisition(s) for s in sessions]
        scale = .022
        try:
            for first in range(0, 1700, 50):
                indexes = np.arange(first, first+50)
                gain = 1000 if first < 1450 else 100000
                counts = np.rint(gain*np.sin(2*np.pi*indexes[:,None]/250*np.arange(8,16))).astype(np.int32)
                pending, stopped = queue.Queue(), threading.Event()
                items = []
                for i, values in zip(indexes, counts):
                    packet = bytes((0xa0, int(i)%256))+b''.join(
                        (int(v)&0xffffff).to_bytes(3,'big') for v in values)+bytes(6)+bytes((0xc0,))
                    items.append((int(i)+1, packet, 0, clock()))
                    adapters[0].packet(values, int(i)%256, False, received_at=clock(), microvolts_per_count=scale)
                for offset in range(0,50,10):
                    pending.put(tuple(items[offset:offset+10]))
                original = adapters[1].packet
                def receive(values, sequence, malformed, **kwargs):
                    original(values, sequence, malformed, **kwargs)
                    if sequence == (first+49)%256:
                        stopped.set()
                with patch.object(adapters[1], 'packet', receive):
                    _forward_reader_packets(pending, adapters[1], decode_eeg_counts, scale, stopped, 10)
                for adapter in adapters:
                    adapter.pending.join()
                for name in ('raw', 'filtered', 'band_zi'):
                    np.testing.assert_array_equal(getattr(sessions[0],name), getattr(sessions[1],name))
                self.assertEqual(sessions[0].model.calls, sessions[1].model.calls)
                if first == 700:
                    for session in sessions:
                        trial = session.command(dict(action='start', target='right', virtual_control=True))
                        session.command(dict(action='presented', id=trial['id'], browser_onset_ms=100, browser_send_ms=101))
                states = [s.snapshot() for s in sessions]
                for state in states:
                    state.pop('id')
                    if state['virtual_hand']['last_command']:
                        state['virtual_hand']['last_command'].pop('trial_id')
                self.assertEqual(states[0], states[1])
            self.assertEqual(sessions[1].model.calls, 1)
            self.assertEqual(sessions[1].snapshot()['reason'], 'signal_invalid')
        finally:
            for adapter in adapters:
                adapter.close()

    def test_candidate_rejects_foreign_and_unconnected_modes_before_spawn(self):
        for source, decoder in (('other', decode_eeg_counts), ('replay', None), ('live', None)):
            with patch('mi_acquisition.multiprocessing.get_context', side_effect=AssertionError('spawned')):
                with self.assertRaisesRegex(ValueError, 'reader-backed live or replay'):
                    MICandidateRuntime('unused', CHANNELS, source=source, host='127.0.0.1', port=0,
                        log_path=None, status_paths={}, packet_decoder=decoder, reader_batch_samples=10)

    @unittest.skipUnless(os.name == 'posix', 'Serial reader uses Linux fork')
    def test_short_serial_read_flushes_tap_without_waiting_for_next_read(self):
        from cyton_guardianloop import packets
        r, w = os.pipe()
        frames = [bytes((0xa0,i))+bytes(30)+bytes((0xc0,)) for i in range(2)]
        os.write(w,b''.join(frames))
        sink = ReaderPacketSink(multiprocessing.get_context('spawn'), batch_samples=10)
        reader = packets(r, 1, with_timing=True, packet_sink=sink, reader_batch_samples=10)
        try:
            actual = [next(reader) for _ in frames]
            tapped = sink.pending.get(timeout=1)
            self.assertEqual(tuple((i+1,*v) for i,v in enumerate(actual)), tapped)
        finally:
            reader.close(); sink.close(); os.close(r); os.close(w)


if __name__ == '__main__':
    unittest.main()
