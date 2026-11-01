"""Prepare source-video playback and camera/photo registration assets."""
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from zipfile import ZipFile,ZIP_DEFLATED

import cv2
import numpy as np
from PIL import Image,ImageDraw

from build_fixed_scene_board import write_sha256_manifest
from z20_compute.fixed_scene_demo import render,_font
from z20_compute.fixed_scene import describe_scene
from z20_compute.video_timeline import VideoTimeline
from z20_compute.tablet_photo import RegisteredPhotos


def scene_frame(rgb,scene,title,note):
    prediction=SimpleNamespace(scores=[0,0,0])
    demo=SimpleNamespace(index=0,current=lambda:(Image.fromarray(rgb),prediction,scene))
    frame=render(demo)
    draw=ImageDraw.Draw(frame);bg='#faf8f3';ink='#262421'
    draw.rectangle((35,15,1245,78),fill=bg)
    draw.text((42,22),title,font=_font(29),fill=ink)
    draw.rectangle((800,575,1245,649),fill=bg)
    draw.text((810,581),note,font=_font(18),fill=ink)
    draw.rectangle((800,102,1240,146),fill=bg)
    draw.text((810,107),'关键帧行为标注' if '视频' in title else '当前匹配的登记场景',
              font=_font(22),fill='#655f57')
    draw.rectangle((800,532,1240,571),fill=bg)
    draw.text((810,538),'当前视频帧 · 参考尺度计算' if '视频' in title else '图内深度 · 参考尺度计算',
              font=_font(18),fill='#655f57')
    draw.rectangle((35,658,1245,719),fill=bg)
    draw.text((42,670),'视频：标注回放    照片：摄像头像素配准',font=_font(18),fill='#655f57')
    return frame


def write_launch_scripts(output):
    for mode in ('video','photos','diagnostic'):
        (output/('run_'+mode+'.sh')).write_bytes((
            '#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nexport PYTHONPATH=.\n'
            'exec python3 -m z20_compute.person_dog_runner --root . --mode '+mode+
            ' --hdmi "$@"\n').encode('utf-8'))


def main():
    root=Path(__file__).resolve().parent
    output=root/'artifacts/person_dog_two';output.mkdir(exist_ok=True)
    report=root/'report/person_dog_two';report.mkdir(exist_ok=True)
    for name in ('video','photos','backgrounds','fixtures','z20_compute','hardware'):
        (output/name).mkdir(exist_ok=True)
    diagnostic=Image.new('RGB',(1280,720),'white')
    d=ImageDraw.Draw(diagnostic)
    colors=('#efcfc7','#d7e4c8','#d5dfea','#e7dfc9')
    for i,color in enumerate(colors):
        d.rectangle((i*320,0,(i+1)*320-1,719),fill=color)
        d.text((i*320+24,100),'区域 {}'.format(i+1),font=_font(36),fill='black')
        d.text((i*320+24,165),'x={}…{}'.format(i*320,(i+1)*320-1),font=_font(22),fill='black')
        d.ellipse((i*320+60,280,i*320+260,480),outline='black',width=5)
    for x in (0,319,639,959,1279):d.line((x,0,x,719),fill='black',width=3)
    d.rectangle((2,2,1277,717),outline='black',width=4)
    d.text((25,20),'HDMI 几何诊断：四块等宽、圆形不变形、左右边界完整',font=_font(27),fill='black')
    diagnostic.save(report/'hdmi_diagnostic.png')
    (output/'backgrounds/diagnostic.rgb').write_bytes(diagnostic.tobytes())
    src=root/'artifacts/dog_walk_video'
    for name in ('source.mp4','source.json','annotations.json'):
        shutil.copyfile(src/name,output/'video'/name)
    annotation=json.loads((src/'annotations.json').read_text())
    assert hashlib.sha256((src/'source.mp4').read_bytes()).hexdigest()==annotation['source_sha256']
    timeline=VideoTimeline(annotation)
    blank=np.full((480,640,3),250,np.uint8)
    base=scene_frame(blank,timeline.at(0),'Z20 · 视频文件标注回放','单目距离：参考尺寸估算')
    (output/'backgrounds/video.rgb').write_bytes(base.tobytes())
    for position in ('person_left_of_dog','person_right_of_dog','same_horizontal_position'):
        scene=timeline.at(0);scene['position']=position
        base=scene_frame(blank,scene,'Z20 · 视频文件标注回放','单目距离：参考尺寸估算')
        (output/'backgrounds'/('video_'+position+'.rgb')).write_bytes(base.tobytes())
    source=cv2.VideoCapture(str(src/'source.mp4'));assert source.isOpened()
    playback=cv2.VideoWriter(str(output/'video/playback.avi'),cv2.VideoWriter_fourcc(*'MJPG'),30,(640,360))
    assert playback.isOpened()
    writer=cv2.VideoWriter(str(report/'annotated_video.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),10,(1280,720))
    assert writer.isOpened()
    records=[];contacts=Image.new('RGB',(1280,720),'white')
    for frame_number in range(180):
        ok,bgr=source.read();assert ok
        small=cv2.resize(bgr,(640,360),interpolation=cv2.INTER_AREA)
        playback.write(small)
        if frame_number%3:continue
        image=np.full((480,640,3),255,np.uint8);image[60:420]=cv2.cvtColor(small,cv2.COLOR_BGR2RGB)
        scene=timeline.at(frame_number/30.)
        frame=scene_frame(image,scene,'Z20 · 视频文件标注回放  {:.2f} s'.format(frame_number/30.),
                          '单目距离：参考尺寸估算')
        writer.write(cv2.cvtColor(np.asarray(frame),cv2.COLOR_RGB2BGR))
        if frame_number%15==0:
            index=frame_number//15
            frame.save(report/('video_%03d.png'%frame_number))
            contacts.paste(frame.resize((320,180)),((index%4)*320,(index//4)*180))
        records.append(dict(time_s=frame_number/30.,scene=scene))
    source.release();writer.release();playback.release();contacts.save(report/'video_contact.jpg')
    (output/'video/conversion.json').write_text(json.dumps(dict(
        source='source.mp4',source_sha256=annotation['source_sha256'],
        playback='playback.avi',playback_sha256=hashlib.sha256((output/'video/playback.avi').read_bytes()).hexdigest(),
        codec='MJPEG',image_size=[640,360],fps=30,frames=180,
        reason='vendor OpenCV lacks source MP4 codec; preserve original and source frame times'),indent=2),encoding='utf-8')
    (report/'video_results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    gallery=root/'artifacts/person_dog'
    config=json.loads((gallery/'gallery.json').read_text(encoding='utf-8'))
    for name in ('gallery.json','sources.json'):shutil.copyfile(gallery/name,output/'photos'/name)
    images=[]
    for i,entry in enumerate(config['images']):
        image=cv2.imread(str(gallery/entry['file']));images.append(image)
        shutil.copyfile(gallery/entry['file'],output/'photos'/('scene%d.png'%i))
        scene=describe_scene(entry,(640,480))
        bg=scene_frame(blank,scene,'Z20 · 双目实拍登记照片','图内距离估算；平板距离待标定')
        (output/'backgrounds'/('photo%d.rgb'%i)).write_bytes(bg.tobytes())
    unknown=scene_frame(blank,None,'Z20 · 双目实时输入','未匹配登记照片；平板距离待标定')
    (output/'backgrounds/unknown.rgb').write_bytes(unknown.tobytes())
    matcher=RegisteredPhotos(images)
    srcpoints=np.float32([[0,0],[639,0],[639,479],[0,479]])
    dst=np.float32([[90,150],[560,110],[545,550],[75,590]])
    h=cv2.getPerspectiveTransform(srcpoints,dst)
    matches=[]
    for i,image in enumerate(images):
        camera=cv2.warpPerspective(image,h,(640,720),borderValue=(45,45,45))
        camera=cv2.convertScaleAbs(camera,alpha=.7,beta=15)
        result=matcher.match(camera);assert result['scene_id']==i
        rgb=cv2.cvtColor(camera,cv2.COLOR_BGR2RGB)
        (output/'fixtures'/('camera%d.rgb'%i)).write_bytes(rgb.tobytes())
        Image.fromarray(rgb).save(report/('camera_fixture%d.png'%i))
        matches.append(result)
    (output/'fixtures/expected.json').write_text(json.dumps(dict(homography=h.tolist(),matches=matches)),encoding='utf-8')
    modules=('__init__.py','fixed_scene.py','fixed_scene_depth.py','fixed_scene_hdmi.py',
             'fixed_scene_package.py','video_timeline.py','native_person_dog.py','npu.py',
             'stereo_live.py','video.py','vdma.py','person_dog_capture_start.py')
    for name in modules:shutil.copyfile(root/'z20_compute'/name,output/'z20_compute'/name)
    for name in ('person_dog_runner.py','isolated_hdmi.py'):
        if (root/'z20_compute'/name).exists():shutil.copyfile(root/'z20_compute'/name,output/'z20_compute'/name)
    shutil.copyfile(root/'z20_compute/person_dog_camera_scene.py',output/'z20_compute/person_dog_camera_scene.py')
    shutil.copyfile(root/'build/native-person-dog/libperson_dog.so',output/'libperson_dog.so')
    shutil.copyfile(root/'build/navigator/navigator-camera-demo.dtb',output/'hardware/navigator-camera-demo.dtb')
    shutil.copyfile(root/'build/navigator/camera-geometry/camera_geometry',output/'hardware/camera_geometry')
    shutil.copyfile(root/'build/navigator/camera-probe/camera_probe',output/'hardware/camera_probe')
    readme='''# Z20 视频与平板照片测试包

video/source.mp4 是网上公开的人遛狗片段；原始来源和摘要保存在 source.json。
视频模式按源时间戳回放人工复核的框和行为，在 ARM 计算参考尺度距离。
照片模式从两路摄像头之一的实时帧配准三张登记照片，未知画面清空标注。
单目米制结果依赖参考尺寸与镜头参数，界面保持“估算”。

视频与照片的原厂 OpenCV 3.4 原生适配库已附带；不依赖 Python cv2 扩展。
先恢复匹配的 CLG400 内核、设备树和 PL，再运行包内入口。
实时相机叠加需要独立显示预留内存设备树；旧设备树会拒绝启动照片显示。
具体启动与验收见工程 report/person_dog_two/verification.md。
'''
    (output/'README.md').write_text((root/'PERSON_DOG_TWO.md').read_text(encoding='utf-8'),encoding='utf-8')
    write_launch_scripts(output)
    manifest=write_sha256_manifest(output)
    target=root/'artifacts/person_dog_two.zip'
    with ZipFile(target,'w',ZIP_DEFLATED) as archive:
        for path in sorted(p for p in output.rglob('*') if p.is_file()):
            archive.write(path,path.relative_to(output).as_posix())
    print('TWO_PATH_PACKAGE',len(manifest),'files',target.stat().st_size,hashlib.sha256(target.read_bytes()).hexdigest())


if __name__=='__main__':main()
