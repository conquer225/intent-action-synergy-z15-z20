"""Observation-camera setup for the PL map renderer; source geometry stays intact."""
import math
import numpy as np
from .mapping import MapScene


class MapView:
    def __init__(self, backend, *, width=1280, height=720):
        self.backend, self.width, self.height = backend, width, height

    def render_geometry(self, geometry, *, view=0, sequence=0):
        rows = np.concatenate((geometry.points, geometry.trajectory))
        center = np.median(rows, axis=0) if len(rows) else np.zeros(3)
        span = max(float(np.ptp(rows, axis=0).max()), .1) if len(rows) else 1.
        yaw, pitch = ((0., 0.), (math.pi/2, 0.), (0., -math.pi/2))[view % 3]
        cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
        rotation = np.array([[cy, 0, sy], [sp*sy, cp, -sp*cy], [-cp*sy, sp, cp*cy]])
        camera = np.eye(4)
        camera[:3, :3] = rotation/span
        camera[:3, 3] = -rotation @ center/span + [0, 0, 2.5]
        scene = MapScene(geometry.points, colors=geometry.colors, trajectory=geometry.trajectory,
                         width=self.width, height=self.height, focal=min(self.width, self.height)*1.5,
                         camera=camera, near=.05, far=10., radius=1, units=geometry.units,
                         frame_id=geometry.frame_id, sequence=sequence)
        frame, stats = self.backend.render(scene)
        return frame, dict(stats, view=view % 3, metric_verified=geometry.metric_verified)

    def close(self):self.backend.close()
