"""Small source-only menu update; never reads or writes the frozen archive."""
import hashlib
import json
from pathlib import Path
import zipfile

from z20_compute.z15_visual_patch import patch_hdmi

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
RUNTIME=HERE.parent/'eeg_demo/runtime'


def sha(data):return hashlib.sha256(data).hexdigest()


def dependency_sources():
    names=('presentation_theme.py','presentation_eye.py',
           'system_runtime/guardianloop_system/core.py',
           'system_runtime/guardianloop_system/page_policy.py',
           'system_runtime/guardianloop_system/c3_client.py')
    result={name:RUNTIME/name for name in names}
    for name in ('__init__.py','visual_wire.py','visual_server.py','wireless_only.py','z15_visual_client.py'):
        result['z20_compute/'+name]=HERE/'z20_compute'/name
    return result


def known_hashes(name):
    values=set()
    for family,filename in (('eye_c3','patch_manifest.json'),('eeg_demo','update_manifest.json')):
        row=json.loads((HERE.parent/family/filename).read_text(encoding='utf-8'))
        files=row['files']
        entry=files.get(name) if isinstance(files,dict) else next((r for r in files if r['group']=='media' and r['name']==name),None)
        if entry:
            before=entry['before'];values.update(before if isinstance(before,list) else [before])
            values.add(entry['after'])
    for manifest in (PROJECT/'local').glob('*/bundle_manifest.json'):
        values.add(json.loads(manifest.read_text(encoding='utf-8')).get('files',{}).get(name))
    saved=PROJECT/'local/presentation_bundle_20261025_release'/name
    if saved.is_file():values.add(sha(saved.read_bytes()))
    prior=json.loads((HERE/'report/z15_visual_prior_release_20261027.json').read_text(encoding='utf-8'))
    values.add(prior['files'].get(name))
    if name=='system_hdmi.py':
        values.update(prior['system_hdmi_before'])
        for path in (HERE/'build/eye-audio-fix-20261028/system_hdmi.py',
                     HERE/'report/eye_audio_20261028/board-system_hdmi.py'):
            values.add(sha(path.read_bytes()))
    if name.endswith('/device_link.py'):
        values.add(sha((HERE/'report/eye_audio_20261028/board-device_link.py').read_bytes()))
    return values-{None}


def create_release(output):
    files={};rows={}
    for name in ('system_hdmi.py','system_runtime/guardianloop_system/eye_devices.py',
                 'system_runtime/guardianloop_system/device_link.py',
                 'z20_compute/z15_visual_menu.py','z20_compute/z15_visual_patch.py'):
        source=(HERE/name) if name.startswith('z20_compute/') else RUNTIME/name
        data=source.read_bytes()
        if name=='system_hdmi.py':data=patch_hdmi(data.decode('utf-8')).encode('utf-8')
        member='payload/'+name;files[member]=data
        rows[name]=dict(source=member,sha256=sha(data),before=sorted(known_hashes(name)|{sha(data)}))
    required={name:sorted(known_hashes(name)|{sha(path.read_bytes())}) for name,path in dependency_sources().items()}
    manifest=dict(format='z15-device-menu-v1',revision='20261030-offline',files=rows,required=required,
                  board_validated=False,firmware_included=False,configuration_changed=False,
                  hardware_motion_verified=False)
    files['menu-update.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    for source,name in ((HERE/'install_device_menu.py','install_device_menu.py'),
                        (HERE.parent/'eeg_demo/install_demo.py','install_demo.py'),
                        (HERE/'report/device_menu_20261030.md','README.md')):
        files[name]=source.read_bytes()
    checks=HERE/'report/device_menu_20261030_checks.json'
    if checks.is_file():files[checks.name]=checks.read_bytes()
    for source in (HERE.parent/'eeg_demo/report/previews').glob('*.png'):
        if source.stem in ('equipment','hand','pendulum_menu','pendulum_balance','pendulum_turn','hand_stopped','hand_disconnected'):
            files['previews/'+source.name]=source.read_bytes()
    files['SHA256.json']=(json.dumps({name:sha(data) for name,data in sorted(files.items())},indent=2)+'\n').encode('utf-8')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()):z.writestr(name,data)
    with zipfile.ZipFile(output) as z:
        if z.testzip() is not None:raise ValueError('Menu release CRC failed')
        for name,digest in json.loads(z.read('SHA256.json')).items():
            if sha(z.read(name))!=digest:raise ValueError('Menu release checksum failed: '+name)
    output.with_suffix('.sha256.txt').write_text(sha(output.read_bytes())+'  '+output.name+'\n',encoding='ascii')
    return output


if __name__=='__main__':
    path=create_release(PROJECT/'delivery/GuardianLoop_Device_Menu_20261030_candidate.zip')
    print(json.dumps(dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path.read_bytes())),indent=2))
