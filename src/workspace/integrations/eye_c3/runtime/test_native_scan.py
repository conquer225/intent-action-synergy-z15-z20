"""Deterministic native/software display only: no PYNQ, MMIO or RT scheduling."""
import ctypes as C
import os
from pathlib import Path
import time
import threading
import unittest

import numpy as np
from native_scan import Config,Corner,Feedback,Frame,NativeScan,MAX_ROWS,measurement,pointer,preflight
from ssvep_hdmi import pattern

READ=C.CFUNCTYPE(C.c_uint32)
PARK=C.CFUNCTYPE(C.c_int,C.c_uint)
SYNC=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint,C.c_int,C.c_size_t,C.c_size_t)
CLOCK=C.CFUNCTYPE(C.c_uint64,C.c_int)


class SoftwareDisplay:
    def __init__(self):
        self.now=100000000000;self.counter=0;self.index=0;self.status=0
        self.wrap=False;self.jump=1;self.latch=True;self.flush_error=0
        self.copy_delay=0;self.ack_delay=0;self.flushes=[];self.requested=[];self.fail_at=3
        self.cpu=0;self.cpu_per_park=0
        self.entered=self.release=None
        self.park_delay=0
        self.buffers=[np.zeros((720,1280,3),dtype=np.uint8) for _ in range(3)]
        self.patches=[]
        self.cfg=Config()
        self.functions=[READ(lambda:self.counter),READ(lambda:self.index),READ(lambda:self.status),
                        PARK(self.park),SYNC(self.sync),CLOCK(self.clock)]
        for name,function in zip(('counter','index','status','park','sync','software_clock'),self.functions):
            setattr(self.cfg,name,pointer(function))
        for i,buf in enumerate(self.buffers):self.cfg.frames[i]=Frame(buf.ctypes.data,i,0,0)
        self.boxes=((20,100,20,10),(80,100,20,10),(20,200,20,10),(80,200,20,10))
        for i,(x,y,w,h) in enumerate(self.boxes):
            off=np.full((h,w,3),i+1,dtype=np.uint8)
            on=np.full((h,w,3),i+11,dtype=np.uint8)
            self.patches.append((off,on))
            self.cfg.corners[i]=Corner(x,y,w,h,off.ctypes.data,on.ctypes.data,off.ctypes.data,on.ctypes.data)
            for buf in self.buffers:buf[y:y+h,x:x+w]=on
        self.masks=np.asarray([pattern(i) for i in range(MAX_ROWS)],dtype=np.uint8)
        self.cfg.masks=self.masks.ctypes.data;self.cfg.mask_count=MAX_ROWS
        self.cfg.initial_mask=pattern(0);self.cfg.duration_ns=200000000
        self.cfg.period_ns=16500000;self.cfg.realtime=0;self.cfg.cpu=-1
        self.cfg.initialized_mask=7

    def clock(self,clock):return self.now if clock==1 else self.cpu
    def park(self,index):
        if self.entered:
            self.entered.set()
            self.release.wait(1)
        if self.park_delay:time.sleep(self.park_delay)
        self.requested.append(index)
        self.counter=(self.counter+self.jump)&0xffffffff
        self.now+=16500000
        self.cpu+=self.cpu_per_park
        if self.counter==self.fail_at:self.now+=self.ack_delay
        if self.latch:self.index=index
        return 1
    def sync(self,_,bo,direction,size,offset):
        self.flushes.append((bo,direction,size,offset))
        self.now+=self.copy_delay
        if self.copy_delay:self.counter=(self.counter+1)&0xffffffff
        return self.flush_error


@unittest.skipUnless(os.environ.get('GL_NATIVE_SCAN_LIBRARY'),'Native C library required; no hardware')
class NativeTests(unittest.TestCase):
    def test_nonblocking_request_preserves_other_vdma_bits_and_rejects_faults(self):
        scan=NativeScan(os.environ['GL_NATIVE_SCAN_LIBRARY'])
        base=0x43000000
        registers={base:0x00010003,base+4:0x11000,base+0x28:0x00020102}
        writes=[]
        read=C.CFUNCTYPE(C.c_uint32,C.c_uint32)(lambda address:registers[address])
        def write(address,value):
            writes.append((address,value));registers[address]=value
        out=C.CFUNCTYPE(None,C.c_uint32,C.c_uint32)(write)
        self.assertTrue(scan.lib.gl_scan_bind_vdma(pointer(read),pointer(out)))
        self.assertTrue(scan.lib.gl_scan_request_park(1))
        self.assertEqual(writes,[(base+0x28,0x00020101),(base,0x00010001)])
        writes.clear()
        self.assertFalse(scan.lib.gl_scan_request_park(3))
        registers[base+4]=1
        self.assertFalse(scan.lib.gl_scan_request_park(2))
        registers[base+4]=0x11000;registers[base]=0
        self.assertFalse(scan.lib.gl_scan_request_park(0))
        self.assertEqual(writes,[])

    def run_scan(self,display):
        scan=NativeScan(os.environ['GL_NATIVE_SCAN_LIBRARY'])
        scan.start(display.cfg,display)
        deadline=time.monotonic()+2
        while not scan.done():
            if time.monotonic()>deadline:
                scan.stop();self.fail('Software native test stalled')
            time.sleep(.001)
        result,records=scan.collect()
        return result,records,measurement(result,records)

    def test_equivalence_to_existing_scan_evidence_and_corner_pixels(self):
        display=SoftwareDisplay();result,records,report=self.run_scan(display)
        self.assertEqual(result.error,0);self.assertTrue(report['completed'])
        self.assertGreaterEqual(result.count,12)
        self.assertEqual(len(report['latches']),result.count)
        self.assertFalse(report['optical_measurement'])
        for buf in display.buffers:
            for i,(x,y,w,h) in enumerate(display.boxes):
                roi=buf[y:y+h,x:x+w]
                self.assertTrue(np.array_equal(roi,display.patches[i][0]) or
                                np.array_equal(roi,display.patches[i][1]))
            self.assertEqual(buf[0,0,0],0)
        for row in records[:result.count]:
            self.assertEqual(row.after,(row.before+1)&0xffffffff)
            self.assertEqual(row.mask,pattern((row.after-result.origin)&0xffffffff))
            self.assertLessEqual(row.flushed_bytes,2*10*3840)
        self.assertTrue(all(direction==0 and size==10*3840 and offset in (100*3840,200*3840)
                            for _,direction,size,offset in display.flushes))

    def test_counter_wrap(self):
        display=SoftwareDisplay();display.counter=0xfffffffe
        result,_,report=self.run_scan(display)
        self.assertEqual(result.origin,0xffffffff)
        self.assertTrue(report['completed'])

    def test_feedback_updates_only_its_roi_in_inactive_buffers(self):
        display=SoftwareDisplay();display.park_delay=.005
        states=np.stack([np.full((8,24,3),value,dtype=np.uint8) for value in (21,47)])
        display.cfg.feedback=Feedback(400,300,24,8,states.ctypes.data,2)
        scan=NativeScan(os.environ['GL_NATIVE_SCAN_LIBRARY']);scan.start(display.cfg,(display,states))
        time.sleep(.012)
        scan.feedback(1)
        with self.assertRaises(ValueError):scan.feedback(2)
        deadline=time.monotonic()+2
        while not scan.done():
            self.assertLess(time.monotonic(),deadline);time.sleep(.001)
        result,_=scan.collect();self.assertEqual(result.error,0)
        for buf in display.buffers:
            np.testing.assert_array_equal(buf[300:308,400:424],states[1])
            self.assertEqual(buf[300,399,0],0);self.assertEqual(buf[308,400,0],0)
        self.assertTrue(any(size==8*3840 and offset==300*3840 for _,_,size,offset in display.flushes))

    def test_wrong_latch_and_dma_fault_stop(self):
        for case,expected in (('latch',5),('fault',4)):
            display=SoftwareDisplay()
            if case=='latch':display.latch=False
            else:display.status=1
            result,_,report=self.run_scan(display)
            self.assertEqual(result.error,expected);self.assertFalse(report['completed'])
            self.assertEqual(result.count,0)

    def test_skipped_scan_is_not_accepted(self):
        display=SoftwareDisplay();display.jump=2
        result,_,report=self.run_scan(display)
        self.assertEqual(result.error,6);self.assertFalse(report['completed'])
        self.assertEqual(result.count,0)

    def test_late_receipt_saved_without_accepting_it(self):
        display=SoftwareDisplay();display.ack_delay=16500000
        result,_,report=self.run_scan(display)
        self.assertEqual(result.error,8)
        self.assertEqual(result.count,1)
        self.assertIsNotNone(report['rejected_latch'])

    def test_flush_failure_and_copy_across_scan(self):
        for case,expected in (('flush',9),('copy',7)):
            display=SoftwareDisplay()
            if case=='flush':display.flush_error=-5
            else:display.copy_delay=18000000
            result,_,report=self.run_scan(display)
            self.assertEqual(result.error,expected);self.assertFalse(report['completed'])

    def test_unverified_configuration_rejected_before_thread_start(self):
        for case in ('bounds','pattern','period','realtime','duration'):
            display=SoftwareDisplay()
            if case=='bounds':display.cfg.corners[0].x=1280
            elif case=='pattern':display.masks[0]=0
            elif case=='period':display.cfg.period_ns=16000000
            elif case=='realtime':display.cfg.realtime=1
            else:display.cfg.duration_ns=46000000000
            scan=NativeScan(os.environ['GL_NATIVE_SCAN_LIBRARY'])
            with self.assertRaises(OSError):scan.start(display.cfg,display)
            self.assertIsNone(scan.session)

    def test_cpu_budget_stops_without_accepting_expensive_scan(self):
        display=SoftwareDisplay();display.cpu_per_park=9000000
        result,_,report=self.run_scan(display)
        self.assertEqual(result.error,12)
        self.assertEqual(result.count,0)
        self.assertEqual(report['scheduler']['max_cycle_cpu_ms'],9)

    def test_controlled_stop_retains_buffers_until_worker_join(self):
        display=SoftwareDisplay()
        display.entered=threading.Event();display.release=threading.Event()
        scan=NativeScan(os.environ['GL_NATIVE_SCAN_LIBRARY'])
        scan.start(display.cfg,display)
        self.assertTrue(display.entered.wait(1))
        self.assertIsNotNone(scan.owners)
        release=threading.Timer(.05,display.release.set);release.start()
        try:scan.stop()
        finally:display.release.set();release.join()
        result,records=scan.collect()
        self.assertEqual(result.error,10)
        self.assertFalse(measurement(result,records)['completed'])
        self.assertIsNone(scan.session);self.assertIsNone(scan.owners)

    def test_production_evidence_rejects_modified_pattern(self):
        display=SoftwareDisplay();result,records,_=self.run_scan(display)
        records[0].mask^=1
        report=measurement(result,records)
        self.assertFalse(report['completed'])
        self.assertIn('pattern',report['consumer_error'])
        self.assertEqual(report['verified_single_scan_latches'],0)

    def test_streamed_receipts_are_immutable_and_match_final_records(self):
        display=SoftwareDisplay();display.park_delay=.002
        scan=NativeScan(os.environ['GL_NATIVE_SCAN_LIBRARY']);scan.start(display.cfg,display)
        cursor=0;streamed=[]
        while True:
            result,rows,done=scan.read(cursor)
            streamed.extend(rows);cursor+=len(rows)
            if done and cursor==result.count:break
            time.sleep(.001)
        final,records=scan.collect()
        self.assertEqual(final.error,0);self.assertEqual(cursor,final.count)
        self.assertEqual([bytes(row) for row in streamed],[bytes(row) for row in records[:final.count]])
        self.assertIsNone(scan.session)
        with self.assertRaisesRegex(RuntimeError,'closed'):scan.read(cursor)

    def test_live_start_copies_old_menu_only_after_its_buffer_is_released(self):
        display=SoftwareDisplay();display.buffers[0].fill(77)
        base=np.full((720,1280,3),7,dtype=np.uint8)
        display.cfg.base=base.ctypes.data;display.cfg.initialized_mask=6
        original=display.park;seen=[]
        def checked_park(index):
            seen.append(display.buffers[display.index][0,0,0])
            return original(index)
        callback=PARK(checked_park);display.cfg.park=pointer(callback)
        result,_,_=self.run_scan(display)
        self.assertEqual(result.error,0);self.assertEqual(seen[0],77)
        self.assertEqual(display.buffers[0][0,0,0],7)
        self.assertEqual(display.buffers[1][0,0,0],0)

    def test_expired_or_future_heartbeat_stops_native_scan_without_python_cancellation(self):
        for stamp,minimum in ((100000,15),(100200,0)):
            display=SoftwareDisplay();display.cfg.duration_ns=1000000000
            display.cfg.require_heartbeat=1;display.cfg.heartbeat_ms=stamp
            result,_,report=self.run_scan(display)
            self.assertEqual(result.error,13);self.assertGreaterEqual(result.count,minimum)
            self.assertLess(result.count,22);self.assertFalse(report['completed'])

    def test_heartbeat_wrap_is_valid_then_expires(self):
        display=SoftwareDisplay();display.now=((1<<32)-30)*1000000
        display.cfg.require_heartbeat=1;display.cfg.heartbeat_ms=(1<<32)-30
        display.cfg.duration_ns=1000000000
        result,_,_=self.run_scan(display)
        self.assertEqual(result.error,13);self.assertGreater(result.count,15)

    def test_validated_heartbeat_keeps_scan_live_and_selection_preserves_pattern(self):
        display=SoftwareDisplay();display.park_delay=.003;display.cfg.duration_ns=700000000
        display.cfg.require_heartbeat=1;display.cfg.heartbeat_ms=100000
        chosen_off=np.full((10,20,3),70,dtype=np.uint8)
        chosen_on=np.full((10,20,3),80,dtype=np.uint8)
        display.cfg.corners[2].chosen_off=chosen_off.ctypes.data
        display.cfg.corners[2].chosen_on=chosen_on.ctypes.data
        scan=NativeScan(os.environ['GL_NATIVE_SCAN_LIBRARY']);scan.start(display.cfg,display)
        scan.select(12)
        with self.assertRaises(ValueError):scan.select(11)
        while not scan.done():
            scan.touch(display.now/1e9);time.sleep(.001)
        result,records=scan.collect()
        self.assertEqual(result.error,0)
        self.assertTrue(measurement(result,records)['completed'])
        self.assertTrue(any(row.reserved==3 for row in records[:result.count]))
        for buf in display.buffers:
            roi=buf[200:210,20:40]
            self.assertTrue(np.array_equal(roi,chosen_off) or np.array_equal(roi,chosen_on))


@unittest.skipUnless(os.environ.get('GL_NATIVE_BOARD_PREFLIGHT'),
                     'Real board CMA/XRT preflight only; no PL or display MMIO')
class BoardPreflightTests(unittest.TestCase):
    def test_real_xrt_handle_and_native_cache_sync_before_pl_loading(self):
        from types import SimpleNamespace
        from pynq import allocate,PL
        from system_hdmi import FREQUENCY_BOXES
        display=C.CDLL(os.environ['GL_NATIVE_BOARD_PREFLIGHT'])
        patches={}
        for hz,_,(x,y,x1,y1) in FREQUENCY_BOXES:
            for state in (False,True):
                for chosen in (False,True):
                    patches[(hz,state,chosen)]=np.zeros((y1-y+1,x1-x+1,3),dtype=np.uint8)
        frames=SimpleNamespace(patches=patches)
        buffers=[];original=PL.bitfile_name
        try:
            for _ in range(3):
                buf=allocate(shape=(720,1280,3),dtype=np.uint8)
                buffers.append(buf);buf.fill(0);buf.flush()
            result=preflight(display,frames,buffers,30,os.environ['GL_NATIVE_SCAN_LIBRARY'])
            self.assertTrue(result['config_valid'])
            self.assertTrue(result['opaque_pointer_preserved'])
            self.assertFalse(result['worker_started'])
            self.assertFalse(result['display_functions_called'])
            self.assertEqual(result['cache_sync_checks'],sum(not b.coherent for b in buffers))
            self.assertEqual(PL.bitfile_name,original)
        finally:
            for buf in buffers:buf.freebuffer()


if __name__=='__main__':unittest.main()
