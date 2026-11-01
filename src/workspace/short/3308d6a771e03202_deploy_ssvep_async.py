"""Promote only a passing asynchronous candidate; keep a two-file rollback."""
import hashlib
import json
import time

from validate_ssvep_async import ROOT, OUT, CHANGED, NEW, PROD, connect, command, save


def main():
    audit=json.loads((OUT/'audit.json').read_text())
    m=json.loads((OUT/'manifest.json').read_text())
    assert audit['passed'] and all(audit['checks'].values()), 'Candidate has not passed'
    assert json.loads((OUT/'primary_parity.json').read_text())['passed']
    if (OUT/'deployment.json').exists():
        raise RuntimeError('Deployment ledger exists')
    c=connect()
    backup=PROD+'/backup-ssvep-async-'+time.strftime('%Y%m%d-%H%M%S')
    ledger=dict(backup=backup,phase='preflight',changed=CHANGED,new=NEW)
    changed=False

    def restart():
        i,o,e=c.exec_command("sudo -S -p '' systemctl restart guardianloop-cyton.service",timeout=30)
        i.write('xilinx\n'); i.flush()
        log=o.read().decode()+e.read().decode()
        if o.channel.recv_exit_status(): raise RuntimeError(log)

    try:
        with c.open_sftp() as s:
            for n,h in m['protected'].items():
                assert hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest()==h,n
            assert not set(NEW).intersection(s.listdir(PROD))
            for n,h in m['candidate'].items():
                assert hashlib.sha256((ROOT/'pynq_guardianloop'/n).read_bytes()).hexdigest()==h,n
                assert hashlib.sha256(s.open(m['stage']+'/candidate/'+n).read()).hexdigest()==h,n
        assert command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')==m['bitstreams']
        command(c,'mkdir '+backup)
        command(c,'cp -p '+' '.join(PROD+'/'+n for n in CHANGED)+' '+backup+'/')
        save('deployment.json',ledger)
        with c.open_sftp() as s:
            for n,h in m['candidate'].items():
                s.put(str(ROOT/'pynq_guardianloop'/n),PROD+'/'+n+'.async-new')
                assert hashlib.sha256(s.open(PROD+'/'+n+'.async-new').read()).hexdigest()==h
            for n in NEW:
                s.posix_rename(PROD+'/'+n+'.async-new',PROD+'/'+n)
            changed=True
            for n in CHANGED:
                s.posix_rename(PROD+'/'+n+'.async-new',PROD+'/'+n)
        restart()
        for _ in range(20):
            time.sleep(2)
            response=json.loads(command(c,'curl --max-time 5 -fsS http://127.0.0.1:9102/api/ssvep-shadow'))
            if response['live'].get('async_worker'):
                break
        assert response['live'].get('async_worker') and not response['live']['control_enabled']
        assert response['live']['state']!='error',response
        ledger['http']=response
        ledger['services']=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p MainPID -p ActiveState -p SubState')
        assert ledger['services'].count('ActiveState=active')==2
        with c.open_sftp() as s:
            ledger['installed']={n:hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest() for n in CHANGED+NEW}
            assert ledger['installed']==m['candidate']
            ledger['protected_unchanged']=all(hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest()==h
                                               for n,h in m['protected'].items() if n not in CHANGED)
        assert ledger['protected_unchanged']
        assert command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')==m['bitstreams']
        ledger['phase']='deployed'
        save('deployment.json',ledger)
        print(json.dumps(ledger,indent=2))
    except Exception:
        if changed:
            command(c,'cp -p '+' '.join(backup+'/'+n for n in CHANGED)+' '+PROD+'/')
            restart()
            ledger['phase']='rolled_back'
            save('deployment.json',ledger)
        raise
    finally:
        c.close()


if __name__=='__main__':
    main()
