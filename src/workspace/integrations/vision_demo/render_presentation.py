"""Render actual HDMI surfaces without connecting hardware or sending commands."""
import sys,time,os
from pathlib import Path
import numpy as np
from PIL import Image

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
runtime=HERE.parent/'eeg_demo/runtime'
eye=HERE.parent/'guardianloop_team_20261017_03/projects/codex_project/brain_eye_coexist/candidate/eye'
if not eye.exists():eye=Path(os.environ.get('GL_BASELINE_ROOT',str(ROOT.parent)))/'projects/codex_project/brain_eye_coexist/candidate/eye'
sys.path[:0]=[str(runtime),str(runtime/'system_runtime'),str(eye/'src')]
from system_hdmi import UnifiedDisplay
from guide import View

class Buffer(np.ndarray):
 def flush(self):pass
class InactiveLink:
 def snapshot(self):return dict(enabled=None,connected=False,pending=False,debug_hold=True,message='等待启用')
 def stop(self,reason):pass

def main():
 out=HERE/'report/presentation';(out/'hdmi').mkdir(parents=True,exist_ok=True)
 display=UnifiedDisplay(eye,live=True,device_link=InactiveLink())
 pages={'home':'主页','equipment':'设备与方向','hand':'灵巧手','pendulum_menu':'倒立摆',
  'pendulum_balance':'平衡控制','pendulum_turn':'短动作','speed':'速度选择','music':'音乐',
  'video_nav':'视频导航','speech':'表达'}
 for page in pages:
  display.controller._enter(page,time.monotonic())
  display.refresh_labels({},dict(state='待标定'),'')
  frame=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
  display.compose(frame,0,None)
  Image.fromarray(frame[:,:,::-1]).save(out/'hdmi'/(page+'.png'))
 frame=display.renderer.render(View(phase='positioning',detail='调整坐姿，使双眼进入跟踪范围'))
 Image.fromarray(frame[:,:,::-1]).save(out/'hdmi/eye_positioning.png');pages['eye_positioning']='眼控定位'
 cards=''.join('<figure><img src="/hdmi/%s.png" alt="%s"><figcaption>%s</figcaption></figure>'%(p,t,t) for p,t in pages.items())
 (out/'gallery.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>我们意念合一 · HDMI 界面</title><link rel="stylesheet" href="/presentation.css"><main><div class="site-nav"><h1>HDMI 界面</h1><a href="/">脑电与音乐</a></div><div class="gallery-grid">'+cards+'</div></main></html>',encoding='utf-8')
 print('NATIVE_PRESENTATION_PAGES',len(pages))
if __name__=='__main__':main()
