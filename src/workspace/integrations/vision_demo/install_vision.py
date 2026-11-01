"""Paired, stopped-runtime vision installation using the existing integrity transaction."""
import argparse,hashlib,json,os,sys,uuid
from pathlib import Path
import xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'eeg_demo'))
import install_demo as transaction

def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def retire_display_status(roots,ram_root=Path('/dev/shm')):
    """Preserve completed session history; prevent adoption across FPGA changes."""
    transaction.ensure_stopped(roots)
    media=roots['media'].resolve();path=media/'player_status.json'
    if not path.exists():return None
    row=json.loads(path.read_text());ident=row.get('session_id','')
    if not __import__('re').fullmatch('play-[a-f0-9]{8}',ident):
        raise ValueError('Unrecognized display history; inspect before retiring')
    report=json.loads((media/(ident+'-report.json')).read_text())
    if not all(report.get(k) is True for k in ('display_halted','buffers_released','original_restored')):
        raise ValueError('Display cleanup unverified')
    token=uuid.uuid4().hex[:8];archive=media/('vision-status-before-'+token+'.json')
    path.rename(archive)
    ram=Path(ram_root)/(media.name+'-player-status.json')
    if ram.exists():ram.rename(ram.with_name(media.name+'-status-before-vision-'+token+'.json'))
    return archive

def plan_update(roots,bundle):
    bundle=Path(bundle).resolve();manifest=json.loads((bundle/'bundle_manifest.json').read_text())
    if manifest.get('version')!=1 or manifest.get('gates_passed') is not True:raise ValueError('Routed hardware gates are required')
    payload={}
    for name,sha in manifest['files'].items():
        supplied=bundle/name;source=supplied.resolve()
        try:source.relative_to(bundle)
        except ValueError:raise ValueError('Bundle path escapes package: '+name)
        if supplied.is_symlink() or transaction.digest(source)!=sha:
            raise ValueError('Bundle checksum mismatch: '+name)
        payload[('media',name)]=source.read_bytes()
    required={'media_player.py','vision_demo/addon.py','vision_demo/libvision_capture.so','vision_demo/bin/tobii-images',
              'vision_demo/overlay/display_vision.bit','vision_demo/overlay/display_vision.hwh'}
    if not required.issubset(manifest['files']):raise ValueError('Incomplete vision bundle')
    hwh=ET.fromstring(payload[('media','vision_demo/overlay/display_vision.hwh')])
    addresses={r.get('INSTANCE'):int(r.get('BASEVALUE'),16) for r in hwh.iter('MEMRANGE')}
    required_addresses={'axi_vdma_0':0x43000000,'axi_vdma_1':0x43010000,'live_osd_0':0x43c00000,
        'v_tc_0':0x43c10000,'pcm_buffer_0':0x43c20000,'vision_core_0':0x43c30000,'vision_keys_0':0x43c40000}
    if any(addresses.get(name)!=address for name,address in required_addresses.items()):
        raise ValueError('Vision HWH ABI mismatch')
    if manifest.get('signal_pages'):
        if addresses.get('audio_fft_0')!=0x43c50000:raise ValueError('Audio FFT HWH mismatch')
        extra={'vision_demo/bin/signal-pcm','vision_demo/music/catalog.json','vision_demo/replay/replay.json','vision_demo/replay/eeg_replay.npz'}
        if not extra.issubset(manifest['files']):raise ValueError('Signal asset bundle incomplete')
    if manifest.get('presentation_release'):
        surfaces={'system_hdmi.py','presentation_theme.py','presentation_eye.py','presentation.css',
          'system_mobile.html','system_mobile.js','media_server.py','eeg_demo.html','eeg_demo.css',
          'eeg_demo.js','eeg_demo_core.js','eeg_recording.json','player.html','upload.html'}
        if manifest.get('signal_pages') is not True or not surfaces.issubset(manifest['files']):raise ValueError('Presentation bundle incomplete')
    media=roots['media'].resolve()
    pins=json.loads((media/'boot-pins.json').read_text())
    for name,sha in pins['files'].items():
        if transaction.digest(Path(name))!=sha:raise ValueError('Existing boot pin differs: '+name)
    state=json.loads((media/'media_state.json').read_text())
    state['vision_demo']=dict(camera_library=str(media/'vision_demo/libvision_capture.so'),
        tobii_binary=str(media/'vision_demo/bin/tobii-images'),cascade_root='/usr/share/opencv4/haarcascades',
        font='/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',streaming=manifest.get('architecture')=='native_stream',signal_pages=manifest.get('signal_pages',False))
    state['display_overlay']=str(media/'vision_demo/overlay/display_vision.bit')
    for name in ('display_vision.bit','display_vision.hwh'):
        relative='vision_demo/overlay/'+name
        state['hardware_hashes'][str(media/relative)]=manifest['files'][relative]
    payload[('media','media_state.json')]=encoded(state)
    payload[('media','vision_demo/bundle_manifest.json')]=(bundle/'bundle_manifest.json').read_bytes()
    expected={('media','media_player.py'):manifest['baseline_player']}
    expected.update({('media',name):sha for name,sha in manifest.get('baseline_files',{}).items()})
    # New package files may not replace an unreviewed existing installation.
    for key in payload:
        if key[1].startswith('vision_demo/'):expected[key]=None
    return transaction.prepare(roots,payload,expected)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for group in ('media','brain','eye'):p.add_argument('--'+group+'-root',type=Path,required=True)
    p.add_argument('--bundle',type=Path);p.add_argument('--apply',action='store_true');p.add_argument('--rollback',type=Path)
    a=p.parse_args();roots={k:getattr(a,k+'_root').resolve() for k in ('media','brain','eye')}
    if a.rollback:
        transaction.rollback(roots,a.rollback);retire_display_status(roots)
        print('Vision paired rollback verified');return
    if a.bundle is None:p.error('--bundle is required unless --rollback is used')
    plan=plan_update(roots,a.bundle)
    print(json.dumps(dict(preview=not a.apply,files=[str(transaction.target(roots,k)) for k in plan]),indent=2))
    if a.apply:
        backup=transaction.apply_transaction(roots,plan)
        try:
            (roots['media']/'vision_demo/bin/tobii-images').chmod(0o755)
            if (roots['media']/'vision_demo/bin/signal-pcm').exists():(roots['media']/'vision_demo/bin/signal-pcm').chmod(0o755)
        except Exception:transaction.rollback(roots,backup);raise
        retire_display_status(roots)
        print('INSTALLED_BACKUP='+str(backup))
if __name__=='__main__':main()
