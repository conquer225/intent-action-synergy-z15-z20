"""Freeze the exact original and previous eye patch baselines for installation."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    baseline=json.loads((ROOT/'baseline_sha256.json').read_text(encoding='utf-8'))
    previous=ROOT.parent/'eye_c3'
    if not previous.exists():previous=ROOT.parent/'eye_c3_update'
    eye=json.loads((previous/'patch_manifest.json').read_text(encoding='utf-8'))
    entries=[]
    media=['media_player.py','system_hdmi.py','system_runtime/guardianloop_system/eye_devices.py',
           'system_runtime/guardianloop_system/device_link.py','system_runtime/guardianloop_system/c3_client.py',
           'media_server.py','system_mobile.html','system_mobile.js','eeg_demo_bridge.py']
    for name in media:
        source='runtime/'+name;before=baseline.get(source)
        if name in eye['files']:before=list(dict.fromkeys([eye['files'][name]['before'],eye['files'][name]['after']]))
        entries.append(dict(group='media',name=name,source=source,before=before,after=sha(ROOT/source)))
    for name in ('eeg_demo.html','eeg_demo.css','eeg_demo.js','eeg_demo_core.js'):
        entries.append(dict(group='media',name=name,source='web/'+name,before=None,after=sha(ROOT/'web'/name)))
    for name in ('cyton_covariance.py','cyton_fatigue.py','cyton_guardianloop.py','primary_window.py','processing_diagnostics.py'):
        source='brain_runtime/'+name
        entries.append(dict(group='brain',name=name,source=source,before=baseline.get(source),after=sha(ROOT/source)))
    original=ROOT.parent/'guardianloop_team_20261017_03'
    if not original.exists():original=ROOT.parent
    base=original/'latest_saved_runtime/rootfs'
    guard=base/'home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py'
    manifest={'version':1,'source_archive_sha256':eye['source_archive_sha256'],'previous_eye_delivery':'GuardianLoop_Eye_C3_20261018.zip',
              'brain_manifest_before':baseline['brain_runtime/release_manifest.json'],'guard_before':sha(guard),'files':entries}
    (ROOT/'update_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Reviewed payload files:',len(entries))


if __name__=='__main__':main()
