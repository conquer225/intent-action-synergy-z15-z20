"""Isolated, instrumented board comparison; production never stopped or modified."""
import hashlib
import json
import sys
from pathlib import Path

from run_soak_stage import connect, PROD
from run_ssvep_causal_board_replay import command
from validate_ssvep_cache import CACHE, PREFIX, ROOT

OUT = ROOT/'eeg_apps_z15/output/stall_trace_20260927'
PREVIOUS = ROOT/'eeg_apps_z15/output/ssvep_cache_20260927'


def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2), encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=False)
    previous = json.loads((PREVIOUS/'manifest.json').read_text())
    c = connect()
    c.get_transport().set_keepalive(15)
    try:
        remote = command(c, 'mktemp -d /home/xilinx/stall-trace-XXXXXX').strip()
        if not remote.startswith('/home/xilinx/stall-trace-') or '\n' in remote:
            raise RuntimeError('Invalid stage path')
        manifest = dict(stage=remote, protected=previous['protected'],
            input_sha256=previous['input_sha256'], sources={},
            protocol='90s recorded paced replay: baseline, cache, cache without telemetry. '
                'All use stage tracing; no promotion decision from instrumented timings. '
                'Compare primary results exactly; separate wall and thread CPU. '
                'Production stays active; no USB or PL access; no new EEG labels.',
            services_before=command(c, 'systemctl show guardianloop-cyton guardianloop-web -p Id -p MainPID -p NRestarts -p ActiveState'))
        with c.open_sftp() as s:
            for name, digest in previous['protected'].items():
                if hashlib.sha256(s.open(PROD+'/'+name).read()).hexdigest() != digest:
                    raise RuntimeError('Production changed: '+name)
            for variant in ('baseline', 'cached'):
                command(c, 'mkdir '+remote+'/'+variant)
                for name in previous['protected']:
                    path = CACHE[name] if variant == 'cached' and name in CACHE else PREVIOUS/'original'/name
                    s.put(str(path), remote+'/'+variant+'/'+name)
                    manifest['sources'][variant+'/'+name] = hashlib.sha256(path.read_bytes()).hexdigest()
                for name in ('soak_service_replay.py', 'replay_stage_trace.py', 'test_replay_stage_trace.py'):
                    path = ROOT/'pynq_guardianloop'/name
                    s.put(str(path), remote+'/'+variant+'/'+name)
                    manifest['sources'][variant+'/'+name] = hashlib.sha256(path.read_bytes()).hexdigest()
            s.put(str(PREVIOUS.parent/'board_pipeline_profile_20260926/input.npz'), remote+'/input.npz')
        save('manifest.json', manifest)
        tests = command(c, 'cd '+remote+'/cached && '+PREFIX+'-m unittest test_replay_stage_trace 2>&1', timeout=30)
        (OUT/'tests.txt').write_text(tests)
        print(tests, flush=True)
        reports = {}
        for variant, output, extra in (('baseline','baseline',''), ('cached','cached',''),
                                       ('cached','without_telemetry',' --without-telemetry')):
            print('Starting '+output, flush=True)
            command(c, 'cd '+remote+'/'+variant+' && '+PREFIX+
                'soak_service_replay.py --input ../input.npz --seconds 90 --trace-stages --output '+output+extra,
                timeout=180)
            local = OUT/output
            local.mkdir()
            with c.open_sftp() as s:
                for name in s.listdir(remote+'/'+variant+'/'+output):
                    if name.endswith(('.json', '.jsonl', '.log')):
                        s.get(remote+'/'+variant+'/'+output+'/'+name, str(local/name))
            reports[output] = json.loads((local/'report.json').read_text())
            print(json.dumps(reports[output], indent=2), flush=True)
            (local/'services_after.txt').write_text(command(c,
                'systemctl show guardianloop-cyton guardianloop-web -p Id -p MainPID -p NRestarts -p ActiveState'))
        reference = json.loads((OUT/'baseline/primary_results.json').read_text())
        parity = {name: json.loads((OUT/name/'primary_results.json').read_text()) == reference
                  for name in reports}
        with c.open_sftp() as s:
            unchanged = all(hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest() == h
                            for n,h in previous['protected'].items())
        save('audit.json', dict(reports=reports, primary_exact=parity,
            production_unchanged=unchanged, deployed=False,
            complete=all(parity.values()) and unchanged and all(
                r['packets_consumed']==22500 and not r['error'] and not r['remaining_children']
                for r in reports.values())))
    finally:
        c.close()


def storage_check():
    manifest = json.loads((OUT/'manifest.json').read_text())
    if not (OUT/'audit.json').exists():
        raise RuntimeError('Finish the initial comparison first')
    remote = manifest['stage']
    c = connect()
    c.get_transport().set_keepalive(15)
    try:
        memory = command(c, 'mktemp -d /dev/shm/stall-primary-XXXXXX').strip()
        if not memory.startswith('/dev/shm/stall-primary-') or '\n' in memory:
            raise RuntimeError('Invalid temporary path')
        mounts = command(c, 'findmnt -T /run/guardianloop; findmnt -T /tmp; findmnt -T '+remote+'; findmnt -T '+memory)
        path = ROOT/'pynq_guardianloop/soak_service_replay.py'
        with c.open_sftp() as s:
            s.put(str(path), remote+'/cached/soak_service_replay.py')
        save('storage_check_manifest.json', dict(primary_dir=memory+'/data', mounts=mounts,
            harness_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            hypothesis='Original replay writes primary telemetry/status on SD; production uses /run tmpfs. '
                'Change only these destinations, retaining shadow/log files on SD. Exploratory one-run check.'))
        print('Starting production-like primary tmpfs storage', flush=True)
        command(c, 'cd '+remote+'/cached && '+PREFIX+
            'soak_service_replay.py --input ../input.npz --seconds 90 --trace-stages --output primary_tmpfs '
            '--volatile-primary-dir '+memory+'/data', timeout=180)
        local = OUT/'primary_tmpfs'
        local.mkdir()
        with c.open_sftp() as s:
            for name in s.listdir(remote+'/cached/primary_tmpfs'):
                if name.endswith(('.json','.jsonl','.log')):
                    s.get(remote+'/cached/primary_tmpfs/'+name, str(local/name))
            for name in s.listdir(memory+'/data'):
                s.get(memory+'/data/'+name, str(local/name))
            unchanged = all(hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest()==h
                            for n,h in manifest['protected'].items())
        report = json.loads((local/'report.json').read_text())
        reference = json.loads((OUT/'baseline/primary_results.json').read_text())
        save('storage_check_audit.json', dict(report=report,
            primary_exact=json.loads((local/'primary_results.json').read_text())==reference,
            production_unchanged=unchanged, deployed=False))
        print(json.dumps(report,indent=2), flush=True)
    finally:
        c.close()


def observe_live():
    manifest = json.loads((OUT/'manifest.json').read_text())
    remote = manifest['stage']
    c = connect()
    try:
        path = ROOT/'pynq_guardianloop/observe_live_runtime.py'
        with c.open_sftp() as s:
            s.put(str(path), remote+'/'+path.name)
        save('passive_manifest.json', dict(script_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            seconds=60, processes_before=command(c,'ps -eo pid,ppid,pcpu,args'),
            services_before=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p MainPID -p NRestarts -p ActiveState')))
        print('Read-only production timing, 60 seconds; no replay',flush=True)
        command(c,'cd '+remote+' && '+PREFIX+'observe_live_runtime.py --output passive.json',timeout=90)
        with c.open_sftp() as s:
            s.get(remote+'/passive.json',str(OUT/'passive.json'))
            unchanged=all(hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest()==h
                          for n,h in manifest['protected'].items())
        save('passive_after.json',dict(production_unchanged=unchanged,
            services_after=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p MainPID -p NRestarts -p ActiveState'),
            journal=command(c,"journalctl -u guardianloop-cyton -o short-monotonic -n 180 --no-pager | grep -v CYTON_WINDOW_RESULT | tail -25")))
        print('Passive observation complete; production unchanged='+str(unchanged),flush=True)
    finally:
        c.close()


if __name__ == '__main__':
    if '--observe-live' in sys.argv:
        observe_live()
    elif '--storage-check' in sys.argv:
        storage_check()
    else:
        main()
