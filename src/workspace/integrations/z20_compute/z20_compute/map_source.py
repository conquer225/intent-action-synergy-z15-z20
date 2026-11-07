"""Reuse the existing depth-NPZ / camera-to-world fusion input for map display."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .cloud import fuse_clouds
from .visual_wire import GeometryFrame


def load_fusion_geometry(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    manifest = json.loads(raw)
    views = manifest.get('views')
    if not isinstance(views, list) or not 1 <= len(views) <= 1024:
        raise ValueError('fusion manifest requires 1..1024 known camera poses')
    clouds, poses = [], []
    identity = hashlib.sha256(raw)
    total = 0
    for view in views:
        source = (path.parent/view['depth_npz']).resolve()
        source.relative_to(path.parent)
        with np.load(source, allow_pickle=False) as data:
            xyz, mask = data['xyz'], data['valid_mask']
            if xyz.shape != mask.shape+(3,) or mask.dtype != np.bool_:
                raise ValueError('depth xyz/valid_mask contract')
            points = np.asarray(xyz[mask], np.float64)
        total += len(points)
        if total > 2000000:raise ValueError('fusion input exceeds two million valid points')
        identity.update(points.astype('<f8').tobytes())
        clouds.append(points)
        poses.append(np.asarray(view['camera_to_world'], np.float64))
    points = fuse_clouds(clouds, poses, voxel_m=float(manifest.get('voxel_m', .005)))
    points = points[::max(1, (len(points)+65535)//65536)]
    trajectory = np.asarray([pose[:3, 3] for pose in poses])
    return GeometryFrame(points, trajectory=trajectory, units='m',
        frame_id='fusion:'+identity.hexdigest(), metric_verified=manifest.get('metric_verified', False))
