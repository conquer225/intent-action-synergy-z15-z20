"""Read-only live checks after the ARM cue-owner update; starts no trial."""
from datetime import datetime
import json
import shlex
import time

from deploy_ssvep_producer_cue import OUT, backend_probe, ledger
from run_soak_stage import PROD, command, connect
from run_mi_arm_acceptance import dump


def log_lines(client):
    code = """import pathlib,json
p=pathlib.Path(%s)
print(json.dumps({'exists':p.exists(),'lines':sum(1 for _ in p.open()) if p.exists() else 0}))
""" % repr(PROD + '/ssvep_cued_trials.jsonl')
    return json.loads(command(client, 'python3 -c ' + shlex.quote(code)))


def main():
    client = connect()
    try:
        plan = ledger()
        if plan['phase'] != 'verified':
            raise ValueError('Runtime update has not passed installation verification')
        before_log = log_lines(client)
        samples = []
        started = time.monotonic()
        for index in range(3):
            if index:
                time.sleep(10)
            probe = backend_probe(client)
            if probe['boot_id'] != plan['boot_id']:
                raise ValueError('Board rebooted during postflight')
            cue = probe['urls']['/api/ssvep-cue']
            if (cue.get('state_owner') != 'acquisition'
                    or cue.get('observation_mode') != 'producer_callbacks'
                    or cue.get('state') != 'idle' or cue.get('accepted') is not False
                    or cue.get('control_enabled') is not False
                    or probe['backend_listeners'] != ['0100007F:2391']):
                raise ValueError('Cue ownership, idle state or loopback binding changed')
            if probe['urls']['/api/mi-cue'].get('enabled') is not False:
                raise ValueError('MI must remain disabled')
            samples.append(dict(elapsed_seconds=time.monotonic()-started, probe=probe))
        after_log = log_lines(client)
        if before_log != after_log:
            raise ValueError('Idle polling changed cue audit; inspect concurrent activity')
        dump(OUT/'POSTFLIGHT.json', dict(
            pc_local_time=datetime.now().isoformat(), passed=True, samples=samples,
            cue_log_before=before_log, cue_log_after=after_log,
            trial_started=False, raw_recording_started=False,
            model_accuracy_evaluated=False, normal_boot_retested=False))
        logs = command(client, 'journalctl -u guardianloop-cyton.service '
                       '-u guardianloop-web.service -n 60 --no-pager')
        (OUT/'postflight-service.log').write_text(logs, encoding='utf-8')
        print(json.dumps(dict(passed=True, snapshots=[
            item['probe']['urls']['/api/ssvep-shadow'] for item in samples],
            units=samples[-1]['probe']['units'],
            idle_polling_added_audit_rows=False), ensure_ascii=False))
    finally:
        client.close()


if __name__ == '__main__':
    main()
