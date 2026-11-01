"""Depth-map backprojection and an edge-aware visible-surface mesh.

Coordinate units are inherited from the supplied depth; this module adds no scale.
"""
from dataclasses import dataclass
from pathlib import Path
import numpy as np


@dataclass
class DepthSurface:
    vertices: np.ndarray
    colors: np.ndarray
    faces: np.ndarray


def depth_surface(depth, bgr, K, *, stride=1, max_relative_jump=.08):
    depth = np.asarray(depth, np.float64)
    bgr, K = np.asarray(bgr), np.asarray(K, np.float64)
    if (depth.ndim != 2 or bgr.shape != (*depth.shape, 3) or bgr.dtype != np.uint8
            or K.shape != (3, 3) or not np.isfinite(K).all()
            or min(K[0, 0], K[1, 1]) <= 0 or not np.allclose(K[2], [0, 0, 1])
            or type(stride) is not int or stride < 1
            or not np.isfinite(max_relative_jump) or max_relative_jump <= 0):
        raise ValueError('depth, BGR pixels, pinhole intrinsics and positive mesh limits required')
    if K[0, 1] != 0 or K[1, 0] != 0:
        raise ValueError('zero-skew intrinsics required')
    y, x = np.indices(depth.shape)
    z = depth[::stride, ::stride]
    u, v = x[::stride, ::stride], y[::stride, ::stride]
    valid = np.isfinite(z) & (z > 0)
    xyz = np.stack(((u-K[0, 2])*z/K[0, 0],
                    (v-K[1, 2])*z/K[1, 1], z), axis=-1)
    indices = np.full(z.shape, -1, np.int64)
    indices[valid] = np.arange(int(valid.sum()))
    a, b = indices[:-1, :-1], indices[:-1, 1:]
    c, d = indices[1:, :-1], indices[1:, 1:]
    triangles = np.concatenate((np.stack((a, c, b), -1).reshape(-1, 3),
                                np.stack((b, c, d), -1).reshape(-1, 3)))
    triangles = triangles[(triangles >= 0).all(axis=1)]
    vertices = xyz[valid].astype(np.float32)
    if len(triangles):
        triangle_z = vertices[triangles, 2]
        keep = np.ptp(triangle_z, axis=1) <= max_relative_jump * triangle_z.min(axis=1)
        triangles = triangles[keep]
    colors = bgr[::stride, ::stride, ::-1][valid].copy()
    return DepthSurface(vertices, colors, triangles.astype(np.int32))


def write_surface_ply(path, surface, *, provenance, mesh=True):
    """Write colors and optional faces, with an explicit provenance comment."""
    if '\n' in provenance or '\r' in provenance:
        raise ValueError('PLY provenance must be one line')
    faces = surface.faces if mesh else np.empty((0, 3), np.int32)
    with Path(path).open('w', encoding='ascii') as stream:
        stream.write('ply\nformat ascii 1.0\ncomment '+provenance+'\n'
                     f'element vertex {len(surface.vertices)}\n'
                     'property float x\nproperty float y\nproperty float z\n'
                     'property uchar red\nproperty uchar green\nproperty uchar blue\n'
                     f'element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n')
        for vertex, color in zip(surface.vertices, surface.colors):
            stream.write('%.6f %.6f %.6f %d %d %d\n' % tuple([*vertex, *color]))
        for face in faces:
            stream.write('3 %d %d %d\n' % tuple(face))
