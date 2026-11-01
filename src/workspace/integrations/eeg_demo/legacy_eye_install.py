"""Install only the eye-device delta into a verified, stopped October 17 runtime."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import tempfile

BASE=Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def member(root, name):
    path=(root/name).resolve()
    path.relative_to(root.resolve())
    return path


def require_stopped(runtime):
    status=runtime/'player_status.json'
    if status.is_file():
        ident=json.loads(status.read_text(encoding='utf-8')).get('session_id','')
        if ident.startswith('play-') and len(ident)==13 and all(c in '0123456789abcdef' for c in ident[5:]):
            report=runtime/(ident+'-report.json')
            row=json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
            if not all(row.get(key) is True for key in ('display_halted','buffers_released','original_restored')):
                raise ValueError('Previous display cleanup is unverified; finish original recovery before installing')
    proc=Path('/proc')
    if not proc.is_dir(): return
    for path in proc.glob('[0-9]*/cmdline'):
        try: words=path.read_bytes().split(b'\0')
        except OSError: continue
        for word in words:
            if not word or Path(os.fsdecode(word)).name!='media_player.py': continue
            candidate=Path(os.fsdecode(word))
            if not candidate.is_absolute():
                try: candidate=path.parent.joinpath('cwd').resolve()/candidate
                except OSError: continue
            if candidate.resolve()==runtime/'media_player.py':
                raise ValueError('Stop the display session from the original phone panel before installing')


def atomic_write(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    mode=path.stat().st_mode if path.exists() else 0o644
    fd,name=tempfile.mkstemp(prefix='.eye-c3-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as handle: handle.write(data)
        os.chmod(name,mode)
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def apply_patch(runtime,payload,manifest,s3_host,apply=False):
    runtime=Path(runtime).resolve();payload=Path(payload).resolve()
    if not runtime.is_dir(): raise ValueError('Existing runtime directory required')
    address=ipaddress.ip_address(s3_host)
    if address.version!=4 or not address.is_private or address.is_loopback or address.is_unspecified:
        raise ValueError('Use the actual private S3 LAN IPv4 address')
    require_stopped(runtime)
    for name,expected in manifest['required'].items():
        if digest(member(runtime,name))!=expected:
            raise ValueError('Required baseline differs: '+name)
    planned={}
    for name,row in manifest['files'].items():
        target=member(runtime,name);source=member(payload,name)
        if digest(target)!=row['before']: raise ValueError('Installed baseline differs: '+name)
        if digest(source)!=row['after']: raise ValueError('Patch payload changed: '+name)
        planned[name]=source.read_bytes()
    config=runtime/'eye_devices.json'
    if config.exists(): raise ValueError('eye_devices.json already exists; inspect or roll back first')
    planned['eye_devices.json']=(json.dumps(dict(version=1,s3_host=str(address),s3_port=9000),
                                         indent=2)+'\n').encode()
    pins_path=runtime/'boot-pins.json'
    if pins_path.is_file():
        pins=json.loads(pins_path.read_text(encoding='utf-8'))
        if not isinstance(pins.get('files'),dict):raise ValueError('Invalid boot hash pins')
        for name,data in planned.items():
            target=str(member(runtime,name))
            if target in pins['files'] and pins['files'][target]!=digest(Path(target)):
                raise ValueError('Existing boot pin differs: '+name)
            pins['files'][target]=hashlib.sha256(data).hexdigest()
        planned['boot-pins.json']=(json.dumps(pins,indent=2)+'\n').encode()
    if not apply: return dict(runtime=str(runtime),files=list(planned),s3_host=str(address),preview=True)
    parent=runtime/'.eye-c3-backups';parent.mkdir(exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix='install-',dir=str(parent)))
    record={'runtime':str(runtime),'files':{}}
    for name,data in planned.items():
        target=member(runtime,name)
        record['files'][name]={'before':digest(target),'after':hashlib.sha256(data).hexdigest()}
        if target.exists():
            saved=member(backup,name);saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
    (backup/'record.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    written=[]
    try:
        for name,data in planned.items():
            atomic_write(member(runtime,name),data);written.append(name)
    except Exception:
        for name in reversed(written):
            target=member(runtime,name);original=member(backup,name)
            if original.exists(): shutil.copy2(original,target)
            else: target.unlink()
        raise
    return backup


def rollback(runtime,backup):
    runtime=Path(runtime).resolve();backup=Path(backup).resolve()
    require_stopped(runtime)
    record=json.loads((backup/'record.json').read_text(encoding='utf-8'))
    if str(runtime)!=record['runtime']: raise ValueError('Backup belongs to another runtime')
    for name,row in record['files'].items():
        if digest(member(runtime,name))!=row['after']:
            raise ValueError('Installed file changed after patch: '+name)
        if row['before'] is not None and digest(member(backup,name))!=row['before']:
            raise ValueError('Backup changed: '+name)
    for name,row in record['files'].items():
        target=member(runtime,name)
        if row['before'] is None: target.unlink()
        else: atomic_write(target,member(backup,name).read_bytes())
    return dict(restored=True,runtime=str(runtime))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--s3-host')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--rollback',type=Path)
    args=parser.parse_args()
    if args.rollback:
        print(json.dumps(rollback(args.runtime,args.rollback),indent=2));return
    if not args.s3_host: parser.error('--s3-host is required for preview/apply')
    manifest=json.loads((BASE/'patch_manifest.json').read_text(encoding='utf-8'))
    result=apply_patch(args.runtime,BASE/'runtime',manifest,args.s3_host,args.apply)
    print(str(result) if isinstance(result,Path) else json.dumps(result,indent=2))
    if args.apply: print('PATCH_INSTALLED. Restart the existing display session; enable each device by gaze.')


if __name__=='__main__': main()
