"""Promote exactly the isolated-tested serial-reader diagnostic entry point."""
import hashlib
import json
from pathlib import Path
import time

from run_soak_stage import connect, PROD
from run_ssvep_causal_board_replay import command
from validate_ssvep_cache import ROOT

OUT = ROOT/'eeg_apps_z15/output/reader_faults_final_20260927'
ENTRY = ROOT/'pynq_guardianloop/cyton_guardianloop.py'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(value):
    (OUT/'deployment.json').write_text(json.dumps(value,indent=2),encoding='utf-8')


def restart(c):
    stdin,stdout,stderr=c.exec_command("sudo -S -p '' systemctl restart guardianloop-cyton.service",timeout=30)
    stdin.write('xilinx\n')
    stdin.flush()
    output=stdout.read().decode()+stderr.read().decode()
    if stdout.channel.recv_exit_status():
        raise RuntimeError(output)


def main():
    manifest=json.loads((OUT/'manifest.json').read_text())
    audit=json.loads((OUT/'audit.json').read_text())
    if not audit['passed'] or not audit['production_unchanged']:
        raise RuntimeError('Isolated acceptance did not pass')
    if (OUT/'deployment.json').exists():
        raise RuntimeError('A deployment has already been attempted')
    expected=manifest['candidate_sha256']
    if digest(ENTRY.read_bytes())!=expected:
        raise RuntimeError('Local entry point changed after testing')
    c=connect()
    backup=PROD+'/backup-reader-faults-'+time.strftime('%Y%m%d-%H%M%S')
    ledger=dict(phase='preflight',backup=backup,changed='cyton_guardianloop.py',
                expected_sha256=expected,rollback='Restore saved file and restart guardianloop-cyton.service')
    changed=False
    try:
        with c.open_sftp() as s:
            for n,h in manifest['protected'].items():
                if digest(s.open(PROD+'/'+n).read())!=h:
                    raise RuntimeError('Production changed since isolation: '+n)
            if digest(s.open(manifest['stage']+'/candidate/cyton_guardianloop.py').read())!=expected:
                raise RuntimeError('Tested stage changed')
        ledger['bitstreams_before']=command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')
        ledger['services_before']=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p ActiveState -p MainPID -p NRestarts')
        if ledger['services_before'].count('ActiveState=active')!=2:
            raise RuntimeError('Baseline services not active')
        command(c,'mkdir '+backup)
        command(c,'cp -p '+PROD+'/cyton_guardianloop.py '+backup+'/')
        save(ledger)
        with c.open_sftp() as s:
            s.put(str(ENTRY),PROD+'/cyton_guardianloop.py.reader-new')
            if digest(s.open(PROD+'/cyton_guardianloop.py.reader-new').read())!=expected:
                raise RuntimeError('Upload checksum mismatch')
            changed=True
            s.posix_rename(PROD+'/cyton_guardianloop.py.reader-new',PROD+'/cyton_guardianloop.py')
        ledger['phase']='installed'
        save(ledger)
        restart(c)
        time.sleep(8)
        ledger['services_after']=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p ActiveState -p MainPID -p NRestarts')
        if ledger['services_after'].count('ActiveState=active')!=2:
            raise RuntimeError('Services not active after restart')
        ledger['web_http']=json.loads(command(c,'curl --max-time 5 -fsS http://127.0.0.1:9102/api/ssvep-shadow'))
        live=ledger['web_http']['live']
        if live.get('source')!='live' or live.get('control_enabled') is not False:
            raise RuntimeError('Live shadow endpoint is not safely observation-only')
        with c.open_sftp() as s:
            ledger['installed_sha256']=digest(s.open(PROD+'/cyton_guardianloop.py').read())
            ledger['other_protected_unchanged']=all(
                digest(s.open(PROD+'/'+n).read())==h for n,h in manifest['protected'].items()
                if n!='cyton_guardianloop.py')
        if ledger['installed_sha256']!=expected or not ledger['other_protected_unchanged']:
            raise RuntimeError('Post-install checksum mismatch')
        ledger['bitstreams_after']=command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')
        if ledger['bitstreams_after']!=ledger['bitstreams_before']:
            raise RuntimeError('Unexpected PL artifact change')
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
