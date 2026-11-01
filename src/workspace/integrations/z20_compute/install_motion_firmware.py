"""Install the Z15 firmware pair and its audio pins in one stopped transaction."""
import argparse,hashlib,json,re,sys,uuid,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'eeg_demo'))
import install_demo as transaction

ADDRESSES=dict(axi_vdma_0=0x43000000,axi_vdma_1=0x43010000,live_osd_0=0x43c00000,
              v_tc_0=0x43c10000,pcm_buffer_0=0x43c20000,vision_core_0=0x43c30000,
              vision_keys_0=0x43c40000,audio_fft_0=0x43c50000)
REPORTS=('timing.rpt','cdc.rpt','methodology.rpt','drc.rpt','io.rpt','utilization.rpt')


def plan_update(roots,candidate):
    transaction.ensure_stopped(roots)
    media=roots['media'];pins=json.loads((media/'boot-pins.json').read_text())
    for name,digest in pins['files'].items():
        if transaction.digest(Path(name))!=digest:raise ValueError('Existing boot pin differs: '+name)
    with zipfile.ZipFile(candidate) as archive:
        quality=json.loads(archive.read('quality.json'))
        if quality.get('passed') is not True or quality.get('part')!='xc7z015clg485-2':
            raise ValueError('Passed Z15 routed candidate required')
        names=['candidate/guardianloop_display_audio.'+suffix for suffix in ('bit','hwh')]
        files={}
        for name in names+list(REPORTS):
            info=archive.getinfo(name)
            if info.file_size>16*1024*1024:raise ValueError('Oversized candidate member')
            data=archive.read(name)
            if hashlib.sha256(data).hexdigest()!=quality['files'].get(name):
                raise ValueError('Candidate checksum mismatch: '+name)
            files[name]=data
    hwh=ET.fromstring(files[names[1]])
    addresses={r.get('INSTANCE'):int(r.get('BASEVALUE'),16) for r in hwh.iter('MEMRANGE')}
    if any(addresses.get(n)!=a for n,a in ADDRESSES.items()):raise ValueError('Z15 HWH ABI mismatch')
    state_path=media/'media_state.json';state=json.loads(state_path.read_text())
    audio_path=media/'page_audio.py';audio=audio_path.read_text();payload={};expected={}
    for suffix,member in zip(('bit','hwh'),names):
        name='vision_demo/overlay/display_vision.'+suffix;path=media/name
        old=state['hardware_hashes'].get(str(path));new=hashlib.sha256(files[member]).hexdigest()
        if not old or transaction.digest(path)!=old:raise ValueError('Installed firmware differs: '+name)
        if audio.count(old)!=1:raise ValueError('Audio firmware pin differs: '+suffix)
        audio=audio.replace(old,new,1)
        payload[('media',name)]=files[member];expected[('media',name)]=old
        state['hardware_hashes'][str(path)]=new
    compile(audio,str(audio_path),'exec')
    for name,data in (('page_audio.py',audio.encode()),('media_state.json',(json.dumps(state,indent=2)+'\n').encode())):
        payload[('media',name)]=data;expected[('media',name)]=transaction.digest(media/name)
    return transaction.prepare(roots,payload,expected)


def retire_history(roots):
    transaction.ensure_stopped(roots);media=roots['media'];path=media/'player_status.json'
    if not path.exists():return
    ident=json.loads(path.read_text()).get('session_id','')
    if not re.fullmatch('play-[a-f0-9]{8}',ident):raise ValueError('Unknown display history')
    # ensure_stopped already verified this session's completed recovery flags.
    token=uuid.uuid4().hex[:8];path.rename(media/('vision-status-before-'+token+'.json'))
    ram=Path('/dev/shm')/(media.name+'-player-status.json')
    if ram.exists():ram.rename(ram.with_name(media.name+'-status-before-firmware-'+token+'.json'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('media','brain','eye'):parser.add_argument('--'+name+'-root',type=Path,required=True)
    parser.add_argument('--candidate',type=Path);parser.add_argument('--apply',action='store_true')
    parser.add_argument('--rollback',type=Path)
    args=parser.parse_args();roots={n:getattr(args,n+'_root').resolve() for n in ('media','brain','eye')}
    if args.rollback:
        transaction.rollback(roots,args.rollback);retire_history(roots);print('ROLLBACK_VERIFIED');return
    if args.candidate is None:parser.error('--candidate required')
    plan=plan_update(roots,args.candidate)
    print(json.dumps(dict(preview=not args.apply,files=[str(transaction.target(roots,k)) for k in plan]),indent=2))
    if args.apply:
        backup=transaction.apply_transaction(roots,plan);retire_history(roots)
        print('INSTALLED_BACKUP='+str(backup))


if __name__=='__main__':main()
