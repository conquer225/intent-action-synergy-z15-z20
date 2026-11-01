"""Preserve the working Navigator tree and add an isolated output reservation."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'build/fdt_tools'))
import fdt

from z20_compute.isolated_hdmi import DISPLAY_BASE,DISPLAY_SIZE


def camera_demo_tree(data):
    tree=fdt.parse_dtb(data)
    reserved=tree.get_node('/reserved-memory')
    for node in reserved.nodes:
        reg=list(node.get_property('reg'))
        for start,size in zip(reg[::2],reg[1::2]):
            if start<DISPLAY_BASE+DISPLAY_SIZE and DISPLAY_BASE<start+size:
                raise ValueError('display reservation would overlap existing reserved memory')
    reserved.append(fdt.Node('display@4000000',fdt.PropWords('reg',DISPLAY_BASE,DISPLAY_SIZE),
                             fdt.Property('no-map')))
    observer=tree.get_node('/video-observer@43c20000')
    current=list(observer.get_property('reg'))
    if current!=[0x43c20000,0x10000,0x01000000,8294400]:
        raise ValueError('unexpected base observer memory map')
    observer.set_property('reg',current+[DISPLAY_BASE,DISPLAY_SIZE])
    return tree


def main():
    path=ROOT/'build/navigator/navigator-stereo.dtb'
    tree=camera_demo_tree(path.read_bytes())
    output=ROOT/'build/navigator/navigator-camera-demo.dtb'
    output.write_bytes(tree.to_dtb())
    output.with_suffix('.dts').write_text(tree.to_dts(),encoding='utf-8')
    readback=fdt.parse_dtb(output.read_bytes())
    assert list(readback.get_node('/reserved-memory/display@4000000').get_property('reg'))==[DISPLAY_BASE,DISPLAY_SIZE]
    report=dict(base_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                display_address=DISPLAY_BASE,display_bytes=DISPLAY_SIZE,
                board_executed=False,source='existing Navigator CLG400 tree plus display reservation')
    (ROOT/'build/navigator/camera-demo-dtb.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('CAMERA_DEMO_DTB',report)


if __name__=='__main__':main()
