"""PC-only measured chessboard calibration -> exact observer ARM maps."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from z20_compute.stereo_board import CAPTURE_MODE


def export_calibration(calibration,source,output):
    if calibration.capture_mode!=CAPTURE_MODE or tuple(calibration.image_size)!=(160,180):
        raise ValueError('must calibrate exact quarter-sampled observer pairs')
    maps,q=calibration.rectify();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    path=output/'maps.npz';np.savez_compressed(path,maps=np.array([a for pair in maps for a in pair]),q=q)
    meta=dict(format='z20-board-stereo-v1',capture_mode=CAPTURE_MODE,image_size=[160,180],units='m',
        calibration_id=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        maps_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (output/'calibration.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    return meta


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs',type=Path,required=True)
    parser.add_argument('--columns',type=int,required=True);parser.add_argument('--rows',type=int,required=True)
    parser.add_argument('--square-m',type=float,required=True,help='measured square side, metres')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from z20_compute.data_tools import calibrate_images
    value=json.loads(args.pairs.read_text(encoding='utf-8'))
    if value.get('capture_mode')!=CAPTURE_MODE:raise ValueError('capture mode differs')
    calibration,report=calibrate_images(args.pairs,columns=args.columns,rows=args.rows,
        square_m=args.square_m,capture_mode=CAPTURE_MODE)
    args.output.mkdir(parents=True,exist_ok=True);source=args.output/'source.json';calibration.save(source)
    export_calibration(calibration,source,args.output)
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
