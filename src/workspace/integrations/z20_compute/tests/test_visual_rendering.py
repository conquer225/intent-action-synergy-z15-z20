import threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from z20_compute.visual_demo import DemoState
from z20_compute.visual_display import DemoDisplay
from z20_compute.visual_pipeline import VisualPipeline
from z20_compute.headless_display import ACCENT,LINE
from z20_compute.headless_pipeline import HeadlessPipeline


class Font:
    def text(self,*args,**kwargs):pass


class RenderingTests(unittest.TestCase):
    def test_remote_frame_does_not_allocate_a_discarded_local_canvas(self):
        state=DemoState();state.attach_renderer();state.command('test',1,'enter')
        decoded=np.zeros((720,1280,3),np.uint8)
        display=DemoDisplay(Font(),decoder=lambda jpeg:decoded)
        with patch('z20_compute.visual_display.np.empty',side_effect=AssertionError('discarded canvas allocated')):
            actual,_=display.render(state.snapshot(),(state.epoch,1,b'valid'))
        self.assertIs(actual,decoded)

    def test_visual_snapshot_polling_leaves_cpu_for_display(self):
        waits=[]
        class Stop:
            def is_set(self):return len(waits)>=3
            def wait(self,seconds):waits.append(seconds)
        pipeline=HeadlessPipeline.__new__(HeadlessPipeline)
        pipeline.camera=SimpleNamespace(latest=lambda:None)
        pipeline.visual=object();pipeline.stopped=Stop();pipeline.errors={};pipeline.lock=threading.Lock()
        pipeline._vision_loop()
        self.assertEqual(pipeline.errors,{})
        self.assertEqual(len(waits),3)
        self.assertTrue(all(seconds>=.1 for seconds in waits))

    def test_local_npu_ignores_remote_jpeg_sequence(self):
        state=DemoState();state.attach_renderer()
        for i,command in enumerate(('right','right','enter'),1):state.command('test',i,command)
        display=DemoDisplay(Font())
        first,key=display.render(state.snapshot(),(state.epoch,1,b'one'))
        second,next_key=display.render(state.snapshot(),(state.epoch,2,b'two'))
        self.assertEqual(key,next_key)
        self.assertIs(first,second)
        self.assertEqual(second.shape,(720,1280,3))

    def test_result_names_and_real_processing_are_visible_without_hidden_node_animation(self):
        labels=[]
        class RecordingFont:
            def text(self,frame,value,*args,**kwargs):labels.append(str(value))
        state=DemoState();state.attach_renderer()
        for i,command in enumerate(('right','right','enter'),1):state.command('test',i,command)
        state.publish('npu',dict(task='fatigue',valid=True,class_id=1,scores=[1.,3.,2.],quantized_features=[0]*20,event='completed',backend='PL_z20_mlp',integer_reference_equal=True),epoch=state.epoch)
        DemoDisplay(RecordingFont()).render(state.snapshot(),None)
        self.assertIn('轻度疲劳',labels);self.assertIn('20 项实际输入特征',labels)
        self.assertIn('全连接 / ReLU / 三输出',labels)

    def test_slow_png_preview_does_not_block_display_updates(self):
        stopped=threading.Event();entered=threading.Event();release=threading.Event()
        pipeline=SimpleNamespace(renderer=SimpleNamespace(font=Font()),lock=threading.Lock(),
            stopped=stopped,display=None,frames=0,display_matches=0,preview=Path('unused.png'))
        state=DemoState();visual=VisualPipeline(pipeline,state)
        frame=np.zeros((720,1280,3),np.uint8);counter=[0]
        def render(*_):
            counter[0]+=1
            return frame,counter[0]
        def slow_preview(*args,**kwargs):entered.set();release.wait(2)
        visual.display.render=render
        with patch('z20_compute.headless_preview.publish_frame',side_effect=slow_preview):
            thread=threading.Thread(target=visual.render_loop);thread.start()
            try:
                self.assertTrue(entered.wait(1))
                deadline=time.monotonic()+.25
                while pipeline.frames<3 and time.monotonic()<deadline:time.sleep(.005)
                self.assertGreaterEqual(pipeline.frames,3)
            finally:stopped.set();release.set();thread.join(2)
        self.assertFalse(thread.is_alive())
