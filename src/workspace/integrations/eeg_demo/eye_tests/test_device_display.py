import sys
from pathlib import Path
import time
import unittest
import os

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'runtime'), str(ROOT/'runtime/system_runtime')]
from test_eye_devices import Link
from system_hdmi import UnifiedDisplay

EYE = Path(os.environ.get('GL_BASELINE_ROOT',str(ROOT.parent/'guardianloop_team_20261017_03')))/'projects/codex_project/brain_eye_coexist/candidate/eye'


class Buffer(np.ndarray):
    def flush(self): pass


class DisplayTests(unittest.TestCase):
    def test_ack_changes_status_keeps_action_labels_and_original_video_roi(self):
        link = Link()
        display = UnifiedDisplay(str(EYE), live=True, dimensions=(288,512), device_link=link,
                                 font_paths=('C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/arial.ttf') if os.name=='nt' else None)
        now=time.monotonic(); controller=display.controller
        controller._enter('hand', now)
        display.refresh_labels({}, {}, 'clip')
        output=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        display.compose(output,0,now=now)
        stopped=output.copy()
        labels=controller.labels()
        link.view.update(connected=True, enabled='hand', pending=False, message='设备就绪，请换区选择动作')
        controller.device_update(now)
        self.assertTrue(display.refresh_labels({}, {}, 'clip'))
        display.compose(output,0,now=now)
        self.assertEqual(controller.labels(), labels)
        self.assertGreater(np.count_nonzero(output[20:130]!=stopped[20:130]),100)
        self.assertTrue(np.array_equal(output[200:500],stopped[200:500]))
        self.assertEqual(display.roi,(505,148,270,480))
        self.assertFalse(display.tasks_for('hand')['ssvep_candidate'])
        folder=ROOT/'report/previews';folder.mkdir(parents=True,exist_ok=True)
        for page in ('home','equipment','hand','pendulum_menu','pendulum_balance','pendulum_turn'):
            controller._enter(page,now)
            if page in ('hand','pendulum_balance','pendulum_turn'):
                link.view.update(connected=True,enabled='hand' if page=='hand' else 'pendulum',
                                 pending=False,message='设备就绪，请换区选择动作')
                controller.device_update(now)
            display.refresh_labels({}, {}, 'clip');display.compose(output,0,now=now)
            Image.fromarray(output[:,:,::-1]).save(folder/(page+'.png'))

    def test_stop_changes_centre_and_updates_same_page_overlay(self):
        link=Link()
        display=UnifiedDisplay(str(EYE),live=True,device_link=link,
            font_paths=('C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/arial.ttf') if os.name=='nt' else None)
        now=time.monotonic();controller=display.controller
        controller._enter('hand',now)
        controller.presented(controller.page_id,now);now+=1.3
        display.refresh_labels({}, {}, 'clip')
        before=display.overlays['hand'].copy()
        controller.choose(1,now)
        self.assertEqual(controller.page,'hand')
        self.assertEqual(controller.device_presentation()['badge'],'已停止')
        self.assertTrue(display.refresh_labels({}, {}, 'clip'))
        self.assertGreater(np.count_nonzero(display.overlays['hand'][250:500,450:830]!=before[250:500,450:830]),100)
        folder=ROOT/'report/previews';folder.mkdir(parents=True,exist_ok=True)
        output=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
        display.compose(output,0,now=now)
        Image.fromarray(output[:,:,::-1]).save(folder/'hand_stopped.png')
        controller.return_pending=False
        link.view.update(connected=False,enabled=None,pending=False,message='连接中断，请重新连接')
        display.refresh_labels({}, {}, 'clip');display.compose(output,0,now=now)
        Image.fromarray(output[:,:,::-1]).save(folder/'hand_disconnected.png')


if __name__ == '__main__': unittest.main()
