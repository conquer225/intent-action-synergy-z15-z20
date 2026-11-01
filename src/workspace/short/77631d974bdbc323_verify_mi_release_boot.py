"""Verify one authorized normal reboot; do not install files or change PL images."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shlex

from deploy_mi_formal_entry import CONFIGS, OUT as DEPLOYMENT, postflight
from deploy_ssvep_rail_coalesce import sudo
from run_mi_arm_acceptance import dump
from run_soak_stage import ROOT, PROD, command, connect

OUT = ROOT / 'eeg_apps_z15/output/mi_boot_acceptance_20261002'
RELEASE = 'guardianloop-fixed-cap-mi-entry-20261002'
UNITS = ('guardianloop-startup.service', 'guardianloop-cyton.service',
         'guardianloop-web.service', 'guardianloop-ap.service', 'guardianloop-dhcp.service')
UNIT_FILES = (
    '/etc/systemd/system/guardianloop-startup.service',
    '/etc/systemd/system/guardianloop-cyton.service.d/20-startup.conf',
    '/etc/systemd/system/guardianloop-web.service.d/20-startup.conf',
    '/etc/systemd/system/guardianloop-ap.service',
    '/etc/systemd/system/guardianloop-dhcp.service',
    *CONFIGS.values(),
)


def capture(client, ledger):
    result = postflight(client, ledger)
    probe = """import hashlib,json,pathlib,urllib.request,urllib.error
units=%r
root=pathlib.Path(%r)
boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
startup=json.loads(pathlib.Path('/run/guardianloop-startup/status.json').read_text())
unit_hashes={p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in units}
backup_hashes={name:hashlib.sha256(pathlib.Path(%r+'/'+name+'.original').read_bytes()).hexdigest()
 for name in ('cyton_guardianloop.py','guardianloop_web.py','release_manifest.json')}
with urllib.request.urlopen('http://192.168.50.1:9102/api/mi-cue',timeout=5) as response:
 hotspot=json.load(response)
request=urllib.request.Request('http://127.0.0.1:9102/api/mi-cue',
 data=b'{"action":"start","target":"left"}',
 headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:9102'})
try:
 with urllib.request.urlopen(request,timeout=5) as response:
  rejected={'status':response.status,'body':json.load(response)}
except urllib.error.HTTPError as error:
 with error:rejected={'status':error.code,'body':json.load(error)}
print(json.dumps({'boot_id':boot_id,'startup':startup,'unit_hashes':unit_hashes,
 'backup_hashes':backup_hashes,'hotspot_local_mi':hotspot,'disabled_post':rejected,
 'mi_config':json.loads(pathlib.Path('/etc/default/guardianloop-mi.json').read_text()),
 'dma_keeper':pathlib.Path('/dev/guardianloop_dma_keeper').exists(),
 'dma_modules':[x for x in pathlib.Path('/proc/modules').read_text().splitlines() if 'gldma' in x],
 'candidate_dt_node':pathlib.Path('/proc/device-tree/amba/dma-owner@40410000').exists(),
 'board_model':pathlib.Path('/proc/device-tree/model').read_bytes().rstrip(b'\\0').decode(),
 'uptime_seconds':float(pathlib.Path('/proc/uptime').read_text().split()[0]),
 'boot_run_files':sorted(str(p) for p in pathlib.Path('/run/guardianloop').glob('*'))}))
""" % (UNIT_FILES, PROD, ledger['stage'])
    result['boot_checks'] = json.loads(command(client, 'python3 -c ' + shlex.quote(probe)))
    result['services'] = {}
    for unit in UNITS:
        value = command(client, 'systemctl show ' + unit +
                        ' -p Id -p ActiveState -p SubState -p UnitFileState -p MainPID -p NRestarts')
        result['services'][unit] = dict(line.split('=', 1) for line in value.splitlines() if '=' in line)
    result['ip_addresses'] = command(client, 'ip -br addr')
    policy = command(client, 'systemctl show guardianloop-cyton.service '
                     '-p Restart -p RestartUSec -p TimeoutStopUSec -p KillMode -p Result')
    result['acquisition_policy'] = dict(line.split('=', 1) for line in policy.splitlines() if '=' in line)
    result['pc_local_time'] = datetime.now().astimezone().isoformat()
    return result


def check_common(result, ledger, offline_retry_observed=False):
    boot = result['boot_checks']
    if boot['mi_config'] != {'enabled': False} or boot['dma_keeper'] or boot['dma_modules'] or boot['candidate_dt_node']:
        raise ValueError('MI switch or candidate DMA state is not the approved formal state')
    if boot['disabled_post']['status'] != 409 or boot['disabled_post']['body']['result'] is not None:
        raise ValueError('Disabled MI accepted a command or kept a result')
    if boot['hotspot_local_mi']['state'] != 'disabled' or boot['hotspot_local_mi']['result'] is not None:
        raise ValueError('Hotspot-address MI endpoint is not disabled')
    for name, sha in boot['backup_hashes'].items():
        if sha != ledger['before']['hashes'][PROD + '/' + name]:
            raise ValueError('Original rollback backup changed: ' + name)
    for unit, state in result['services'].items():
        offline_retry = (unit == 'guardianloop-cyton.service' and offline_retry_observed
                         and state['ActiveState'] == 'activating' and state['SubState'] == 'auto-restart')
        if state['UnitFileState'] != 'enabled' or (state['ActiveState'] != 'active' and not offline_retry):
            raise ValueError('Automatic service is not enabled and active: ' + unit)
    if result['checks']['verified_files'] != 35:
        raise ValueError('Installed file count differs from the frozen release')


def preflight(client, ledger):
    OUT.mkdir(exist_ok=False)
    result = capture(client, ledger)
    dump(OUT / 'preflight.json', result)
    check_common(result, ledger)
    if result['checks']['http']['/api/status']['system']['startup'].get('arm_update_pending_boot') is not True:
        raise ValueError('This acceptance expects the original boot with the new ARM update pending')
    package = Path('D:/ican/handoff/GuardianLoop_MI_ENTRY_20261002.zip')
    sha = hashlib.sha256(package.read_bytes()).hexdigest()
    if sha != '1ebd95492e1dcb72ba253e265e3954e100673725f640c5e4db6f7c6081e6c0cc':
        raise ValueError('Sealed recovery bundle changed')
    dump(OUT / 'PLAN.json', {
        'preflight_passed': True, 'boot_id_before': result['boot_checks']['boot_id'],
        'release_id': RELEASE, 'target': 'Z15 / 192.168.2.99 / XC7Z015-CLG485-2',
        'project': PROD + '/guardianloop_pynq.bit', 'normal_reboot_authorized': True,
        'pl_action': 'Existing startup unit loads the unchanged production bit/HWH',
        'rollback_backup': ledger['stage'], 'recovery_package': str(package), 'package_sha256': sha,
        'no_boot_image_writes': True, 'no_new_bitstream': True, 'mi_enabled': False,
        'accuracy_tested': False, 'ethernet_unplug_test_planned': False,
    })
    print('BOOT_PREFLIGHT_PASSED', result['boot_checks']['boot_id'], flush=True)


def reboot(client):
    plan = json.loads((OUT / 'PLAN.json').read_text(encoding='utf-8'))
    if (OUT / 'REBOOT_REQUEST.json').exists():
        raise ValueError('One reboot was already requested; inspect the result instead of repeating')
    current = command(client, 'cat /proc/sys/kernel/random/boot_id').strip()
    if current != plan['boot_id_before']:
        raise ValueError('Board already rebooted; do not issue another reset')
    dump(OUT / 'REBOOT_REQUEST.json', {'pc_local_time': datetime.now().astimezone().isoformat(),
                                      'boot_id_before': current, 'command': 'systemctl reboot --no-block'})
    print(sudo(client, 'systemctl reboot --no-block'), flush=True)
    print('NORMAL_REBOOT_REQUESTED', flush=True)


def verify(client, ledger):
    before = json.loads((OUT / 'preflight.json').read_text(encoding='utf-8'))
    result = capture(client, ledger)
    dump(OUT / 'postflight.json', result)
    logs = sudo(client, 'journalctl -b -u guardianloop-startup.service -u guardianloop-cyton.service '
                '-u guardianloop-web.service -u guardianloop-ap.service -u guardianloop-dhcp.service '
                '--no-pager -n 160 -o short-monotonic')
    (OUT / 'boot-services.log').write_text(logs, encoding='utf-8')
    policy = result['acquisition_policy']
    offline_retry = ('CYTON_READER_TIMEOUT: No complete Cyton packet for 5 seconds' in logs
                     and 'Scheduled restart job' in logs
                     and 'FATIGUE_MODEL_READY' in logs and 'COVARIANCE_MODEL_READY' in logs
                     and policy['Restart'] == 'always' and policy['RestartUSec'] == '15s')
    check_common(result, ledger, offline_retry_observed=offline_retry)
    boot = result['boot_checks']
    startup = boot['startup']
    if boot['boot_id'] == before['boot_checks']['boot_id'] or startup['boot_id'] != boot['boot_id']:
        raise ValueError('No fresh matching boot report')
    if startup['state'] != 'ready' or startup['release_id'] != RELEASE or startup['verified_files'] != 35:
        raise ValueError('New release did not complete its boot self-test')
    pl = startup['pl']
    if pl['loaded'] is not True or pl['ids'] != {'de': '44453031', 'hgb': '48473031', 'model': '50537911'}:
        raise ValueError('Production PL identity check failed')
    if result['snapshot']['hashes'] != before['snapshot']['hashes'] or boot['unit_hashes'] != before['boot_checks']['unit_hashes']:
        raise ValueError('Runtime, models, PL pair, boot files or units changed across reboot')
    http = result['checks']['http']
    if http['/api/status']['system']['startup'].get('arm_update_pending_boot', False):
        raise ValueError('Web still reports pending boot')
    fatigue = http['/api/status']['fatigue']
    if not http['/api/status']['stale'] or fatigue.get('valid') or fatigue.get('score') is not None or fatigue.get('emotion', {}).get('valid'):
        raise ValueError('No-input state contains an emotion/fatigue prediction')
    for endpoint in ('/api/seed-shadow', '/api/ssvep-shadow'):
        if http[endpoint]['live'].get('valid'):
            raise ValueError('No-input shadow contains a valid candidate: ' + endpoint)
    if http['/api/ssvep-cue'].get('control_enabled') is not False:
        raise ValueError('SSVEP external control is enabled')
    dump(OUT / 'VERIFICATION.json', {
        'passed': True, 'new_boot_id': boot['boot_id'], 'release_id': RELEASE,
        'verified_files': 35, 'same_production_pl_loaded': True,
        'artifact_hashes_unchanged': True, 'all_five_units_enabled': True,
        'startup_web_ap_dhcp_active': True,
        'acquisition_state': result['services']['guardianloop-cyton.service'],
        'cyton_off_expected_timeout_restart_observed': offline_retry,
        'mi_disabled': True, 'mi_worker_listener_absent': not result['checks']['mi_listeners'],
        'no_old_predictions': True, 'hotspot_service_and_local_address_http_checked': True,
        'ethernet_unplug_retested': False, 'live_eeg_checked': False, 'accuracy_tested': False,
        'bitstream_generated': False, 'boot_images_modified': False,
        'shutdown_limit_seconds': 20, 'graceful_usb_shutdown_proven': False,
    })
    print('NEW_RELEASE_BOOT_VERIFIED', boot['boot_id'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'reboot', 'verify'))
    args = parser.parse_args()
    ledger = json.loads((DEPLOYMENT / 'deployment.json').read_text(encoding='utf-8'))
    if ledger['phase'] != 'installed_verified':
        raise ValueError('Formal ARM deployment is not verified')
    client = connect()
    try:
        if args.action == 'preflight':
            preflight(client, ledger)
        elif args.action == 'reboot':
            reboot(client)
        else:
            verify(client, ledger)
    finally:
        client.close()


if __name__ == '__main__':
    main()
