"""Build separate Windows gaze runtime without changing model.dll or firmware."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from build_pc_model import INPUTS as MODEL_INPUTS

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('stable pair can_calibrate cal_mask stage stable_frames stage_ms settle_ms failed '
        'valid direction armed dwell_ms event_seq commit reason '
        'lx ly lw lh rx ry rw rh '
        'left_valid left_nx left_x left_y left_dark left_contrast left_quality '
        'right_valid right_nx right_x right_y right_dark right_contrast right_quality '
        'cal_l_left cal_l_center cal_l_right cal_r_left cal_r_center cal_r_right '
        'left_samples left_selected left_threshold left_reason '
        'right_samples right_selected right_threshold right_reason '
        'cal_left_count cal_right_count paused cal_samples_required cal_settle_required '
        'target_side_percent target_y_percent gaze_raw_offset gaze_filtered_offset filter_count tracking_reason '
        'cal_l_mad_left cal_l_mad_center cal_l_mad_right cal_r_mad_left cal_r_mad_center cal_r_mad_right '
        'cal_failure_reason cal_failure_eye cal_retry_stage cal_failure_gap cal_failure_noise '
        'cal_left_ready cal_right_ready cal_left_core_span cal_right_core_span '
        'cal_left_min cal_left_max cal_right_min cal_right_max').split()
INPUTS=MODEL_INPUTS+['tools/pc_gaze_bridge.c','src/app/eye_tracker.c','src/app/main.c']

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--gcc',default='C:/mingw64/mingw64/bin/gcc.exe')
    args=p.parse_args()
    out=ROOT/'pc_runtime';out.mkdir(exist_ok=True)
    dll=out/'gaze.dll'
    subprocess.run([args.gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-shared',
                    '-static-libgcc','-static','-Itests/include','-Isrc/app',
                    'src/app/haar.c','src/app/auto_face.c','src/app/eye_tracker.c',
                    'tools/pc_bridge.c','tools/pc_gaze_bridge.c','-lm','-o',str(dll)],
                   cwd=ROOT,check=True)
    hashes={n:hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in INPUTS}
    manifest=dict(abi=1,fields=FIELDS,dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(),sources=hashes)
    (out/'gaze_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('Built '+str(dll))
if __name__=='__main__':main()
