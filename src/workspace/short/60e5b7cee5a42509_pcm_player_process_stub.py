"""Process-lifecycle test fixture. No audio, device files or FPGA access."""
import argparse
import json
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--play', type=Path, required=True)
parser.add_argument('--start-frame', type=int, required=True)
parser.add_argument('--volume', type=int, required=True)
args = parser.parse_args()
data = args.play.read_bytes()
mode = 'hold' if data[:4] == b'RIFF' else data.decode()
position = args.start_frame
if mode == 'failure':
    print('fixture failure', file=sys.stderr, flush=True)
    sys.exit(3)
for n in range(100 if mode == 'flood' else 1):
    print(json.dumps(dict(phase='feeding', position_frames_estimate=position+n,
                          underruns=0, audible_verified=False)), flush=True)
if mode == 'complete':
    print(json.dumps(dict(phase='completed', position_frames_estimate=position+480,
                          underruns=0, audible_verified=False)), flush=True)
else:
    time.sleep(30)
