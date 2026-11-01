"""CPU reference only; the on-board PL adapter never silently falls back here."""
import cv2
import numpy as np
from .session import MODES


def luminance(rgb):
    wide = np.asarray(rgb, dtype=np.uint32)
    return ((77*wide[..., 0] + 150*wide[..., 1] + 29*wide[..., 2] + 128) >> 8).astype(np.uint8)


def palette(level):
    """Deterministic black-to-cyan-to-yellow colour map; not thermal sensing."""
    value = level.astype(np.uint16)
    return np.stack((np.minimum(value*2, 255), value,
                     np.minimum(value*3, 255)), axis=-1).astype(np.uint8)


class ReferenceProcessor:
    backend = 'CPU reference / OpenCV'

    def __init__(self, threshold=127):
        self.threshold = threshold
        self.previous = self.trail = None

    def reset(self):
        self.previous = self.trail = None

    def process(self, rgb, mode, reset=False):
        if mode not in dict(MODES):
            raise ValueError('Unknown image mode')
        if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError('Expected RGB8 image')
        if type(self.threshold) is not int or not 0 <= self.threshold <= 255:
            raise ValueError('Invalid threshold')
        gray = luminance(rgb)
        fresh = reset or self.previous is None or self.previous.shape != gray.shape
        delta = np.zeros_like(gray) if fresh else cv2.absdiff(gray, self.previous)
        old_trail = np.zeros_like(gray) if fresh else self.trail
        trail = np.maximum(delta, (old_trail.astype(np.uint16)*7 >> 3).astype(np.uint8))
        self.previous, self.trail = gray.copy(), trail
        if mode == 'original':
            return rgb.copy()
        if mode in ('trails', 'motion'):
            value = trail if mode == 'trails' else delta
            output = np.repeat((gray >> 2)[..., None], 3, axis=2)
            mask = value > 16
            output[mask] = palette(value)[mask]
            return output
        if mode in ('sobel', 'neon'):
            x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, borderType=cv2.BORDER_REPLICATE)
            y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, borderType=cv2.BORDER_REPLICATE)
            edge = np.clip(np.abs(x).astype(np.int32)+np.abs(y).astype(np.int32), 0, 255).astype(np.uint8)
            if mode == 'neon':
                edge[edge < 32] = 0
                return palette(edge)
            gray = edge
        elif mode == 'median':
            gray = cv2.medianBlur(gray, 3)
        elif mode == 'binary':
            gray = cv2.threshold(gray, self.threshold, 255, cv2.THRESH_BINARY)[1]
        elif mode == 'equalize':
            gray = cv2.equalizeHist(gray)
        return np.repeat(gray[..., None], 3, axis=2)
