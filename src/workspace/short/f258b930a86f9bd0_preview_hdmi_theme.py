"""Render the HDMI theme to PNG files; no PYNQ, USB or register access."""
import argparse
from pathlib import Path
import json
import sys
import time

import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from system_hdmi import UnifiedDisplay,BOXES


class PreviewFrame(np.ndarray):
    def flush(self):pass


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--eye-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--portrait',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    renderer=UnifiedDisplay(args.eye_root,live=True,dimensions=(288,512))
    portrait=None
    if args.portrait:
        with Image.open(args.portrait) as original:
            if original.size!=(640,360):raise ValueError('Expected audited SD JPEG dimensions')
            image=original.crop((218,0,420,360)).resize((288,512),Image.BILINEAR)
            portrait=np.asarray(image)[:,:,::-1].copy()
    for page in ('home','speed','video_rate','video_nav','video'):
        renderer.controller._enter(page,time.monotonic())
        renderer.refresh_labels({'emotion':{'valid':False},'fatigue':{'valid':False}},
                                {'state':'未标定'},'小狗（SD竖版）')
        frame=np.empty((720,1280,3),dtype=np.uint8).view(PreviewFrame)
        renderer.compose(frame,0,portrait if page=='video' else None)
        Image.fromarray(frame[:,:,::-1]).save(args.output/(page+'.png'))
    (args.output/'layout.json').write_text(json.dumps(dict(
        software_render_only=True,physical_output_enabled=False,audio_output=False,
        card_boxes=BOXES,video_roi=renderer.roi,label_bounds=renderer.label_bounds),
        ensure_ascii=False,indent=2),encoding='utf-8')
    print('HDMI_THEME_SOFTWARE_PREVIEWS_READY',args.output)


if __name__=='__main__':main()
