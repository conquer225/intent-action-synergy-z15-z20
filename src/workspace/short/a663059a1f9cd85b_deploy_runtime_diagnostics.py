"""Deploy the audited two-file runtime repair, preserving models and rollback copies."""
import hashlib
import json
import time
from eeg_apps_z15.run_soak_stage import ROOT,OUT,PROD,connect,command


def main():
    audit=json.loads((OUT/'audit.json').read_text())
    assert audit['soak']['passed'] and audit['final_candidate_soak']['passed']
    assert audit['freshness_guard_soak']['passed']
    assert all(v['passed'] for v in audit['no_fault_parity'].values())
    assert all(v['passed'] for v in audit['recovery']['cases'])
    tests=(OUT/'candidate/final-tests.txt').read_text()
    assert 'Ran 21 tests' in tests and tests.rstrip().endswith('OK')
    m=json.loads((OUT/'manifest.json').read_text())
    final=json.loads((OUT/'candidate_manifest.json').read_text())
    c=connect();changed=False
    backup=PROD+'/backup-runtime-diagnostics-'+time.strftime('%Y%m%d-%H%M%S')
    ledger={'backup':backup,'changed':m['changed'],'phase':'preflight'}
    def save():(OUT/'deployment.json').write_text(json.dumps(ledger,indent=2))
    def restart():
        stdin,stdout,stderr=c.exec_command("sudo -S -p '' systemctl restart guardianloop-web.service guardianloop-cyton.service",timeout=30)
        stdin.write('xilinx\n');stdin.flush()
        output=stdout.read().decode()+stderr.read().decode()
        if stdout.channel.recv_exit_status():raise RuntimeError(output)
    try:
        with c.open_sftp() as s:
            for name,sha in m['protected'].items():
                with s.open(PROD+'/'+name,'rb') as f:assert hashlib.sha256(f.read()).hexdigest()==sha,name
            for name in m['changed']:
                assert hashlib.sha256((ROOT/'pynq_guardianloop'/name).read_bytes()).hexdigest()==final['hashes'][name],name
        command(c,'mkdir '+backup)
        command(c,'cp -p '+' '.join(PROD+'/'+n for n in m['changed'])+' '+backup+'/')
        save()
        with c.open_sftp() as s:
            for name in m['changed']:
                s.put(str(ROOT/'pynq_guardianloop'/name),PROD+'/'+name+'.runtime-new')
                with s.open(PROD+'/'+name+'.runtime-new','rb') as f:
                    assert hashlib.sha256(f.read()).hexdigest()==final['hashes'][name]
            changed=True
            for name in m['changed']:s.posix_rename(PROD+'/'+name+'.runtime-new',PROD+'/'+name)
        restart()
        # Board imports and first acquisition startup take several seconds.
        time.sleep(8)
        for _ in range(40):
            time.sleep(1)
            raw=command(c,'curl --max-time 3 -fsS http://127.0.0.1:9102/api/telemetry')
            response=json.loads(raw);t=response.get('telemetry',{})
            if not response['stale'] and 'primary_stream_resets' in (t.get('runtime') or {}):
                break
        else:raise RuntimeError('Fresh diagnostics not observed after restart; rolling back')
        assert t['source']=='cyton_usb' and t['real'] is True and not t.get('offline')
        ledger['telemetry']={k:v for k,v in t.items() if k not in ('samples','raw_samples','sqi','emotion')}
        ledger['snapshot_age_seconds']=response.get('snapshot_age_seconds')
        ledger['services']=command(c,'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        assert ledger['services'].count('ActiveState=active')==2
        assert command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')==m['bitstreams']
        with c.open_sftp() as s:
            for name,sha in m['protected'].items():
                expected=final['hashes'][name] if name in m['changed'] else sha
                with s.open(PROD+'/'+name,'rb') as f:assert hashlib.sha256(f.read()).hexdigest()==expected,name
        ledger['phase']='deployed';save();print(json.dumps(ledger,indent=2))
    except Exception:
        if changed:
            command(c,'cp -p '+' '.join(backup+'/'+n for n in m['changed'])+' '+PROD+'/')
            restart()
            ledger['phase']='rolled_back';save()
        raise
    finally:c.close()


if __name__=='__main__':main()
