"""Map registered boxes into actual captured pixels; absent matches stay empty."""
import numpy as np
import time

from .fixed_scene import describe_scene

PHOTO_CAPTURE_STEP=(4,4)


def photo_input_rgb(paired_bgr):
    """Expand the quarter-sampled main view in owned RAM, preserving aspect."""
    if (not isinstance(paired_bgr,np.ndarray) or paired_bgr.dtype!=np.uint8
            or paired_bgr.shape!=(180,320,3)):
        raise ValueError('expected quarter-sampled BGR stereo 320x180')
    return main_input_rgb(paired_bgr[:,:160])


def main_input_rgb(main_bgr):
    """Owned RGB view for the mono-depth demo; no right-camera pixels."""
    if (not isinstance(main_bgr,np.ndarray) or main_bgr.dtype!=np.uint8
            or main_bgr.shape!=(180,160,3)):
        raise ValueError('expected quarter-sampled BGR main camera 160x180')
    return np.ascontiguousarray(np.repeat(np.repeat(main_bgr[...,::-1],2,axis=0),2,axis=1))


def project_boxes(boxes,homography,size):
    h=np.asarray(homography,dtype=np.float64)
    if h.shape!=(3,3) or not np.isfinite(h).all():raise ValueError('invalid homography')
    result=[]
    for label in ('person','dog'):
        x0,y0,x1,y1=boxes[label]
        points=np.array([[x0,y0,1],[x1,y0,1],[x1,y1,1],[x0,y1,1]],float)@h.T
        if np.any(np.abs(points[:,2])<1e-8):raise ValueError('degenerate homography')
        points=points[:,:2]/points[:,2:]
        a=np.maximum(points.min(axis=0),[0,0])
        b=np.minimum(points.max(axis=0),np.asarray(size)-1)
        if not np.isfinite(points).all() or np.any(a>=b):raise ValueError('projected box outside image')
        result.append([float(a[0]),float(a[1]),float(b[0]),float(b[1])])
    return result


def camera_scene(rgb,media,entries,*,captured_ns=None,now_ns=time.monotonic_ns):
    match=media.match(rgb)
    result=dict(match=match,scene=None,display_boxes=None,camera_depth_m=None,
                camera_depth_state='requires_current_mode_stereo_calibration',
                input_source='actual_camera_pixels')
    if captured_ns is not None and now_ns()-captured_ns>2_000_000_000:
        result['match']=dict(scene_id=None,homography=None,inliers=0,state='expired_capture')
        return result
    if match['scene_id'] is not None:
        scene=describe_scene(entries[match['scene_id']],(640,480))
        try:boxes=project_boxes(scene['boxes'],match['homography'],(rgb.shape[1],rgb.shape[0]))
        except ValueError:
            result['match']=dict(scene_id=None,homography=None,inliers=0,state='invalid_projection')
            return result
        result.update(scene=scene,display_boxes=boxes)
    return result
