"""Stopped-runtime, paired-integrity update for the live EEG demonstration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

BASE=Path(__file__).resolve().parent
CAP=['F3','F4','C3','C4','T7','T8','O1','O2']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def target(roots,key):
    group,name=key;root=roots[group].resolve();path=(root/name).resolve();path.relative_to(root)
    return path


def ensure_stopped(roots):
    if os.name!='posix':return
    watched={'media_player.py','media_server.py','guardianloop_acquisition.py','cyton_guardianloop.py','hdmi_live_entry.py'}
    for cmdline in Path('/proc').glob('[0-9]*/cmdline'):
        try:words=cmdline.read_bytes().split(b'\0')
        except OSError:continue
        for word in words:
            if not word:continue
            p=Path(os.fsdecode(word))
            if p.name not in watched:continue
            if not p.is_absolute():
                try:p=(cmdline.parent/'cwd').resolve()/p
                except OSError:continue
            p=p.resolve()
            if any(parent.resolve() in p.parents for parent in roots.values()):
                raise ValueError('Stop existing display, media web and acquisition services before applying: '+str(p))
    status=roots['media']/'player_status.json'
    if status.is_file():
        ident=json.loads(status.read_text(encoding='utf-8')).get('session_id','')
        if re.fullmatch('play-[a-f0-9]{8}',ident):
            report=roots['media']/(ident+'-report.json')
            row=json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
            if not all(row.get(k) is True for k in ('display_halted','buffers_released','original_restored')):
                raise ValueError('Original display cleanup is unverified; complete recovery first')


def prepare(roots,payload,expected):
    ensure_stopped(roots)
    for key,old in expected.items():
        actual=digest(target(roots,key));allowed=old if isinstance(old,list) else [old]
        if actual not in allowed:raise ValueError('Installed baseline differs: '+str(key))
    manifest_path=roots['brain']/'release_manifest.json'
    old_manifest=manifest_path.read_bytes();old_sha=hashlib.sha256(old_manifest).hexdigest()
    release=json.loads(old_manifest)
    if release.get('channels')!=CAP:raise ValueError('Fixed cap changed')
    for name,sha in release['files'].items():
        if Path(name).name!=name or digest(target(roots,('brain',name)))!=sha:
            raise ValueError('Release checksum mismatch: '+name)
    changes=dict(payload)
    for (group,name),data in payload.items():
        if group=='brain':
            if Path(name).name!=name:raise ValueError('Brain release names must be flat')
            release['files'][name]=hashlib.sha256(data).hexdigest()
    release['release_id']='guardianloop-eeg-demo-20261018'
    encoded=(json.dumps(release,ensure_ascii=False,indent=2)+'\n').encode()
    new_sha=hashlib.sha256(encoded).hexdigest();changes[('brain','release_manifest.json')]=encoded
    guard=target(roots,('eye','src/coexist_guard.py')).read_text(encoding='utf-8')
    if not re.search(r"PRIMARY_MANIFEST = '"+old_sha+"'",guard):raise ValueError('Coexistence guard does not match current release')
    guard=guard.replace("PRIMARY_MANIFEST = '"+old_sha+"'","PRIMARY_MANIFEST = '"+new_sha+"'")
    changes[('eye','src/coexist_guard.py')]=guard.encode()
    state_path=roots['media']/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'))
    if state.get('formal_hashes')!=json.loads(old_manifest)['files']:raise ValueError('Media formal hashes differ from current release')
    state['formal_hashes']=release['files'];changes[('media','state.json')]=(json.dumps(state,indent=2)+'\n').encode()
    pins=json.loads((roots['media']/'boot-pins.json').read_text(encoding='utf-8'))
    if pins.get('manifest_sha256',old_sha)!=old_sha:raise ValueError('Boot manifest pin differs')
    for key,data in changes.items():
        path=target(roots,key);name=str(path)
        if name in pins['files'] and pins['files'][name]!=digest(path):raise ValueError('Existing boot pin differs: '+name)
        # Original hdmi_boot updates state.json on every boot, outside fixed file pins.
        if key==('media','state.json') and name not in pins['files']:continue
        pins['files'][name]=hashlib.sha256(data).hexdigest()
    pins['manifest_sha256']=new_sha
    changes[('media','boot-pins.json')]=(json.dumps(pins,indent=2)+'\n').encode()
    return changes


def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    info=path.stat() if path.exists() else path.parent.stat()
    fd,tmp=tempfile.mkstemp(prefix='.eeg-update-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(tmp,(info.st_mode&0o777) if path.exists() else 0o644)
        if hasattr(os,'chown'):os.chown(tmp,info.st_uid,info.st_gid)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def apply_transaction(roots,plan):
    ensure_stopped(roots)
    parent=roots['media']/'.eeg-demo-backups';parent.mkdir(exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix='install-',dir=parent))
    record={'roots':{k:str(v.resolve()) for k,v in roots.items()},'files':[]}
    for key,data in plan.items():
        path=target(roots,key);old=digest(path);saved=backup/key[0]/key[1]
        if old is not None:saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,saved)
        record['files'].append(dict(group=key[0],name=key[1],before=old,after=hashlib.sha256(data).hexdigest()))
    (backup/'record.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    done=[]
    try:
        for key,data in plan.items():atomic(target(roots,key),data);done.append(key)
    except Exception:
        for key in reversed(done):
            saved=backup/key[0]/key[1];dest=target(roots,key)
            if saved.is_file():atomic(dest,saved.read_bytes())
            elif dest.exists():dest.unlink()
        raise
    return backup


def rollback(roots,backup):
    ensure_stopped(roots);backup=Path(backup).resolve();record=json.loads((backup/'record.json').read_text(encoding='utf-8'))
    if record['roots']!={k:str(v.resolve()) for k,v in roots.items()}:raise ValueError('Backup belongs to different roots')
    for row in record['files']:
        path=target(roots,(row['group'],row['name']));saved=backup/row['group']/row['name']
        if digest(path)!=row['after']:raise ValueError('Installed file changed: '+str(path))
        if row['before'] is not None and digest(saved)!=row['before']:raise ValueError('Backup changed: '+str(saved))
    for row in reversed(record['files']):
        path=target(roots,(row['group'],row['name']));saved=backup/row['group']/row['name']
        if row['before'] is None:path.unlink()
        else:atomic(path,saved.read_bytes())


def payload_files(roots,s3_host=None):
    manifest=json.loads((BASE/'update_manifest.json').read_text(encoding='utf-8'));payload={};expected={}
    if digest(roots['brain']/'release_manifest.json')!=manifest['brain_manifest_before']:
        raise ValueError('Unknown brain release manifest; inspect baseline first')
    if digest(roots['eye']/'src/coexist_guard.py')!=manifest['guard_before']:
        raise ValueError('Unknown coexistence guard baseline')
    for row in manifest['files']:
        key=(row['group'],row['name']);source=BASE/row['source']
        if digest(source)!=row['after']:raise ValueError('Reviewed payload changed: '+row['source'])
        payload[key]=source.read_bytes();expected[key]=row['before']
    config=roots['media']/'eye_devices.json'
    if not config.exists():
        if not s3_host:raise ValueError('Fresh baseline needs --s3-host with actual S3 address')
        import ipaddress
        address=ipaddress.ip_address(s3_host)
        if address.version!=4 or not address.is_private or address.is_loopback or address.is_unspecified:raise ValueError('Private S3 IPv4 required')
        key=('media','eye_devices.json');payload[key]=(json.dumps(dict(version=1,s3_host=str(address),s3_port=9000),indent=2)+'\n').encode();expected[key]=None
    return payload,expected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media-root',type=Path,required=True);parser.add_argument('--brain-root',type=Path,required=True)
    parser.add_argument('--eye-root',type=Path,required=True);parser.add_argument('--s3-host');parser.add_argument('--apply',action='store_true');parser.add_argument('--rollback',type=Path)
    args=parser.parse_args();roots={'media':args.media_root.resolve(),'brain':args.brain_root.resolve(),'eye':args.eye_root.resolve()}
    if any(not p.is_dir() for p in roots.values()):raise ValueError('Existing runtime roots required')
    if args.rollback:rollback(roots,args.rollback);print('Paired rollback verified');return
    payload,expected=payload_files(roots,args.s3_host);plan=prepare(roots,payload,expected)
    print(json.dumps({'preview':not args.apply,'files':[str(target(roots,k)) for k in plan]},indent=2))
    if args.apply:print('INSTALLED_BACKUP='+str(apply_transaction(roots,plan)))


if __name__=='__main__':main()
