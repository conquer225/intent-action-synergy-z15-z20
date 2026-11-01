import unittest,numpy as np
from vision_demo.continuous import ContinuousVideo
class Buffer(np.ndarray):
    def __new__(cls,shape,dtype,address):
        obj=np.zeros(shape,dtype).view(cls);obj.physical_address=address;obj.freed=False;obj.flushes=0;return obj
    def flush(self):self.flushes+=1
    def freebuffer(self):self.freed=True
class Native:
    def __init__(self):self.opens=0;self.halt=True;self.forget=0
    def vision_live_open(self,p):self.opens+=1;return 1
    def vision_live_health(self):return 1
    def vision_live_close(self):return self.halt
    def vision_live_forget(self):self.forget+=1
class Registers:
    def __init__(self):self.data={0:0x56495332,4:0,8:0,12:0,16:0,20:0}
    def read(self,a):return self.data[a]
    def write(self,a,v):self.data[a]=v
class ContinuousVideoTests(unittest.TestCase):
    def test_camera_start_failure_is_recoverable_only_after_dma_cleanup(self):
        from vision_demo.continuous import CameraStartError
        v=self.setup_video();self.native.vision_live_open=lambda addresses:0
        with self.assertRaises(CameraStartError):v.start(0)
        self.assertFalse(v.active);self.assertEqual(v.buffers,[])
        self.assertTrue(all(b.freed for b in self.buffers))
        v=self.setup_video();self.native.vision_live_open=lambda addresses:0;self.native.halt=False
        with self.assertRaises(RuntimeError) as caught:v.start(0)
        self.assertNotIsInstance(caught.exception,CameraStartError)
        self.assertTrue(v.buffers);self.assertFalse(any(b.freed for b in self.buffers))
        v.close(pl_reset=True)
    def setup_video(self):
        self.buffers=[];self.native=Native();self.ip=Registers()
        def allocate(shape,dtype):
            b=Buffer(shape,dtype,0x20000000+len(self.buffers)*0x1000000);self.buffers.append(b);return b
        return ContinuousVideo(self.ip,None,allocator=allocate,native=self.native)
    def test_camera_is_started_once_and_service_never_submits_cpu_frames(self):
        v=self.setup_video();v.start(0)
        for mode in range(9):v.select(mode);v.service()
        self.assertEqual(self.native.opens,1);self.assertEqual([b.flushes for b in self.buffers],[1,1,1])
        self.assertFalse(v.snapshot()['ps_frame_submission']);v.close()
        self.assertTrue(all(b.freed for b in self.buffers))
    def test_failed_halt_keeps_all_dma_memory_until_verified_reset(self):
        v=self.setup_video();v.start(1);self.native.halt=False
        with self.assertRaisesRegex(RuntimeError,'retain'):v.close()
        self.assertFalse(any(b.freed for b in self.buffers));v.close(pl_reset=True)
        self.assertEqual(self.native.forget,1);self.assertTrue(all(b.freed for b in self.buffers))
    def test_address_above_dma_range_is_rejected_before_uint32_truncation(self):
        v=self.setup_video();allocate=v.allocator
        def invalid(shape,dtype):
            b=allocate(shape,dtype);b.physical_address+=1<<32;return b
        v.allocator=invalid
        with self.assertRaisesRegex(ValueError,'DDR'):v.start(0)
        self.assertEqual(self.native.opens,0)
        self.assertTrue(all(b.freed for b in self.buffers))
    def test_closed_stream_does_not_publish_old_source_counters(self):
        v=self.setup_video();self.ip.data[16]=7;v.start(0)
        self.assertEqual(v.snapshot()['frame_sequence'],7);v.close()
        self.assertIsNone(v.snapshot()['frame_sequence'])
    def test_mode_request_without_frame_acknowledgment_times_out(self):
        v=self.setup_video();clock=[10.0];v.now=lambda:clock[0]
        self.ip.data[8]=1;v.start(0)
        clock[0]+=.7;self.ip.data[16]+=20;self.ip.data[12]+=40
        with self.assertRaisesRegex(RuntimeError,'acknowledgment'):v.service()
        v.close(pl_reset=True)
    def test_hdmi_stall_is_detected_even_when_camera_vsync_keeps_advancing(self):
        v=self.setup_video();clock=[10.0];v.now=lambda:clock[0];v.start(0)
        clock[0]+=1.6;self.ip.data[16]+=50
        with self.assertRaisesRegex(RuntimeError,'HDMI'):v.service()
        v.close(pl_reset=True)
    def test_failed_initial_flush_releases_the_allocated_buffer(self):
        v=self.setup_video();allocate=v.allocator
        def invalid(shape,dtype):
            b=allocate(shape,dtype)
            def fail():raise RuntimeError('cache flush failed')
            b.flush=fail;return b
        v.allocator=invalid
        with self.assertRaisesRegex(RuntimeError,'cache flush'):v.start(0)
        self.assertEqual(self.native.opens,0)
        self.assertTrue(all(b.freed for b in self.buffers))
    def test_cadence_reports_distinct_camera_display_and_pixel_rates_with_wrap(self):
        v=self.setup_video();clock=[10.0];v.now=lambda:clock[0]
        self.ip.data.update({16:0xfffffff0,12:1000,20:100});v.start(0)
        self.ip.data.update({16:15,12:1030,20:27648100});clock[0]+=.5;v.service()
        row=v.snapshot()
        self.assertEqual(row['camera_fps'],62);self.assertEqual(row['hdmi_hz'],60)
        self.assertEqual(row['filter_pixels_per_second'],55296000);v.close()
