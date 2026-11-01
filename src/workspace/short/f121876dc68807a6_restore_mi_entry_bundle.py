"""On-board ARM-only restore/rollback for this bundle; default is read-only check."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

APP = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
CONFIGS = {'guardianloop-mi.json':Path('/etc/default/guardianloop-mi.json'),
           'guardianloop-cyton-mi.conf':Path('/etc/systemd/system/guardianloop-cyton.service.d/30-mi-entry.conf')}
OLD = ('cyton_guardianloop.py','guardianloop_web.py','release_manifest.json')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect(bundle):
    ledger=json.loads((bundle/'evidence/deployment.json').read_text())
    if ledger['phase']!='installed_verified' or not ledger.get('passed'):
        raise ValueError('Bundle does not describe a verified install')
    if not set(ledger['install_hashes']).issubset(ledger['application_hashes']):
        raise ValueError('Install targets are outside the verified runtime')
    for name,value in ledger['application_hashes'].items():
        if Path(name).name!=name or sha(bundle/'runtime'/name)!=value:
            raise ValueError('Package runtime checksum/path mismatch: '+name)
    for name,value in ledger['config_hashes'].items():
        if name not in CONFIGS or sha(bundle/'systemd'/name)!=value:
            raise ValueError('Package configuration mismatch: '+name)
    for name in OLD:
        if sha(bundle/'rollback_original'/name)!=ledger['before']['hashes'][str(APP/name)]:
            raise ValueError('Original rollback checksum mismatch: '+name)
    for text,value in ledger['before']['hashes'].items():
        path=Path(text)
        if path in (APP/name for name in OLD):continue
        if sha(path)!=value:raise ValueError('Untouched board file differs: '+text)
    for name,new in ledger['install_hashes'].items():
        path=APP/name
        if path.exists() and sha(path) not in (new,ledger['before']['hashes'].get(str(path))):
            raise ValueError('Foreign modification: '+str(path))
    for name,path in CONFIGS.items():
        if not path.exists():continue
        if name=='guardianloop-mi.json':
            value=json.loads(path.read_text())
            if not isinstance(value,dict) or set(value)!={'enabled'} or type(value['enabled']) is not bool:
                raise ValueError('Foreign MI configuration')
        elif sha(path)!=ledger['config_hashes'][name]:
            raise ValueError('Foreign service drop-in')
    subprocess.run(['systemctl','is-active','--quiet','guardianloop-startup.service'],check=True)
    return ledger


def install(source,destination):
    subprocess.run(['install','-m','644',str(source),str(destination)],check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('check','restore-arm','rollback-arm'),nargs='?',default='check')
    parser.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args();bundle=args.bundle.resolve()
    ledger=inspect(bundle)
    if args.action=='check':
        print('ARM_RESTORE_PREFLIGHT_OK: no board writes or PL operation')
        return
    if os.geteuid()!=0:raise PermissionError('Run the chosen ARM change with sudo')
    subprocess.run(['systemctl','stop','guardianloop-cyton.service','guardianloop-web.service'],check=True)
    saved=None
    try:
        if args.action=='restore-arm':
            for name in ledger['install_hashes']:install(bundle/'runtime'/name,APP/name)
            for name,path in CONFIGS.items():install(bundle/'systemd'/name,path)
        else:
            saved=Path(tempfile.mkdtemp(prefix='withdrawn-mi-',dir=str(APP)))
            for name in OLD:install(bundle/'rollback_original'/name,APP/name)
            for name in ledger['install_hashes']:
                if name not in OLD and (APP/name).exists():shutil.move(str(APP/name),str(saved/name))
            for name,path in CONFIGS.items():
                if path.exists():shutil.move(str(path),str(saved/name))
        subprocess.run(['systemctl','daemon-reload'],check=True)
    finally:
        # The already-active startup oneshot is not restarted or invoked here.
        subprocess.run(['systemctl','start','guardianloop-web.service','guardianloop-cyton.service'],check=True)
    if args.action=='restore-arm':
        for name,value in ledger['application_hashes'].items():
            if sha(APP/name)!=value:raise ValueError('Installed checksum mismatch: '+name)
    else:
        for text,value in ledger['before']['hashes'].items():
            if sha(text)!=value:raise ValueError('Rollback checksum mismatch: '+text)
    print(json.dumps(dict(action=args.action,passed=True,pl_changed=False,boot_changed=False,
                          saved_new_files=str(saved) if saved else None)))


if __name__=='__main__':main()
