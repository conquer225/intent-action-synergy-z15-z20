"""Explicit labels and session groups; no random window split or invented labels."""
import json
from pathlib import Path
import cv2
import numpy as np
from scipy.io import wavfile
from .training import Dataset, DIMENSIONS
from .features import face_features
from .audio import resample_audio, sound_features
from .stereo import Calibration


def prepare_dataset(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    task = manifest["task"]
    if task not in DIMENSIONS:
        raise ValueError("unsupported classification task")
    features, labels, groups, splits = [], [], [], []
    recording_splits = {}
    for record in manifest["records"]:
        path = manifest_path.parent/record["path"]
        identity = path.resolve()
        if identity in recording_splits and recording_splits[identity] != record["split"]:
            raise ValueError("same recording path reused across splits")
        recording_splits[identity] = record["split"]
        kind = record["kind"]
        if type(record["label"]) is not int or record["label"] not in (0, 1, 2):
            raise ValueError("explicit class label 0, 1 or 2 required")
        if not isinstance(record["group"], str) or not record["group"]:
            raise ValueError("recording/session group required")
        if kind == "features":
            rows = np.load(path, allow_pickle=False)
            if rows.ndim == 1:
                rows = rows[None, :]
        elif kind == "image" and task == "face":
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise ValueError(f"cannot read image: {path}")
            rows = [face_features(image, tuple(record["roi"]))]
        elif kind == "wav" and task == "sound":
            rate, pcm = wavfile.read(path)
            if pcm.ndim != 1 or pcm.dtype not in (np.dtype("int16"), np.dtype("float32")):
                raise ValueError("use mono signed PCM16 or normalized float32 WAV")
            samples = pcm.astype(np.float64)/(32768 if pcm.dtype == np.int16 else 1)
            samples = resample_audio(samples, int(rate))
            rows = [sound_features(samples[offset:offset+16000])
                    for offset in range(0, len(samples)-15999, 16000)]
        elif kind == "eeg" and task in ("emotion", "fatigue"):
            from .legacy_eeg import LegacyEEGFeatures
            from .protocol import CHANNELS
            with np.load(path, allow_pickle=False) as recording:
                if int(recording["sample_rate_hz"]) != 250 or tuple(recording["channels"].tolist()) != CHANNELS:
                    raise ValueError("EEG requires 250Hz and the original eight-channel order")
                samples = recording["samples_uv"]
            adapter = LegacyEEGFeatures()
            rows = []
            for offset in range(0, len(samples), 250):
                for output in adapter.feed(samples[offset:offset+250]):
                    if output["task"] == task and output["valid"]:
                        rows.append(output["features"])
        else:
            raise ValueError("record type does not match task")
        if not len(rows):
            raise ValueError(f"no valid features after preprocessing: {path}")
        features.extend(rows)
        labels.extend([record["label"]]*len(rows))
        groups.extend([record["group"]]*len(rows))
        splits.extend([record["split"]]*len(rows))
    data = Dataset(np.asarray(features, dtype=np.float64), np.asarray(labels, dtype=np.int64),
                   np.asarray(groups), np.asarray(splits), manifest["source"], manifest["source_kind"])
    data.validate(task)
    return data


def calibrate_points(objects, left, right, image_size, capture_mode):
    if not (len(objects) == len(left) == len(right) and len(objects) >= 10):
        raise ValueError("at least ten matched chessboard views required")
    objects = [np.asarray(a, np.float32) for a in objects]
    left, right = [[np.asarray(a, np.float32) for a in points] for points in (left, right)]
    k1rms, k1, d1, _, _ = cv2.calibrateCamera(objects, left, image_size, None, None)
    k2rms, k2, d2, _, _ = cv2.calibrateCamera(objects, right, image_size, None, None)
    rms, k1, d1, k2, d2, r, t, _, _ = cv2.stereoCalibrate(
        objects, left, right, k1, d1, k2, d2, image_size,
        flags=cv2.CALIB_FIX_INTRINSIC,
        criteria=(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-7))
    calibration = Calibration(tuple(image_size), k1, d1.reshape(-1), k2, d2.reshape(-1), r, t, capture_mode)
    calibration.rectify()
    r1, r2, p1, p2, *_ = cv2.stereoRectify(k1, d1, k2, d2, image_size, r, t,
                                          flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)
    vertical = []
    for l, rr in zip(left, right):
        a = cv2.undistortPoints(l, k1, d1, R=r1, P=p1)
        b = cv2.undistortPoints(rr, k2, d2, R=r2, P=p2)
        vertical.extend(np.abs(a[:, 0, 1]-b[:, 0, 1]).tolist())
    report = dict(views=len(objects), left_rms_px=float(k1rms), right_rms_px=float(k2rms),
                  stereo_rms_px=float(rms), rectified_vertical_error_px=float(np.mean(vertical)),
                  baseline_m=float(np.linalg.norm(t)), image_size=list(image_size), capture_mode=capture_mode)
    return calibration, report


def calibrate_images(manifest_path, *, columns, rows, square_m, capture_mode):
    if min(columns, rows) < 3 or not np.isfinite(square_m) or square_m <= 0:
        raise ValueError("positive measured square size in metres and inner corner counts required")
    manifest_path = Path(manifest_path)
    pairs = json.loads(manifest_path.read_text(encoding="utf-8"))["pairs"]
    board = np.zeros((columns*rows, 3), np.float32)
    board[:, :2] = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2)*square_m
    objects, left_points, right_points, rejected, size = [], [], [], [], None
    for index, pair in enumerate(pairs):
        images = [cv2.imread(str(manifest_path.parent/pair[key]), cv2.IMREAD_GRAYSCALE) for key in ("left", "right")]
        if any(image is None for image in images):
            raise ValueError("cannot read a calibration pair")
        current = tuple(images[0].shape[::-1])
        if images[0].shape != images[1].shape or (size is not None and current != size):
            raise ValueError("calibration views must share the exact capture size")
        size = current
        corners = [cv2.findChessboardCornersSB(image, (columns, rows)) for image in images]
        if not all(found for found, _ in corners):
            rejected.append(index)
            continue
        objects.append(board.copy())
        left_points.append(corners[0][1]); right_points.append(corners[1][1])
    calibration, report = calibrate_points(objects, left_points, right_points, size, capture_mode)
    report["rejected_pairs"] = rejected
    report["square_size_m"] = square_m
    return calibration, report
