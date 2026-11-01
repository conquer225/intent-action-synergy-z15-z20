"""Cross-compile against the exact OpenCV headers/libraries in vendor rootfs."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import re
import urllib.request


def main():
    root=Path(__file__).resolve().parent
    out=root/'build/native-person-dog';out.mkdir(exist_ok=True)
    include=out/'include';include.mkdir(exist_ok=True)
    libs=out/'lib';libs.mkdir(exist_ok=True)
    archive=root/'build/official_linux/zynq_petalinux/3_linux_lcd_qt/ready_to_test/rootfs.tar.gz'
    count=0
    with tarfile.open(archive) as tar:
        for member in tar:
            name=member.name
            if not member.isfile():continue
            if '/git/' in name and '/include/opencv2/' in name and name.endswith(('.hpp','.h')):
                relative='opencv2/'+name.split('/include/opencv2/',1)[1]
                path=include/relative;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(tar.extractfile(member).read());count+=1
            elif name.startswith('./usr/lib/libopencv_') and name.endswith('.so.3.4.3'):
                (libs/Path(name).name).write_bytes(tar.extractfile(member).read())
    (include/'opencv2/opencv_modules.hpp').write_text(
        '\n'.join('#define HAVE_OPENCV_'+name.upper() for name in
                  ('core','imgproc','imgcodecs','videoio','features2d','calib3d','flann')),encoding='utf-8')
    supplemental={}
    for module,name in (('core','cv_cpu_dispatch.h'),('core','cv_cpu_helper.h'),
                        ('core','version.hpp'),('core','vsx_utils.hpp'),('flann','config.h')):
        relative='opencv2/'+module+'/'+name
        path=include/relative
        url='https://raw.githubusercontent.com/opencv/opencv/3.4.3/modules/'+module+'/include/'+relative
        if not path.exists():path.write_bytes(urllib.request.urlopen(url,timeout=25).read())
        supplemental[relative]=dict(url=url,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    command=json.loads((root/'build/navigator/camera-probe/compile.json').read_text())['command']
    command=command[:command.index('-static')]+['-O2','-std=c++11','-shared','-fPIC',
        '-I'+str(include),str(root/'hardware/native/person_dog_demo.cpp'),
        '-Wl,--allow-shlib-undefined','-L'+str(libs)]
    command += ['-l:libopencv_'+name+'.so.3.4.3' for name in
                ('videoio','imgcodecs','features2d','calib3d','imgproc','core','flann')]
    target=out/'libperson_dog.so';command+=['-o',str(target)]
    fetched=dict(supplemental)
    for _ in range(20):
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode==0:break
        match=re.search(r'fatal error: ([^:]+): No such file',result.stderr)
        if match is None:break
        header=match.group(1)
        if header in fetched:break
        relative=header if header.startswith('opencv2/') else 'opencv2/core/'+header
        parts=relative.split('/')
        module=parts[1].removesuffix('.hpp')
        if module not in ('core','imgproc','imgcodecs','videoio','features2d','calib3d','flann'):
            break
        url='https://raw.githubusercontent.com/opencv/opencv/3.4.3/modules/'+module+'/include/'+relative
        print('FETCH_HEADER',relative,flush=True)
        data=urllib.request.urlopen(url,timeout=25).read()
        path=include/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        fetched[header]=dict(url=url,sha256=hashlib.sha256(data).hexdigest())
    report=dict(command=command,exit_code=result.returncode,stdout=result.stdout,
                  stderr=result.stderr,headers=count,fetched_headers=fetched)
    if result.returncode==0:report['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    (out/'compile.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('NATIVE_BUILD',result.returncode,'headers',count)
    if result.returncode:print(result.stderr[-8000:])
    result.check_returncode()


if __name__=='__main__':main()
