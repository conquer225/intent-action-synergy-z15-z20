"""Vendor ARMv7 rootfs/QEMU checks for the exact native JPEG library."""
import gzip,hashlib,io,json,stat,subprocess,time
from pathlib import Path
import cv2,numpy as np

ROOT=Path(__file__).resolve().parent


def record(stream,name,data,mode,inode):
    encoded=name.encode()+b'\0'
    fields=[inode,mode,0,0,1,0,len(data),0,0,0,0,len(encoded),0]
    header=b'070701'+b''.join(('%08x'%v).encode() for v in fields)+encoded
    stream.write(header);stream.write(b'\0'*(-len(header)%4));stream.write(data);stream.write(b'\0'*(-len(data)%4))


def main():
    out=ROOT/'build/visual-arm';out.mkdir(parents=True,exist_ok=True)
    check=b'''import json,sys
from pathlib import Path
import numpy as np
from z20_compute.visual_codec import NativeJPEG
from z20_compute.visual_demo import DemoState
from z20_compute.visual_display import DemoDisplay
from z20_compute.headless_display import HeadlessDisplay
from z20_compute.visual_server import DemoServer
from z20_compute.headless_server import StatusHTTP
from z20_compute.audio_file import read_pcm
from z20_compute.audio import sound_features
from z20_compute.training import ModelBundle
decode=NativeJPEG('/opt/visual/libz20_visual.so')
encoded=Path('/opt/visual/red.jpg').read_bytes()
for _ in range(20):
    image=decode(encoded)
    assert image.shape==(720,1280,3)
    assert image.dtype==np.uint8
    assert image[360,640,0]>230 and image[360,640,1]<25 and image[360,640,2]<25,image[360,640].tolist()
try:decode(b'not jpeg')
except ValueError:pass
else:raise AssertionError('invalid JPEG accepted')
state=DemoState();state.attach_renderer();state.command('offline',1,'right');state.command('offline',2,'right');state.command('offline',3,'enter')
font=HeadlessDisplay('/opt/visual/glyphs.npz').font
frame,key=DemoDisplay(font,decoder=decode).render(state.snapshot(),None)
assert frame.shape==(720,1280,3)
features=sound_features(read_pcm('/opt/visual/sound.wav'))
prediction=ModelBundle.load('/opt/visual/sound-model').predict(features)
assert features.shape==(40,) and prediction.scores.shape==(3,)
for task,count in (('fatigue',20),('emotion',180),('sound',40)):
    state.publish('npu',dict(task=task,event='completed',window_id='arm:'+task,valid=True,class_id=0,
        scores=[3.,2.,1.],quantized_features=[0]*count,source='recorded:ARM_check',timing=None),epoch=state.epoch)
    image,_=DemoDisplay(font).render(state.snapshot(),None)
    assert image.shape==(720,1280,3)
print('ARM_VISUAL_PASS='+json.dumps(dict(python=sys.version.split()[0],numpy=np.__version__,jpeg_decodes=20,local_npu_render=True,invalid_jpeg_rejected=True,server_import=True,sound_features=40,software_scores=prediction.scores.tolist())),flush=True)
'''
    init=b'''#!/bin/sh
export PATH=/sbin:/bin:/usr/sbin:/usr/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
export PYTHONPATH=/opt/visual
/usr/bin/python3.7 /visual-check.py
printf 'VISUAL_CHECK_EXIT=%s\\n' "$?"
sync
poweroff -f
while true; do sleep 1; done
'''
    stream=io.BytesIO();inode=1
    def put(name,data,mode=stat.S_IFREG|0o644):
        nonlocal inode
        record(stream,name,data,mode,inode);inode+=1
    for name in ('opt','opt/visual','opt/visual/z20_compute'):put(name,b'',stat.S_IFDIR|0o755)
    put('init',init,stat.S_IFREG|0o755);put('visual-check.py',check)
    image=np.zeros((180,320,3),np.uint8);image[:]=(0,0,250)
    put('opt/visual/red.jpg',cv2.imencode('.jpg',image)[1].tobytes())
    put('opt/visual/libz20_visual.so',(ROOT/'build/visual-demo/libz20_visual.so').read_bytes())
    put('opt/visual/glyphs.npz',(ROOT/'artifacts/headless/display/glyphs.npz').read_bytes())
    put('opt/visual/sound-model',b'',stat.S_IFDIR|0o755)
    for path in (ROOT/'artifacts/headless/models/sound').iterdir():
        if path.is_file():put('opt/visual/sound-model/'+path.name,path.read_bytes())
    manifest=json.loads((ROOT/'artifacts/headless/sound/manifest.json').read_text(encoding='utf-8'))
    put('opt/visual/sound.wav',(ROOT/'artifacts/headless/sound'/manifest['windows'][0]['file']).read_bytes())
    for path in (ROOT/'z20_compute').glob('*.py'):put('opt/visual/z20_compute/'+path.name,path.read_bytes())
    put('TRAILER!!!',b'',0)
    archive=out/'rootfs.cpio.gz'
    # Linux initramfs supports concatenated compressed CPIO members; the overlay replaces /init.
    base=ROOT/'build/qemu-person-dog-two/rootfs-person-dog.cpio.gz'
    with archive.open('wb') as target:
        with base.open('rb') as source:
            import shutil
            shutil.copyfileobj(source,target)
        target.write(gzip.compress(stream.getvalue(),compresslevel=1))
    command=['D:/vivado/Vitis/2023.1/data/emulation/qemu/comp/qemu_win/qemu-system-arm.exe',
        '-M','xilinx-zynq-a9','-m','1024','-nographic','-no-reboot',
        '-kernel',str(ROOT/'build/official_linux/zynq_petalinux/4_linux_driver_boot/ready_to_test/zImage'),
        '-dtb',str(ROOT/'build/navigator/navigator-camera-demo.dtb'),'-initrd',str(archive),
        '-append','console=ttyPS0,115200 rdinit=/init clk_ignore_unused']
    started=time.monotonic();log=out/'console.txt'
    with log.open('w',encoding='utf-8') as output:
        process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT)
        deadline=started+180
        while process.poll() is None and time.monotonic()<deadline:
            if 'VISUAL_CHECK_EXIT=' in log.read_text(errors='replace'):break
            time.sleep(.5)
        if process.poll() is None:process.kill()
        code=process.wait()
    console=log.read_text(errors='replace')
    report=dict(passed='ARM_VISUAL_PASS=' in console and 'VISUAL_CHECK_EXIT=0' in console,
        elapsed_seconds=time.monotonic()-started,qemu_exit=code,board_executed=False,
        native_sha256=hashlib.sha256((ROOT/'build/visual-demo/libz20_visual.so').read_bytes()).hexdigest(),
        scope='vendor Python3.7/NumPy1.17/OpenCV3.4 JPEG decode, server imports, PCM40 features, software scores and local NPU page; no DMA, Wi-Fi or PL inference')
    (ROOT/'report/visual-arm.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));print(console[-2400:])
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
