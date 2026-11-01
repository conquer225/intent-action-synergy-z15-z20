"""Promote tested cache files only; unrelated models and PL stay untouched."""
import hashlib
import json
import sys
import time

from validate_ssvep_cache import ROOT, OUT, PROD, CACHE, connect, command, save


def main(folder):
    assert folder in ('cached_sync','cached_async')
    m=json.loads((OUT/'manifest.json').read_text())
    assert json.loads((OUT/'audit.json').read_text())['passed'][folder]
    assert json.loads((OUT/'math_parity.json').read_text())['passed']
    assert json.loads((OUT/(folder+'_primary_parity.json')).read_text())['passed']
    if (OUT/'deployment.json').exists(): raise RuntimeError('Deployment already attempted')
    paths=dict(CACHE)
    if folder=='cached_async':
        paths.update({n:ROOT/'pynq_guardianloop'/n for n in ('ssvep_async.py','cyton_guardianloop.py')})
    c=connect()
    backup=PROD+'/backup-ssvep-cache-'+time.strftime('%Y%m%d-%H%M%S')
    changed=False
    ledger=dict(phase='preflight',variant=folder,backup=backup,files=list(paths))
    existing=[n for n in paths if n in m['protected']]

    def restart():
        i,o,e=c.exec_command("sudo -S -p '' systemctl restart guardianloop-cyton.service",timeout=30)
        i.write('xilinx\n'); i.flush()
        output=o.read().decode()+e.read().decode()
        if o.channel.recv_exit_status(): raise RuntimeError(output)

    try:
        with c.open_sftp() as s:
            for n,h in m['protected'].items():
                assert hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest()==h,n
            for n,p in paths.items():
                assert hashlib.sha256(p.read_bytes()).hexdigest()==m['candidate'][n],n
                assert hashlib.sha256(s.open(m['stage']+'/'+folder+'/'+n).read()).hexdigest()==m['candidate'][n],n
            assert not (set(paths)-set(existing)).intersection(s.listdir(PROD))
        assert command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')==m['bitstreams']
        command(c,'mkdir '+backup)
        command(c,'cp -p '+' '.join(PROD+'/'+n for n in existing)+' '+backup+'/')
        save('deployment.json',ledger)
        with c.open_sftp() as s:
            for n,p in paths.items():
                s.put(str(p),PROD+'/'+n+'.cache-new')
                assert hashlib.sha256(s.open(PROD+'/'+n+'.cache-new').read()).hexdigest()==m['candidate'][n]
            changed=True
            for n in paths: s.posix_rename(PROD+'/'+n+'.cache-new',PROD+'/'+n)
        restart()
        # Allow interpreter/model startup, then confirm the actual board endpoint.
        time.sleep(20)
        ledger['services']=command(c,'systemctl show guardianloop-cyton guardianloop-web -p Id -p MainPID -p ActiveState -p SubState')
        assert ledger['services'].count('ActiveState=active')==2
        ledger['http']=json.loads(command(c,'curl --max-time 5 -fsS http://127.0.0.1:9102/api/ssvep-shadow'))
        assert ledger['http']['live'].get('source')=='live'
        assert ledger['http']['live']['control_enabled'] is False
        assert ledger['http']['live'].get('state')!='error'
        with c.open_sftp() as s:
            ledger['installed']={n:hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest() for n in paths}
            assert ledger['installed']=={n:m['candidate'][n] for n in paths}
            ledger['protected_unchanged']=all(hashlib.sha256(s.open(PROD+'/'+n).read()).hexdigest()==h
                                             for n,h in m['protected'].items() if n not in paths)
        assert ledger['protected_unchanged']
        assert command(c,'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')==m['bitstreams']
        ledger['phase']='deployed'; save('deployment.json',ledger)
        print(json.dumps(ledger,indent=2))
    except Exception:
        if changed:
            command(c,'cp -p '+' '.join(backup+'/'+n for n in existing)+' '+PROD+'/')
            restart(); ledger['phase']='rolled_back'; save('deployment.json',ledger)
        raise
    finally: c.close()


if __name__=='__main__': main(sys.argv[1])
