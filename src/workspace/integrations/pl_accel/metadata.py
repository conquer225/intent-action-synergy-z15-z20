"""Read a generated handoff description without programming an FPGA overlay."""
from pathlib import Path
import xml.etree.ElementTree as ET


def eeg_aperture(path, ip_name):
    path = Path(path)
    if path.stat().st_size > 16*1024*1024:raise ValueError('HWH description exceeds size bound')
    tree = ET.parse(path)
    info = tree.find('.//SYSTEMINFO')
    modules = [node for node in tree.findall('.//MODULE') if node.get('INSTANCE') == ip_name]
    ranges = [node for node in tree.findall('.//MEMRANGE') if node.get('INSTANCE') == ip_name
              and node.get('SLAVEBUSINTERFACE') == 's_axi_control']
    if (info is None or info.get('DEVICE') != '7z015' or info.get('PACKAGE') != 'clg485'
            or len(modules) != 1 or modules[0].get('VLNV') != 'xilinx.com:hls:z15_fbcsp:1.0'
            or len(ranges) != 1):
        raise ValueError('HWH must describe the Z15 CLG485 FBCSP control interface')
    start, end = [int(ranges[0].get(k), 0) for k in ('BASEVALUE', 'HIGHVALUE')]
    if start % 65536 or not 0 < start <= end < 2**32 or end-start+1 != 65536:
        raise ValueError('HWH control aperture')
    return dict(phys_addr=start, addr_range=end-start+1)
