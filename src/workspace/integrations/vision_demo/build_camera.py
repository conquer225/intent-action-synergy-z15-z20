"""Cross-build capture-only ARMv7 library using retained Z15 SCCB/GPIO sources."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gcc',default='D:/vivado/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc.exe')
    p.add_argument('--output',type=Path,default=HERE/'build/camera')
    p.add_argument('--stream',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    source=PROJECT/'ps_eye_net'
    files=[HERE/('native/autonomous_capture.c' if a.stream else 'native/camera_capture.c'),source/'src/app/emio_sccb_cfg/emio_sccb_cfg.c',
        source/'src/app/ov5640/ov5640_init.c']
    files += [source/'linux/driver'/name for name in ('xgpiops.c','xgpiops_g.c','xgpiops_sinit.c')]
    library=a.output/'libvision_capture.so'
    command=[a.gcc,'-std=c11','-D_POSIX_C_SOURCE=200809L','-O2','-Wall','-Wextra','-Werror',
        '-fPIC','-shared','-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-Wl,--no-undefined',
        '-I'+str(source/'linux/include'),'-I'+str(source/'bsp/include'),'-I'+str(source/'src/app'),
        *map(str,files),'-o',str(library)]
    r=subprocess.run(command,capture_output=True,text=True)
    (a.output/'compiler.txt').write_text(r.stdout+r.stderr,encoding='utf-8')
    result=dict(passed=r.returncode==0,exit_code=r.returncode,
        sources={str(f.relative_to(PROJECT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    header=HERE/'native/gpio_scope.h'
    result['sources'][str(header.relative_to(PROJECT))]=hashlib.sha256(header.read_bytes()).hexdigest()
    if a.stream:
        header=HERE/'native/stream_ring.h'
        result['sources'][str(header.relative_to(PROJECT))]=hashlib.sha256(header.read_bytes()).hexdigest()
    if r.returncode==0:result['library_sha256']=hashlib.sha256(library.read_bytes()).hexdigest()
    (a.output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(r.stdout+r.stderr);print(json.dumps(result,indent=2));return int(r.returncode!=0)


if __name__=='__main__':raise SystemExit(main())
