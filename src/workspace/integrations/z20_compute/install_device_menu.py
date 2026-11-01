"""Preview/apply the stopped Z15 device-menu revision with paired rollback."""
import argparse
import ast
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'eeg_demo'))
import install_demo as transaction


def plan_update(roots,bundle):
    transaction.ensure_stopped(roots)
    bundle=Path(bundle).resolve()
    manifest=json.loads((bundle/'menu-update.json').read_text(encoding='utf-8'))
    if manifest.get('format')!='z15-device-menu-v1':raise ValueError('Unknown menu update format')
    required_files={'system_hdmi.py','system_runtime/guardianloop_system/eye_devices.py',
                    'system_runtime/guardianloop_system/device_link.py'}
    if not required_files<=set(manifest['files']):raise ValueError('Incomplete device menu payload')
    pins=json.loads((roots['media']/'boot-pins.json').read_text(encoding='utf-8'))
    for name,sha in pins['files'].items():
        if transaction.digest(Path(name))!=sha:raise ValueError('Existing boot pin differs: '+name)
    payload={};expected={}
    for name,allowed in manifest.get('required',{}).items():
        expected[('media',name)]=allowed
    for name,row in manifest['files'].items():
        raw=bundle/row['source'];source=raw.resolve();source.relative_to(bundle)
        dest=transaction.target(roots,('media',name))
        if raw.is_symlink() or (roots['media']/name).is_symlink():
            raise ValueError('Symlink payload/target rejected')
        data=source.read_bytes()
        if transaction.digest(source)!=row['sha256']:raise ValueError('Menu payload checksum differs: '+name)
        if name.endswith('.py'):ast.parse(data,filename=str(dest),feature_version=(3,8))
        key=('media',name);payload[key]=data;expected[key]=row['before']
    return transaction.prepare(roots,payload,expected)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for group in ('media','brain','eye'):
        parser.add_argument('--'+group+'-root',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,default=HERE)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--rollback',type=Path)
    args=parser.parse_args()
    roots={group:getattr(args,group+'_root').resolve() for group in ('media','brain','eye')}
    if any(not p.is_dir() for p in roots.values()):raise ValueError('Existing runtime roots required')
    if args.rollback:
        transaction.rollback(roots,args.rollback);print('ROLLBACK_VERIFIED');return
    plan=plan_update(roots,args.bundle)
    print(json.dumps(dict(preview=not args.apply,files=[str(transaction.target(roots,k)) for k in plan]),indent=2))
    if args.apply:print('INSTALLED_BACKUP='+str(transaction.apply_transaction(roots,plan)))


if __name__=='__main__':main()
