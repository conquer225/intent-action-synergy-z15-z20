"""Explicit first-start camera owner for the isolated-display demonstration."""
import argparse
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import time

from .fixed_scene_hdmi import _uio,_read,_write
from .vdma import stereo_layout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    reserve=Path('/proc/device-tree/reserved-memory/video@1000000')
    if (reserve/'reg').read_bytes()!=struct.pack('>II',0x01000000,8294400):
        raise ValueError('capture ring reservation differs')
    bases=[int((p/'base').read_text()) for p in Path('/sys/class/gpio').glob('gpiochip*')
           if 'zynq' in (p/'label').read_text().lower()]
    if bases!=[906]:raise ValueError('unexpected PS GPIO controller')
    control=_uio('navigator-vdma-control',0x43000000,0x30000)
    fd=os.open('/dev/'+control.name,os.O_RDWR|os.O_SYNC)
    mapping=mmap.mmap(fd,0x30000,access=mmap.ACCESS_WRITE)
    try:
        if any(not _read(mapping,i*0x10000+0x34)&1 for i in range(2)):
            raise RuntimeError('capture already running; leave its owner in control')
        for name,mode in (('camera_probe','init'),('camera_geometry','crop')):
            path=args.root/'hardware'/name
            path.chmod(path.stat().st_mode|0o111)
            subprocess.run([str(path),'906',mode],check=True)
        layout=stereo_layout(0x01000000,8294400)
        for i,item in enumerate((layout.left,layout.right)):
            base=i*0x10000
            _write(mapping,base+0x30,4)
            deadline=time.monotonic()+1
            while _read(mapping,base+0x30)&4:
                if time.monotonic()>deadline:raise TimeoutError('camera VDMA reset timeout')
                time.sleep(.002)
            _write(mapping,base+0x34,0xfff0)
            _write(mapping,base+0x30,_read(mapping,base+0x30)|3|(8 if i else 0))
            for n,address in enumerate(item.addresses):_write(mapping,base+0xac+4*n,address)
            _write(mapping,base+0xa8,item.stride)
            _write(mapping,base+0xa4,item.hsize)
            _write(mapping,base+0xa0,item.height)
        time.sleep(1)
        initial=[_read(mapping,i*0x10000+0x34) for i in range(2)]
        # Record startup half-frame errors before clearing their W1C bits once.
        for i in range(2):_write(mapping,i*0x10000+0x34,0xff0)
        time.sleep(.2)
        final=[_read(mapping,i*0x10000+0x34) for i in range(2)]
        report=dict(mode='navigator-centered-portrait-640x720-v1',initial_status=initial,
                    status=final,metric_calibration_valid=False)
        Path('/tmp/person_dog_capture_start.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
        if any(s&0xff0 for s in final):raise RuntimeError('camera VDMA error recurred after startup')
    finally:mapping.close();os.close(fd)


if __name__=='__main__':main()
