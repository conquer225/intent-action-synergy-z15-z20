"""Read-only final acceptance after a formal reload or identical-file recovery."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from reload_formal_board import audit, units


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads((args.stage/'expected.json').read_text())
    operation = json.loads((args.stage/'result.json').read_text())
    if operation.get('startup', {}).get('pl', {}).get('loaded') is not True:
        raise ValueError('No evidence that this operation reloaded the formal PL')
    before = audit(expected)
    startup = json.loads(Path('/run/guardianloop-startup/status.json').read_text())
    if (startup.get('state') != 'ready' or startup.get('boot_id') != expected['boot_id']
            or startup.get('release_id') != expected['manifest']['release_id']
            or startup.get('pl', {}).get('ids') != {'de':'44453031','hgb':'48473031','model':'50537911'}):
        raise ValueError('Current PL/model startup evidence mismatch')
    attempts = []
    pages = {}
    for path in ('/', '/mi-cued', '/ssvep-cued', '/ssvep-free'):
        for attempt in range(2):
            began = time.monotonic()
            try:
                response = subprocess.run(['curl','--noproxy','*','--fail','--max-time','3',
                    '-sS','http://127.0.0.1:9102'+path],capture_output=True,timeout=4)
                if response.returncode:
                    raise OSError(response.stderr.decode(errors='replace').strip())
                if b'<!doctype html' not in response.stdout.lower():
                    raise ValueError('Expected complete HTML response')
                pages[path] = len(response.stdout)
                attempts.append(dict(path=path, attempt=attempt+1, passed=True,
                                     seconds=time.monotonic()-began))
                break
            except OSError as exc:
                attempts.append(dict(path=path, attempt=attempt+1, passed=False,
                                     error=type(exc).__name__+': '+str(exc)))
                if attempt == 1:
                    raise
                time.sleep(1)
    service_state = units()
    time.sleep(10)
    after = audit(expected)
    if after['services'] != service_state:
        raise ValueError('Service state changed during the short check')
    result = dict(passed=True, arm_application_recopied=True, pl_reloaded=True,
        initial_acceptance_passed=operation['passed'],
        identical_application_restored=operation.get('application_rollback_completed',False),
        original_failure=operation.get('error'), before=before, after=after, startup=startup,
        page_bytes=pages, page_attempts=attempts, stable_services_seconds=10,
        protected_hashes_verified=True, boot_files_changed=False, board_rebooted=False,
        models_changed=False, physical_control=False, human_accuracy_measured=False,
        daemon_reload_state=subprocess.check_output(['systemctl','show',
            'guardianloop-cyton.service','guardianloop-web.service','-p','Id','-p','NeedDaemonReload'],text=True))
    destination = args.stage/'verification.json'
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(passed=True,result=str(destination),pages=pages)),flush=True)


if __name__ == '__main__':
    main()
