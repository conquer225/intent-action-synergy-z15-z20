"""Explicit, reversible configuration for the retained observation-only MI worker."""
import argparse,json,os,subprocess
from pathlib import Path
CONFIG=Path('/etc/default/guardianloop-mi.json')
BACKUP=Path('/var/lib/intent-one/mi-backup.json')
def main():
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--rollback',action='store_true');a=p.parse_args()
    if not a.apply:
        print(json.dumps({'config':str(CONFIG),'enabled':not a.rollback,'restart':'guardianloop-cyton.service','actuator_control':False}));return
    if os.geteuid()!=0:raise PermissionError('run on the Z15 with sudo')
    # Do not restart acquisition while the integrated display/control owner runs.
    import fcntl
    with open('/run/lock/guardianloop-pl.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.rollback:
            saved=json.loads(BACKUP.read_text(encoding='utf8'))
            if saved['exists']:CONFIG.write_text(saved['content'],encoding='utf8')
            elif CONFIG.exists():CONFIG.unlink()
        else:
            if BACKUP.exists():raise RuntimeError('MI backup already exists; inspect or rollback before reapplying')
            content=CONFIG.read_text(encoding='utf8') if CONFIG.exists() else None
            if content:
                data=json.loads(content)
                if not isinstance(data,dict) or set(data)!={'enabled'} or type(data['enabled']) is not bool:raise ValueError('unexpected original MI configuration')
            BACKUP.parent.mkdir(parents=True,exist_ok=True)
            BACKUP.write_text(json.dumps({'exists':content is not None,'content':content}),encoding='utf8');os.chmod(BACKUP,0o600)
            CONFIG.write_text('{"enabled":true}\n',encoding='utf8')
        subprocess.run(['systemctl','restart','guardianloop-cyton.service'],check=True)
if __name__=='__main__':main()
