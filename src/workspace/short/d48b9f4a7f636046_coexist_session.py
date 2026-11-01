"""Opt-in candidate entry. Preflight is read-only; --run-eye loads eye PL."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from coexist_guard import CoexistGuard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-eye', action='store_true')
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--locate', action='store_true')
    parser.add_argument('--control-dir', default='/dev/shm/brain_eye_coexist/eye')
    args = parser.parse_args()
    from pynq import PL
    report = CoexistGuard(ROOT, PL.bitfile_name).verify()
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if not args.run_eye:
        return
    command = [sys.executable, '-u', str(ROOT / 'src/hdmi_guide.py'),
               '--coexist', '--coexist-seconds', str(args.seconds), '--local-media',
               '--media-dir', '/home/xilinx/tobii_z15/media',
               '--control-dir', args.control_dir]
    if args.locate:
        command.append('--coexist-locate')
    raise SystemExit(subprocess.call(command))


if __name__ == '__main__':
    main()
