"""Compare candidate HWH against inherited display and new PCM contracts; no MMIO."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from rebuild_display import HWH


def modules(path):
    root=ET.parse(path).getroot()
    return root,{m.get('INSTANCE'):m for m in root.findall('./MODULES/MODULE')}


def parameters(module):
    return {p.get('NAME'):p.get('VALUE') for p in module.findall('./PARAMETERS/PARAMETER')}


def verify(path):
    old_root,old=modules(HWH)
    root,new=modules(path)
    def require(ok,detail):
        if not ok:raise ValueError(detail)
    require(root.find('SYSTEMINFO').attrib==old_root.find('SYSTEMINFO').attrib,'Device/package/speed changed')
    inherited={'axi_vdma_0':0x43000000,'axi_vdma_1':0x43010000,
               'live_osd_0':0x43c00000,'v_tc_0':0x43c10000}
    address_ranges=new['processing_system7_0'].findall('./MEMORYMAP/MEMRANGE')
    addresses={p.get('INSTANCE'):int(p.get('BASEVALUE'),16) for p in address_ranges}
    require(addresses==dict(inherited,pcm_buffer_0=0x43c20000),'Unexpected CPU AXI address map')
    for n in ['axi_vdma_0','axi_vdma_1']:
        before,after=parameters(old[n]),parameters(new[n])
        for key,value in before.items():
            if key.startswith('c_') or key in ['C_INCLUDE_MM2S','C_INCLUDE_S2MM','C_ADDR_WIDTH']:
                require(after.get(key)==value,n+'/'+key+' changed')
    before,after=parameters(old['processing_system7_0']),parameters(new['processing_system7_0'])
    for key,value in before.items():
        # Preserve DDR, MIO routing and AXI port configuration, not generated component names.
        if key.startswith(('PCW_UIPARAM_DDR_','PCW_MIO_','PCW_DDR_','PCW_ENET','PCW_UART','PCW_USB','PCW_SD')) or key in (
            'PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ','PCW_ACT_FPGA1_PERIPHERAL_FREQMHZ','PCW_USE_M_AXI_GP0','PCW_USE_S_AXI_HP0'):
            require(after.get(key)==value,'Inherited PS configuration changed: '+key)
    before,after=parameters(old['v_tc_0']),parameters(new['v_tc_0'])
    for key in ['GEN_HACTIVE_SIZE','GEN_HFRAME_SIZE','GEN_HSYNC_START','GEN_HSYNC_END',
                'GEN_VACTIVE_SIZE','GEN_F0_VFRAME_SIZE','GEN_F0_VSYNC_VSTART','GEN_F0_VSYNC_VEND',
                'GEN_HSYNC_POLARITY','GEN_VSYNC_POLARITY']:
        require(after.get(key)==before[key],'VTC raster changed: '+key)
    clock=parameters(new['clk_wiz_0'])
    frequency=[100*float(clock['MMCM_CLKFBOUT_MULT_F'])/float(clock['MMCM_DIVCLK_DIVIDE'])/float(clock[k])
               for k in ['MMCM_CLKOUT0_DIVIDE_F','MMCM_CLKOUT1_DIVIDE','MMCM_CLKOUT2_DIVIDE']]
    require(frequency==[75,375,150],'Candidate MMCM does not generate 75/375/150 MHz')
    audio=parameters(new['pcm_buffer_0'])
    require(audio['FIFO_DEPTH']=='8192','PCM FIFO depth changed')
    require(new['hdmi_audio_tx_0'].get('VLNV')=='xilinx.com:module_ref:hdmi_audio_tx:1.0','Audio transmitter missing')
    def signal(instance,port):
        found=new[instance].find(f'./PORTS/PORT[@NAME="{port}"]')
        require(found is not None,'Port missing: '+instance+'/'+port)
        return found.get('SIGNAME')
    require(audio['USE_SAMPLE_ENABLE']=='1','PCM consumer ignores the sample-enable tick')
    require(signal('audio_sample_tick_0','clk_pixel')==signal('pcm_buffer_0','sample_clk')==signal('clk_wiz_0','clk_out1'),
            'PCM consumer and HDMI use different sample clocks')
    require(signal('audio_sample_tick_0','sample_enable')==signal('pcm_buffer_0','sample_enable')==signal('hdmi_audio_tx_0','sample_enable'),
            'PCM consumer and HDMI use different sample enables')
    for target,source in [('rgb','out_data'),('de','out_de'),('hsync','out_hsync'),('vsync','out_vsync')]:
        require(signal('hdmi_audio_tx_0',target)==signal('live_osd_0',source),'External video path disconnected: '+target)
    return dict(passed=True,scope='HWH structural/parameter contract only; not board/timing/audio verification',
        hwh_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),original_hwh_sha256=hashlib.sha256(HWH.read_bytes()).hexdigest(),
        addresses={k:hex(v) for k,v in addresses.items()},candidate_clocks_mhz=frequency)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('hwh',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    report=verify(args.hwh)
    with args.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(report))


if __name__=='__main__':main()
