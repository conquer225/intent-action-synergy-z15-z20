"""Compare actual label-render methods in a private process and ordinary RAM."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

from profile_video_ram import DISPLAY, SESSION, Timings, verify_pins


def benchmark(path):
    pins=verify_pins()
    if path.resolve().parent not in [Path(__file__).resolve().parent/name
                                   for name in ('bgr-candidate','bgr-strip-candidate')]:
        raise ValueError('Candidate must remain inside the private profile directory')
    spec=importlib.util.spec_from_file_location('candidate_hdmi',path)
    candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
    sys.path.insert(0,str(DISPLAY))
    import system_hdmi as active
    state=json.loads((DISPLAY/(SESSION+'.json')).read_text())
    display=active.UnifiedDisplay(state['eye_root'],live=True,dimensions=(288,512),
                                 shell_cache=DISPLAY/'menu-shells-portrait-live.npz')
    timings=Timings()
    fixtures=[('video',dict(emotion=dict(valid=True,label=label),fatigue=dict(valid=True,level=level)))
              for label in ('boring','calm','funny','horror') for level in (0,1,2)]
    fixtures += [('video',dict(emotion=dict(valid=False,label='horror'),fatigue=dict(valid=False))),
                 ('video',dict(fatigue=dict(valid=False,calibration_retained=True)))]
    fixtures += [(page,{}) for page in ('home','speed','drive','media','video_nav','video_rate',
                                       'speech','music','music_offer','fatigue_alert')]
    golden=[]
    started=time.monotonic()
    for index,(page,row) in enumerate(fixtures):
        now=started+index
        display.controller._enter(page,now);display.controller.last_now=now;display.overlay_key=None
        with timings.measure('reference_label_refresh'):
            display.refresh_labels(row,{},'pinned clip')
        golden.append(hashlib.sha256(display.overlays[page].tobytes()).hexdigest())
    for index,((page,row),expected) in enumerate(zip(fixtures,golden)):
        now=started+index
        display.controller._enter(page,now);display.controller.last_now=now;display.overlay_key=None
        with timings.measure('candidate_label_refresh'):
            candidate.UnifiedDisplay.refresh_labels(display,row,{},'pinned clip')
        if hashlib.sha256(display.overlays[page].tobytes()).hexdigest()!=expected:
            raise ValueError('Full page pixels changed during BGR conversion replacement')
    for index in range(30):
        page,row=fixtures[index%14]
        now=started+index
        display.controller._enter(page,now);display.controller.last_now=now;display.overlay_key=None
        with timings.measure('candidate_video_label_refresh'):
            candidate.UnifiedDisplay.refresh_labels(display,row,{},'pinned clip')
        if hashlib.sha256(display.overlays[page].tobytes()).hexdigest()!=golden[index%14]:
            raise ValueError('Video strip composition changed full-frame pixels')
    if verify_pins()!=pins:
        raise ValueError('Protected display files changed')
    return dict(scope='actual_refresh_method_in_ordinary_RAM_no_DMA_or_screen_FPS',
        full_page_pixel_cases=len(fixtures),pages=sorted({page for page,_ in fixtures}),
        pixel_digests=golden,timings=timings.summary(),protected_hashes=pins,
        candidate_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        pl_loaded=False,live_labels_changed=False,physical_control=False,audio_output=False,
        note='Unchanged active controller/shell fixtures; actual candidate method uses '
             'Pillow raw BGR conversion. Any video-band optimization is pixel-compared '
             'against the original full-frame method. Nothing is installed into the display owner.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(benchmark(args.candidate),indent=2),flush=True)
