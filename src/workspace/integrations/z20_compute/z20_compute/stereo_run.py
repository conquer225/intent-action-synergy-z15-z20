"""Stereo-only board entry point, compatible with vendor Python 3.7/OpenCV 3.4.

Record calibration pairs or publish local metric results; HDMI runs independently.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import cv2
import numpy as np
from .stereo_capture import prepare_stereo_snapshot
from .stereo_live import StereoUIO
from .stereo import Calibration, StereoProcessor, write_ply


def _json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(str(temporary), str(path))


def record_pair(directory, frame, *, pixel_order):
    prepared = prepare_stereo_snapshot(frame, pixel_order=pixel_order)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory/'pairs.json'
    value = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else dict(
        capture_mode=prepared.capture_mode, pairs=[])
    if value['capture_mode'] != prepared.capture_mode:
        raise ValueError('capture mode differs from existing calibration pairs')
    key = '{}-{}'.format(frame.captured_ns, frame.sequence)
    pair = dict(sequence=frame.sequence, captured_ns=frame.captured_ns)
    for name, image in zip(('left', 'right'), prepared.frame.pixels):
        filename = name+'-'+key+'.png'
        if (directory/filename).exists():
            raise ValueError('this calibration frame has already been recorded')
        if not cv2.imwrite(str(directory/filename), image):
            raise RuntimeError('cannot write calibration image')
        pair[name] = filename
    value['pairs'].append(pair)
    _json(manifest, value)
    return manifest


def save_depth_snapshot(directory, result, *, sequence, captured_ns, capture_mode):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'depth.npz.tmp').open('wb') as stream:
        np.savez_compressed(stream,disparity=result.disparity,xyz=result.xyz,valid_mask=result.valid_mask)
    write_ply(directory/'cloud.ply.tmp',result.xyz[result.valid_mask])
    for name in ('depth.npz','cloud.ply'):
        os.replace(str(directory/(name+'.tmp')),str(directory/name))
    # Commit metadata last; hashes detect a reader racing a subsequent snapshot.
    _json(directory/'snapshot.json',dict(sequence=sequence,captured_ns=captured_ns,
        capture_mode=capture_mode,units='m',files={name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
        for name in ('depth.npz','cloud.ply')}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('record', 'depth'))
    parser.add_argument('--device', type=Path, required=True)
    parser.add_argument('--maps', type=Path, help='default /sys/class/uio/<device>/maps')
    parser.add_argument('--pixel-order', choices=('BGR','RGB'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--calibration', type=Path)
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--cloud', action='store_true', help='write latest PLY at most once per interval')
    parser.add_argument('--independent-slots', action='store_true',
                        help='assemble each camera half from its own completed ring slot')
    args = parser.parse_args(argv)
    if args.seconds <= 0 or args.interval <= 0 or args.count <= 0:
        parser.error('positive seconds, interval and count required')
    if args.mode == 'depth' and args.calibration is None:
        parser.error('depth requires --calibration')
    args.output.mkdir(parents=True, exist_ok=True)
    processor = StereoProcessor(Calibration.load(args.calibration)) if args.mode == 'depth' else None
    maps = args.maps or Path('/sys/class/uio')/args.device.name/'maps'
    deadline, next_record, next_cloud, count = time.monotonic()+args.seconds, 0., 0., 0
    latest_ns = 0
    waiting_published = False
    try:
        with StereoUIO(args.device, maps, independent_slots=args.independent_slots) as capture:
            while time.monotonic() < deadline:
                frame = capture.latest()
                if frame is None:
                    if processor and not waiting_published and time.monotonic_ns()-latest_ns > 2_000_000_000:
                        _json(args.output/'depth.json', dict(valid=False, distance_m=None, state='waiting_for_fresh_pair'))
                        waiting_published = True
                    time.sleep(.02)
                    continue
                if args.mode == 'record':
                    if time.monotonic() >= next_record:
                        record_pair(args.output, frame, pixel_order=args.pixel_order)
                        count += 1
                        print(json.dumps(dict(recorded=count, sequence=frame.sequence)), flush=True)
                        next_record = time.monotonic()+args.interval
                        if count >= args.count: break
                    continue
                start = time.monotonic()
                prepared = prepare_stereo_snapshot(frame, pixel_order=args.pixel_order)
                result = processor.process(*prepared.frame.pixels, capture_mode=prepared.capture_mode)
                fresh = time.monotonic_ns()-frame.captured_ns <= 2_000_000_000
                valid = fresh and result.distance_m is not None
                report = dict(valid=valid, distance_m=result.distance_m if valid else None,
                    sequence=frame.sequence, captured_ns=frame.captured_ns, units='m',
                    state='ready' if valid else ('stale' if not fresh else 'invalid_disparity'),
                    backend='PS_StereoBM', processing_ms=(time.monotonic()-start)*1000,
                    capture_mode=prepared.capture_mode, valid_pixels=int(result.valid_mask.sum()))
                _json(args.output/'depth.json', report)
                print(json.dumps(report), flush=True)
                latest_ns = frame.captured_ns
                waiting_published = False
                if args.cloud and valid and time.monotonic() >= next_cloud:
                    save_depth_snapshot(args.output,result,sequence=frame.sequence,
                        captured_ns=frame.captured_ns,capture_mode=prepared.capture_mode)
                    next_cloud = time.monotonic()+args.interval
    finally:
        if processor:
            _json(args.output/'depth.json', dict(valid=False, distance_m=None, state='stopped'))
    if args.mode == 'record' and count < args.count:
        raise RuntimeError('capture deadline reached before requested calibration pair count')


if __name__ == '__main__': main()
