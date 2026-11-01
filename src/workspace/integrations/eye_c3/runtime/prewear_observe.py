"""Bounded, read-only software frame/health observations during recorded loads."""
import argparse
import json
import math
import os
from pathlib import Path
import time


def process_progress(pid):
    path = Path('/proc') / str(pid) / 'task' / str(pid)
    fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
    context = {key: int(value.strip()) for key, value in
               (line.split(':', 1) for line in (path / 'status').read_text().splitlines())
               if key in ('voluntary_ctxt_switches', 'nonvoluntary_ctxt_switches')}
    return dict(pid=pid, main_thread_cpu_ticks=int(fields[11])+int(fields[12]),
                clock_ticks_per_second=os.sysconf('SC_CLK_TCK'), **context)


def frame_progress(rows):
    """Use counter publication time, not the later observer polling time."""
    intervals = []
    maximum_age = 0.
    duplicate_publications = 0
    previous = None
    for row in rows:
        stamp = row.get('updated_monotonic')
        if (row.get('state') != 'playing' or row.get('page') != 'video'
                or type(stamp) not in (int,float) or not math.isfinite(stamp)
                or type(row.get('frame')) is not int or 'error' in row):
            previous = None
            continue
        maximum_age = max(maximum_age, row['monotonic']-stamp)
        if previous is not None and previous.get('session') == row.get('session'):
            dt = stamp-previous['updated_monotonic']
            count = row['frame']-previous['frame']
            if dt == 0 and count == 0:
                duplicate_publications += 1
                continue
            if dt > 0 and count >= 0:
                intervals.append((count,dt))
        previous = row
    rates = [count/dt for count,dt in intervals]
    return dict(intervals=len(rates),
                weighted_fps=sum(n for n,_ in intervals)/sum(dt for _,dt in intervals) if rates else None,
                minimum_interval_fps=min(rates) if rates else None,
                intervals_below16=sum(rate < 16 for rate in rates),
                duplicate_publications=duplicate_publications,
                maximum_publication_age_seconds=maximum_age,
                scope='Published software video frame progress; not per-scan or optical measurement')


def sample_display(base, pid=None):
    status = Path('/dev/shm') / (base.name + '-player-status.json')
    row = json.loads(status.read_text())
    system = row.get('system') or {}
    sample = dict(monotonic=time.monotonic(), updated_monotonic=row.get('updated_monotonic'),
        session=row.get('session_id'), frame=row.get('frame'), state=row.get('state'),
        page=system.get('page'), physical=system.get('physical_output_enabled'),
        stimulus=system.get('stimulus_enabled'), silent=row.get('silent'),
        direction=system.get('direction'))
    sample['memory'] = {k: v.strip() for k, v in
        (line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        if k in ('CmaFree', 'MemAvailable')}
    sample['memstat_raw'] = Path('/sys/class/drm/card0/device/memstat_raw').read_text().strip()
    if pid is not None:
        sample['display_process'] = process_progress(pid)
    return sample


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--stage',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=420)
    parser.add_argument('--label',choices=('actual',)+tuple('actual'+str(i) for i in range(7,24)))
    parser.add_argument('--display-pid', type=int, help='Read-only main-thread CPU/context switches')
    args=parser.parse_args()
    if (args.base!=Path('/home/xilinx/gl-hdmi-live-20261008-ea117349') or
            args.stage!=Path(__file__).resolve().parent or not 1<=args.seconds<=450
            or (args.display_pid is not None and args.display_pid <= 0)):
        raise ValueError('Read-only observation is limited to this pinned session')
    output=args.stage/('display-observations'+('-'+args.label if args.label else '')+'.json')
    if output.exists():raise ValueError('Do not overwrite retained observations')
    rows=[];end=time.monotonic()+args.seconds
    while time.monotonic()<end:
        try:
            sample = sample_display(args.base, args.display_pid)
        except (OSError,ValueError) as error:
            sample=dict(monotonic=time.monotonic(),error=type(error).__name__)
        rows.append(sample)
        temporary=output.with_suffix('.new');temporary.write_text(json.dumps(rows,indent=2));temporary.replace(output)
        time.sleep(1)
    print('READ_ONLY_DISPLAY_OBSERVATION_COMPLETE_NOT_OPTICAL_MEASUREMENT',flush=True)


if __name__=='__main__':main()
