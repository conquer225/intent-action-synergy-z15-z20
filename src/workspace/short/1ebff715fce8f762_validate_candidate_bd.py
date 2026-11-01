"""Rebuild a PS-config-preserving isolated BD; validation only, never build runs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def tcl_string(value):
    # Vivado BD JSON wraps long string properties as arrays of whitespace-separated fragments.
    if isinstance(value,list):
        value = ' '.join(value)
    value = str(value).replace('\\','/')
    if any(c in value for c in '{}\n\r'):
        raise ValueError('Unsupported Tcl literal')
    return '{'+value+'}'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source-bd',required=True)
    p.add_argument('--evidence',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--vivado-bin',required=True)
    args = p.parse_args()
    version_run = subprocess.run([str(Path(args.vivado_bin)/'vivado.bat'),'-version'],
                                 capture_output=True,text=True,timeout=30)
    version_text = version_run.stdout+version_run.stderr
    # AMD's Windows -version launcher can return 1 even for a valid version banner.
    # The batch script also verifies version -short before creating any project.
    if version_run.returncode not in (0,1) or 'vivado v2025.2 ' not in version_text.lower():
        raise RuntimeError('This candidate now requires Vivado 2025.2; no fallback allowed')
    src, evidence, out = map(lambda s:Path(s).resolve(),(args.source_bd,args.evidence,args.output))
    if out.exists():
        raise FileExistsError(out)
    design = json.loads(src.read_text())['design']
    params = design['components']['processing_system7_0']['parameters']
    part = design['design_info']['device']
    if part!='xc7z015clg485-2' or float(params['PCW_FPGA0_PERIPHERAL_FREQMHZ']['value'])!=50:
        raise ValueError('Unexpected source device/clock')
    if any(params[k]['value']!='1' for k in ('PCW_USE_M_AXI_GP0','PCW_USE_S_AXI_HP0')):
        raise ValueError('Verified source GP0/HP0 required')
    audit = json.loads((evidence/'control_audit.json').read_text())
    if not audit['passed']:
        raise ValueError('Control RTL simulation must pass first')
    for path, digest in audit['sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise ValueError('RTL evidence changed: '+path)
    out.mkdir(parents=True)
    ps_properties = ' '.join('CONFIG.'+k+' '+tcl_string(v['value']) for k,v in params.items())
    script = f'''
if {{[version -short] ne "2025.2"}} {{error "Vivado 2025.2 required"}}
create_project pl_filter_candidate_dma {tcl_string(out/'project')} -part {part}
set_property target_language Verilog [current_project]
create_bd_design filter_candidate
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:* processing_system7_0]
set_property -dict [list {ps_properties}] $ps
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/DDR]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/FIXED_IO]
set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:* pf_shell_reset]
set one [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:* pf_shell_one]
set_property -dict [list CONFIG.CONST_WIDTH 1 CONFIG.CONST_VAL 1] $one
set zero [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:* pf_shell_zero]
set_property -dict [list CONFIG.CONST_WIDTH 1 CONFIG.CONST_VAL 0] $zero
connect_bd_net [get_bd_pins pf_shell_one/dout] [get_bd_pins pf_shell_reset/dcm_locked] [get_bd_pins pf_shell_reset/aux_reset_in]
connect_bd_net [get_bd_pins pf_shell_zero/dout] [get_bd_pins pf_shell_reset/mb_debug_sys_rst]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins processing_system7_0/M_AXI_GP0_ACLK] [get_bd_pins processing_system7_0/S_AXI_HP0_ACLK] [get_bd_pins pf_shell_reset/slowest_sync_clk]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins pf_shell_reset/ext_reset_in]
source {tcl_string(HERE/'attach_candidate.tcl')}
primary_filter_candidate::attach processing_system7_0 processing_system7_0/FCLK_CLK0 pf_shell_reset/peripheral_aresetn processing_system7_0/M_AXI_GP0 processing_system7_0/S_AXI_HP0 {tcl_string(evidence/'coeff.hex')}
if {{[get_property CONFIG.C_EXT_RESET_HIGH $rst] != 0}} {{error "PS reset polarity was not propagated as active-low"}}
if {{[get_property CONFIG.C_AUX_RESET_HIGH $rst] != 0}} {{error "Auxiliary reset tied high requires active-low polarity"}}
set bd [get_files */filter_candidate.bd]
set_property synth_checkpoint_mode None $bd
generate_target all $bd
puts "PRIMARY_FILTER_BD_VALIDATED_NO_SYNTHESIS"
close_project
exit
'''
    script_path = out/'validate_only.tcl'
    script_path.write_text(script,encoding='utf-8')
    inputs = (src,script_path,HERE/'attach_candidate.tcl',HERE/'validate_candidate_bd.py')
    hashes = {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs}
    result = subprocess.run([str(Path(args.vivado_bin)/'vivado.bat'),'-mode','batch','-source',str(script_path),
                             '-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')],
                            cwd=out,capture_output=True,text=True,timeout=240)
    log = result.stdout+result.stderr
    (out/'stdout.log').write_text(log,encoding='utf-8')
    unchanged = all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in hashes.items())
    critical_warnings = [line for line in log.splitlines() if 'CRITICAL WARNING:' in line]
    passed = unchanged and result.returncode==0 and 'PRIMARY_FILTER_BD_VALIDATED_NO_SYNTHESIS' in log and 'ERROR:' not in log and not critical_warnings
    result_data = dict(passed=passed,returncode=result.returncode,scope='Vivado BD validation only',
                       tool_version=version_text.strip(),
                       source_tool_version=design['design_info']['tool_version'],
                       synthesis_run=False,implementation_run=False,bitstream_generated=False,board_modified=False,
                       source_files_unchanged=unchanged, critical_warnings=critical_warnings, sha256=hashes)
    (out/'bd_audit.json').write_text(json.dumps(result_data,indent=2),encoding='utf-8')
    print(log[-14000:])
    if not passed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
