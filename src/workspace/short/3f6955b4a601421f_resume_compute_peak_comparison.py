"""Recover a detached comparison without repeating completed input cases."""
import argparse
import json
from pathlib import Path
import re
import shlex
import time

from run_compute_peak_comparison import run_job
from run_soak_stage import connect
from run_ssvep_backlog_replay import ROOT, PYTHON, checked, save, snapshot, download_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-service-pause', action='store_true',
                        help='Explicit authorization to supplement the last case after restoration')
    args = parser.parse_args()
    out = ROOT / 'eeg_apps_z15/output/ssvep_compute_peak_20261003/paired_run'
    isolation = json.loads((out / 'isolation.json').read_text())
    plan = json.loads((out / 'PLAN.json').read_text())
    before = json.loads((out / 'before.json').read_text())
    work, timer = isolation['remote_work'], isolation['restore_timer']
    if not work.startswith('/home/xilinx/guardianloop-compute-peak.'):
        raise ValueError('Unexpected private directory')
    token = Path(work).name.rsplit('.', 1)[-1]
    client = connect()
    try:
        # The interrupted client detached the already-started array job.
        for _ in range(40):
            running = checked(client, "ps -eo args | grep '[s]oak_service_replay.py' || true")
            if not running.strip():
                break
            if work + '/input.npz' not in running:
                raise RuntimeError('Another replay is running')
            time.sleep(1)
        else:
            raise RuntimeError('Detached array job did not finish; restore without new work')

        def collect(name):
            volatile = '/dev/shm/gl-peak-' + token + '-' + name
            destination = work + '/' + name + '/run'
            for src, dst in [(volatile + '-shadow/shadow.events.jsonl', 'seed.events.jsonl'),
                             (volatile + '-shadow/shadow.json', 'seed.final.json'),
                             (volatile + '-shadow/ssvep.json', 'ssvep.final.json'),
                             (volatile + '-primary/status.json', 'primary.final.json')]:
                checked(client, 'cp -- ' + shlex.quote(src) + ' ' + shlex.quote(destination + '/' + dst))
            local = out / name
            local.mkdir(exist_ok=True)
            if not (local / 'run').exists():
                sftp = client.open_sftp()
                try:
                    download_tree(sftp, destination, local / 'run')
                finally:
                    sftp.close()
            report = json.loads((local / 'run/report.json').read_text())
            if report['error'] or report['packets_consumed'] != 39000 or report['remaining_children']:
                raise RuntimeError('Detached case incomplete; preserve outputs and restore')
            print(json.dumps(dict(case=name, packets=report['packets_consumed'],
                age_p95_ms=report['packet_input_age_p95_ms'], age_max_ms=report['packet_input_age_max_ms'],
                total_cpu_s=report['parent_cpu_seconds']+report['children_cpu_seconds'])), flush=True)

        collect('array')
        # systemctl renders this usec field as a duration on this board.
        uptime = float(checked(client, "cut -d ' ' -f1 /proc/uptime").strip())
        if args.allow_service_pause:
            current = snapshot(client, sorted(plan['protected_runtime_hashes']))
            if current['hashes'] != before['hashes'] or current['service_active'] != ['active', 'active']:
                raise RuntimeError('Protected runtime/live services changed; no supplemental pause')
            if (out / 'array_async_seed').exists():
                raise RuntimeError('Last case already exists; refuse duplicate execution')
            timer += '-pending'
            checked(client, 'systemd-run --unit='+timer+
                ' --on-active=195s /bin/systemctl start guardianloop-cyton.service', sudo=True)
            checked(client, 'systemctl stop guardianloop-cyton.service', sudo=True)
            deadline = float(checked(client, "cut -d ' ' -f1 /proc/uptime").strip()) + 190
        else:
            raw = checked(client, 'systemctl show -p NextElapseUSecMonotonic --value '+timer+'.timer').strip()
            units = dict(h=3600, min=60, s=1, ms=.001, us=.000001)
            parts = re.findall(r'([0-9.]+)(h|min|ms|us|s)', raw)
            if not parts:
                raise RuntimeError('Recovery timer deadline unavailable; restore without new work')
            deadline = sum(float(value)*units[unit] for value, unit in parts)
        if deadline - uptime < 183:
            save(out / 'resume.json', dict(reason='insufficient authorized timer budget',
                remaining_seconds=deadline-uptime, next_case_not_started=True))
            return
        if checked(client, 'systemctl show -p ActiveState --value guardianloop-cyton.service').strip() != 'inactive':
            raise RuntimeError('Live acquisition restarted; no candidate started')
        save(out / 'resume.json', dict(reason='client interrupted while array replay remained on board',
            array_recovered=True, remaining_seconds=deadline-uptime, repeated_cases=False,
            supplemental_pause_authorized=args.allow_service_pause))
        name = 'array_async_seed'
        local = out / name
        local.mkdir(exist_ok=False)
        volatile = '/dev/shm/gl-peak-' + token + '-' + name
        shell = ('cd ' + shlex.quote(work+'/'+name) + ' && timeout 180s env '
            'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr '+PYTHON+
            ' soak_service_replay.py --input '+shlex.quote(work+'/input.npz')+
            ' --output run --seconds 156 --trace-stages --record-raw --audit-seed-candidate '
            '--array-covariance --async-seed-candidate --volatile-primary-dir '+
            shlex.quote(volatile+'-primary')+' --volatile-shadow-dir '+shlex.quote(volatile+'-shadow'))
        print('START array_async_seed; remaining authorized pause only', flush=True)
        run_job(client, shell, local/'process.json')
        collect(name)
    finally:
        try:
            checked(client, 'systemctl start guardianloop-cyton.service', sudo=True)
            if checked(client, 'systemctl show -p LoadState --value '+timer+'.timer').strip() != 'not-found':
                checked(client, 'systemctl stop '+timer+'.timer', sudo=True)
            after = snapshot(client, sorted(plan['protected_runtime_hashes']))
            save(out/'after.json', after)
            save(out/'preservation.json', dict(
                formal_file_hashes_unchanged=before['hashes']==after['hashes'],
                service_config_hash_unchanged=before['service_configuration_sha256']==after['service_configuration_sha256'],
                boot_id_unchanged=before['boot_id']==after['boot_id'],
                services_restored=before['service_active']==after['service_active']))
            save(out/'restoration.json', dict(client_recovered=True, remote_work=work,
                services=after['service_active'], all_case_files_present=all(
                    (out/n/'run/report.json').exists() for n in plan['cases'])))
        finally:
            client.close()
    print('Recovered comparison finished; original services restored', flush=True)


if __name__ == '__main__':
    main()
