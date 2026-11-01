"""Fixed-ROI identity preprocessing, without a face detector or display writes."""
import cv2
import numpy as np


def face_features(frame, roi):
    frame = np.asarray(frame)
    if frame.dtype != np.uint8 or frame.ndim not in (2, 3):
        raise ValueError("expected GRAY8 or BGR888 frame")
    if frame.ndim == 3:
        if frame.shape[2] != 3:
            raise ValueError("expected three BGR channels")
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    x, y, width, height = roi
    if (any(type(v) is not int for v in roi) or min(x, y) < 0 or min(width, height) <= 0
            or x+width > frame.shape[1] or y+height > frame.shape[0]):
        raise ValueError("face ROI outside capture frame")
    crop = frame[y:y+height, x:x+width]
    if crop.std() < 3 or crop.mean() < 5 or crop.mean() > 250:
        raise ValueError("ROI empty, flat or exposure outside usable range")
    return (cv2.resize(crop, (32, 32), interpolation=cv2.INTER_AREA).reshape(-1)/255.).astype(np.float32)
