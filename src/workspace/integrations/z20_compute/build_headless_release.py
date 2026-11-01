"""Self-contained candidate runtime; pending hardware gates remain in its manifest."""
import hashlib
import json
from pathlib import Path
import zipfile
from build_z15_adapter import create_bundle as create_adapter

HERE=Path(__file__).resolve().parent


def create_release(output):
    payload={}
    def add(source,name):payload[name]=Path(source).read_bytes()
    for path in (HERE/'z20_compute').glob('*.py'):add(path,'z20_compute/'+path.name)
    for name in ('manage_headless.py','prepare_board_calibration.py','verify_unified_board.py','verify_headless_link.py'):
        add(HERE/name,name)
    for source,target in [('artifacts/headless/models','models'),('artifacts/headless/display','assets/display'),
            ('artifacts/headless/sound/pcm','assets/sound/pcm')]:
        for path in (HERE/source).rglob('*'):
            if path.is_file():add(path,target+'/'+path.relative_to(HERE/source).as_posix())
    for name in ('manifest.json','features.npz','grouped_training.json','selection.json'):
        add(HERE/'artifacts/headless/sound'/name,'assets/sound/'+name)
    add(HERE/'artifacts/headless/lemon_features.json','assets/lemon_features.json')
    recovery=HERE/'artifacts/headless/recovery/headless_baseline.zip'
    if recovery.is_file():add(recovery,'recovery/headless_baseline.zip')
    add(HERE/'report/headless/baseline.json','recovery/baseline.json')
    with zipfile.ZipFile(HERE/'artifacts/person_dog_two.zip') as archive:
        for name in archive.namelist():
            if name.startswith(('photos/','video/')) or name=='libperson_dog.so':payload['media/'+name]=archive.read(name)
    add(create_adapter(HERE/'artifacts/z15_auxiliary_adapter.zip'),'z15/z15_auxiliary_adapter.zip')
    for name in ('HEADLESS_OPERATOR_GUIDE.md','GLOSSARY.md'):
        if (HERE/name).is_file():add(HERE/name,'docs/'+name)
    config=dict(bind='192.168.1.20',data_port=9020,http_port=9021,backend='pl',pipeline=True,
        hdmi=True,keys=True,calibration=None,record_pairs=None,autostart=False,actuator_control=False)
    payload['config.example.json']=json.dumps(config,indent=2).encode()
    meta=dict(format='z20-headless-release-v1',kind='candidate',complete=False,autostart=False,silent=True,
        network='explicit private lab bind; TCP9020 + read-only HTTP9021; no S3 9000',
        depends_on=dict(linux='5.4.0-xilinx-v2020.2',python='3.7',numpy='1.17',native_opencv='3.4.3',
            pl='navigator CLG400 camera + observer + NPU + independent display ring'),
        pending=['wifi_driver_load_unload','final_unified_soak','cold_boot','wifi_association','physical_keys',
            'hdmi_visual_geometry','metric_calibration','tablet_switching','real_z15_installation'],
        model_quality='teacher consistency and recorded-source classification reports are separate from PL integer agreement')
    payload['release.json']=json.dumps(meta,indent=2).encode()
    payload['SHA256.json']=json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in sorted(payload.items())},indent=2).encode()
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(payload.items()):archive.writestr(name,data)
    return output


if __name__=='__main__':
    path=create_release(HERE/'artifacts/z20-headless-candidate.zip')
    print(json.dumps(dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
