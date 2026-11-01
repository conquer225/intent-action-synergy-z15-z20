"""Fault injection via Linux pipes only: never opens Cyton, USB, or PL."""
import errno
import multiprocessing
import os
import time
import threading
import unittest


@unittest.skipUnless(os.name == 'posix', 'Reader requires Linux fork')
class ReaderFaultTests(unittest.TestCase):
    @staticmethod
    def frame(sequence):
        return bytes((0xA0, sequence)) + bytes(30) + bytes((0xC0,))

    def test_eof_has_bounded_diagnostic(self):
        from cyton_guardianloop import CytonReaderError, packets
        r,w = os.pipe()
        os.close(w)
        reader = packets(r,1)
        try:
            with self.assertRaises(CytonReaderError) as caught:
                next(reader)
            self.assertEqual(caught.exception.report['kind'], 'serial_eof')
            self.assertEqual(caught.exception.report['bytes_read'], 0)
        finally:
            reader.close()
            os.close(r)

    def test_eof_drains_accepted_frames_before_failure(self):
        from cyton_guardianloop import CytonReaderError, packets
        r,w = os.pipe()
        os.write(w,b''.join(self.frame(i) for i in range(200)))
        os.close(w)
        reader=packets(r,2)
        try:
            self.assertEqual([next(reader)[0][1] for _ in range(200)],list(range(200)))
            with self.assertRaises(CytonReaderError) as caught:
                next(reader)
            self.assertEqual(caught.exception.report['kind'],'serial_eof')
            self.assertEqual(caught.exception.report['packets_queued'],200)
        finally:
            reader.close()
            os.close(r)

    def test_injected_io_error_reports_errno(self):
        from cyton_guardianloop import CytonReaderError, packets
        r,w = os.pipe()
        def read_error(_fd, _size):
            raise OSError(errno.EIO, 'injected serial read error')
        os.write(w, b'fault')
        reader = packets(r,1,read_chunk=read_error)
        try:
            with self.assertRaises(CytonReaderError) as caught:
                next(reader)
            self.assertEqual(caught.exception.report['kind'], 'serial_io_error')
            self.assertEqual(caught.exception.report['errno'], errno.EIO)
        finally:
            reader.close()
            os.close(r)
            os.close(w)

    def test_queue_overflow_is_not_reported_as_serial_io(self):
        from cyton_guardianloop import CytonReaderError, packets
        r,w = os.pipe()
        os.write(w, b''.join(self.frame(i%256) for i in range(200)))
        reader = packets(r,1,queue_capacity=1)
        try:
            next(reader)
            time.sleep(.1)
            with self.assertRaises(CytonReaderError) as caught:
                for _ in range(200):
                    next(reader)
            self.assertEqual(caught.exception.report['kind'], 'queue_full')
            self.assertGreaterEqual(caught.exception.report['packets_queued'], 1)
        finally:
            reader.close()
            os.close(r)
            os.close(w)

    def test_overflow_error_is_not_hidden_behind_backlogged_feeder(self):
        from cyton_guardianloop import CytonReaderError, packets
        r,w = os.pipe()
        os.write(w, self.frame(0)+self.frame(1))
        reader = packets(r,1,queue_capacity=64)
        try:
            next(reader)
            os.write(w,b''.join(self.frame(i%256) for i in range(2,202)))
            time.sleep(.2)
            started=time.monotonic()
            with self.assertRaises(CytonReaderError) as caught:
                next(reader)
            self.assertEqual(caught.exception.report['kind'],'queue_full')
            self.assertLess(time.monotonic()-started,2)
        finally:
            reader.close();os.close(r);os.close(w)

    def test_unexpected_child_exit_has_distinct_report(self):
        from cyton_guardianloop import CytonReaderError, packets
        r,w = os.pipe()
        os.write(w,b'fault')
        def crash(_fd,_size):
            os._exit(7)
        reader=packets(r,1,read_chunk=crash)
        try:
            with self.assertRaises(CytonReaderError) as caught:
                next(reader)
            self.assertEqual(caught.exception.report,
                             {'kind':'unexpected_exit','exitcode':7})
        finally:
            reader.close()
            os.close(r)
            os.close(w)

    def test_silence_timeout_and_fresh_reader_recovery(self):
        from cyton_guardianloop import packets
        r,w = os.pipe()
        reader = packets(r,.3)
        try:
            with self.assertRaises(TimeoutError):
                next(reader)
        finally:
            reader.close()
            os.close(r)
            os.close(w)
        r,w = os.pipe()
        os.write(w,self.frame(10)+self.frame(11)+self.frame(12))
        recovered = packets(r,1,with_timing=True)
        try:
            self.assertEqual([next(recovered)[0][1] for _ in range(3)], [10,11,12])
        finally:
            recovered.close()
            os.close(r)
            os.close(w)
        self.assertFalse(any(child.name=='cyton-serial-reader'
                             for child in multiprocessing.active_children()))

    def test_wait_keeps_same_reader_through_initial_and_midstream_silence(self):
        from cyton_guardianloop import packets
        r,w = os.pipe()
        idle_times = []
        def writer():
            time.sleep(.4)
            os.write(w, self.frame(10)+self.frame(11))
            time.sleep(.4)
            os.write(w, self.frame(12)+self.frame(13))
        worker = threading.Thread(target=writer)
        reader = packets(r,.1,with_timing=True,on_idle=idle_times.append,wait_for_data=True)
        worker.start()
        try:
            values = [next(reader) for _ in range(4)]
            self.assertEqual([item[0][1] for item in values], [10,11,12,13])
            self.assertGreaterEqual(len(idle_times), 4)
            self.assertGreater(values[2][2]-values[1][2], .3)
            self.assertEqual(sum(child.name=='cyton-serial-reader'
                                 for child in multiprocessing.active_children()), 1)
        finally:
            reader.close();worker.join(2);os.close(r);os.close(w)

    def test_wait_does_not_hide_eof(self):
        from cyton_guardianloop import CytonReaderError, packets
        r,w = os.pipe();os.close(w)
        reader = packets(r,.1,wait_for_data=True)
        try:
            with self.assertRaises(CytonReaderError) as caught:next(reader)
            self.assertEqual(caught.exception.report['kind'], 'serial_eof')
        finally:
            reader.close();os.close(r)

    def test_tap_runs_while_primary_consumer_is_paused(self):
        from cyton_guardianloop import packets
        from mi_acquisition import ReaderPacketSink
        sink = ReaderPacketSink(multiprocessing.get_context('spawn'))
        second_sink = ReaderPacketSink(multiprocessing.get_context('spawn'))
        r,w = os.pipe()
        os.write(w, self.frame(0)+self.frame(1))
        reader = packets(r, 2, with_timing=True, packet_sink=sink, packet_sinks=(second_sink,))
        try:
            first = next(reader)
            os.write(w, b''.join(self.frame(i) for i in range(2, 52)))
            time.sleep(.3)  # No next(reader): emulate a blocked primary model.
            tapped = [sink.pending.get(timeout=2) for _ in range(52)]
            self.assertEqual([second_sink.pending.get(timeout=2) for _ in range(52)],tapped)
            self.assertEqual([item[0] for item in tapped], list(range(1, 53)))
            self.assertEqual([item[1][1] for item in tapped], list(range(52)))
            self.assertEqual(tapped[0][3], first[2])
            self.assertEqual([next(reader)[0][1] for _ in range(51)], list(range(1,52)))
        finally:
            reader.close(); sink.close(); second_sink.close(); os.close(r); os.close(w)

    def test_full_tap_does_not_break_primary_reader(self):
        from cyton_guardianloop import packets
        from mi_acquisition import ReaderPacketSink
        sink = ReaderPacketSink(multiprocessing.get_context('spawn'), capacity=1)
        r,w = os.pipe()
        os.write(w, b''.join(self.frame(i) for i in range(52)))
        reader = packets(r, 2, packet_sink=sink)
        try:
            self.assertEqual([next(reader)[0][1] for _ in range(52)], list(range(52)))
            self.assertEqual(sink.pending.get(timeout=2)[0], 1)
        finally:
            reader.close(); sink.close(); os.close(r); os.close(w)


if __name__ == '__main__':
    unittest.main()
