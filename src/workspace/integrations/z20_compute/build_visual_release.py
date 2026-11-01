"""Content-pinned four-mode offline release. All real-board gates remain explicit."""
import hashlib,json,zipfile
from pathlib import Path
from z20_compute.z15_visual_patch import patch_hdmi,_patch_menu

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]


def create_release(output):
    payload={}
    def add(path,name):payload[name]=Path(path).read_bytes()
    def tree(source,target):
        for path in sorted(Path(source).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:add(path,target+'/'+path.relative_to(source).as_posix())
    tree(HERE/'z20_compute','z20_compute');tree(HERE/'web/visual_demo','web/visual_demo')
    tree(HERE/'third_party/visual','third_party/visual')
    payload['web/visual_demo/LICENSE']=payload['third_party/visual/spectrum/LICENSE']
    for row in json.loads(payload['third_party/visual/sources.json'])['files']:
        if hashlib.sha256(payload['third_party/visual/'+row['path']]).hexdigest()!=row['sha256']:
            raise ValueError('upstream asset checksum differs: '+row['path'])
    tree(HERE/'artifacts/headless/models','models');tree(HERE/'artifacts/headless/display','assets/display')
    tree(HERE/'artifacts/headless/sound/pcm','assets/sound/pcm')
    add(HERE/'artifacts/headless/sound/manifest.json','assets/sound/manifest.json')
    add(HERE/'artifacts/headless/lemon_features.json','assets/lemon_features.json')
    add(HERE/'build/navigator/scene-bgr.npy','assets/replay/scene-bgr.npy')
    add(HERE/'build/visual-demo/libz20_visual.so','assets/display/libz20_visual.so')
    add(HERE/'build/visual-demo/native-build.json','sources/visual-native-build.json')
    add(HERE/'build/reconstruction/models/yolo26m-depth.pt','build/reconstruction/models/yolo26m-depth.pt')
    checkpoint=payload['build/reconstruction/models/yolo26m-depth.pt']
    payload['sources/yolo26m-depth.json']=json.dumps(dict(name='yolo26m-depth.pt',
        url='https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26m-depth.pt',
        sha256=hashlib.sha256(checkpoint).hexdigest(),license='AGPL-3.0',metric_verified=False),indent=2).encode()
    for path in (HERE/'build/reconstruction-venv/Lib/site-packages').glob('ultralytics-*.dist-info/licenses/*'):
        if path.is_file():add(path,'sources/ultralytics/'+path.name)
    add(HERE/'artifacts/wifi-build/rtl8733bu.tar.gz','sources/rtl8733bu.tar.gz')
    add(HERE/'artifacts/wifi-build/8733bu-navigator-20261027.ko','drivers/8733bu-navigator-20261027.ko')
    add(HERE/'report/board_20261027/wifi-build-result.json','drivers/build-result.json')
    add(HERE/'hardware/linux/build_wifi_native.py','drivers/build_wifi_native.py')
    payload['drivers/README.md']=('RTL8733BU / Navigator CLG400\n\n'
        'Built for 5.4.0-xilinx-v2020.2 SMP preempt mod_unload modversions ARMv7 p2v8.\n'
        'The build record describes compilation only; physical checks are separate.\n'
        'Manual insmod only after matching kernel and USB 0bda:b733 checks.\n'
        'Do not force-load or replace the running kernel. No autoload/startup changes.\n'
        'Driver source and license: sources/rtl8733bu.tar.gz.\n').encode()
    for name in ('npu-100.json','pc-arm-parity.json','socket-check.json','summary.json','visual/verification.json',
                 'z15-final-state.json','z15-actual-menu-check.json','z15-to-s3-wireless.json'):
        source=HERE/'report/board_20261027'/name
        if source.is_file():add(source,'verification/board-20261027/'+name)
    for name in ('run_visual_demo.py','install_visual_z15.py'):
        add(HERE/name,name)
    add(HERE.parent/'eeg_demo/install_demo.py','install_demo.py')
    # Exact known source revisions; an unlisted installed version is rejected.
    historical=json.loads((HERE/'report/z15_baseline.json').read_text(encoding='utf-8'))['files']
    prior=json.loads((HERE/'report/z15_visual_prior_release_20261027.json').read_text(encoding='utf-8'))
    manifests=[]
    for path in (PROJECT/'local').glob('*/bundle_manifest.json'):
        manifests.append(json.loads(path.read_text(encoding='utf-8')).get('files',{}))
    def old_hashes(name,current=None):
        values={None,current}
        for row in historical:
            if row['path']=='integrations/vision_demo/'+name:values.add(row['sha256'])
        for manifest in manifests:values.add(manifest.get(name))
        values.add(prior['files'].get(name))
        return sorted((v for v in values if v is not None))+([None] if None in values else [])
    rows={}
    def overlay(source,name,before):
        data=Path(source).read_bytes();member='z15/payload/'+name
        payload[member]=data;rows[name]=dict(source='payload/'+name,sha256=hashlib.sha256(data).hexdigest(),before=before)
    for path in sorted((HERE.parent/'vision_demo/vision_demo').glob('*.py')):
        name='vision_demo/'+path.name
        overlay(path,name,old_hashes(name,hashlib.sha256(path.read_bytes()).hexdigest()))
    for name in ('__init__.py','visual_demo.py','visual_wire.py','visual_server.py','wireless_only.py',
                 'z15_visual_client.py','z15_visual_menu.py','z15_visual_patch.py'):
        source=HERE/'z20_compute'/name
        overlay(source,'z20_compute/'+name,old_hashes('z20_compute/'+name,hashlib.sha256(source.read_bytes()).hexdigest()))
    versions=[]
    for family in ('eeg_demo','eye_c3'):
        source=HERE.parent/family/'runtime/system_hdmi.py'
        data=source.read_bytes();versions.extend(hashlib.sha256(value).hexdigest() for value in (
            data,_patch_menu(data.decode('utf-8')).encode('utf-8'),patch_hdmi(data.decode('utf-8')).encode('utf-8')))
    payload['z15/z15-overlay.json']=json.dumps(dict(files=rows,system_hdmi_before=sorted(set(versions)),signal_player_guards=True),indent=2).encode()
    for name in ('preview_signals.py','signal_brain_preview.html'):
        add(HERE.parent/'vision_demo'/name,'z15_preview/'+name)
    for name in ('__init__.py','presentation.py','signal_source.py','signal_core.py','signal_audio.py','signal_render.py','signal_charts.py'):
        add(HERE.parent/'vision_demo/vision_demo'/name,'z15_preview/vision_demo/'+name)
    for name in ('presentation_theme.py','presentation.css'):
        add(HERE.parent/'eeg_demo/runtime'/name,'z15_preview/'+name)
    for folder in ('music','replay'):
        tree(HERE.parent/'vision_demo/build/signal_assets'/folder,'z15_preview/build/signal_assets/'+folder)
    for name in ('VISUAL_DEMO_GUIDE.md','SHOOTING_PLAN.md','GLOSSARY.md'):
        add(HERE/name,'docs/'+name)
    if (HERE/'report/feedback_offline_20261027.md').is_file():add(HERE/'report/feedback_offline_20261027.md','docs/feedback_offline_20261027.md')
    for name in ('offline_verification.json','visual-arm.json'):
        add(HERE/'report'/name,'verification/'+name)
    for source,name in (('artifacts/visual-demo/final/verification.json','browser.json'),
                       ('artifacts/visual-demo/loopback/verification.json','desktop-soak.json')):
        add(HERE/source,'verification/'+name)
    for source,name in (('report/board_20261027/feedback-browser-final/verification.json','feedback-browser.json'),
                        ('build/feedback-motion-rtl/result.json','feedback-motion-rtl.json')):
        if (HERE/source).is_file():add(HERE/source,'verification/'+name)
    payload['START_BOARD.sh']=b'#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nexec python3 run_visual_demo.py board "$@"\n'
    payload['START_PC.ps1']=b'param([string]$Python="python")\r\n$ErrorActionPreference="Stop"\r\nSet-Location $PSScriptRoot\r\n& $Python run_visual_demo.py pc\r\nexit $LASTEXITCODE\r\n'
    payload['START_OFFLINE.ps1']=b'param([string]$Python="python")\r\n$ErrorActionPreference="Stop"\r\nSet-Location $PSScriptRoot\r\n& $Python -m z20_compute.visual_offline\r\nexit $LASTEXITCODE\r\n'
    z15_report=HERE/'report/board_20261027/z15-final-state.json'
    z15_installed=z15_report.is_file() and json.loads(z15_report.read_text(encoding='utf-8')).get('passed') is True
    payload['release.json']=json.dumps(dict(format='z20-wireless-visual-v1',silent=True,autostart=False,
        complete=False,firmware_included=False,network='USB Wi-Fi only; 9020/9021/9022/9023',
        driver_autoload=False,
        feedback_revision='20261027-offline',feedback_board_validated=False,
        audio_policy='silent on startup; restored Z15 music pages may play; PC capture has no microphone monitor',
        actual_z15_installed=z15_installed,
        pending=([] if z15_installed else ['real_z15_install'])+['z15_hotspot_lan','eye_controls','hdmi',
                 '10_fps','10min_combined_soak','esp32_concurrent_wireless_stability',
                 'feedback_board_acceptance','motion_rtl_bitstream','physical_microphone_and_sound_quality'],
        third_party='Bundled source licenses retained. Spectrum adapter follows upstream GPL-3.0.'),indent=2).encode()
    payload['SHA256.json']=json.dumps({n:hashlib.sha256(v).hexdigest() for n,v in sorted(payload.items())},indent=2).encode()
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(payload.items()):archive.writestr(name,data)
    return output


if __name__=='__main__':
    result=create_release(HERE/'artifacts/z15-z20-wireless-visual-candidate.zip')
    print(json.dumps(dict(path=str(result),bytes=result.stat().st_size,sha256=hashlib.sha256(result.read_bytes()).hexdigest())))
