"""Board-local StereoBM and metric reprojection; PC and ARM share this source."""
from dataclasses import dataclass
import json
from pathlib import Path
import cv2
import numpy as np


@dataclass
class Calibration:
    image_size: tuple
    K1: object
    D1: object
    K2: object
    D2: object
    R: object
    T: object
    capture_mode: str

    def rectify(self):
        width, height = self.image_size
        if not isinstance(self.capture_mode, str) or not self.capture_mode or width < 80 or height < 40:
            raise ValueError("invalid calibration capture mode or size")
        k1, k2, r = [np.asarray(v, dtype=np.float64) for v in (self.K1, self.K2, self.R)]
        d1, d2, t = [np.asarray(v, dtype=np.float64).reshape(-1) for v in (self.D1, self.D2, self.T)]
        if (any(a.shape != (3, 3) for a in (k1, k2, r)) or d1.size != 5 or d2.size != 5 or t.size != 3
                or not all(np.isfinite(a).all() for a in (k1, k2, r, d1, d2, t))
                or np.linalg.norm(t) <= 0 or k1[0, 0] <= 0 or k1[1, 1] <= 0
                or k2[0, 0] <= 0 or k2[1, 1] <= 0
                or not np.allclose(r.T @ r, np.eye(3), atol=1e-5)
                or not np.isclose(np.linalg.det(r), 1, atol=1e-5)):
            raise ValueError("invalid metric calibration matrices")
        r1, r2, p1, p2, q, roi1, roi2 = cv2.stereoRectify(
            k1, d1, k2, d2, tuple(self.image_size), r, t.reshape(3, 1),
            flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)
        maps = [cv2.initUndistortRectifyMap(k, d, rect, p, tuple(self.image_size), cv2.CV_32FC1)
                for k, d, rect, p in [(k1, d1, r1, p1), (k2, d2, r2, p2)]]
        return maps, q

    def save(self, path):
        self.rectify()
        value = dict(format="z20-stereo-v1", units="m", pixel_mode="GRAY8",
                     image_size=list(self.image_size), capture_mode=self.capture_mode)
        value.update({name: np.asarray(getattr(self, name)).tolist() for name in ("K1", "D1", "K2", "D2", "R", "T")})
        Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")

    @classmethod
    def load(cls, path):
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if value.pop("format") != "z20-stereo-v1" or value.pop("units") != "m" or value.pop("pixel_mode") != "GRAY8":
            raise ValueError("unsupported calibration")
        value["image_size"] = tuple(value["image_size"])
        calibration = cls(**value)
        calibration.rectify()
        return calibration


@dataclass
class DepthResult:
    distance_m: object
    disparity: np.ndarray
    xyz: np.ndarray
    valid_mask: np.ndarray


class StereoProcessor:
    def __init__(self, calibration, *, disparities=64, block_size=15, depth_range=(.1, 10.)):
        self.calibration = calibration
        self.maps, self.q = calibration.rectify()
        self.depth_range = depth_range
        self.matcher = cv2.StereoBM_create(numDisparities=disparities, blockSize=block_size)
        self.matcher.setUniquenessRatio(15)
        self.matcher.setTextureThreshold(10)
        self.matcher.setSpeckleWindowSize(50)
        self.matcher.setSpeckleRange(2)

    def process(self, left, right, *, capture_mode, roi=None):
        expected = tuple(reversed(self.calibration.image_size))
        if capture_mode != self.calibration.capture_mode:
            raise ValueError("calibration does not match the capture mode")
        images = [np.asarray(a) for a in (left, right)]
        if any(a.shape != expected or a.dtype != np.uint8 for a in images):
            raise ValueError("expected calibrated-size GRAY8 stereo pair")
        images = [cv2.remap(a, *maps, interpolation=cv2.INTER_LINEAR) for a, maps in zip(images, self.maps)]
        disparity = self.matcher.compute(*images).astype(np.float32) / 16.0
        return self.from_disparity(disparity, roi=roi)

    def from_disparity(self, disparity, *, roi=None):
        disparity = np.asarray(disparity, dtype=np.float32)
        width, height = self.calibration.image_size
        if disparity.shape != (height, width):
            raise ValueError("disparity size does not match calibration")
        with np.errstate(invalid="ignore", divide="ignore"):
            xyz = cv2.reprojectImageTo3D(disparity, self.q)
        valid = ((disparity > 0) & np.isfinite(xyz).all(axis=2)
                 & (xyz[:, :, 2] >= self.depth_range[0]) & (xyz[:, :, 2] <= self.depth_range[1]))
        if roi is None:
            roi = ((width - 32)//2, (height - 32)//2, 32, 32)
        x, y, w, h = roi
        if any(type(v) is not int for v in roi) or min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
            raise ValueError("measurement ROI outside image")
        z = xyz[y:y+h, x:x+w, 2][valid[y:y+h, x:x+w]]
        distance = float(np.median(z)) if z.size >= 10 else None
        return DepthResult(distance, disparity, xyz, valid)


def write_ply(path, points):
    points = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    points = points[np.isfinite(points).all(axis=1)]
    with Path(path).open("w", encoding="ascii", newline="\n") as stream:
        stream.write("ply\nformat ascii 1.0\ncomment units metre\n")
        stream.write(f"element vertex {len(points)}\nproperty float x\nproperty float y\nproperty float z\nend_header\n")
        np.savetxt(stream, points, fmt="%.7g")
