"""Authorized three-case ARM comparison; never install candidate files."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shlex
import time

from run_soak_stage import connect
from run_ssvep_backlog_replay import (ROOT, BASE, PYTHON, checked, digest, save,
                                      snapshot, download_tree)


CASES=(('baseline',False,False),('array',True,False),('array_async_seed',True,True))


def run_job(client, shell, path):
    _,stdout,stderr=client.exec_command(shell)
    channel=stdout.channel
    output,errors=bytearray(),bytearray()
    progress=time.monotonic()
    while not channel.exit_status_ready():
        while channel.recv_ready(): output.extend(channel.recv(65536))
        while channel.recv_stderr_ready(): errors.extend(channel.recv_stderr(65536))
        if time.monotonic()-progress>=30:
            print('Private comparison case running: '+path.parent.name,flush=True)
            progress=time.monotonic()
        time.sleep(.2)
    while channel.recv_ready(): output.extend(channel.recv(65536))
    while channel.recv_stderr_ready(): errors.extend(channel.recv_stderr(65536))
    code=channel.recv_exit_status()
    save(path,dict(exit_code=code,stdout=output.decode(errors='replace'),stderr=errors.decode(errors='replace')))
    if code:
        raise RuntimeError('Private replay failed; preserve '+str(path))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'eeg_apps_z15/output/ssvep_compute_peak_20261003/paired_run')
    parser.add_argument('--allow-service-pause',action='store_true')
    args=parser.parse_args()
    if not args.allow_service_pause:
        parser.error('Human authorization to pause acquisition is required')
    out=args.output.resolve()
    if ROOT/'eeg_apps_z15/output/ssvep_compute_peak_20261003' not in out.parents:
        raise ValueError('Output must be a fresh directory within this experiment')
    out.mkdir(exist_ok=False)
    frozen=BASE/'runtime'
    files=sorted(p for p in frozen.iterdir() if p.is_file())
    names=[p.name for p in files]
    runtime=ROOT/'pynq_guardianloop'
    extra=[runtime/n for n in ('soak_service_replay.py','replay_stage_trace.py',
        'async_seed_candidate.py','audited_seed_shadow.py','test_async_seed_candidate.py',
        'test_async_seed_integration.py')]
    candidate=runtime/'cyton_covariance.py'
    source=ROOT/'eeg_apps_z15/output/ssvep_backlog_idle_20261002/arm_replay_profile/input.npz'
    plan=dict(created_pc_local=datetime.now().isoformat(),authorization='User allowed about nine minutes of pause and restoration',
        cases=[name for name,_,_ in CASES],input_sha256=digest(source),input_repeated=False,
        samples_per_case=39000,seconds_per_case=156,filter_backend='arm',record_raw=True,
        seed_event_audit=True,trace_stages=True,protected_runtime_hashes={p.name:digest(p) for p in files},
        harness_hashes={p.name:digest(p) for p in extra},candidate_covariance_sha256=digest(candidate),
        numerical_atol=1e-9,numerical_rtol=1e-9,min_feature_max_speedup_fraction=.50,
        min_age_p95_improvement_fraction=.15,max_cpu_total_increase_fraction=.10,
        independent_accuracy_claimed=False,control_enabled=False)
    save(out/'PLAN.json',plan)
    copied=out/'code_snapshot'
    copied.mkdir()
    for p in extra+[candidate]:
        (copied/p.name).write_bytes(p.read_bytes())
    client=connect()
    stopped=False
    recovery_scheduled=False
    work=None
    timer=None
    started_pause=None
    try:
        before=snapshot(client,names)
        save(out/'before.json',before)
        if before['service_active']!=['active','active'] or before['hashes']!=plan['protected_runtime_hashes']:
            raise RuntimeError('Protected runtime/services differ; no pause performed')
        work=checked(client,'mktemp -d /home/xilinx/guardianloop-compute-peak.XXXXXX').strip()
        if not work.startswith('/home/xilinx/guardianloop-compute-peak.'):
            raise RuntimeError('Unexpected private workspace')
        token=Path(work).name.rsplit('.',1)[-1]
        timer='guardianloop-peak-restore-'+token.lower()
        save(out/'isolation.json',dict(remote_work=work,restore_timer=timer,filter_backend='arm',
            source='offline_replay_not_live',real_serial_opened=False,control_enabled=False))
        sftp=client.open_sftp()
        try:
            sftp.put(str(source),work+'/input.npz')
            for name,array,_ in CASES:
                stage=work+'/'+name
                sftp.mkdir(stage)
                for p in files:
                    if p.suffix in ('.py','.json','.npy','.npz'):
                        sftp.put(str(p),stage+'/'+p.name)
                for p in extra:
                    sftp.put(str(p),stage+'/'+p.name)
                if array:
                    sftp.put(str(candidate),stage+'/cyton_covariance.py')
        finally:sftp.close()
        # Real spawned-worker fault tests run before pausing the live service.
        test_dir=work+'/array_async_seed'
        fault_output=checked(client,'cd '+shlex.quote(test_dir)+' && env OPENBLAS_NUM_THREADS=1 '
            'OMP_NUM_THREADS=1 XILINX_XRT=/usr '+PYTHON+
            ' -m unittest test_async_seed_candidate test_async_seed_integration -v')
        (out/'board_fault_tests.txt').write_text(fault_output,encoding='utf-8')
        checked(client,'systemd-run --unit='+timer+' --on-active=540s /bin/systemctl start guardianloop-cyton.service',sudo=True)
        recovery_scheduled=True
        stopped=True  # Also restore when a stop request succeeds but its response is lost.
        checked(client,'systemctl stop guardianloop-cyton.service',sudo=True)
        started_pause=time.monotonic()
        if checked(client,'systemctl show -p ActiveState --value guardianloop-cyton.service').strip()!='inactive':
            raise RuntimeError('Acquisition did not stop')
        for name,array,async_seed in CASES:
            local=out/name
            local.mkdir()
            volatile='/dev/shm/gl-peak-'+token+'-'+name
            primary,shadow=volatile+'-primary',volatile+'-shadow'
            shell=('cd '+shlex.quote(work+'/'+name)+' && timeout 180s env '+
                'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr '+PYTHON+
                ' soak_service_replay.py --input '+shlex.quote(work+'/input.npz')+
                ' --output run --seconds 156 --trace-stages --record-raw --audit-seed-candidate '+
                '--volatile-primary-dir '+shlex.quote(primary)+' --volatile-shadow-dir '+shlex.quote(shadow))
            if array:shell+=' --array-covariance'
            if async_seed:shell+=' --async-seed-candidate'
            print('START '+name+'; private ARM replay, real acquisition temporarily stopped',flush=True)
            run_job(client,shell,local/'process.json')
            destination=work+'/'+name+'/run'
            for src,dst in [(shadow+'/shadow.events.jsonl','seed.events.jsonl'),
                            (shadow+'/shadow.json','seed.final.json'),
                            (shadow+'/ssvep.json','ssvep.final.json'),
                            (primary+'/status.json','primary.final.json')]:
                checked(client,'cp -- '+shlex.quote(src)+' '+shlex.quote(destination+'/'+dst))
            sftp=client.open_sftp()
            try:download_tree(sftp,destination,local/'run')
            finally:sftp.close()
            report=json.loads((local/'run/report.json').read_text())
            print(json.dumps(dict(case=name,packets=report['packets_consumed'],
                age_p95_ms=report['packet_input_age_p95_ms'],age_max_ms=report['packet_input_age_max_ms'],
                total_cpu_s=report['parent_cpu_seconds']+report['children_cpu_seconds']),ensure_ascii=False),flush=True)
    finally:
        try:
            if stopped:
                checked(client,'systemctl start guardianloop-cyton.service',sudo=True)
            if recovery_scheduled:
                checked(client,'systemctl stop '+timer+'.timer',sudo=True)
            after=snapshot(client,names)
            save(out/'after.json',after)
            if 'before' in locals():
                save(out/'preservation.json',dict(
                    formal_file_hashes_unchanged=before['hashes']==after['hashes'],
                    service_config_hash_unchanged=before['service_configuration_sha256']==after['service_configuration_sha256'],
                    boot_id_unchanged=before['boot_id']==after['boot_id'],
                    services_restored=before['service_active']==after['service_active']))
            save(out/'restoration.json',dict(pause_seconds=None if started_pause is None else time.monotonic()-started_pause,
                remote_work=work,services=after['service_active']))
        finally:client.close()
    print('All three cases completed; original services restored',flush=True)


if __name__=='__main__':
    main()
