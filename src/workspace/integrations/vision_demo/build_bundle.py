"""Assemble only a gated FPGA pair, measured ARM workers and reviewed runtime."""
import argparse,ast,hashlib,json,shutil
from pathlib import Path
from patch_media import patch,patch_audio
from elf_compat import validate_arm_runtime
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--hardware',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();hardware=a.hardware.resolve();quality=json.loads((hardware/'quality.json').read_text())
    if quality.get('passed') is not True:raise ValueError('Hardware gates did not pass')
    for name,digest in quality['files'].items():
        if sha(hardware/name)!=digest:raise ValueError('Hardware evidence changed: '+name)
    for name,digest in quality.get('source_hashes',{}).items():
        if sha(HERE/'hardware'/name)!=digest:raise ValueError('Hardware source changed after build: '+name)
    a.output.mkdir(parents=True,exist_ok=False);out=a.output
    baseline=HERE.parent/'eeg_demo/runtime/media_player.py'
    payload={'media_player.py':patch(baseline.read_text(encoding='utf-8')).encode()}
    audio=HERE.parent/'eeg_demo/runtime/page_audio.py'
    payload['page_audio.py']=patch_audio(audio.read_text(encoding='utf-8'),
        quality['files']['candidate/guardianloop_display_audio.bit'],
        quality['files']['candidate/guardianloop_display_audio.hwh']).encode()
    for source in (HERE/'vision_demo').glob('*.py'):payload['vision_demo/'+source.name]=source.read_bytes()
    for suffix in ('bit','hwh'):payload['vision_demo/overlay/display_vision.'+suffix]=(hardware/('candidate/guardianloop_display_audio.'+suffix)).read_bytes()
    streaming=quality.get('architecture')=='native_stream'
    camera=HERE/('build/stream_camera' if streaming else 'build/camera')
    camera_result=json.loads((camera/'result.json').read_text(encoding='utf-8'))
    if not camera_result.get('passed') or sha(camera/'libvision_capture.so')!=camera_result['library_sha256']:
        raise ValueError('Capture library build evidence mismatch')
    for name,digest in camera_result['sources'].items():
        if sha(HERE.parents[1]/name)!=digest:raise ValueError('Capture source changed after build: '+name)
    payload['vision_demo/libvision_capture.so']=(camera/'libvision_capture.so').read_bytes()
    tobii=HERE/'build/native';evidence=json.loads((tobii/'result.json').read_text(encoding='utf-8'))
    if (sha(tobii/'tobii-images')!=evidence['binary_sha256'] or
            sha(HERE/'native/tobii_images.c')!=evidence['source_sha256'] or
            sha(HERE.parents[1]/'ps_tobii/build/is4-probe.c')!=evidence['protocol_sha256']):
        raise ValueError('Tobii image worker build evidence mismatch')
    payload['vision_demo/bin/tobii-images']=(tobii/'tobii-images').read_bytes()
    for name in ('vision_demo/libvision_capture.so','vision_demo/bin/tobii-images'):
        data=payload[name]
        if data[:6]!=b'\x7fELF\x01\x01' or int.from_bytes(data[18:20],'little')!=40:raise ValueError('ARMv7 ELF required: '+name)
    if quality.get('signal_pages'):
        evidence=quality['audio_fft']
        if sha(HERE/'hls/audio_fft.cpp')!=evidence['source_sha256'] or sha(HERE/'hls/audio_twiddle.h')!=evidence['twiddle_sha256']:raise ValueError('Audio FFT changed after routing')
        cosim=json.loads((HERE.parents[1]/'local/audio_hls_20261020/cosim-direct-result.json').read_text(encoding='utf-8'))
        if not cosim.get('passed') or cosim['source_sha256']!=sha(HERE/'hls/audio_fft.cpp') or cosim['testbench_sha256']!=sha(HERE/'hls/test_audio.cpp') or cosim['twiddle_sha256']!=sha(HERE/'hls/audio_twiddle.h'):raise ValueError('Audio RTL numeric verification missing')
        native=HERE/'build/signal_pcm';built=json.loads((native/'result.json').read_text(encoding='utf-8'))
        if not built['passed'] or sha(HERE/'native/signal_pcm.c')!=built['source_sha256'] or sha(native/'signal_pcm')!=built['binary_sha256']:raise ValueError('Signal PCM build mismatch')
        payload['vision_demo/bin/signal-pcm']=(native/'signal_pcm').read_bytes()
        validate_arm_runtime(payload['vision_demo/bin/signal-pcm'])
        for source in (HERE/'build/signal_assets').rglob('*'):
            if source.is_file():payload['vision_demo/'+source.relative_to(HERE/'build/signal_assets').as_posix()]=source.read_bytes()
        data=payload['vision_demo/bin/signal-pcm']
        if data[:6]!=b'\x7fELF\x01\x01' or int.from_bytes(data[18:20],'little')!=40:raise ValueError('ARM signal PCM required')
    front_baseline={}
    if quality.get('signal_pages'):
        runtime=HERE.parent/'eeg_demo/runtime'
        front_baseline=json.loads((HERE/'presentation_baseline.json').read_text(encoding='utf-8'))
        front_baseline.update(json.loads((HERE/'device_control_baseline.json').read_text(encoding='utf-8')))
        for name in list(front_baseline)+['presentation_theme.py','presentation_eye.py','presentation.css','eeg_recording.json']:
            payload[name]=(runtime/name).read_bytes()
            if name not in front_baseline:front_baseline[name]=None
        if payload['presentation_theme.py']!=(HERE/'presentation_theme.py').read_bytes():raise ValueError('Presentation palette source mismatch')
    for name,data in payload.items():
        if name.endswith('.py'):ast.parse(data.decode('utf-8'),feature_version=(3,8))
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    manifest=dict(version=1,gates_passed=True,baseline_player=sha(baseline),
                  baseline_files=dict({'media_player.py':sha(baseline),'page_audio.py':sha(audio)},**front_baseline),
                  files={name:hashlib.sha256(data).hexdigest() for name,data in payload.items()},
                  hardware_quality_sha256=sha(hardware/'quality.json'),
                  source_mapping={'0-8':'OV5640','9':'Tobii IS4'},pupil_backend='PS OpenCV',pl_size=[1280,720] if streaming else [320,180],
                  architecture='native_stream' if streaming else 'memory_hls',signal_pages=quality.get('signal_pages',False),presentation_release=bool(front_baseline))
    (out/'bundle_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('BUNDLE_READY',out)
if __name__=='__main__':main()
