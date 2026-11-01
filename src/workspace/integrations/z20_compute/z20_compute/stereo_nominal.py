"""PC-only experimental geometry with an explicitly assumed focal length.

Assumptions: equal square-pixel intrinsics, centered principal points, zero
distortion and a horizontal rig. Baseline length is one arbitrary unit.
This is separate from Calibration and cannot supply metric distances.
"""
from dataclasses import dataclass
import cv2
import numpy as np
from scipy.optimize import least_squares


@dataclass
class NominalRig:
    image_size: tuple
    K: np.ndarray
    R: np.ndarray
    T: np.ndarray
    points0: np.ndarray
    points1: np.ndarray
    xyz: np.ndarray
    valid_mask: np.ndarray
    reprojection_error_px: np.ndarray
    units: str = 'baseline_lengths'
    metric: bool = False


@dataclass
class NominalPreview:
    rectified0: np.ndarray
    rectified1: np.ndarray
    disparity: np.ndarray
    xyz: np.ndarray
    valid_mask: np.ndarray
    disparity_search: tuple
    units: str = 'baseline_lengths'
    metric: bool = False


def fit_nominal_rig(points0, points1, image_size, *, focal_px):
    """Fit rotation under the stated assumptions, choosing translation sign.

    Correspondences should already have passed robust image matching. Fitting
    error measures image agreement, not the truth of the assumed intrinsics.
    """
    a, b = [np.asarray(v, dtype=np.float64) for v in (points0, points1)]
    if (a.ndim != 2 or a.shape[1:] != (2,) or b.shape != a.shape or len(a) < 12
            or not np.isfinite(a).all() or not np.isfinite(b).all()
            or not np.isfinite(focal_px) or focal_px <= 0):
        raise ValueError('need at least twelve finite correspondences and a positive assumed focal length')
    width, height = image_size
    if width < 80 or height < 40:
        raise ValueError('invalid nominal image size')
    for points in (a, b):
        if np.linalg.svd(points-points.mean(0), compute_uv=False)[-1] < 1:
            raise ValueError('correspondences have insufficient two-dimensional spread')
    K = np.array([[focal_px, 0, (width-1)/2],
                  [0, focal_px, (height-1)/2], [0, 0, 1.]], dtype=np.float64)
    inv = np.linalg.inv(K)
    x, y = np.c_[a, np.ones(len(a))], np.c_[b, np.ones(len(b))]
    cross = np.array([[0., 0, 0], [0, 0, 1], [0, -1, 0]])

    def residual(rot):
        F = inv.T @ cross @ cv2.Rodrigues(rot)[0] @ inv
        fx, fy = x @ F.T, y @ F
        denominator = np.sqrt((fx[:, :2]**2).sum(1)+(fy[:, :2]**2).sum(1)+1e-20)
        return (y*fx).sum(1)/denominator

    solution = least_squares(residual, [0., 0, 0], bounds=(-.35, .35),
                             loss='soft_l1', f_scale=.5, max_nfev=300)
    R = cv2.Rodrigues(solution.x)[0]
    P0 = K @ np.c_[np.eye(3), np.zeros(3)]
    candidates = []
    for sign in (-1., 1.):
        T = np.array([sign, 0, 0.])
        P1 = K @ np.c_[R, T]
        homogeneous = cv2.triangulatePoints(P0, P1, a.T, b.T)
        with np.errstate(divide='ignore', invalid='ignore'):
            xyz = (homogeneous[:3]/homogeneous[3]).T
            other = xyz @ R.T+T
            errors = []
            for P, expected in ((P0, a), (P1, b)):
                projected = np.c_[xyz, np.ones(len(xyz))] @ P.T
                errors.append(np.linalg.norm(projected[:, :2]/projected[:, 2:]-expected, axis=1))
            error = np.maximum(*errors)
        valid = (np.isfinite(xyz).all(1) & (xyz[:, 2] > 0)
                 & (other[:, 2] > 0) & (error < 2.))
        candidates.append((int(valid.sum()), T, xyz, valid, error))
    _, T, xyz, valid, error = max(candidates, key=lambda value: value[0])
    if not solution.success or valid.sum() < 12:
        raise ValueError('nominal horizontal rig does not explain enough correspondences')
    return NominalRig(tuple(image_size), K, R, T.reshape(3, 1), a, b, xyz, valid, error)


def nominal_dense(image0, image1, rig):
    """SGBM preview with two-way consistency, using an assumed NominalRig.

    Results within thirty baseline lengths are retained for this diagnostic.
    Neither the sparse nor dense agreement verifies the physical shape.
    """
    width, height = rig.image_size
    a, b = [np.asarray(v) for v in (image0, image1)]
    if (a.shape != (height, width, 3) or b.shape != a.shape
            or a.dtype != np.uint8 or b.dtype != np.uint8 or rig.metric):
        raise ValueError('nominal preview requires matching uint8 BGR images and a nonmetric rig')
    R0, R1, P0, P1, Q, _, _ = cv2.stereoRectify(
        rig.K, None, rig.K, None, rig.image_size, rig.R, rig.T,
        flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)
    maps = [cv2.initUndistortRectifyMap(rig.K, None, R, P, rig.image_size, cv2.CV_32FC1)
            for R, P in ((R0, P0), (R1, P1))]
    rectified = [cv2.remap(image, *mapping, cv2.INTER_LINEAR)
                 for image, mapping in zip((a, b), maps)]
    points = [cv2.undistortPoints(p[rig.valid_mask, None], rig.K, None, R=R, P=P)[:, 0]
              for p, R, P in ((rig.points0, R0, P0), (rig.points1, R1, P1))]
    sparse_disparity = points[0][:, 0]-points[1][:, 0]
    low, high = np.percentile(sparse_disparity, [2, 98])
    minimum = int(np.floor((low-32)/16)*16)
    maximum = int(np.ceil((high+32)/16)*16)
    count = maximum-minimum
    if count <= 0 or count >= width:
        raise ValueError('nominal disparity search does not fit image width')

    def matcher(start):
        return cv2.StereoSGBM_create(minDisparity=start, numDisparities=count,
            blockSize=7, P1=8*49, P2=32*49, disp12MaxDiff=1, uniquenessRatio=8,
            speckleWindowSize=60, speckleRange=2, mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY)

    grey0, grey1 = [cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) for image in rectified]
    disparity = matcher(minimum).compute(grey0, grey1).astype(np.float32)/16
    reverse_minimum = -minimum-count+1
    reverse = matcher(reverse_minimum).compute(grey1, grey0).astype(np.float32)/16
    y, x = np.indices(disparity.shape)
    other_x = np.rint(x-disparity).astype(np.int32)
    inside = (other_x >= 0) & (other_x < width)
    safe = np.clip(other_x, 0, width-1)
    valid = ((disparity > minimum-1) & (abs(disparity) > .5) & inside
             & (reverse[y, safe] > reverse_minimum-1)
             & (abs(disparity+reverse[y, safe]) < 1.5))
    support = [cv2.remap(np.ones((height, width), np.uint8), *mapping, cv2.INTER_NEAREST) > 0
               for mapping in maps]
    valid &= support[0] & support[1][y, safe]
    xyz = cv2.reprojectImageTo3D(disparity, Q)
    valid &= np.isfinite(xyz).all(2) & (xyz[:, :, 2] > 0) & (xyz[:, :, 2] < 30)
    xyz[~valid] = np.nan
    return NominalPreview(*rectified, disparity, xyz, valid, (minimum, count))
