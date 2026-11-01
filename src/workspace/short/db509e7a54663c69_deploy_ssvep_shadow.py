"""Install a validated shadow branch with a recoverable two-file rollback."""
import hashlib
import json
import time

from validate_ssvep_shadow import OUT, PROD, CHANGED, NEW, sources, connect, command


def main():
    audit = json.loads((OUT/'audit.json').read_text())
    manifest = json.loads((OUT/'manifest.json').read_text())
    assert audit['passed'] and all(audit['parity'].values())
    assert audit['paced_check']['passed'] and audit['recorded_bridge_pc_arm']['passed']
    if (OUT/'deployment.json').exists():
        raise RuntimeError('Existing deployment ledger: inspect before modifying')
    client = connect()
    backup = PROD+'/backup-ssvep-shadow-'+time.strftime('%Y%m%d-%H%M%S')
    ledger = dict(backup=backup, phase='preflight', changed=CHANGED, added=NEW,
                  rollback='Restore the two backed-up Python files and restart cyton/web; added modules remain inert.')
    changed = False

    def save():
        (OUT/'deployment.json').write_text(json.dumps(ledger,indent=2),encoding='utf-8')

    def restart():
        stdin, stdout, stderr = client.exec_command("sudo -S -p '' systemctl restart guardianloop-cyton.service guardianloop-web.service",timeout=30)
        stdin.write('xilinx\n'); stdin.flush()
        text = stdout.read().decode()+stderr.read().decode()
        if stdout.channel.recv_exit_status():
            raise RuntimeError(text)

    try:
        with client.open_sftp() as sftp:
            for name, digest in manifest['protected'].items():
                assert hashlib.sha256(sftp.open(PROD+'/'+name).read()).hexdigest() == digest, name
            for name, path in sources().items():
                assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['candidate'][name], name
            existing = set(sftp.listdir(PROD))
            assert not existing.intersection(NEW), 'Do not overwrite an existing candidate'
        command(client, 'mkdir '+backup)
        command(client, 'cp -p '+' '.join(PROD+'/'+name for name in CHANGED)+' '+backup+'/')
        ledger['bitstreams_before'] = command(client, 'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')
        save()
        with client.open_sftp() as sftp:
            for name, path in sources().items():
                sftp.put(str(path),PROD+'/'+name+'.ssvep-new')
                assert hashlib.sha256(sftp.open(PROD+'/'+name+'.ssvep-new').read()).hexdigest()==manifest['candidate'][name]
            # Dependencies first; all files verified before replacing production entry points.
            for name in NEW:
                sftp.posix_rename(PROD+'/'+name+'.ssvep-new',PROD+'/'+name)
            changed = True
            for name in CHANGED:
                sftp.posix_rename(PROD+'/'+name+'.ssvep-new',PROD+'/'+name)
            sftp.put(str(OUT/'replay_status.json'),'/tmp/guardianloop-ssvep-replay.json.new')
            sftp.posix_rename('/tmp/guardianloop-ssvep-replay.json.new','/tmp/guardianloop-ssvep-replay.json')
        restart()
        time.sleep(4)
        ledger['http'] = json.loads(command(client,'curl --max-time 5 -fsS http://127.0.0.1:9102/api/ssvep-shadow'))
        assert ledger['http']['live']['source']=='live'
        assert ledger['http']['live']['control_enabled'] is False
        assert ledger['http']['replay']['source']=='replay'
        ledger['services'] = command(client,'systemctl show guardianloop-cyton guardianloop-web -p Id -p MainPID -p ActiveState -p SubState')
        assert ledger['services'].count('ActiveState=active') == 2
        ledger['bitstreams_after'] = command(client, 'sha256sum '+PROD+'/guardianloop_pynq.bit '+PROD+'/guardianloop_pynq.hwh')
        assert ledger['bitstreams_before']==ledger['bitstreams_after']==manifest['bitstreams']
        with client.open_sftp() as sftp:
            ledger['protected_unchanged'] = all(hashlib.sha256(sftp.open(PROD+'/'+n).read()).hexdigest()==h
                                               for n,h in manifest['protected'].items() if n not in CHANGED)
            ledger['installed_hashes'] = {n:hashlib.sha256(sftp.open(PROD+'/'+n).read()).hexdigest() for n in CHANGED+NEW}
        assert ledger['protected_unchanged']
        assert ledger['installed_hashes']==manifest['candidate']
        ledger['phase']='deployed'; save()
        print(json.dumps(ledger,indent=2))
    except Exception:
        if changed:
            command(client,'cp -p '+' '.join(backup+'/'+name for name in CHANGED)+' '+PROD+'/')
            restart()
            ledger['phase']='rolled_back'; save()
        raise
    finally:
        client.close()


if __name__=='__main__':
    main()
