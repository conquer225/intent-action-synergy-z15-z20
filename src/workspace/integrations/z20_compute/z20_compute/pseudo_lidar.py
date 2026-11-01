"""PC pseudo-LiDAR from recorded or streamed Navigator stereo pairs.

The coordinate unit is one camera baseline; this module never produces metres.
"""

import argparse
import json
import re
import struct
import subprocess
import sys
import threading
from pathlib import Path

import cv2
import numpy as np

MAX_JPEG_BYTES = 2 * 1024 * 1024
BOARD_JPEG_COMMAND = 'cd /tmp/navigator-check && PYTHONPATH=. python3 jpeg_stdout.py'


def board_ssh_command(host):
    """Use the pinned board diagnostic without a local command shell."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', host):
        raise ValueError('expected a board IP address or hostname')
    return ['ssh', '-T', '-o', 'ConnectTimeout=5', f'root@{host}', BOARD_JPEG_COMMAND]


def _read_exact(stream, count, *, allow_eof=False):
    data = bytearray()
    while len(data) < count:
        chunk = stream.read(count - len(data))
        if not chunk:
            if allow_eof and not data:
                return None
            raise ValueError('truncated stereo JPEG stream')
        data.extend(chunk)
    return bytes(data)


def decode_pairs(stream):
    """Yield (sequence, left BGR, right BGR) from board's >II/JPEG stream."""
    while True:
        header = _read_exact(stream, 8, allow_eof=True)
        if header is None:
            return
        sequence, size = struct.unpack('>II', header)
        if not 1 <= size <= MAX_JPEG_BYTES:
            raise ValueError('JPEG size outside stream bound')
        image = cv2.imdecode(np.frombuffer(_read_exact(stream, size), np.uint8),
                            cv2.IMREAD_COLOR)
        if image is None or image.ndim != 3 or image.shape[1] % 2:
            raise ValueError('stereo stream requires an even-width BGR image')
        half = image.shape[1] // 2
        yield sequence, image[:, :half].copy(), image[:, half:].copy()


class LatestPair:
    """One-slot handoff; camera reading never waits for stereo matching."""

    def __init__(self):
        self._condition = threading.Condition()
        self._pair = None
        self._last_sequence = -1
        self._closed = False
        self._error = None

    def offer(self, sequence, left, right):
        with self._condition:
            if sequence <= self._last_sequence or self._closed:
                return False
            self._last_sequence = sequence
            self._pair = (sequence, left, right)
            self._condition.notify()
            return True

    def close(self, error=None):
        with self._condition:
            self._closed = True
            self._error = error
            self._condition.notify_all()

    def take(self, timeout=None):
        with self._condition:
            if self._pair is None and not self._closed:
                self._condition.wait(timeout)
            pair, self._pair = self._pair, None
            if pair is None and self._error is not None:
                raise self._error
            return pair

    @property
    def closed(self):
        with self._condition:
            return self._closed


def estimate_nominal_rig(left, right, *, focal_px):
    """Match one stereo pair and fit the explicitly assumed horizontal rig."""
    from .stereo_nominal import fit_nominal_rig
    if left.shape != right.shape or left.dtype != np.uint8 or left.ndim != 3 or left.shape[2] != 3:
        raise ValueError('matching uint8 BGR images required')
    cv2.setRNGSeed(42)
    sift = cv2.SIFT_create(nfeatures=6000, contrastThreshold=.012, edgeThreshold=15)
    descriptors = [sift.detectAndCompute(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), None)
                   for image in (left, right)]
    (keys0, desc0), (keys1, desc1) = descriptors
    if desc0 is None or desc1 is None or min(len(desc0), len(desc1)) < 12:
        raise ValueError('too few image features for nominal stereo')
    matcher = cv2.BFMatcher()
    forward = matcher.knnMatch(desc0, desc1, k=2)
    backward = matcher.knnMatch(desc1, desc0, k=2)
    reverse = {match.queryIdx: match.trainIdx for pair in backward if len(pair) == 2
               for match, other in [pair] if match.distance < .75 * other.distance}
    matches = [match for pair in forward if len(pair) == 2
               for match, other in [pair]
               if match.distance < .75 * other.distance
               and reverse.get(match.trainIdx) == match.queryIdx]
    if len(matches) < 12:
        raise ValueError('too few mutual stereo matches')
    points0 = np.float32([keys0[match.queryIdx].pt for match in matches])
    points1 = np.float32([keys1[match.trainIdx].pt for match in matches])
    fundamental, mask = cv2.findFundamentalMat(
        points0, points1, cv2.USAC_MAGSAC, 1., .999, 10000)
    if fundamental is None or mask is None or int(mask.sum()) < 12:
        raise ValueError('too few robust stereo correspondences')
    points0, points1 = points0[mask.ravel() > 0], points1[mask.ravel() > 0]
    rig = fit_nominal_rig(points0, points1, left.shape[1::-1], focal_px=focal_px)
    return rig, {'mutual_matches': len(matches), 'fundamental_inliers': len(points0),
                 'sparse_inliers': int(rig.valid_mask.sum()), 'assumed_focal_px': focal_px,
                 **assess_nominal_geometry(points0, points1, rig)}


def assess_nominal_geometry(points0, points1, rig):
    """Expose single-pair ambiguity and alignment, rather than using point count as quality."""
    a, b = np.asarray(points0, np.float32), np.asarray(points1, np.float32)
    _, mask = cv2.findHomography(a, b, cv2.USAC_MAGSAC, 1.5,
                                maxIters=10000, confidence=.999)
    planar = float(mask.mean()) if mask is not None else 0.
    area = float(np.prod(rig.image_size))
    coverage = [float(cv2.contourArea(cv2.convexHull(p))) / area for p in (a, b)]
    R0, R1, P0, P1, *_ = cv2.stereoRectify(
        rig.K, None, rig.K, None, rig.image_size, rig.R, rig.T,
        flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)
    rectified = [cv2.undistortPoints(p[rig.valid_mask, None], rig.K, None, R=R, P=P).reshape(-1, 2)
                 for p, R, P in ((a, R0, P0), (b, R1, P1))]
    vertical = abs(rectified[0][:, 1] - rectified[1][:, 1])
    warnings = []
    if planar >= .8:
        warnings.append('predominantly_planar_matches')
    if min(coverage) < .05:
        warnings.append('small_feature_coverage')
    if float(np.percentile(vertical, 95)) > 2.:
        warnings.append('large_rectified_vertical_residual')
    return {'geometry_status': 'weak_single_pair' if warnings else 'assumed_geometry',
            'geometry_verified': False, 'warnings': warnings,
            'homography_inlier_ratio': planar, 'feature_hull_coverage': coverage,
            'rectified_vertical_p95_px': float(np.percentile(vertical, 95)),
            'sparse_reprojection_median_px': float(np.median(
                rig.reprojection_error_px[rig.valid_mask]))}


def save_preview(sequence, left, right, rig, output, *, quality=None):
    """Save an independently labelled nonmetric cloud and disparity preview."""
    from .stereo_nominal import nominal_dense
    result = nominal_dense(left, right, rig)
    valid = result.valid_mask
    if int(valid.sum()) < 100:
        raise ValueError('too few consistent disparity pixels')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    points = result.xyz[valid]
    colors = cv2.cvtColor(result.rectified0, cv2.COLOR_BGR2RGB)[valid]
    cloud = output / f'cloud-{sequence:010d}.ply'
    with cloud.open('w', encoding='ascii') as stream:
        stream.write('ply\nformat ascii 1.0\n'
                     'comment pseudo-LiDAR; nonmetric assumed stereo geometry\n'
                     'comment units baseline_lengths; NOT metres\n'
                     f'element vertex {len(points)}\n'
                     'property float x\nproperty float y\nproperty float z\n'
                     'property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
        for vertex, color in zip(points, colors):
            stream.write('%.6f %.6f %.6f %d %d %d\n' % tuple([*vertex, *color]))
    disparity = result.disparity.astype(np.float32)
    displayed = np.zeros(disparity.shape, np.uint8)
    shown = disparity[valid]
    low, high = np.percentile(shown, [2, 98])
    if high > low:
        displayed[valid] = np.clip((shown - low) * 255 / (high - low), 0, 255).astype(np.uint8)
    colored = cv2.applyColorMap(displayed, cv2.COLORMAP_TURBO)
    colored[~valid] = 0
    cv2.imwrite(str(output / f'disparity-{sequence:010d}.png'), colored)
    depth_file = f'depth-{sequence:010d}.npz'
    np.savez_compressed(output/depth_file, xyz=result.xyz, valid_mask=valid,
                        disparity=result.disparity, rectified0=result.rectified0,
                        metric=np.array(False), units=np.array('baseline_lengths'))
    record = {**(quality or {}), 'geometry_verified': False,
              'sequence': sequence, 'valid': True, 'points': len(points),
              'units': 'baseline_lengths', 'metric': False,
              'assumed_focal_px': float(rig.K[0, 0]),
              'cloud': cloud.name, 'depth_data': depth_file,
              'disparity': f'disparity-{sequence:010d}.png'}
    (output / 'latest.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def invalidate_preview(sequence, output, reason, *, units='baseline_lengths',
                       depth_source='stereo_correspondence'):
    """Publish invalid status so a viewer cannot mistake a prior cloud for live data."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    record = {'sequence': sequence, 'valid': False, 'points': 0,
              'units': units, 'depth_source': depth_source,
              'metric': False, 'reason': reason}
    (output / 'latest.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description='Nonmetric stereo pseudo-LiDAR on the PC')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--npy', type=Path, help='saved 720x1280 BGR stereo frame')
    source.add_argument('--stdin-jpeg', action='store_true', help='board >II/JPEG stdout stream')
    source.add_argument('--ssh-host', help='read the board JPEG diagnostic over SSH')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--focal-px', type=float, default=600.,
                        help='assumed focal length at 640px per camera; not calibration')
    parser.add_argument('--max-clouds', type=int, default=1)
    parser.add_argument('--backend', choices=('stereo', 'yolo26'), default='stereo')
    parser.add_argument('--model', default='yolo26n-depth.pt', help='optional PC depth model')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--imgsz', type=int, default=768)
    args = parser.parse_args(argv)
    if args.max_clouds < 1:
        parser.error('--max-clouds must be positive')
    runner = None
    if args.backend == 'yolo26':
        from .mono_depth import YoloDepthRunner, process_monocular_frame
        runner = YoloDepthRunner(args.model, device=args.device, imgsz=args.imgsz)

    def process(sequence, left, right):
        width = left.shape[1]
        focal = args.focal_px * width / 640
        return estimate_nominal_rig(left, right, focal_px=focal)

    if args.npy:
        image = np.load(args.npy, allow_pickle=False)
        if image.shape != (720, 1280, 3) or image.dtype != np.uint8:
            raise ValueError('saved board frame must be uint8 BGR 720x1280')
        left, right = (cv2.resize(half, (640, 480))
                       for half in (image[:, :640], image[:, 640:]))
        if runner is not None:
            print(json.dumps(process_monocular_frame(0, left, args.output,
                              infer=runner.infer, focal_px=args.focal_px)))
            return
        rig, quality = process(0, left, right)
        print(json.dumps(save_preview(0, left, right, rig, args.output, quality=quality)))
        return

    latest = LatestPair()
    remote = None
    source_stream = sys.stdin.buffer
    if args.ssh_host:
        remote = subprocess.Popen(board_ssh_command(args.ssh_host), stdout=subprocess.PIPE)
        source_stream = remote.stdout

    def receive():
        try:
            for pair in decode_pairs(source_stream):
                latest.offer(*pair)
        except Exception as error:
            latest.close(error)
        else:
            latest.close()

    threading.Thread(target=receive, daemon=True).start()
    rig = None
    completed = 0
    try:
        while completed < args.max_clouds:
            pair = latest.take(timeout=1.)
            if pair is None:
                if latest.closed:
                    break
                continue
            sequence, left, right = pair
            try:
                if runner is not None:
                    record = process_monocular_frame(sequence, left, args.output,
                              infer=runner.infer, focal_px=args.focal_px*left.shape[1]/640)
                else:
                    if rig is None:
                        rig, quality = process(sequence, left, right)
                    record = save_preview(sequence, left, right, rig, args.output, quality=quality)
            except ValueError as error:
                units = 'relative_depth_median' if runner is not None else 'baseline_lengths'
                source = 'monocular_model_prediction' if runner is not None else 'stereo_correspondence'
                print(json.dumps(invalidate_preview(sequence, args.output, str(error),
                                                    units=units, depth_source=source)),
                      file=sys.stderr, flush=True)
                continue
            print(json.dumps(record), flush=True)
            completed += 1
    finally:
        if remote is not None:
            remote.terminate()
            remote.wait(timeout=5)
    if completed == 0:
        raise RuntimeError('stream ended without a valid pseudo-LiDAR cloud')


if __name__ == '__main__':
    main()
