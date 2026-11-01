"""Stopped-display real-PL numerical check; always restore verified recovery PL."""
import argparse,fcntl,hashlib,json,signal,time
from pathlib import Path
import numpy as np
from pynq import Overlay,PL
from vision_demo.pl_processor import PLProcessor
from vision_demo.processing import ReferenceProcessor
from vision_demo.session import MODES

def main():
    p=argparse.ArgumentParser();p.add_argument('--bit',type=Path,required=True);p.add_argument('--recovery',type=Path,required=True)
    p.add_argument('--camera-library',type=Path);p.add_argument('--recovery-sha',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if hashlib.sha256(a.recovery.read_bytes()).hexdigest()!=a.recovery_sha:raise RuntimeError('Recovery checksum mismatch')
    if PL.bitfile_name!=str(a.recovery):raise RuntimeError('Another PL owner is active')
    core=None;camera=None;capture_retained=False;loaded=False;report=dict(passed=False,scope='Real PL on synthetic numeric inputs; no gaze or physical actions')
    lock=open('/run/lock/guardianloop-pl.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        loaded=True;overlay=Overlay(str(a.bit));core=PLProcessor(overlay,width=16,height=12)
        report['keys_raw']=int(overlay.vision_keys_0.read(0));report['cases']=[]
        rng=np.random.default_rng(20261019)
        for name,_ in MODES:
            reference=ReferenceProcessor();durations=[]
            for index in range(3):
                rgb=rng.integers(0,256,(12,16,3),dtype=np.uint8);start=time.monotonic()
                output=core.process(rgb,name,reset=index==0);durations.append((time.monotonic()-start)*1000)
                np.testing.assert_array_equal(output,reference.process(rgb,name,reset=index==0))
            report['cases'].append(dict(mode=name,frames=3,exact_match=True,call_ms=durations))
        if a.camera_library:
            import cv2
            from vision_demo.sources import OV5640Source,CaptureCleanupError
            core.close();core=PLProcessor(overlay)
            try:camera=OV5640Source(a.camera_library,1)
            except CaptureCleanupError as exc:camera=exc.owner;raise
            report['real_camera']=[]
            for name,_ in MODES[:9]:
                reference=ReferenceProcessor();durations=[]
                for index in range(2):
                    frame=camera.read(time.monotonic());start=time.monotonic()
                    output=core.process(frame.rgb,name,reset=index==0)
                    durations.append((time.monotonic()-start)*1000)
                    expected=reference.process(cv2.resize(frame.rgb,(320,180),interpolation=cv2.INTER_AREA),name,reset=index==0)
                    np.testing.assert_array_equal(output,expected)
                report['real_camera'].append(dict(mode=name,frames=2,source_shape=list(frame.rgb.shape),pl_shape=list(output.shape),exact_match=True,call_ms=durations))
        report['passed']=True
    finally:
        if camera:
            try:camera.close()
            except RuntimeError:capture_retained=True
        if core and not core.running:core.close()
        if loaded:
            try:
                Overlay(str(a.recovery))
                if PL.bitfile_name!=str(a.recovery):raise RuntimeError('Recovery PL did not verify')
            except Exception as exc:
                report['recovery_error']=str(exc);a.output.write_text(json.dumps(report,indent=2))
                if (core and core.running) or capture_retained:
                    signal.signal(signal.SIGTERM,signal.SIG_IGN);signal.signal(signal.SIGINT,signal.SIG_IGN)
                    while True:time.sleep(1)
                raise
        if camera and capture_retained:camera.release_after_reset()
        if core:core.close(pl_reset=True)
        report['recovery_verified']=PL.bitfile_name==str(a.recovery)
        a.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
if __name__=='__main__':main()
