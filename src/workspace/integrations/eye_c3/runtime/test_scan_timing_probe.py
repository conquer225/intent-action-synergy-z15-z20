"""Scan sampling tests use a fake clock and never import PYNQ."""
import unittest
from scan_timing_probe import counter_delta, measure


class Clock:
    def __init__(self):
        self.now = 0.

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Display:
    def __init__(self, clock):
        self.clock = clock
        self.hz = 60
        self.status = 0

    def display_frames(self):
        return int(self.clock.now * self.hz)

    def display_status(self):
        return self.status


class ScanTests(unittest.TestCase):
    def test_visible_preview_needs_its_own_explicit_consent(self):
        from scan_timing_probe import visible_preview
        for consent in (None, False, 1, 'true'):
            with self.assertRaises(ValueError):
                visible_preview(dict(probe_mode='visible_display_only', seconds=10,
                                     visible_flicker_consent=consent))
        self.assertTrue(visible_preview(dict(probe_mode='visible_display_only', seconds=10,
                                            visible_flicker_consent=True)))

    def test_visible_preview_is_exactly_ten_seconds(self):
        from scan_timing_probe import visible_preview
        for seconds in (5, 9, 11, 45):
            with self.assertRaises(ValueError):
                visible_preview(dict(probe_mode='visible_display_only', seconds=seconds,
                                     visible_flicker_consent=True))

    def test_existing_diagnostics_remain_nonflashing(self):
        from scan_timing_probe import visible_preview
        for mode in ('static', 'dynamic_nonflashing', 'integrated_nonflashing'):
            self.assertFalse(visible_preview(dict(probe_mode=mode, seconds=30,
                                                 visible_flicker_consent=True)))

    def test_runtime_revocation_stops_before_touching_scan_counter_again(self):
        clock=Clock();display=Display(clock);calls=[]
        def revoked():
            calls.append(clock.now)
            raise RuntimeError('Runtime admission revoked')
        with self.assertRaisesRegex(RuntimeError,'revoked'):
            measure(display,1,clock.monotonic,clock.sleep,require=revoked)
        self.assertEqual(calls,[.001])

    def test_unsigned_wrap(self):
        self.assertEqual(counter_delta(2, 0xfffffffe), 4)

    def test_static_scan_is_not_new_video_frames(self):
        clock = Clock()
        result = measure(Display(clock), 1, clock.monotonic, clock.sleep)
        self.assertAlmostEqual(result["scan_hz"], 60, delta=1)
        self.assertEqual(result["unobserved_individual_increments"], 0)
        self.assertTrue(result["single_increment_intervals_ms"])

    def test_coarse_polling_does_not_lose_counter_total(self):
        clock = Clock()
        def delayed_sleep(_):
            clock.sleep(.04)
        result = measure(Display(clock), 1, clock.monotonic, delayed_sleep)
        self.assertAlmostEqual(result["scan_hz"], 60, delta=1)
        self.assertGreater(result["unobserved_individual_increments"], 0)
        self.assertGreater(result["max_poll_gap_ms"], 39)

    def test_stall_rejected(self):
        clock = Clock()
        display = Display(clock)
        display.hz = 0
        with self.assertRaisesRegex(RuntimeError, "stalled"):
            measure(display, 1, clock.monotonic, clock.sleep)

    def test_fault_rejected(self):
        clock = Clock()
        display = Display(clock)
        display.status = 1
        with self.assertRaisesRegex(RuntimeError, "fault/halt"):
            measure(display, 1, clock.monotonic, clock.sleep)


class DynamicTests(unittest.TestCase):
    def test_late_receipt_is_retained_in_diagnostic_report(self):
        from test_hdmi_stimulus import FakeLibrary
        from unittest.mock import Mock
        from scan_timing_probe import measure_dynamic
        from ssvep_hdmi import SCAN_PERIOD
        class LateDisplay(FakeLibrary):
            def display_park(self, index):
                result=super().display_park(index)
                if self.counter==3:self.now+=SCAN_PERIOD
                return result
        lib=LateDisplay()
        result=measure_dynamic(lib,Mock(),[None]*3,1.,clock=lambda:lib.now)
        self.assertFalse(result['completed'])
        self.assertEqual(result['verified_single_scan_latches'],1)
        self.assertEqual(result['rejected_latch']['counter_after'],3)
        gap=result['rejected_latch']['ack_monotonic']-result['latches'][-1]['ack_monotonic']
        self.assertGreater(gap,1.5*SCAN_PERIOD)

    def test_diagnostic_trace_wraps_park_and_copy_without_changing_count(self):
        from test_hdmi_stimulus import FakeLibrary
        from unittest.mock import Mock
        from scan_timing_probe import measure_dynamic
        lib=FakeLibrary();trace=Mock()
        trace.end.return_value={'calls':1,'cpu_ns':10}
        result=measure_dynamic(lib,Mock(),[None]*3,.1,clock=lambda:lib.now,trace=trace)
        self.assertTrue(result['completed'])
        rows=result['diagnostic_stages']
        self.assertEqual(len(rows),len(result['copy_and_flush_ms'])+len(result['park_ack_ms']))
        self.assertEqual(trace.begin.call_count,trace.end.call_count)
        self.assertTrue(all(row['sleep']['cpu_ns']==10 for row in rows))

    def test_same_scan_pump_and_constant_brightness_can_run_without_hardware(self):
        from test_hdmi_stimulus import FakeLibrary
        from unittest.mock import Mock
        from scan_timing_probe import measure_dynamic
        lib=FakeLibrary();frames=Mock()
        result=measure_dynamic(lib,frames,[None]*3,1.,clock=lambda:lib.now)
        self.assertTrue(result['completed']);self.assertIsNone(result['error'])
        self.assertGreaterEqual(result['verified_single_scan_latches'],60)
        self.assertFalse(result['visible_stimulus_tested'])
        self.assertEqual(frames.paint.call_count,result['verified_single_scan_latches']+3)

    def test_dynamic_bad_latch_is_recorded_as_failure_not_success(self):
        from test_hdmi_stimulus import FakeLibrary
        from unittest.mock import Mock
        from scan_timing_probe import measure_dynamic
        lib=FakeLibrary();lib.latch=False
        result=measure_dynamic(lib,Mock(),[None]*3,1.,clock=lambda:lib.now)
        self.assertFalse(result['completed']);self.assertIn('latch',result['error'])
        self.assertEqual(result['verified_single_scan_latches'],0)

    def test_every_logical_phase_is_pixel_identical_in_nonflashing_mode(self):
        import os
        from pathlib import Path
        import numpy as np
        from scan_timing_probe import fixed_brightness
        from hdmi_stimulus import StimulusFrames
        from system_hdmi import UnifiedDisplay
        from test_hdmi_stimulus import Buffer
        root=os.environ.get('GL_TEST_EYE_ROOT',str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye'))
        frames=fixed_brightness(StimulusFrames(UnifiedDisplay(root,live=True)))
        buffers=[np.empty((720,1280,3),dtype=np.uint8).view(Buffer) for _ in range(3)]
        for index,b in enumerate(buffers):frames.paint(b,index,0)
        expected=buffers[0].copy()
        for mask in range(16):
            for index,b in enumerate(buffers):
                frames.paint(b,index,mask)
                np.testing.assert_array_equal(b,expected)


if __name__ == "__main__":
    unittest.main()
