"""Reconstruct an isolated BD from the installed display HWH and explicit audio additions."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from run_simulation import HERE, BIN, SERIALIZER

ROOT = HERE.parent
HWH = ROOT/'brain_eye_coexist/candidate/eye/overlay/eye_wifi.hwh'
VENDOR = SERIALIZER.parents[3]
REFERENCE_PINS = VENDOR.parents[3]/'5_High_Level_Synthesis/ZYNQ_7015/5_ov5640_rgb2gray/ov5640_rgb2gray_ip_test/ov5640_rgb2gray_ip_test.srcs/constrs_1/new/pin.xdc'
REFERENCE_HDMI = VENDOR.parent/'Z15_ZYNQ.srcs/constrs_1/system.xdc'


def literal(value):
    value = str(value)
    if any(c in value for c in '{}\\\r\n'):
        return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('[','\\[').replace('\n','\\n').replace('\r','\\r')+'"'
    return '{'+value+'}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    hardware = ET.parse(HWH).getroot()
    if hardware.find('SYSTEMINFO').attrib != dict(ARCH='zynq', DEVICE='7z015', NAME='system', PACKAGE='clg485', SPEEDGRADE='-2'):
        raise RuntimeError('Unexpected source device')
    # HWH is authoritative for inherited configuration, internal nets and address ranges.
    modules = hardware.findall('./MODULES/MODULE')
    lines = ['set legacy_config [dict create]', 'set legacy_vlnv [dict create]']
    bus_groups, signal_groups = defaultdict(list), defaultdict(list)
    bus_ports = defaultdict(set)
    for m in modules:
        name = m.get('INSTANCE')
        if name == 'DVI_Transmitter_0':
            continue
        lines.append(f'dict set legacy_vlnv {literal(name)} {literal(m.get("VLNV"))}')
        for p in m.findall('./PARAMETERS/PARAMETER'):
            key = p.get('NAME')
            if key.lower() != 'component_name':
                lines.append(f'dict set legacy_config {literal(name)} {literal(key)} {literal(p.get("VALUE", ""))}')
        for b in m.findall('./BUSINTERFACES/BUSINTERFACE'):
            if b.get('BUSNAME') not in [None,'__NOC__']:
                bus_groups[b.get('BUSNAME')].append((name,b.get('NAME'),b))
    external_bus_names = {b.get('BUSNAME'):b.get('NAME') for b in hardware.findall('./EXTERNALINTERFACES/BUSINTERFACE')}
    for bus, endpoints in bus_groups.items():
        if len(endpoints) > 1 or bus in external_bus_names:
            for name, _, b in endpoints:
                bus_ports[name].update(p.get('PHYSICAL') for p in b.findall('./PORTMAPS/PORTMAP'))
    connections=[]
    for bus, endpoints in bus_groups.items():
        paths=[n+'/'+p for n,p,_ in endpoints]
        if bus in external_bus_names:
            if len(paths)!=1: raise RuntimeError('Unexpected external bus fanout: '+bus)
            external = external_bus_names[bus]
            connections += [f'make_bd_intf_pins_external [get_bd_intf_pins {literal(paths[0])}]',
                            f'set ext [get_bd_intf_ports -of_objects [get_bd_intf_nets -of_objects [get_bd_intf_pins {literal(paths[0])}]]]',
                            f'set_property name {literal(external)} $ext']
        elif len(paths)>1:
            connections.append('connect_bd_intf_net '+' '.join('[get_bd_intf_pins '+literal(p)+']' for p in paths))
    external_bus_ports={p.get('PHYSICAL') for b in hardware.findall('./EXTERNALINTERFACES/BUSINTERFACE')
                        if b.get('NAME')!='TMDS_0' for p in b.findall('./PORTMAPS/PORTMAP')}
    for m in modules:
        name=m.get('INSTANCE')
        for p in m.findall('./PORTS/PORT'):
            port=p.get('NAME')
            if name=='DVI_Transmitter_0':
                rename={'pclk':'clk_pixel','pclk_x5':'clk_pixel_x5','video_din':'rgb',
                        'video_hsync':'hsync','video_vsync':'vsync','video_de':'de',
                        'tmds_data_p':'tmds_data_p','tmds_data_n':'tmds_data_n',
                        'tmds_clk_p':'tmds_clk_p','tmds_clk_n':'tmds_clk_n'}
                if port not in rename: continue
                path='hdmi_audio_tx_0/'+rename[port]
            else:
                if port in bus_ports[name]: continue
                path=name+'/'+port
            if p.get('SIGNAME'): signal_groups[p.get('SIGNAME')].append('[get_bd_pins '+literal(path)+']')
    for p in hardware.findall('./EXTERNALPORTS/PORT'):
        name=p.get('NAME')
        if name in external_bus_ports: continue
        width='' if p.get('LEFT') is None else f' -from {p.get("LEFT")} -to {p.get("RIGHT")}'
        clock=' -type clk -freq_hz 100000000' if name=='cam_pclk' else ''
        connections.append(f'create_bd_port -dir {p.get("DIR")}{width}{clock} {literal(name)}')
        signal_groups[p.get('SIGNAME')].append('[get_bd_ports '+literal(name)+']')
    for endpoints in signal_groups.values():
        if len(endpoints)>1: connections.append('connect_bd_net '+' '.join(endpoints))
    lines += ['proc connect_legacy {} {', *connections, '}']
    addresses=[]
    seen=[]
    for m in modules:
        for a in m.findall('./MEMORYMAP/MEMRANGE'):
            address=int(a.get('BASEVALUE'),16); size=int(a.get('HIGHVALUE'),16)-address+1
            target='/'.join([a.get('INSTANCE'),a.get('SLAVEBUSINTERFACE'),a.get('ADDRESSBLOCK')])
            source=m.get('INSTANCE')+'/'+a.get('MASTERBUSINTERFACE')
            addresses.append((source,target,address,size))
            if m.get('INSTANCE')=='processing_system7_0': seen.append((address,address+size))
    new_address=0x43c20000
    if any(a<new_address+0x10000 and b>new_address for a,b in seen):
        raise RuntimeError('Audio address overlaps existing map')
    lines += ['set legacy_addresses [list]']
    for source,target,address,size in addresses:
        lines.append(f'lappend legacy_addresses [list {literal(source)} {literal(target)} {hex(address)} {hex(size)}]')
    (out/'legacy_contract.tcl').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    manifest=dict(source_hwh=str(HWH),hwh_sha256=hashlib.sha256(HWH.read_bytes()).hexdigest(),
        part='xc7z015clg485-2',candidate_audio_address=hex(new_address),
        board_loaded=False,bitstream_generated=False,scope='isolated reconstruction; no runtime modification')
    pin_lines=[]
    for line in REFERENCE_PINS.read_text(encoding='gb18030').splitlines():
        if line.startswith(('set_property','create_clock')) and any(s in line for s in ['get_ports cam_', 'get_ports {cam_', 'emio_sccb', 'get_nets cam_pclk_IBUF']):
            pin_lines.append(line)
    for line in REFERENCE_HDMI.read_text(encoding='gb18030').splitlines():
        if line.startswith('set_property PACKAGE_PIN') and 'tmds_tmds_' in line:
            pin_lines.append(line.replace('tmds_tmds_', 'TMDS_0_tmds_'))
    if len(pin_lines)!=22:
        raise RuntimeError('Unexpected reference pin command count: '+str(len(pin_lines)))
    (out/'pins.xdc').write_text('\n'.join(pin_lines)+'\n',encoding='utf-8')
    manifest['constraint_sources']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [REFERENCE_PINS,REFERENCE_HDMI]}
    (out/'source_contract.json').write_text(json.dumps(manifest,indent=2))
    command=[str(BIN/'vivado.bat'),'-mode','batch','-nojournal','-log',(out/'create.log').as_posix(),
        '-source',(HERE/'create_display.tcl').as_posix(),'-tclargs',out.as_posix(),HERE.as_posix(),VENDOR.as_posix(),SERIALIZER.as_posix()]
    result=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=600)
    print('\n'.join((result.stdout+result.stderr).splitlines()[-65:]),flush=True)
    if result.returncode or 'DISPLAY_AUDIO_BD_READY' not in result.stdout:
        raise RuntimeError('BD reconstruction failed; inspect '+str(out/'create.log'))


if __name__=='__main__':
    main()
