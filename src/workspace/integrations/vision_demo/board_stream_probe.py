"""Stopped-display autonomous raw-video test; restore paired recovery before free."""
import argparse,ctypes as C,fcntl,hashlib,json,signal,time
from pathlib import Path
from pynq import Overlay,PL,allocate
import numpy as np
from probe_checks import check_stall_continuity

def main():
    p=argparse.ArgumentParser();p.add_argument('--bit',required=True,type=Path);p.add_argument('--recovery',required=True,type=Path)
    p.add_argument('--recovery-sha',required=True);p.add_argument('--library',required=True,type=Path)
    p.add_argument('--display-library',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();report=dict(passed=False,physical_commands=False);buffers=[];loaded=False;display=None;native=None;ip=None
    if hashlib.sha256(a.recovery.read_bytes()).hexdigest()!=a.recovery_sha:raise RuntimeError('Recovery hash mismatch')
    if PL.bitfile_name!=str(a.recovery):raise RuntimeError('Existing PL owner is active')
    locks=[]
    for name in ('guardianloop-pl.lock','tobii_display.lock'):
        f=open('/run/lock/'+name,'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
    try:
        loaded=True;overlay=Overlay(str(a.bit))
        display=C.CDLL(str(a.display_library));display.display_open.argtypes=[C.POINTER(C.c_uint32)]
        display.display_frames.restype=C.c_uint32;display.display_close.restype=C.c_int
        native=C.CDLL(str(a.library));native.vision_live_open.argtypes=[C.POINTER(C.c_uint32)]
        native.vision_live_indices.restype=C.c_uint32
        for _ in range(6):
            b=allocate(shape=(720,1280,3),dtype=np.uint8);b[:]=0;b.flush();buffers.append(b)
        if not display.display_open((C.c_uint32*3)(*[b.physical_address for b in buffers[:3]])):raise RuntimeError('Display open failed')
        if not native.vision_live_open((C.c_uint32*3)(*[b.physical_address for b in buffers[3:]])):raise RuntimeError('Ring open failed')
        if not overlay.ip_dict.get('vision_core_0') or overlay.vision_core_0.read(0)!=0x56495332:
            raise RuntimeError('VIS2 streaming hardware required; raw video alone cannot pass this probe')
        ip=overlay.vision_core_0
        def config(value):
            end=time.monotonic()+1
            while True:
                if not ip.read(8):
                    if ip.read(4)==value:return
                    ip.write(4,value)
                if time.monotonic()>end:raise RuntimeError('Filter commit timed out')
                time.sleep(.002)
        def counts():
            return [ip.read(12),ip.read(16),ip.read(20)] if ip else [display.display_frames()]
        report['modes']=[]
        for mode in (range(9) if ip else [-1]):
            if ip:config(0x10|mode)
            start=time.monotonic();before=counts();previous=native.vision_live_indices();reads=writes=0
            while time.monotonic()-start<1:
                if not native.vision_live_health():raise RuntimeError('Ring health failed')
                cur=native.vision_live_indices();reads+=bool((cur^previous)&0x001f0000);writes+=bool((cur^previous)&0x1f000000);previous=cur
                time.sleep(.002)
            duration=time.monotonic()-start;after=counts();delta=[(v-u)&0xffffffff for u,v in zip(before,after)]
            if delta[0]<50 or reads<5 or writes<5:raise RuntimeError('Autonomous video did not advance')
            row=dict(mode=mode,seconds=duration,hdmi_hz=delta[0]/duration,observed_read_changes=reads,observed_write_changes=writes)
            if ip:
                row.update(camera_fps=delta[1]/duration,filter_pixels_per_second=delta[2]/duration)
                if delta[2]<40_000_000:raise RuntimeError('Pixel pipeline throughput below video rate')
            report['modes'].append(row)
        before=counts();start=time.monotonic();time.sleep(2);duration=time.monotonic()-start;after=counts()
        report['cpu_sleep']=check_stall_continuity(before,after,duration)
        if ip:config(0)
        if not native.vision_live_close():raise RuntimeError('Live DMA failed to halt')
        native=None
        if not display.display_close():raise RuntimeError('Display DMA failed to halt')
        display=None;report['passed']=True
    except BaseException as exc:report['error']=type(exc).__name__+': '+str(exc);raise
    finally:
        if native:
            try:native.vision_live_close()
            except Exception:pass
        if display:
            try:display.display_close()
            except Exception:pass
        if loaded:
            try:
                Overlay(str(a.recovery))
                if PL.bitfile_name!=str(a.recovery):raise RuntimeError('PL restore failed')
                report['recovery_verified']=True
            except BaseException as exc:
                report['recovery_error']=str(exc);a.output.write_text(json.dumps(report,indent=2))
                signal.signal(signal.SIGTERM,signal.SIG_IGN)
                while True:time.sleep(1)
        for b in buffers:b.freebuffer()
        a.output.write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
