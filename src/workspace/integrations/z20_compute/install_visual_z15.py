"""Preview/apply a stopped-runtime overlay with the established paired rollback."""
import argparse,hashlib,ipaddress,json,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'eeg_demo'))
import install_demo as transaction


from z20_compute.z15_visual_patch import patch_hdmi
from z20_compute.z15_feedback_patch import patch_signal_audio_guards


def encoded(row):return (json.dumps(row,ensure_ascii=False,indent=2)+'\n').encode('utf-8')


def plan_update(roots,bundle,*,host,token):
    address=ipaddress.IPv4Address(host)
    if not address.is_private or address.is_loopback or address.is_unspecified:raise ValueError('private wireless IPv4 required')
    if not 32<=len(token)<=128:raise ValueError('private token must contain 32..128 characters')
    bundle=Path(bundle).resolve();manifest=json.loads((bundle/'z15-overlay.json').read_text(encoding='utf-8'))
    media=roots['media'];payload={};expected={}
    pins=json.loads((media/'boot-pins.json').read_text(encoding='utf-8'))
    for name,sha in pins['files'].items():
        if transaction.digest(Path(name))!=sha:raise ValueError('Existing boot pin differs: '+name)
    for name,row in manifest['files'].items():
        source=(bundle/row['source']).resolve();source.relative_to(bundle)
        dest=transaction.target(roots,('media',name))
        if (bundle/row['source']).is_symlink() or dest.is_symlink():raise ValueError('symlink payload/target rejected')
        data=source.read_bytes()
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('overlay checksum mismatch: '+name)
        if name.endswith('.py'):compile(data,str(dest),'exec')
        payload[('media',name)]=data;expected[('media',name)]=row['before']
    source=(media/'system_hdmi.py').read_text(encoding='utf-8')
    payload[('media','system_hdmi.py')]=patch_hdmi(source).encode('utf-8')
    expected[('media','system_hdmi.py')]=manifest['system_hdmi_before']
    if manifest.get('signal_player_guards'):
        key=('media','media_player.py');path=media/'media_player.py'
        payload[key]=patch_signal_audio_guards(path.read_text(encoding='utf-8')).encode('utf-8')
        expected[key]=transaction.digest(path)
    state=json.loads((media/'media_state.json').read_text(encoding='utf-8'))
    if not state.get('vision_demo',{}).get('signal_pages'):raise ValueError('installed signal/vision baseline required')
    state['vision_demo'].update(enabled_image_modes=['neon','trails','motion'],enabled_signal_pages=['fatigue','emotion','music','audio'])
    payload[('media','media_state.json')]=encoded(state)
    payload[('media','z20_visual_config.json')]=encoded(dict(enabled=True,host=str(address),token=token))
    expected[('media','z20_visual_config.json')]=transaction.digest(media/'z20_visual_config.json')
    return transaction.prepare(roots,payload,expected)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for group in ('media','brain','eye'):parser.add_argument('--'+group+'-root',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,default=HERE/'z15');parser.add_argument('--host')
    parser.add_argument('--token-file',type=Path);parser.add_argument('--apply',action='store_true');parser.add_argument('--rollback',type=Path)
    args=parser.parse_args();roots={group:getattr(args,group+'_root').resolve() for group in ('media','brain','eye')}
    if args.rollback:transaction.rollback(roots,args.rollback);print('ROLLBACK_VERIFIED');return
    if not args.host or not args.token_file:parser.error('--host and --token-file are required')
    plan=plan_update(roots,args.bundle,host=args.host,token=args.token_file.read_text().strip())
    print(json.dumps(dict(preview=not args.apply,files=[str(transaction.target(roots,k)) for k in plan]),indent=2))
    if args.apply:
        backup=transaction.apply_transaction(roots,plan)
        (roots['media']/'z20_visual_config.json').chmod(0o600)
        print('INSTALLED_BACKUP='+str(backup))


if __name__=='__main__':main()
