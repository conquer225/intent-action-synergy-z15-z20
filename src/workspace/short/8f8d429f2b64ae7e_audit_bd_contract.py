"""Read-only BD contract audit, independent of Vivado's validation exit code."""
import argparse
import hashlib
import json
from pathlib import Path
from reset_contract import reset_parameters, reset_failures


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source-bd',required=True)
    p.add_argument('--candidate-bd',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--reset-wrapper',required=True)
    args = p.parse_args()
    source, candidate, out = [Path(v).resolve() for v in (args.source_bd,args.candidate_bd,args.output)]
    if out.exists():
        raise FileExistsError(out)
    old = json.loads(source.read_text())['design']
    new = json.loads(candidate.read_text())['design']
    components = new['components']
    wrapper = Path(args.reset_wrapper).resolve()
    reset_params = reset_parameters(wrapper.read_text())
    a = old['components']['processing_system7_0']['parameters']
    b = components['processing_system7_0']['parameters']
    def normalized(value):
        return ' '.join(value) if isinstance(value,list) else str(value)
    differences = [k for k,v in a.items() if k not in b or normalized(v['value'])!=normalized(b[k]['value'])]
    failures = ['Changed PS parameter: '+k for k in differences]
    failures.extend(reset_failures(new, reset_params))
    expected = {'c_addr_width':32,'c_include_mm2s':1,'c_include_s2mm':1,'c_include_sg':0,
                'c_m_axi_mm2s_data_width':64,'c_m_axi_s2mm_data_width':64,
                'c_m_axis_mm2s_tdata_width':64,'c_s_axis_s2mm_tdata_width':64,'c_sg_length_width':16}
    for key,value in expected.items():
        if int(components['pf_dma']['parameters'][key]['value'])!=value:
            failures.append('DMA parameter mismatch: '+key)
    for name in ('s_axis','m_axis'):
        params = components['pf_filter']['interface_ports'][name]['parameters']
        for key,value in {'TDATA_NUM_BYTES':8,'HAS_TKEEP':1,'HAS_TLAST':1,'HAS_TREADY':1,'FREQ_HZ':50000000}.items():
            if int(params[key]['value'])!=value:
                failures.append('Stream mismatch: '+name+'/'+key)
    for ends in ({'pf_dma/M_AXIS_MM2S','pf_filter/s_axis'}, {'pf_filter/m_axis','pf_dma/S_AXIS_S2MM'}):
        if not any(ends <= set(net['interface_ports']) for net in new['interface_nets'].values()):
            failures.append('Stream net missing: '+str(sorted(ends)))
    clock_ports = set(new['nets']['processing_system7_0_FCLK_CLK0']['ports'])
    if not {'pf_filter/aclk','pf_dma/s_axi_lite_aclk','pf_dma/m_axi_mm2s_aclk','pf_dma/m_axi_s2mm_aclk',
            'pf_control/s_axi_aclk','processing_system7_0/S_AXI_HP0_ACLK'} <= clock_ports:
        failures.append('Clock net incomplete')
    gpio = components['pf_control']['parameters']
    if int(gpio['C_DOUT_DEFAULT']['value'],0)!=1 or gpio['C_ALL_INPUTS_2']['value']!='1':
        failures.append('GPIO reset/status mismatch')
    files = (source,candidate,wrapper,Path(__file__).resolve(),Path(__file__).with_name('reset_contract.py'))
    result = dict(passed=not failures,ps_parameters_compared=len(a),failures=failures,
                  scope='Saved BD structure/configuration only; no synthesis/timing/hardware guarantee',
                  reset_parameters=reset_params,
                  sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if failures:
        raise SystemExit(1)


if __name__=='__main__':
    main()
