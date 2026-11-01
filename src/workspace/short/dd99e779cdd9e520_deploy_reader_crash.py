"""Promote tested crash-edge fix only; backup and restore on failed verification."""
import hashlib
import json
import time

from deploy_reader_faults import restart
from run_soak_stage import connect, PROD
from run_ssvep_causal_board_replay import command
from validate_ssvep_cache import ROOT

OUT=ROOT/'eeg_apps_z15/output/reader_crash_final_20260927'
PRIOR=ROOT/'eeg_apps_z15/output/reader_faults_final_20260927'
ENTRY=ROOT/'pynq_guardianloop/cyton_guardianloop.py'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(value):
    (OUT/'deployment.json').write_text(json.dumps(value,indent=2),encoding='utf-8')


def main():
    if (OUT/'deployment.json').exists():
        raise RuntimeError('Deployment already attempted')
    manifest=json.loads((OUT/'manifest.json').read_text())
    audit=json.loads((OUT/'audit.json').read_text())
    previous=json.loads((PRIOR/'deployment.json').read_text())
    if not audit['passed'] or previous['phase']!='verified':
        raise RuntimeError('Pre-deployment audit failed')
    expected=manifest['entry_sha256']
    if sha(ENTRY.read_bytes())!=expected:
        raise RuntimeError('Local file changed after isolated validation')
    c=connect()
    backup=PROD+'/backup-reader-crash-'+time.strftime('%Y%m%d-%H%M%S')
    ledger=dict(phase='preflight',backup=backup,changed='cyton_guardianloop.py',
        expected_sha256=expected,
        rollback='Restore backup/cyton_guardianloop.py and restart guardianloop-cyton.service')
    changed=False
    try:
        with c.open_sftp() as s:
            for n,h in manifest['protected'].items():
                want=previous['installed_sha256'] if n=='cyton_guardianloop.py' else h
                if sha(s.open(PROD+'/'+n).read())!=want:
                    raise RuntimeError('Production drift: '+n)
            if sha(s.open(manifest['stage']+'/candidate/cyton_guardianloop.py').read())!=expected:
                raise RuntimeError('Tested staged file drift')
        ledger['bitstreams_before']=command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')
        ledger['services_before']=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p ActiveState -p MainPID -p NRestarts')
        if ledger['services_before'].count('ActiveState=active')!=2:
            raise RuntimeError('Production baseline services not both active')
        command(c,'mkdir '+backup)
        command(c,'cp -p '+PROD+'/cyton_guardianloop.py '+backup+'/')
        save(ledger)
        with c.open_sftp() as s:
            s.put(str(ENTRY),PROD+'/cyton_guardianloop.py.crash-new')
            if sha(s.open(PROD+'/cyton_guardianloop.py.crash-new').read())!=expected:
                raise RuntimeError('Upload checksum mismatch')
            changed=True
            s.posix_rename(PROD+'/cyton_guardianloop.py.crash-new',PROD+'/cyton_guardianloop.py')
        restart(c)
        time.sleep(8)
        ledger['services_after']=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p ActiveState -p MainPID -p NRestarts')
        if ledger['services_after'].count('ActiveState=active')!=2:
            raise RuntimeError('Services not both active')
        ledger['web_http']=json.loads(command(c,'curl --max-time 5 -fsS http://127.0.0.1:9102/api/ssvep-shadow'))
        live=ledger['web_http']['live']
        if live.get('source')!='live' or live.get('control_enabled') is not False:
            raise RuntimeError('Unsafe or missing live shadow state')
        with c.open_sftp() as s:
            ledger['installed_sha256']=sha(s.open(PROD+'/cyton_guardianloop.py').read())
            ledger['other_protected_unchanged']=all(
                sha(s.open(PROD+'/'+n).read())==h for n,h in manifest['protected'].items()
                if n!='cyton_guardianloop.py')
        ledger['bitstreams_after']=command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')
        if (ledger['installed_sha256']!=expected or not ledger['other_protected_unchanged']
                or ledger['bitstreams_before']!=ledger['bitstreams_after']):
            raise RuntimeError('Post-install checksum mismatch')
        ledger['phase']='verified'
        save(ledger)
        print(json.dumps({k:v for k,v in ledger.items() if k!='web_http'},indent=2))
    except Exception as exc:
        ledger['error']=repr(exc)
        if changed:
            try:
                command(c,'cp -p '+backup+'/cyton_guardianloop.py '+PROD+'/cyton_guardianloop.py')
                restart(c)
                ledger['phase']='rolled_back'
            except Exception as rollback_exc:
                ledger['phase']='rollback_failed'
                ledger['rollback_error']=repr(rollback_exc)
        else:
            ledger['phase']='preflight_failed'
        save(ledger)
        raise
    finally:
        c.close()


if __name__=='__main__':
    main()
