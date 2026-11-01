"""Acceptance checks for independently observed hardware counters."""
import math

def check_stall_continuity(before,after,seconds):
    if len(before)!=3 or len(after)!=3 or not math.isfinite(seconds) or seconds<=0:
        raise ValueError('Expected scan, camera and pixel counters over a positive interval')
    delta=[(current-previous)&0xffffffff for previous,current in zip(before,after)]
    if delta[0]/seconds<50:raise RuntimeError('HDMI video stopped during CPU sleep')
    if not delta[1]:raise RuntimeError('camera input stopped during CPU sleep')
    if delta[2]/seconds<40_000_000:raise RuntimeError('pixel pipeline stopped during CPU sleep')
    return dict(seconds=seconds,hdmi_hz=delta[0]/seconds,camera_fps=delta[1]/seconds,
                filter_pixels_per_second=delta[2]/seconds,ps_frame_submissions=0)
