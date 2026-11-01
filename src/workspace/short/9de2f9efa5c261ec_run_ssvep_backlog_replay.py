"""One authorized private ARM replay, with timed service restoration and hashes."""
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import stat
import sys
import time

import numpy as np

from run_soak_stage import connect, command, PROD

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT/'eeg_apps_z15/output/ssvep_raw_sync_20261002'
OUT = ROOT/'eeg_apps_z15/output/ssvep_backlog_idle_20261002/arm_replay'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def checked(client, cmd, sudo=False):
    if sudo:
        password = client.get_transport().auth_handler.password
        if not isinstance(password, str) or not password:
            raise RuntimeError('Authenticated SSH session has no reusable password for sudo')
        stdin, stdout, stderr = client.exec_command("sudo -S -p '' -- "+cmd)
        stdin.write(password+'\n')
        stdin.flush()
    else:
        _, stdout, stderr = client.exec_command(cmd)
    result = stdout.read().decode() + stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if code:
        raise RuntimeError('Remote command failed (%d): %s' % (code, result[-3000:]))
    return result


def snapshot(client, names):
    probe = ('import pathlib,hashlib,json; p=pathlib.Path(%r); '
             'print(json.dumps({n:hashlib.sha256((p/n).read_bytes()).hexdigest() '
             'for n in %r}))') % (PROD, names)
    return dict(boot_id=checked(client, 'cat /proc/sys/kernel/random/boot_id').strip(),
                hashes=json.loads(checked(client, 'python3 -c '+shlex.quote(probe))),
                service_active=checked(client, 'systemctl is-active guardianloop-cyton.service guardianloop-web.service').split(),
                service_configuration_sha256=hashlib.sha256(checked(client,
                    'systemctl cat guardianloop-cyton.service guardianloop-web.service').encode()).hexdigest())


def download_tree(sftp, remote, local):
    local.mkdir(exist_ok=False)
    for entry in sftp.listdir_attr(remote):
        src, dst = remote+'/'+entry.filename, local/entry.filename
        if stat.S_ISDIR(entry.st_mode):
            download_tree(sftp, src, dst)
        else:
            sftp.get(src, str(dst))


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args()
    OUT=args.output.resolve()
    if ROOT/'eeg_apps_z15/output/ssvep_backlog_idle_20261002' not in OUT.parents:
        raise ValueError('Output must be a fresh directory inside this diagnostic experiment')
    OUT.mkdir(exist_ok=False)
    frozen = BASE/'runtime'
    files = sorted(p for p in frozen.iterdir() if p.is_file())
    names = [p.name for p in files]
    capture = BASE/'recordings/d106522f443ce69b'
    raw = np.fromfile(capture/'samples_i32le.bin', dtype='<i4').reshape(-1,8)[:39000]
    sequence = np.fromfile(capture/'sequence_u8.bin', dtype='u1')[:39000]
    flags = np.fromfile(capture/'flags_u8.bin', dtype='u1')[:39000]
    metadata = json.loads((capture/'metadata.json').read_text())
    if len(raw) != 39000 or flags.any():
        raise ValueError('Replay requires 156 continuous original seconds')
    values = raw.astype(np.float64)*metadata['microvolts_per_count']
    if not np.array_equal(np.rint(values/metadata['microvolts_per_count']).astype(np.int32), raw):
        raise ValueError('ADC integer round-trip failed')
    np.savez_compressed(OUT/'input.npz', recorded=values, recorded_seq=sequence)
    replay_files = [ROOT/'pynq_guardianloop/soak_service_replay.py',
                    ROOT/'pynq_guardianloop/replay_stage_trace.py']
    save(OUT/'PLAN.json', dict(created_pc_local=datetime.now().isoformat(),
        authorization='User allowed temporary acquisition stop and restoration',
        seconds=156, input_rows=[0,39000], input_repeated=False,
        input_sha256=digest(OUT/'input.npz'), original_capture_id=metadata['trial_id'],
        filter_backend='arm', raw_recording_in_private_directory=True,
        active_visual_trial=False, browser_network_rendering_excluded=True,
        independent_accuracy_claimed=False,
        frozen_hashes={p.name:digest(p) for p in files},
        harness_hashes={p.name:digest(p) for p in replay_files}))
    client = connect()
    stopped = False
    timer = 'guardianloop-replay-restore-ssvep-20261002'
    work = None
    try:
        before = snapshot(client, names)
        save(OUT/'before.json', before)
        if before['service_active'] != ['active','active']:
            raise RuntimeError('Original services are not both active')
        if before['hashes'] != {p.name:digest(p) for p in files}:
            raise RuntimeError('Board formal runtime differs from saved snapshot; no stop performed')
        work = checked(client, 'mktemp -d /home/xilinx/guardianloop-ssvep-backlog.XXXXXX').strip()
        if not work.startswith('/home/xilinx/guardianloop-ssvep-backlog.'):
            raise RuntimeError('Unexpected staging directory')
        sftp = client.open_sftp()
        try:
            for p in files:
                if p.suffix in ('.py','.json','.npy','.npz'):
                    sftp.put(str(p),work+'/'+p.name)
            for p in replay_files:
                sftp.put(str(p),work+'/'+p.name)
            sftp.put(str(OUT/'input.npz'),work+'/input.npz')
        finally:
            sftp.close()
        checked(client, 'env XILINX_XRT=/usr '+PYTHON+' -m py_compile '+
                shlex.quote(work+'/soak_service_replay.py')+' '+
                shlex.quote(work+'/replay_stage_trace.py'))
        checked(client, 'systemd-run --unit='+timer+
                ' --on-active=240s /bin/systemctl start guardianloop-cyton.service', sudo=True)
        checked(client, 'systemctl stop guardianloop-cyton.service', sudo=True)
        stopped = True
        state = checked(client,'systemctl show --property=ActiveState --value guardianloop-cyton.service').strip()
        if state != 'inactive':
            raise RuntimeError('Acquisition did not stop: '+state)
        save(OUT/'isolation.json', dict(remote_work=work, filter_backend='arm',
            formal_service_temporarily_stopped=True, recovery_timer_seconds=240,
            protected_files_changed=False, real_serial_opened=False, control_enabled=False))
        print('STARTED private 156-second ARM replay; live acquisition temporarily stopped', flush=True)
        shell = ('cd '+shlex.quote(work)+' && timeout 185s env '+
                 'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr '+PYTHON+
                 ' soak_service_replay.py --input input.npz --output run --seconds 156 '+
                 '--trace-stages --record-raw --volatile-primary-dir /dev/shm/ssvep-backlog-primary-20261002 '+
                 '--volatile-shadow-dir /dev/shm/ssvep-backlog-shadow-20261002')
        _, stdout, stderr = client.exec_command(shell)
        channel = stdout.channel
        output, errors, last_progress = bytearray(), bytearray(), time.monotonic()
        while not channel.exit_status_ready():
            while channel.recv_ready(): output.extend(channel.recv(65536))
            while channel.recv_stderr_ready(): errors.extend(channel.recv_stderr(65536))
            if time.monotonic()-last_progress >= 30:
                print('Private replay still running', flush=True)
                last_progress=time.monotonic()
            time.sleep(.2)
        while channel.recv_ready(): output.extend(channel.recv(65536))
        while channel.recv_stderr_ready(): errors.extend(channel.recv_stderr(65536))
        code=channel.recv_exit_status()
        save(OUT/'process.json', dict(exit_code=code,stdout=output.decode(errors='replace'),
                                    stderr=errors.decode(errors='replace')))
        if code:
            raise RuntimeError('Replay exit %d; preserve process.json and remote run' % code)
    finally:
        try:
            if stopped:
                checked(client,'systemctl start guardianloop-cyton.service',sudo=True)
                checked(client,'systemctl stop '+timer+'.timer',sudo=True)
            after=snapshot(client,names)
            save(OUT/'after.json',after)
            if 'before' in locals():
                save(OUT/'preservation.json',dict(
                    formal_file_hashes_unchanged=before['hashes']==after['hashes'],
                    service_config_hash_unchanged=before['service_configuration_sha256']==after['service_configuration_sha256'],
                    boot_id_unchanged=before['boot_id']==after['boot_id'],
                    services_restored=before['service_active']==after['service_active']))
        finally:
            if work is not None:
                sftp=client.open_sftp()
                try:
                    if 'run' in sftp.listdir(work):
                        download_tree(sftp,work+'/run',OUT/'run')
                finally:sftp.close()
            client.close()
    report=json.loads((OUT/'run/report.json').read_text())
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
