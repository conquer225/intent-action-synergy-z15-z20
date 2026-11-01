"""Read-only published video progress; not an optical or per-scan measurement."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


def observe(session, seconds):
    unit = session + '.service'
    pid = int(subprocess.run(['systemctl', 'show', unit, '-p', 'MainPID', '--value'],
        check=True, capture_output=True, text=True, timeout=10).stdout.strip())
    if pid <= 0:
        raise ValueError('Display is not running')
    path = Path('/dev/shm/gl-hdmi-live-20261008-ea117349-player-status.json')
    def cpu():
        fields = Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK')
    rows, problems = [], []
    previous = None
    started, cpu_before = time.monotonic(), cpu()
    while time.monotonic() - started < seconds:
        stamp = path.stat().st_mtime_ns
        if stamp != previous:
            row = json.loads(path.read_text())
            previous = stamp
            system = row.get('system') or {}
            if row.get('session_id') != session:
                raise ValueError('Display owner changed')
            if system.get('stimulus_enabled') is not False or system.get('physical_output_enabled') is not False:
                raise ValueError('Observation scope changed')
            if time.monotonic() - row.get('updated_monotonic', 0) > 2:
                problems.append('expired_status')
            rows.append(dict(stamp=row.get('updated_monotonic'), frame=row.get('frame'),
                             state=row.get('state'), page=system.get('page')))
        time.sleep(.05)
    elapsed, used = time.monotonic() - started, cpu() - cpu_before
    if not rows or time.monotonic() - rows[-1]['stamp'] > 2:
        problems.append('expired_final_status')
    intervals = []
    for before, after in zip(rows, rows[1:]):
        dt, count = after['stamp'] - before['stamp'], after['frame'] - before['frame']
        if before['state'] != 'playing' or after['state'] != 'playing' or before['page'] != 'video' or after['page'] != 'video':
            problems.append('not_continuous_video')
        elif not 0 < dt <= 2 or count < 0:
            problems.append('invalid_progress_interval')
        else:
            intervals.append(dict(seconds=dt, frames=count, fps=count/dt))
    total_time = sum(row['seconds'] for row in intervals)
    return dict(session_id=session, pid=pid, elapsed_s=elapsed,
        display_cpu_percent=used/elapsed*100, observation='published_frame_progress_only',
        optical_measurement=False, per_frame_interval_verified=False,
        weighted_fps=sum(row['frames'] for row in intervals)/total_time if total_time else None,
        minimum_published_interval_fps=min(row['fps'] for row in intervals) if intervals else None,
        published_intervals_below_16=sum(row['fps'] < 16 for row in intervals),
        intervals=len(intervals), problems=problems, samples=rows, progress=intervals)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--seconds', type=float, default=36)
    args = parser.parse_args()
    if not re.fullmatch('play-[a-f0-9]{8}', args.session) or not 5 <= args.seconds <= 45:
        raise ValueError('Invalid observation scope')
    print(json.dumps(observe(args.session, args.seconds)))


if __name__ == '__main__':
    main()
