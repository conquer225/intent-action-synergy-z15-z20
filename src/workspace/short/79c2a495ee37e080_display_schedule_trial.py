"""Finite scheduling comparisons for one existing HDMI owner; no PL or live inputs."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from prewear_observe import frame_progress, sample_display
from upload_server import write_json

DISPLAY = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
BOOT = Path('/proc/sys/kernel/random/boot_id')


def thread_state(pid, tid):
    root = Path('/proc') / str(pid) / 'task' / str(tid)
    stat = root / 'stat'
    first = stat.read_text().rsplit(')', 1)[1].split()
    value = dict(start_ticks=int(first[19]), nice=os.getpriority(os.PRIO_PROCESS, tid),
        policy=os.sched_getscheduler(tid), affinity=sorted(os.sched_getaffinity(tid)))
    second = stat.read_text().rsplit(')', 1)[1].split()
    if int(second[19]) != value['start_ticks']:
        raise RuntimeError('Thread identity changed while reading')
    return value


def current_threads(plan):
    pid = plan['pid']
    if BOOT.read_text().strip() != plan['boot']:
        raise RuntimeError('Board boot changed; do not touch another display')
    if thread_state(pid, pid)['start_ticks'] != plan['start_ticks']:
        raise RuntimeError('Display PID was reused; do not change priority')
    tasks = Path('/proc') / str(pid) / 'task'
    values = {}
    for task in tasks.iterdir():
        tid = int(task.name)
        try:
            values[tid] = thread_state(pid, tid)
        except FileNotFoundError:
            # The bounded cache reader can finish between listdir and stat.
            continue
    if pid not in values:
        raise RuntimeError('Display main thread disappeared')
    return values


def set_display_nice(plan, desired):
    if desired not in (0, 5) or plan['original_nice'] != 5:
        raise ValueError('Only this ordinary Nice=5/0 trial is allowed')
    threads = current_threads(plan)
    # Validate the entire owner before changing anything. Never modify RT policy,
    # affinity, another owner or a priority changed by someone else.
    if any(v['policy'] != 0 or v['affinity'] != [0, 1] or v['nice'] not in (0, 5)
           for v in threads.values()):
        raise RuntimeError('Unexpected scheduler state; leave it untouched')
    return update_threads(plan, threads, 'nice', desired,
        lambda tid: os.setpriority(os.PRIO_PROCESS, tid, desired))


def set_display_affinity(plan, desired):
    if desired not in ([0, 1], [1]) or plan['original_affinity'] != [0, 1]:
        raise ValueError('Only the audited two-core/display-CPU1 comparison is allowed')
    threads = current_threads(plan)
    if any(v['policy'] != 0 or v['nice'] != 5 or v['affinity'] not in ([0, 1], [1])
           for v in threads.values()):
        raise RuntimeError('Unexpected scheduler state; leave it untouched')
    return update_threads(plan, threads, 'affinity', desired,
        lambda tid: os.sched_setaffinity(tid, set(desired)))


def update_threads(plan, threads, field, desired, apply):
    for tid, before in threads.items():
        try:
            if thread_state(plan['pid'], tid) != before:
                raise RuntimeError('Thread changed before scheduler update')
            if before[field] != desired:
                apply(tid)
                after = thread_state(plan['pid'], tid)
                if after != dict(before, **{field: desired}):
                    raise RuntimeError('Scheduler update was not verified')
        except FileNotFoundError:
            continue
    actual = current_threads(plan)
    if any(v[field] != desired for v in actual.values()):
        raise RuntimeError('A newly created display thread did not inherit the trial setting')
    return actual


def safe_sample(plan, nice, affinity=None):
    affinity = [0, 1] if affinity is None else affinity
    threads = current_threads(plan)
    if any(v['nice'] != nice or v['policy'] != 0 or v['affinity'] != affinity
           for v in threads.values()):
        raise RuntimeError('Display scheduling changed during the comparison')
    row = sample_display(DISPLAY, plan['pid'])
    if (row['session'] != plan['session'] or row['page'] != 'video'
            or row['state'] not in ('playing', 'buffering')
            or row['physical'] is not False or row['stimulus'] is not False
            or row['silent'] is not True or row['direction'] != 'stop'):
        raise RuntimeError('User changed the display scope; end the private comparison')
    row['thread_nice'] = {str(t): v['nice'] for t, v in threads.items()}
    row['thread_affinity'] = {str(t): v['affinity'] for t, v in threads.items()}
    return row


def load_plan(stage):
    plan = json.loads((stage / 'plan.json').read_text())
    division = plan.get('kind') == 'cpu-division'
    prefix = 'gl-display-cpu-20261010-' if division else 'gl-display-schedule-20261010-'
    if (stage.parent != Path('/home/xilinx')
            or not stage.name.startswith(prefix)
            or stage != Path(__file__).resolve().parent):
        raise ValueError('Trial must use its new pinned private directory')
    if plan['pid'] != 900 or plan['session'] != 'play-df4fc516' or plan['original_nice'] != 5:
        raise ValueError('Wrong existing HDMI owner')
    for case in plan['cases']:
        root = Path(case['stage'])
        load_prefix = 'gl-prewear-cpu-' if division else 'gl-prewear-schedule'
        if (root.parent != Path('/home/xilinx') or not root.name.startswith(load_prefix)
                or case['nice'] not in (0, 5)):
            raise ValueError('Load must remain in its separate recorded-only stage')
    if division:
        expected = [('shared', 5, [0, 1], False), ('separate', 5, [1], True)]
        actual = [(c['label'], c['nice'], c['affinity'], c['eeg_cpu0']) for c in plan['cases']]
        if plan['original_affinity'] != [0, 1] or actual != expected:
            raise ValueError('Wrong CPU division profiles')
    elif [c['nice'] for c in plan['cases']] != [5, 0]:
        raise ValueError('Run the unchanged baseline before the temporary comparison')
    return plan


def run_case(stage, plan, case):
    nice = case['nice']
    root = Path(case['stage'])
    division = plan.get('kind') == 'cpu-division'
    label = case['label'] if division else 'nice' + str(nice)
    affinity = case['affinity'] if division else [0, 1]
    folder = stage / label
    folder.mkdir()
    actual = set_display_affinity(plan, affinity) if division else set_display_nice(plan, nice)
    write_json(folder / 'priority-start.json', actual)
    safe_sample(plan, nice, affinity)
    command = [sys.executable, str(root / 'prewear_load.py'), '--stage', str(root),
        '--scheduled', '--only', 'hardened', '--attempt', '23', '--idle-mi',
        '--async-primary-candidate', '--reader-batch-candidate',
        '--mi-tap-batch-candidate']
    command.append('--eeg-cpu0' if division and case['eeg_cpu0'] else '--split-worker-cpus')
    rows = []
    started = time.monotonic()
    error = None
    process = None
    print('RECORDED_SCHEDULE_CASE_START:' + label, flush=True)
    try:
        with (folder / 'load-driver.log').open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                cwd=root, env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'))
            while process.poll() is None:
                if time.monotonic() - started > 240:
                    raise RuntimeError('Private recorded case exceeded its deadline')
                rows.append(safe_sample(plan, nice, affinity))
                write_json(folder / 'display-observations.json', rows)
                time.sleep(1)
            if process.returncode:
                raise RuntimeError('Private recorded load failed')
        report = json.loads((root / 'load-hardened-scheduled23/report.json').read_text())
        if (report['packets_consumed'] != 39000 or report['packets_expected'] != 39000
                or report['error'] or report['monitor_errors'] or report['remaining_children']):
            raise RuntimeError('Incomplete or erroneous private recorded load')
        safe_sample(plan, nice, affinity)
        return dict(label=label, nice=nice, display_affinity=affinity, completed=True,
            report=report, display=frame_progress(rows),
            buffering_observations=sum(r['state'] == 'buffering' for r in rows))
    except BaseException as exc:
        error = repr(exc)
        raise
    finally:
        write_json(folder / 'case-status.json', dict(error=error,
            elapsed_seconds=time.monotonic()-started, observations=len(rows)))
        # Do not signal the HDMI owner. The unit's control-group cleanup handles
        # this private load if interrupted, including its isolated child sessions.
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def restore(stage, plan):
    try:
        actual = (set_display_affinity(plan, plan['original_affinity'])
            if plan.get('kind') == 'cpu-division' else set_display_nice(plan, plan['original_nice']))
        result = dict(restored=True, actual_threads=actual)
    except BaseException as exc:
        write_json(stage / 'restore-error.json', dict(restored=False, error=repr(exc)))
        raise
    write_json(stage / 'restored.json', result)
    print('DISPLAY_ORIGINAL_SCHEDULER_VERIFIED', flush=True)


def interrupted(signum, frame):
    raise RuntimeError('Finite scheduling comparison interrupted: ' + str(signum))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('run', 'restore'))
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    plan = load_plan(args.stage)
    if args.action == 'restore':
        restore(args.stage, plan)
        return
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, interrupted)
    result = dict(cases=[], completed=False, error=None, live_files_changed=False,
        pl_loaded=False, physical_output=False, accuracy_scored=False,
        scope='Two sequential recorded video-page loads; no optical measurement or causal proof')
    try:
        if any(v['nice'] != 5 or v['policy'] != 0 or v['affinity'] != [0, 1]
               for v in current_threads(plan).values()):
            raise RuntimeError('Baseline display scheduler is not the audited original')
        for case in plan['cases']:
            result['cases'].append(run_case(args.stage, plan, case))
            write_json(args.stage / 'comparison.json', result)
            print('RECORDED_SCHEDULE_CASE_COMPLETE:' +
                case.get('label', 'nice' + str(case['nice'])), flush=True)
        result['completed'] = True
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        try:
            restore(args.stage, plan)
        finally:
            write_json(args.stage / 'comparison.json', result)


if __name__ == '__main__':
    main()
