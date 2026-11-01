import time
import os
import ctypes as C
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
import numpy as np
from system_hdmi import UnifiedDisplay,RuntimeWatch,present_frame,BOXES,centered_text,ACCENT,FREQUENCY_BOXES,CARD,SELECTED,BACKGROUND


class Buffer(np.ndarray):
    def flush(self):pass


class UnifiedTests(unittest.TestCase):
    def test_audio_enabled_labels_do_not_claim_silent_or_verified_audibility(self):
        display,now=self.feedback_display('speech')
        display.controller.phrase='我想喝水'
        words=[];original=display.renderer.write_text
        def record(draw,x,y,text,size=32,color=None):
            words.append(text)
            return original(draw,x,y,text,size,color)
        display.renderer.write_text=record
        display.refresh_labels({}, {},'clip')
        self.assertTrue(any('本轮静音' in word for word in words))
        words.clear()
        display.refresh_labels({}, {},'clip',audio={'volume_percent':40,'player':{'phase':'feeding'}})
        self.assertTrue(any('音量 40%' in word for word in words))
        self.assertFalse(any('本轮静音' in word or '已听到' in word for word in words))

    def test_four_corner_layout_preserves_mapping_size_and_clear_spacing(self):
        self.assertEqual([(hz,direction) for hz,direction,_ in FREQUENCY_BOXES],
                         [(8,'前进'),(10,'后退'),(12,'左转'),(14,'右转')])
        for _,_,(left,top,right,bottom) in FREQUENCY_BOXES:
            self.assertEqual((right-left,bottom-top),(384,192))
            self.assertGreaterEqual(top,140)
            self.assertLessEqual(bottom,638)
        upper_left,upper_right,lower_left,lower_right=[box for _,_,box in FREQUENCY_BOXES]
        self.assertEqual(lower_left[1]-upper_left[3],114)
        self.assertEqual(lower_right[1]-upper_right[3],114)
        self.assertEqual(upper_right[0]-upper_left[2],460)
        display,_=self.feedback_display('drive')
        blank=display.shells['drive'][333:446,26:411]
        self.assertTrue(np.all(blank==np.array(BACKGROUND[::-1],dtype=np.uint8)))
        blank=display.shells['drive'][333:446,870:1255]
        self.assertTrue(np.all(blank==np.array(BACKGROUND[::-1],dtype=np.uint8)))

    def test_frequency_cards_start_same_colour_and_only_trusted_choice_changes(self):
        from wheelchair_ssvep.dry_run_bridge import demo_snapshot
        display,now=self.feedback_display('drive');state=display.controller
        output=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        display.refresh_labels({}, {},'clip');display.compose(output,0,now=now)
        for _,_,box in FREQUENCY_BOXES:
            np.testing.assert_array_equal(output[box[1]+32,box[0]+32],CARD[::-1])
        self.assertTrue(state.arm_virtual_direction(now))
        state.ssvep(demo_snapshot(12),now);display.refresh_labels({}, {},'clip')
        display.compose(output,0,now=now)
        for hz,_,box in FREQUENCY_BOXES:
            np.testing.assert_array_equal(output[box[1]+32,box[0]+32],(SELECTED if hz==12 else CARD)[::-1])
        state.tick(now+.31);display.refresh_labels({}, {},'clip');display.compose(output,0,now=now+.31)
        for _,_,box in FREQUENCY_BOXES:
            np.testing.assert_array_equal(output[box[1]+32,box[0]+32],CARD[::-1])
        self.assertFalse(state.snapshot(now+.31)['stimulus_enabled'])

    def test_direction_centre_has_a_return_card_and_normal_dwell_feedback(self):
        display,now=self.feedback_display('drive');selection=display.controller.selection
        selection.hover=1;selection.progress=.5
        self.assertEqual(display.feedback(now),(None,('dwell',10),None))
        buffer=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        display.compose(buffer,0,now=now)
        x,y=BOXES[1][0]+24,BOXES[1][3]-120
        np.testing.assert_array_equal(buffer[y+20,x+5],ACCENT[::-1])

    def test_prepared_shells_skip_rendering_and_preserve_every_pixel(self):
        root=os.environ.get('GL_TEST_EYE_ROOT',str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye'))
        original=UnifiedDisplay(root,live=True,dimensions=(288,512))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'shells.npz';original.save_shell_cache(path)
            with patch('system_hdmi.centered_text',side_effect=AssertionError('Startup rendered text')):
                cached=UnifiedDisplay(root,live=True,dimensions=(288,512),shell_cache=path)
            for page in original.shells:
                np.testing.assert_array_equal(cached.shells[page],original.shells[page])
            with self.assertRaisesRegex(ValueError,'contract'):
                UnifiedDisplay(root,live=False,dimensions=(288,512),shell_cache=path)
            with np.load(path,allow_pickle=False) as data:broken={key:data[key] for key in data.files}
            broken['video']=broken['video'].copy();broken['video'][0,0,0]^=1
            np.savez_compressed(path,**broken)
            with self.assertRaisesRegex(ValueError,'Corrupt'):
                UnifiedDisplay(root,live=True,dimensions=(288,512),shell_cache=path)

    def feedback_display(self,page='home'):
        root=os.environ.get('GL_TEST_EYE_ROOT',str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye'))
        display=UnifiedDisplay(root,live=True,dimensions=(288,512))
        now=time.monotonic();display.controller._enter(page,now)
        display.controller.presented(display.controller.page_id,now)
        now+=display.controller.read_seconds+.1
        selection=display.controller.selection
        selection.last_source=now;selection.hover=0;selection.progress=.5
        return display,now

    def test_progress_changes_menu_presentation_key_without_redrawing_shell(self):
        display,now=self.feedback_display();selection=display.controller.selection
        before=display.presentation_key(now);shell=display.shells['home']
        selection.progress=.75
        self.assertNotEqual(before,display.presentation_key(now))
        self.assertIs(shell,display.shells['home'])
        self.assertEqual(display.feedback(now)[0],('dwell',15))

    def test_progress_paints_true_fraction_and_clears_stale_fill(self):
        display,now=self.feedback_display()
        buffer=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        self.assertTrue(display.compose(buffer,0,now=now))
        x,y=BOXES[0][0]+24,BOXES[0][3]-120;w=BOXES[0][2]-BOXES[0][0]-48
        np.testing.assert_array_equal(buffer[y+20,x+5],ACCENT[::-1])
        self.assertFalse(np.array_equal(buffer[y+20,x+w-5],ACCENT[::-1]))
        self.assertTrue(display.compose(buffer,0,now=now+.26))
        self.assertFalse(np.any(np.all(buffer[y+17:y+26,x+3:x+w-3]==ACCENT[::-1],axis=2)))
        self.assertEqual(display.feedback(now+.26)[0],('lost',0))

    def test_progress_is_repainted_in_each_rotating_buffer(self):
        display,now=self.feedback_display()
        buffers=[np.empty((720,1280,3),dtype=np.uint8).view(Buffer) for _ in range(3)]
        for index,buffer in enumerate(buffers):display.compose(buffer,index,now=now)
        display.controller.selection.progress=.9
        for index,buffer in enumerate(buffers):
            self.assertTrue(display.compose(buffer,index,now=now))
            self.assertEqual(display.buffer_feedback[index][0],('dwell',18))
        for buffer in buffers[1:]:np.testing.assert_array_equal(buffer,buffers[0])

    def test_reading_and_held_lock_are_visible_without_new_selection(self):
        display,now=self.feedback_display();selection=display.controller.selection
        selection.locked=0;selection.selected=0;selection.progress=1
        before=dict(selection.__dict__)
        self.assertEqual(display.feedback(now)[0],('locked',0))
        buffer=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        display.compose(buffer,0,now=now)
        self.assertEqual(before,selection.__dict__)
        display.controller._enter('speed',now)
        self.assertTrue(all(item==('reading',0) for item in display.feedback(now)))

    def test_cross_page_lock_never_looks_like_current_action_success(self):
        display,now=self.feedback_display();state=display.controller
        state.selection.hover=1;state.selection.locked=1;state.selection.progress=1
        self.assertTrue(state.choose(1,now))
        state.presented(state.page_id,now);now+=state.read_seconds+.1
        state.selection.last_source=now;state.selection.hover=1;state.selection.progress=1
        self.assertEqual(state.page,'speech')
        self.assertEqual(display.feedback(now)[1],('locked',0))

    def test_same_page_action_receipt_shows_success_and_updates_expression(self):
        display,now=self.feedback_display('speech');state=display.controller
        self.assertTrue(state.choose(0,now))
        state.selection.locked=0;state.selection.progress=1
        self.assertEqual(display.feedback(now)[0],('executed',20))
        display.refresh_labels({}, {},'clip');before=display.overlay_key
        self.assertTrue(state.choose(2,now+.01))
        self.assertTrue(display.refresh_labels({}, {},'clip'))
        self.assertNotEqual(before,display.overlay_key)
        self.assertEqual(state.phrase,'我需要帮助')

    def test_emotion_display_grouping_preserves_raw_labels_and_revokes_invalid(self):
        from unittest.mock import patch
        display,now=self.feedback_display()
        for label,expected in (('funny','正向情绪'),('calm','中性情绪'),('boring','中性情绪'),('horror','负向情绪')):
            emotion={'valid':True,'label':label}
            display.overlay_key=None
            with patch('system_hdmi.status_bar') as bar:
                display.refresh_labels({'emotion':emotion},{},'clip')
                self.assertEqual(bar.call_args[0][2][0],'心情参考 '+expected)
            self.assertEqual(emotion['label'],label)
        with patch('system_hdmi.status_bar') as bar:
            display.refresh_labels({'emotion':{'valid':False,'label':'boring'}},{},'clip')
            self.assertEqual(bar.call_args[0][2][0],'心情参考 无可信结果')
        with patch('system_hdmi.status_bar') as bar:
            display.refresh_labels({'emotion':{'valid':True,'class_name':'funny'}},{},'clip')
            self.assertEqual(bar.call_args[0][2][0],'心情参考 正向情绪')

    def test_board_numeric_fatigue_levels_are_rendered_as_words_and_revoked(self):
        display,now=self.feedback_display();words=[]
        original=display.renderer.write_text
        def record(draw,x,y,text,size=32,color=None):
            words.append(text)
            return original(draw,x,y,text,size,color)
        display.renderer.write_text=record
        for level,label in ((0,'正常'),(1,'轻度'),(2,'严重')):
            words.clear();display.refresh_labels({'fatigue':{'valid':True,'level':level}}, {}, 'clip')
            self.assertIn('疲劳 '+label,words)
        words.clear();display.refresh_labels({'fatigue':{'valid':False,'level':2}}, {}, 'clip')
        self.assertIn('疲劳 无可信结果',words);self.assertNotIn('疲劳 严重',words)

    def test_disconnect_render_has_a_visible_manual_reconnect_instruction(self):
        from guide import View
        display,now=self.feedback_display();words=[]
        original=display.renderer.write_text
        def record(draw,x,y,text,size=32,color=None):
            words.append(text)
            return original(draw,x,y,text,size,color)
        display.renderer.write_text=record
        frame=display.renderer.render(View(phase='failed',detail='采样中断，旧选择已撤销；PS_KEY0 重连，PS_KEY1 停止'))
        self.assertEqual(frame.shape,(720,1280,3))
        self.assertTrue(any('PS_KEY0 重连' in word for word in words))

    def test_video_progress_never_covers_central_viewing_region(self):
        display,now=self.feedback_display('video')
        self.assertIsNone(display.feedback(now)[1])
        buffer=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        frame=np.full(288*512*3,137,dtype=np.uint8)
        display.compose(buffer,0,frame,now=now)
        before=buffer.copy();display.controller.selection.progress=.9
        display.compose(buffer,0,now=now)
        x,y,w,h=display.roi
        np.testing.assert_array_equal(buffer[y:y+h,x:x+w],before[y:y+h,x:x+w])

    def test_paused_progress_cannot_appear_confirmed(self):
        display,now=self.feedback_display();selection=display.controller.selection
        selection.locked=0;selection.progress=1;selection.paused=True
        self.assertTrue(all(item==('lost',0) for item in display.feedback(now)))

    def test_menu_glyph_bounds_are_centered_in_every_card(self):
        root=os.environ.get('GL_TEST_EYE_ROOT',str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye'))
        renderer=UnifiedDisplay(root,live=True,dimensions=(288,512))
        for page,bounds in renderer.label_bounds.items():
            for box,text in zip(BOXES,bounds):
                if text is None:
                    self.assertIn(page,('video','drive'));continue
                with self.subTest(page=page,box=box):
                    self.assertLessEqual(abs((text[0]+text[2]-box[0]-box[2])/2),.5)
                    self.assertLessEqual(abs((text[1]+text[3]-box[1]-box[3])/2),.5)
                    self.assertGreaterEqual(text[0],box[0]+12)
                    self.assertLessEqual(text[2],box[2]-12)

    def test_long_mixed_font_status_is_centered_and_contained(self):
        from PIL import Image
        root=os.environ.get('GL_TEST_EYE_ROOT',str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye'))
        renderer=UnifiedDisplay(root)
        canvas=Image.new('RGB',(1280,720));box=(18,86,409,128)
        bounds=centered_text(canvas,renderer.renderer,'心情参考 GAMEEMO-0123456789 '+('未确认'*20),box,24)
        self.assertGreaterEqual(bounds[0],box[0]+10);self.assertLessEqual(bounds[2],box[2]-10)
        self.assertGreaterEqual(bounds[1],box[1]);self.assertLessEqual(bounds[3],box[3])
        self.assertLessEqual(abs((bounds[0]+bounds[2]-box[0]-box[2])/2),.5)
        self.assertLessEqual(abs((bounds[1]+bounds[3]-box[1]-box[3])/2),.5)

    def test_already_progressed_latch_does_not_wait_for_an_extra_scan(self):
        class Display:
            def __init__(self):self.count=1;self.index=0
            def display_frames(self):return self.count
            def display_park(self,target):self.count+=1;self.index=target;return 1
            def display_index(self):return self.index
            def display_status(self):return 0
        present_frame(Display(),1,clock=lambda:0.,sleep=lambda _:self.fail('Extra scan waited'))

    def test_frozen_scan_and_bad_latch_rejected(self):
        class Display:
            def display_frames(self):return 1
            def display_park(self,target):return 1
            def display_index(self):return 1
            def display_status(self):return 0
        now=[0.]
        def sleep(seconds):now[0]+=seconds
        with self.assertRaisesRegex(ValueError,'stalled'):
            present_frame(Display(),1,clock=lambda:now[0],sleep=sleep)
        with self.assertRaisesRegex(ValueError,'latch'):
            present_frame(Display(),2,clock=lambda:now[0],sleep=sleep)
    def test_prepared_video_waits_only_remaining_time_and_rechecks_guard(self):
        class Display:
            def __init__(self):self.count=1;self.index=0;self.calls=[]
            def display_frames(self):self.calls.append('counter');return self.count
            def display_park(self,target):self.calls.append('park');self.count+=1;self.index=target;return 1
            def display_index(self):return self.index
            def display_status(self):return 0
        now=[.017];display=Display();events=[]
        def sleep(seconds):events.append(('wait',seconds));now[0]+=seconds
        def require():events.append(('guard',now[0]));self.assertEqual(display.calls,[])
        result=present_frame(display,1,clock=lambda:now[0],sleep=sleep,not_before=.05,require=require)
        self.assertAlmostEqual(events[0][1],.033)
        self.assertEqual(events[1],('guard',.05))
        self.assertAlmostEqual(result['playback_wait_ms'],33)
        self.assertEqual(result['latch_scan_ms'],0)

    def test_late_prepared_video_never_waits_or_skips_latch_checks(self):
        class Display:
            def display_frames(self):return 1
            def display_park(self,target):return 1
            def display_index(self):return 2
            def display_status(self):return 0
        checks=[]
        with self.assertRaisesRegex(ValueError,'latch'):
            present_frame(Display(),1,clock=lambda:.2,sleep=lambda _:self.fail('Late frame slept'),
                          not_before=.05,require=lambda:checks.append('checked'))
        self.assertEqual(checks,['checked'])

    def test_guard_revoked_during_deadline_wait_prevents_submission(self):
        class Display:
            def display_frames(self):raise AssertionError('Revoked display touched')
        now=[0.]
        def sleep(seconds):now[0]+=seconds
        def require():raise RuntimeError('Runtime admission revoked')
        with self.assertRaisesRegex(RuntimeError,'revoked'):
            present_frame(Display(),1,clock=lambda:now[0],sleep=sleep,not_before=.05,require=require)
        self.assertEqual(now[0],.05)

    def test_prepared_video_still_checks_dma_after_successful_latch(self):
        class Display:
            def __init__(self):self.count=1
            def display_frames(self):return self.count
            def display_park(self,target):self.count+=1;return 1
            def display_index(self):return 1
            def display_status(self):return 0x1
        with self.assertRaisesRegex(ValueError,'DMA'):
            present_frame(Display(),1,clock=lambda:0.,sleep=lambda _:None,not_before=0.)
    @unittest.skipUnless(Path(__file__).with_name('frame_fitter.so').exists(),'Board-compiled fitter only')
    def test_c_fitter_exact_reference_and_padding_guard(self):
        lib=C.CDLL(str(Path(__file__).with_name('frame_fitter.so')))
        lib.fit_bgr.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_void_p,C.c_int,C.c_int,C.c_int]
        lib.fit_bgr.restype=C.c_int
        random=np.random.default_rng(771)
        for width,height,dw,dh in ((640,360,384,216),(1280,720,384,216),(360,640,216,384),
                                  (288,512,270,480),(13,7,27,19),(1,1,270,480),(288,512,1,1)):
            frame=random.integers(0,256,(height,width,3),dtype=np.uint8)
            output=np.full((dh,dw*3+12),213,dtype=np.uint8)
            self.assertEqual(lib.fit_bgr(frame.ctypes.data,width,height,output.ctypes.data,dw,dh,output.shape[1]),1)
            expected=frame[(np.arange(dh)*height//dh)[:,None],(np.arange(dw)*width//dw)[None,:]]
            np.testing.assert_array_equal(output[:,:dw*3].reshape((dh,dw,3)),expected)
            self.assertTrue(np.all(output[:,dw*3:]==213))
        self.assertEqual(lib.fit_bgr(None,640,360,None,384,216,1152),0)
    def test_roi_does_not_overwrite_menu_and_stays_bgr_exact(self):
        import sys
        from pathlib import Path
        root=os.environ.get('GL_TEST_EYE_ROOT',str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye'))
        sys.path.insert(0,str(Path(root)/'src'))
        renderer=UnifiedDisplay(root)
        renderer.advance(16,time.monotonic())
        buffer=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        frame=np.arange(640*360*3,dtype=np.uint8)
        renderer.compose(buffer,0,frame)
        pixels=frame.reshape((360,640,3))
        expected=pixels[(np.arange(216)*360//216)[:,None],(np.arange(384)*640//384)[None,:]]
        np.testing.assert_array_equal(buffer[245:461,448:832],expected)
        before=buffer.copy();renderer.compose(buffer,0,np.zeros_like(frame))
        np.testing.assert_array_equal(buffer[:245],before[:245])
        np.testing.assert_array_equal(buffer[461:],before[461:])
        np.testing.assert_array_equal(buffer[245:461,:448],before[245:461,:448])
        np.testing.assert_array_equal(buffer[245:461,832:],before[245:461,832:])
        self.assertGreater(renderer.roi[0],1280/3)
        self.assertLess(renderer.roi[0]+renderer.roi[2],1280*2/3)
        self.assertFalse(renderer.lease(time.monotonic())['physical_output_enabled'])
        self.assertEqual(len(renderer.transitions),1)

    def test_prescaled_pixels_equal_runtime_fit_and_keep_menu_intact(self):
        import sys
        root=os.environ.get('GL_TEST_EYE_ROOT',str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye'))
        sys.path.insert(0,str(Path(root)/'src'))
        renderer=UnifiedDisplay(root);renderer.advance(16,time.monotonic())
        original=np.random.default_rng(72).integers(0,256,(360,640,3),dtype=np.uint8)
        fitted=original[(np.arange(216)*360//216)[:,None],(np.arange(384)*640//384)[None,:]].copy()
        runtime=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        prepared=np.empty_like(runtime)
        renderer.compose(runtime,0,original);renderer.compose(prepared,1,fitted)
        np.testing.assert_array_equal(runtime,prepared)

    def test_live_portrait_fills_only_verified_central_roi(self):
        root=os.environ.get('GL_TEST_EYE_ROOT',str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye'))
        renderer=UnifiedDisplay(root,live=True,dimensions=(288,512))
        now=time.monotonic();renderer.controller._enter('video',now)
        renderer.refresh_labels({'emotion':{'valid':False},'fatigue':{'valid':False}},{},'SD portrait')
        output=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        frame=np.full(288*512*3,135,dtype=np.uint8)
        renderer.compose(output,0,frame);before=output.copy()
        renderer.compose(output,0,np.zeros_like(frame));x,y,w,h=renderer.roi
        np.testing.assert_array_equal(output[:y],before[:y])
        np.testing.assert_array_equal(output[y+h:],before[y+h:])
        np.testing.assert_array_equal(output[y:y+h,:x],before[y:y+h,:x])
        np.testing.assert_array_equal(output[y:y+h,x+w:],before[y:y+h,x+w:])
        self.assertFalse(output[y:y+h,x:x+w].any())
        self.assertGreater(x,1280/3);self.assertLess(x+w,1280*2/3)
        self.assertGreaterEqual(y,142);self.assertLessEqual(y+h,628)
        self.assertEqual(renderer.transitions,[])

    def test_runtime_guard_expiry_aborts(self):
        clock=[10.];watch=RuntimeWatch(lambda:None,clock=lambda:clock[0])
        try:
            watch.require();clock[0]=14.1
            with self.assertRaisesRegex(RuntimeError,'expired'):watch.require()
        finally:watch.close()

    def test_runtime_pause_recovers_only_after_completed_check(self):
        now=[10.]
        with patch('system_hdmi.threading.Thread.start'):
            watch=RuntimeWatch(lambda:None,clock=lambda:now[0])
        self.assertTrue(watch.ready());now[0]=15.
        self.assertFalse(watch.ready());watch.diagnostic['pending']=True
        self.assertFalse(watch.ready())
        watch.verified=15.;watch.diagnostic['pending']=False
        self.assertTrue(watch.ready())
        watch.error=ValueError('PL owner changed')
        with self.assertRaisesRegex(RuntimeError,'PL owner changed'):watch.ready()

    def test_runtime_guard_failure_is_not_swallowed(self):
        def reject():raise ValueError('changed')
        watch=RuntimeWatch(reject)
        try:
            watch.thread.join(timeout=2)
            with self.assertRaisesRegex(RuntimeError,'changed'):watch.require()
        finally:watch.close()

    def test_runtime_diagnostics_separate_scheduled_wakeup_and_check_cost(self):
        now=[10.]
        with patch('system_hdmi.threading.Thread.start'):
            watch=RuntimeWatch(lambda:now.__setitem__(0,now[0]+.2),clock=lambda:now[0])
        def wait(_):
            if watch.diagnostic['checks']!=0:return True
            now[0]=11.5
            return False
        with patch.object(watch.stopped,'wait',side_effect=wait):watch._run()
        row=watch.snapshot()
        self.assertEqual(row['checks'],1)
        self.assertAlmostEqual(row['wake_delay_ms'],500.)
        self.assertAlmostEqual(row['last_check_ms'],200.)
        self.assertFalse(row['pending'])
        self.assertAlmostEqual(watch.verified,11.7)

    def test_pending_check_cannot_refresh_verified_heartbeat(self):
        import threading
        entered=threading.Event();release=threading.Event();now=[10.]
        def blocked():
            entered.set();release.wait(3)
        watch=RuntimeWatch(blocked,clock=lambda:now[0])
        try:
            self.assertTrue(entered.wait(2))
            now[0]=15.
            row=watch.snapshot()
            self.assertTrue(row['pending']);self.assertEqual(row['checks'],0)
            self.assertEqual(row['verification_age_ms'],5000.)
            with self.assertRaisesRegex(RuntimeError,'expired'):watch.require()
        finally:release.set();watch.close()
