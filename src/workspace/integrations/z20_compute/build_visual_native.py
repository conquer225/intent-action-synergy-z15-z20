"""Reuse the verified ARM compiler and exact original OpenCV 3.4 ABI."""
import hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent

def main():
    base=HERE/'build/native-person-dog'
    old=json.loads((base/'compile.json').read_text())['command']
    source=HERE/'hardware/native/visual_codec.cpp'
    output=HERE/'build/visual-demo';output.mkdir(parents=True,exist_ok=True)
    command=old[:old.index('-O2')]+['-O2','-std=c++11','-shared','-fPIC','-I'+str(base/'include'),str(source),
        '-Wl,--allow-shlib-undefined','-L'+str(base/'lib')]
    command+=['-l:libopencv_'+name+'.so.3.4.3' for name in ('imgcodecs','imgproc','core')]
    target=output/'libz20_visual.so';command+=['-o',str(target)]
    result=subprocess.run(command,capture_output=True,text=True)
    report=dict(command=command,exit_code=result.returncode,stderr=result.stderr,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    if result.returncode==0:report['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    (output/'native-build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    result.check_returncode();print('ARM_VISUAL_CODEC_BUILT',target)

if __name__=='__main__':main()
