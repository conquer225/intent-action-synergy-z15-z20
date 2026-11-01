"""Fake display library only; these tests cannot touch FPGA registers."""
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from hdmi_stimulus import HdmiStimulus, ScanPump, StimulusFrames
from ssvep_hdmi import SCAN_PERIOD, ScanEvidence, pattern
from system_hdmi import ACCENT, FREQUENCY_BOXES, UnifiedDisplay
from guardianloop_system.core import SystemController
from ssvep_hdmi import POLICY


class FakeLibrary:
    def __init__(self):
        self.now=100.;self.counter=0;self.index=0;self.fault=0;self.jump=1;self.latch=True
    def display_frames(self):return self.counter
    def display_index(self):return self.index
    def display_status(self):return self.fault
    def display_park(self,index):
        self.counter=(self.counter+self.jump)&0xffffffff;self.now+=SCAN_PERIOD*self.jump
        if self.latch:self.index=index
        return 1


class Buffer(np.ndarray):
    def __array_finalize__(self, source):
        self.flushes = getattr(source, 'flushes', None)
        self.root_address = getattr(source, 'root_address', None)
    def flush(self):
        if self.flushes is not None:
            row = (self.ctypes.data-self.root_address)//(1280*3)
            self.flushes.append((row, row+self.shape[0], self.flags.c_contiguous))


class PumpTests(unittest.TestCase):
    def make(self):
        lib=FakeLibrary();frames=[]
        pump=ScanPump(lib,lambda index,mask:frames.append((index,mask)),clock=lambda:lib.now)
        return lib,frames,pump

    def test_each_new_pattern_is_latched_on_its_expected_scan(self):
        lib,frames,pump=self.make();origin=pump.begin()
        track=ScanEvidence(origin['origin_counter'],origin['presented_monotonic'],origin['active_index'])
        for _ in range(144):
            row=pump.step();track.observe([row],lib.now)
        self.assertTrue(track.snapshot(lib.now)['ready'])
        self.assertEqual([mask for _,mask in frames],[pattern(n) for n in range(147)])

    def test_dma_fault_skipped_scan_wrong_latch_and_missed_copy_fail_closed(self):
        for case in ('fault','jump','latch','copy','deadline'):
            with self.subTest(case=case):
                lib,_,pump=self.make();pump.begin()
                if case=='fault':lib.fault=1
                elif case=='jump':lib.jump=2
                elif case=='latch':lib.latch=False
                elif case=='copy':pump.paint=lambda *_:setattr(lib,'counter',lib.counter+1)
                else:lib.counter+=1
                with self.assertRaises(ValueError):pump.step()

    def test_counter_wrap_is_a_single_new_scan(self):
        lib,_,pump=self.make();lib.counter=0xfffffffe
        pump.begin();row=pump.step()
        self.assertEqual(row['counter_after'],0)
        self.assertEqual(row['pattern_mask'],pattern(1))

    def test_future_frames_ready_before_park_and_active_buffer_never_written(self):
        lib=FakeLibrary();ready={};park=lib.display_park
        def paint(index,mask):
            self.assertNotEqual(index,lib.index)
            ready[index]=mask
        def checked_park(index):
            self.assertIn(index,ready)
            ready.pop(index)
            return park(index)
        lib.display_park=checked_park
        pump=ScanPump(lib,paint,clock=lambda:lib.now)
        pump.begin()
        self.assertEqual(len(ready),2)
        for _ in range(10):
            pump.step()
            self.assertEqual(len(ready),2)
            self.assertNotIn(lib.index,ready)

    def test_missing_prepared_frame_and_changed_owner_fail_before_submission(self):
        for case in ('missing','owner'):
            lib,_,pump=self.make();pump.begin()
            if case=='missing':pump.prepared.clear()
            else:lib.index=(lib.index+1)%3
            park=Mock(wraps=lib.display_park);lib.display_park=park
            with self.assertRaises(ValueError):pump.step()
            park.assert_not_called()

    def test_ack_timestamp_is_captured_before_future_copy(self):
        lib,_,pump=self.make();pump.begin()
        pump.paint=lambda *_:setattr(lib,'now',lib.now+.003)
        row=pump.step()
        self.assertAlmostEqual(lib.now-row['ack_monotonic'],.003)


class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=os.environ.get('GL_TEST_EYE_ROOT',str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye'))
        cls.display=UnifiedDisplay(root,live=True,dimensions=(288,512))
        cls.frames=StimulusFrames(cls.display)

    def test_only_corners_change_and_all_start_with_the_same_colour(self):
        before=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        self.frames.keys.clear();self.frames.paint(before,0,15)
        points=[before[box[1]+30,box[0]+30].copy() for _,_,box in FREQUENCY_BOXES]
        for point in points[1:]:np.testing.assert_array_equal(point,points[0])
        after=before.copy().view(Buffer);self.frames.paint(after,0,0,12)
        outside=np.ones((720,1280),dtype=bool)
        for _,_,box in FREQUENCY_BOXES:outside[box[1]:box[3]+1,box[0]:box[2]+1]=False
        np.testing.assert_array_equal(before[outside],after[outside])
        for hz,_,box in FREQUENCY_BOXES:
            pixel=after[box[1]+1,(box[0]+box[2])//2]
            self.assertEqual(bool(np.array_equal(pixel,ACCENT[::-1])),hz==12)

    def test_patch_memory_is_bounded_and_not_full_frame_bank(self):
        self.assertLess(sum(x.nbytes for x in self.frames.patches.values()),4*1024**2)

    def test_flushes_only_changed_contiguous_row_bands(self):
        buffer=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        buffer.flushes=[];buffer.root_address=buffer.ctypes.data
        self.frames.keys.clear()
        self.frames.paint(buffer,0,15)
        self.assertEqual(buffer.flushes,[(0,720,True)])
        upper=(FREQUENCY_BOXES[0][2][1],FREQUENCY_BOXES[0][2][3]+1,True)
        lower=(FREQUENCY_BOXES[2][2][1],FREQUENCY_BOXES[2][2][3]+1,True)
        for mask,expected in ((15,[]),(14,[upper]),(10,[lower]),(0,[upper,lower])):
            buffer.flushes.clear()
            sizes=self.frames.paint(buffer,0,mask)
            self.assertEqual(buffer.flushes,expected)
            self.assertEqual(sizes['flushed_bytes'],sum((end-start)*1280*3 for start,end,_ in expected))
        buffer.flushes.clear()
        self.frames.paint(buffer,0,0,12)
        self.assertEqual(buffer.flushes,[lower])

    def test_failed_flush_does_not_commit_the_buffer_cache_key(self):
        buffer=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        self.frames.keys.clear();self.frames.paint(buffer,0,15)
        key=self.frames.keys[0]
        with patch.object(Buffer,'flush',side_effect=RuntimeError('flush failed')):
            with self.assertRaises(RuntimeError):self.frames.paint(buffer,0,0)
        self.assertEqual(self.frames.keys[0],key)

    def test_no_consent_or_wrong_page_never_touches_the_library(self):
        bridge=Mock();lib=Mock();self.display.controller._enter('drive',100.)
        lane=HdmiStimulus(lib,[],self.display,bridge)
        with self.assertRaises(ValueError):lane.start(self.display.controller.page_id,consent=False)
        with self.assertRaises(ValueError):lane.start(self.display.controller.page_id-1,consent=True)
        bridge.hdmi_command.assert_not_called();lib.display_park.assert_not_called()
        self.assertFalse(lane.snapshot()['active'])

    def test_old_page_cannot_read_current_native_session(self):
        lane=HdmiStimulus(Mock(),[],self.display,Mock(),clock=lambda:100.)
        lane.active=True;lane.ended=threading.Event();lane.page_id=8;lane.session_id='native'
        lane.row=({'id':'native'},100.,.01,None)
        self.assertIsNone(lane.input(7,100.));self.assertIsNotNone(lane.input(8,100.))
        self.assertIsNone(lane.input(8,100.36));lane.ended.set()
        self.assertIsNone(lane.input(8,100.))

    def test_future_and_nonfinite_response_times_fail_closed(self):
        lane=HdmiStimulus(Mock(),[],self.display,Mock(),clock=lambda:100.)
        lane.active=True;lane.ended=threading.Event();lane.page_id=8
        for stamp in (100.1,float('nan'),float('inf')):
            lane.row=({},stamp,.01,None)
            self.assertIsNone(lane.input(8,100.))

    def test_changed_vtc_mode_cannot_start_even_with_consent(self):
        self.display.controller._enter('drive',100.)
        bridge=Mock();lib=Mock();lib.Xil_In32.return_value=0
        lane=HdmiStimulus(lib,[],self.display,bridge)
        with self.assertRaisesRegex(ValueError,'configuration'):
            lane.start(self.display.controller.page_id,consent=True)
        bridge.hdmi_command.assert_not_called();lib.display_park.assert_not_called()


class ThreadTests(unittest.TestCase):
    def setUp(self):
        priority=patch('hdmi_stimulus.ordinary_control_thread')
        priority.start();self.addCleanup(priority.stop)
        self.controller=SystemController(time.monotonic())
        self.controller._enter('drive',time.monotonic())
        self.display=SimpleNamespace(controller=self.controller,buffer_pages={0:'drive'},feedback=lambda _:())
        self.lib=Mock()
        registers={0x43c10060:(720<<16)|1280,0x43c10070:1650,0x43c10074:750}
        self.lib.Xil_In32.side_effect=registers.__getitem__
        self.bridge=Mock();self.bridge.hdmi_command.side_effect=self.response
        self.frames_patch=patch('hdmi_stimulus.StimulusFrames')
        self.frames_patch.start();self.addCleanup(self.frames_patch.stop)
        self.steps=threading.Event()
        self.steps.set()
        self.pump=Mock()
        self.pump.begin.side_effect=lambda:dict(origin_counter=1,active_index=1,presented_monotonic=time.monotonic())
        self.pump.read.side_effect=self.step
        self.pump.close.return_value=None
        self.lane=HdmiStimulus(self.lib,[],self.display,self.bridge,scan_factory=lambda *_:self.pump)
        self.addCleanup(self.lane.close)

    def response(self,command):
        return dict(id='native',policy=POLICY,display_page_id=self.controller.page_id,
                    state='awaiting_presentation' if command['action']=='start' else 'active',
                    display_timing={'ready':True})

    def step(self):
        if not self.steps.wait(.1):raise ValueError('fake scan stopped')
        time.sleep(.002)
        return [{'ack_monotonic':time.monotonic()}]

    def wait_for(self,predicate):
        end=time.monotonic()+1.
        while not predicate() and time.monotonic()<end:time.sleep(.001)
        self.assertTrue(predicate())

    def start(self):self.lane.start(self.controller.page_id,consent=True)

    def test_native_starts_before_sender_is_pinned_to_cpu_zero(self):
        pinned=threading.Event()
        def begin():
            if pinned.is_set():raise ValueError('Native cannot inherit CPU1')
            return dict(origin_counter=1,active_index=1,presented_monotonic=time.monotonic())
        self.pump.begin.side_effect=begin
        with patch('hdmi_stimulus.ordinary_control_thread',side_effect=pinned.set):
            self.start();self.wait_for(lambda:self.lane.row is not None)
        self.assertTrue(pinned.is_set());self.assertIsNone(self.lane.error)

    def test_entry_without_eeg_starts_display_without_querying_or_fabricating_eeg(self):
        self.controller.direction_idle_enabled=False
        now=time.monotonic();self.controller.presented(self.controller.page_id,now)
        now+=self.controller.read_seconds+.1
        self.pump.read.side_effect=lambda:(time.sleep(.01) or [])
        self.lane.start_on_entry(self.controller,now,enabled=True,input_ready=False)
        self.wait_for(lambda:self.lane.report_stats['count']>0)
        self.assertTrue(self.lane.active);self.assertTrue(self.lane.display_only)
        self.bridge.hdmi_command.assert_not_called()
        self.assertIsNone(self.lane.input(self.controller.page_id,time.monotonic()))
        self.assertIsNone(self.lane.snapshot()['votes']['selected_hz'])
        self.lane.service(self.controller,time.monotonic())
        self.controller.force_stop(now+.1);self.lane.service(self.controller,now+.1)
        self.assertFalse(self.lane.active);self.bridge.hdmi_command.assert_not_called()

    def test_entry_waits_for_presentation_and_starts_only_once_per_page(self):
        start=Mock();self.lane.start=start
        now=time.monotonic()
        self.lane.start_on_entry(self.controller,now,enabled=True,input_ready=False)
        start.assert_not_called()
        self.controller.presented(self.controller.page_id,now);now+=self.controller.read_seconds+.1
        self.lane.start_on_entry(self.controller,now,enabled=True,input_ready=True)
        self.lane.start_on_entry(self.controller,now+.1,enabled=True,input_ready=True)
        start.assert_called_once_with(self.controller.page_id,consent=True,display_only=False)

    def test_navigation_joins_workers_before_releasing_buffer_ownership(self):
        self.start();self.wait_for(lambda:self.lane.row is not None)
        self.assertIsNotNone(self.lane.input(self.controller.page_id,time.monotonic()))
        self.controller._enter('home',time.monotonic())
        self.lane.service(self.controller,time.monotonic())
        self.assertFalse(self.lane.report_thread.is_alive())
        self.assertFalse(self.lane.active);self.assertFalse(self.display.buffer_pages)
        self.assertIsNone(self.lane.input(self.controller.page_id,time.monotonic()))
        self.assertEqual(self.bridge.hdmi_command.call_args.args[0]['action'],'stop')
        self.pump.cancel.assert_called();self.pump.close.assert_called_once()

    def test_wrong_producer_session_stops_and_clears_evidence(self):
        original=self.bridge.hdmi_command.side_effect
        def wrong(command):
            reply=original(command)
            if command['action']!='start':reply['id']='old'
            return reply
        self.bridge.hdmi_command.side_effect=wrong
        self.start();self.wait_for(self.lane.ended.is_set)
        self.assertIn('mismatched',self.lane.error)
        self.assertIsNone(self.lane.input(self.controller.page_id,time.monotonic()))
        self.assertIsNone(self.lane.snapshot()['timing'])
        self.lane.service(self.controller,time.monotonic())
        self.assertEqual(self.controller.direction,'stop')

    def test_expired_native_receipts_stop_without_skipping_evidence(self):
        self.pump.read.side_effect=lambda:[{'ack_monotonic':time.monotonic()-.36}]*8
        self.start();self.wait_for(self.lane.ended.is_set)
        self.assertEqual(self.lane.error,'HDMI latch evidence expired; no records skipped')
        self.assertFalse(any(call.args[0]['action']=='heartbeat' for call in self.bridge.hdmi_command.call_args_list))
        self.lane.stop()
        self.assertFalse(self.lane.snapshot()['active'])

    def test_stuck_worker_does_not_release_buffer_ownership(self):
        release=threading.Event();entered=threading.Event()
        def blocked():
            entered.set();release.wait(4.)
            return [{'ack_monotonic':time.monotonic()}]
        self.pump.read.side_effect=blocked
        self.start();self.assertTrue(entered.wait(1.))
        buffers=self.lane.buffers
        try:
            with self.assertRaisesRegex(RuntimeError,'ownership retained'):self.lane.stop()
            self.assertTrue(self.lane.active);self.assertIs(self.lane.buffers,buffers)
            self.pump.close.assert_not_called()
            self.assertIsNotNone(self.lane.session_id)
        finally:
            release.set();self.lane.stop()
        self.assertFalse(self.lane.report_thread.is_alive());self.assertFalse(self.display.buffer_pages)

    def test_force_stop_cancels_scan_and_withdraws_direction(self):
        self.start();self.wait_for(lambda:self.lane.row is not None)
        self.controller.force_stop(time.monotonic())
        self.lane.service(self.controller,time.monotonic())
        self.assertEqual(self.controller.direction,'stop')
        self.assertFalse(self.lane.active);self.pump.cancel.assert_called()
        self.assertIsNone(self.lane.input(self.controller.page_id,time.monotonic()))

    def test_selection_only_changes_display_feedback(self):
        self.start();self.wait_for(lambda:self.lane.row is not None)
        self.controller.selected_frequency=14
        with self.lane.lock:
            self.lane.vote_counts[12]=3
            reply=dict(self.lane.row[0],input={'ready':True})
            self.lane.row=(reply,time.monotonic(),.001,None)
        self.lane.service(self.controller,time.monotonic())
        self.pump.select.assert_called_with(12)
        self.assertEqual(self.controller.selected_frequency,14)
        commands=[call.args[0] for call in self.bridge.hdmi_command.call_args_list]
        self.assertTrue(all('expected_frequency' not in command for command in commands))

    def test_small_receipt_batches_and_retained_native_failure_diagnostics(self):
        response=self.bridge.hdmi_command.side_effect
        def delayed(command):
            time.sleep(.02)
            return response(command)
        self.bridge.hdmi_command.side_effect=delayed
        self.pump.read.side_effect=lambda: (time.sleep(.01) or [{'ack_monotonic':time.monotonic()}])
        self.start();self.wait_for(lambda:self.lane.report_stats['count']>=4)
        commands=[call.args[0] for call in self.bridge.hdmi_command.call_args_list]
        self.assertTrue(all(len(c['latches'])==8 for c in commands if c['action']=='heartbeat'))
        self.assertGreater(self.lane.report_stats['max_http_ms'],0)
        self.pump.close.return_value=SimpleNamespace(error=13,count=17,policy=2,priority=1,
            cpu=1,worker_cpu_ns=10000,max_cycle_cpu_ns=1000)
        self.lane.stop()
        view=self.lane.snapshot()
        self.assertEqual(view['native_result']['reason'],'producer_heartbeat_expired')
        self.assertEqual(view['native_result']['count'],17)
        self.assertFalse(view['active']);self.assertIsNone(view['timing'])

    def test_coalesces_backlog_without_dropping_or_reordering_scan_receipts(self):
        origin=time.monotonic();produced=0
        def begin():
            nonlocal origin
            origin=time.monotonic()
            return dict(origin_counter=0,active_index=0,presented_monotonic=origin)
        self.pump.begin.side_effect=begin
        def real_rate():
            nonlocal produced
            latest=int((time.monotonic()-origin)/SCAN_PERIOD)
            latest=min(latest,produced+8)
            rows=[dict(counter_after=i,ack_monotonic=origin+i*SCAN_PERIOD)
                  for i in range(produced+1,latest+1)]
            produced=latest
            return rows
        self.pump.read.side_effect=real_rate
        def delayed(command):
            time.sleep(.131)
            return self.response(command)
        self.bridge.hdmi_command.side_effect=delayed
        self.start();self.wait_for(lambda:self.lane.report_stats['count']>=5)
        self.assertIsNone(self.lane.error)
        self.lane.stop()
        batches=[call.args[0]['latches'] for call in self.bridge.hdmi_command.call_args_list
                 if call.args[0]['action']=='heartbeat']
        self.assertTrue(any(len(batch)==8 for batch in batches))
        self.assertTrue(all(len(batch)==8 for batch in batches))
        receipts=[row['counter_after'] for batch in batches for row in batch]
        self.assertEqual(receipts,list(range(1,len(receipts)+1)))

    def test_votes_count_each_eligible_window_once_without_accepting_control(self):
        self.start();self.wait_for(lambda:self.lane.row is not None)
        reply=dict(self.response({'action':'heartbeat'}),frame_ok=True,
                   decision={'top_hz':12,'window_end_index_exclusive':500},
                   input={'ready':True,'quality':{'hard_bad':False},'age_seconds':.1},
                   display_timing={'ready':True},accepted=False,result=None)
        with self.lane.lock:
            self.lane._vote(reply);self.lane._vote(reply)
        view=self.lane.snapshot()['votes']
        self.assertEqual(view['unique_windows'],1)
        self.assertEqual(view['plurality_hz'],12)
        self.assertEqual(reply['result'],None)
        self.assertFalse(reply['accepted'])
        self.assertFalse(view['physical_output_enabled'])

    def test_votes_reject_bad_input_and_do_not_force_a_tie(self):
        reply=dict(frame_ok=True,decision={'top_hz':8,'window_end_index_exclusive':500},
                   input={'ready':True,'quality':{'hard_bad':True},'age_seconds':.1},
                   display_timing={'ready':True})
        self.lane._vote(reply)
        self.assertEqual(self.lane.snapshot()['votes']['unique_windows'],0)
        self.lane.vote_counts[8]=self.lane.vote_counts[12]=1
        self.assertIsNone(self.lane.snapshot()['votes']['plurality_hz'])

    def test_native_join_failure_keeps_display_buffers(self):
        self.start();self.wait_for(lambda:self.lane.row is not None)
        self.pump.close.side_effect=RuntimeError('native ownership retained')
        buffers=self.lane.buffers
        try:
            with self.assertRaisesRegex(RuntimeError,'ownership retained'):self.lane.stop()
            self.assertTrue(self.lane.active);self.assertIs(self.lane.buffers,buffers)
            self.assertIsNotNone(self.lane.session_id)
        finally:
            self.pump.close.side_effect=None
            self.lane.stop()


if __name__=='__main__':unittest.main()
