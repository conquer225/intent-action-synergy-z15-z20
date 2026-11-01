"""Compare production and cached SSVEP with Cyton service temporarily stopped.

Uses the previously staged, non-wear 250 Hz trace. Never touches live USB or PL.
The service is restored in finally even if a replay or download fails.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import time

from run_accepted_bench_load import PROD, PYTHON, SECONDS, ROOT, connect, remote
from stage_ssvep_opt_candidate import CANDIDATE, OUT as PREVIOUS


PROTECTED = tuple(CANDIDATE) + ('cyton_guardianloop.py', 'guardianloop_pynq.bit', 'guardianloop_pynq.hwh')


def fingerprints(client):
    with client.open_sftp() as sftp:
        return {name: hashlib.sha256(sftp.open(PROD + '/' + name, 'rb').read()).hexdigest()
                for name in PROTECTED}


def service_state(client):
    return remote(client, 'systemctl show guardianloop-cyton guardianloop-web '
                  '-p MainPID -p NRestarts -p ActiveState -p SubState -p UnitFileState').strip()


def service_control(client, action):
    stdin, stdout, stderr = client.exec_command(
        "sudo -S -p '' systemctl " + action + ' guardianloop-cyton', timeout=30)
    stdin.write(os.environ.get('GL_BOARD_SUDO_PASSWORD', 'xilinx') + '\n')
    stdin.flush()
    stdin.channel.shutdown_write()
    output = stdout.read().decode(errors='replace') + stderr.read().decode(errors='replace')
    if stdout.channel.recv_exit_status():
        raise RuntimeError('systemctl '+action+' failed: '+output[-1000:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pairs', type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    previous = json.loads((PREVIOUS/'candidate_manifest.json').read_text())
    if not json.loads((PREVIOUS/'event_parity.json').read_text())['passed']:
        raise RuntimeError('Candidate event parity has not passed')
    stage, candidate = previous['stage'], previous['candidate']
    stamp = time.strftime('%Y%m%d_%H%M%S')
    out = ROOT/'eeg_apps_z15/output'/('ssvep_single_service_'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'source_kind':'2026-09-20 non-wear bench; not EEG accuracy',
                'source_stage':stage, 'candidate_stage':candidate,
                'pairs':args.pairs,
                'scope':'Isolated paced ARM replay with Cyton acquisition service paused; web stays active. '
                        'No radio input, PL, bitstream, or production source changes.',
                'service_restored':False, 'cases':[]}
    path = out/'manifest.json'
    def save():
        path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    client = connect()
    stopped = False
    try:
        client.get_transport().set_keepalive(15)
        manifest['before'] = service_state(client)
        manifest['hashes_before'] = fingerprints(client)
        cyton_before = manifest['before'].split('\n\n', 1)[0]
        if ('UnitFileState=enabled' not in cyton_before or
                not any(s in cyton_before for s in ('ActiveState=active', 'ActiveState=activating'))):
            raise RuntimeError('Cyton acquisition was neither active nor auto-restarting; refusing to alter service')
        existing = remote(client, 'pgrep -af "[s]oak_service_replay.py" || true').strip()
        if existing:
            raise RuntimeError('Another replay is running: '+existing)
        print('SERVICE_STOP',flush=True)
        stopped = True
        service_control(client, 'stop')
        manifest['during'] = service_state(client)
        if 'ActiveState=inactive' not in manifest['during'].split('\n\n', 1)[0]:
            raise RuntimeError('Cyton service did not stop cleanly')
        save()
        order = (('baseline', PROD), ('candidate', candidate+':'+PROD))
        for pair in range(args.pairs):
            cases = order if pair == 0 else tuple(reversed(order))
            for name, module_path in cases:
                label = f'pair{pair+1}_{name}'
                result = stage+'/single-service-'+stamp+'-'+label
                primary = '/dev/shm/single_service_'+stamp+'_'+label
                command = ('cd '+shlex.quote(stage)+' && timeout -s TERM -k 5 205 env '
                           'PYTHONPATH='+shlex.quote(module_path)+' OPENBLAS_NUM_THREADS=1 '
                           'XILINX_XRT=/usr '+PYTHON+' soak_service_replay.py '
                           '--input input.npz --input-kind recorded --output '+shlex.quote(result)
                           +' --seconds '+str(SECONDS)+' --volatile-primary-dir '+shlex.quote(primary))
                print('RUN',label,flush=True)
                remote(client, command, timeout=225)
                with client.open_sftp() as sftp:
                    for filename in ('report.json','producer.json','monitor.jsonl',
                                     'primary_results.json','ssvep.json','offline-replay.log'):
                        try:
                            sftp.get(result+'/'+filename, str(out/(label+'_'+filename)))
                        except FileNotFoundError:
                            pass
                report = json.loads((out/(label+'_report.json')).read_text())
                row = {'label':label,'packets':report['packets_consumed'],
                       'age_p95_ms':report['packet_input_age_p95_ms'],
                       'age_max_ms':report['packet_input_age_max_ms'],
                       'cpu_s':report['parent_cpu_seconds']+report['children_cpu_seconds'],
                       'compute_p99_ms':report['packet_compute_p99_ms'],
                       'error':report['error'],'monitor_errors':report['monitor_errors'],
                       'remaining_children':report['remaining_children']}
                manifest['cases'].append(row)
                save()
                print('DONE',json.dumps(row),flush=True)
        manifest['hashes_after_replay'] = fingerprints(client)
    finally:
        if stopped:
            try:
                print('SERVICE_RESTORE',flush=True)
                service_control(client, 'start')
                manifest['service_restored'] = True
            except Exception as exc:
                manifest['restore_error'] = repr(exc)
            try:
                manifest['after'] = service_state(client)
                manifest['hashes_after'] = fingerprints(client)
            except Exception as exc:
                manifest['postcheck_error'] = repr(exc)
        save()
        client.close()
    cyton_after = manifest.get('after', '').split('\n\n', 1)[0]
    if (not manifest['service_restored'] or 'UnitFileState=enabled' not in cyton_after or
            not any(s in cyton_after for s in ('ActiveState=active', 'ActiveState=activating'))):
        raise RuntimeError('Cyton acquisition service restoration not verified; inspect immediately')
    if manifest['hashes_before'] != manifest['hashes_after']:
        raise RuntimeError('Production file hash changed')
    print('RESULT_DIR',out,flush=True)


if __name__ == '__main__':
    main()
