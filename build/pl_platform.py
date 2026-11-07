"""Build an additive PL integration in a new Vivado project; source projects stay intact."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def literal(path):
    value = Path(path).resolve().as_posix()
    if any(c in value for c in '{}\r\n'):raise ValueError('unsupported Tcl path')
    return '{'+value+'}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', choices=('eeg', 'map'))
    parser.add_argument('--ip', type=Path, required=True, help='HLS solution/impl/ip directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tool', required=True)
    parser.add_argument('--bd-tcl', type=Path, help='existing complete design Tcl; default is a PS compatibility shell')
    parser.add_argument('--project', type=Path, help='copy an existing exact-board XPR with its source settings')
    parser.add_argument('--ip-repo', action='append', type=Path, default=[])
    parser.add_argument('--source', action='append', type=Path, default=[])
    parser.add_argument('--xdc', action='append', type=Path, default=[])
    parser.add_argument('--implement', action='store_true', help='route and write bitstream using supplied board constraints')
    args = parser.parse_args()
    if args.project and args.bd_tcl:parser.error('choose --project or --bd-tcl')
    output = args.output.resolve()
    if output.exists() or not output.is_absolute() or not re.fullmatch(r'[A-Za-z0-9_:/.-]+', output.as_posix()):
        raise ValueError('choose a new, short ASCII external output directory')
    if args.implement and (not (args.bd_tcl or args.project) or (not args.project and not args.xdc)):
        raise ValueError('bitstream build requires original design Tcl and exact-board XDC')
    output.mkdir(parents=True)
    def staged_file(path, name):
        path = path.resolve()
        if path.as_posix().isascii():return path
        target = output/name
        shutil.copyfile(path, target)
        return target
    args.ip = args.ip.resolve()
    if not args.ip.as_posix().isascii():
        target = output/'kernel_ip';shutil.copytree(args.ip, target);args.ip = target
    repos = []
    for index, path in enumerate(args.ip_repo):
        path = path.resolve()
        if not path.as_posix().isascii():
            target = output/('ip_repo_'+str(index));shutil.copytree(path, target);path = target
        repos.append(path)
    args.ip_repo = repos
    if args.bd_tcl:args.bd_tcl = staged_file(args.bd_tcl, 'baseline.tcl')
    args.source = [staged_file(p, 'source_'+str(i)+p.suffix) for i, p in enumerate(args.source)]
    args.xdc = [staged_file(p, 'pins_'+str(i)+p.suffix) for i, p in enumerate(args.xdc)]
    source = Path(__file__).resolve().parents[1]/'src/workspace/integrations/pl_accel/hardware/integrate.tcl'
    shutil.copyfile(source, output/'integrate.tcl')
    part = 'xc7z015clg485-2' if args.kernel == 'eeg' else 'xc7z020clg400-2'
    lines = ['set_param general.maxThreads 2']
    if args.project:
        lines += ['open_project -read_only '+literal(args.project),
            'set original_top [get_property top [current_fileset]]',
            'save_project_as -scan_for_includes -exclude_run_results platform '+literal(output/'project')]
    else:lines += ['create_project platform project -part '+part]
    lines += ['set_property ip_repo_paths [lsort -unique [concat [get_property ip_repo_paths [current_project]] [list '+ ' '.join(literal(p) for p in args.ip_repo+[args.ip])+']]] [current_project]',
             'update_ip_catalog']
    for path in args.source:lines += ['add_files -norecurse '+literal(path)]
    if args.project:
        lines += ['open_bd_design [get_files *.bd]']
    elif args.bd_tcl:
        lines += ['source '+literal(args.bd_tcl)]
    else:
        # The original GP0 register slave exercises compatibility with existing mappings.
        lines += ['create_bd_design system',
            'create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0',
            'set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 1 CONFIG.PCW_EN_CLK0_PORT 1 CONFIG.PCW_EN_RST0_PORT 1 CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ 100.000000] [get_bd_cells processing_system7_0]',
            'apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "0" Master "Disable" Slave "Disable"} [get_bd_cells processing_system7_0]',
            'create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 original_control',
            'set_property -dict [list CONFIG.C_ALL_INPUTS 1 CONFIG.C_GPIO_WIDTH 1] [get_bd_cells original_control]',
            'apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config {Master "/processing_system7_0/M_AXI_GP0" Clk_master "/processing_system7_0/FCLK_CLK0 (100 MHz)" Clk_slave "Auto" Clk_xbar "Auto" intc_ip "New AXI Interconnect" master_apm "0"} [get_bd_intf_pins original_control/S_AXI]',
            'make_bd_pins_external [get_bd_pins original_control/gpio_io_i]',
            'assign_bd_address -offset 0x43c00000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs original_control/S_AXI/Reg] -force']
    lines += ['source integrate.tcl', 'pl_accel::attach '+args.kernel+' '+literal(args.ip),
        'save_bd_design', 'write_bd_tcl -force integrated.tcl',
        'set bd [get_files *.bd]', 'generate_target all $bd',
        'set wrapper [make_wrapper -files $bd -top]', 'add_files -norecurse $wrapper']
    if args.project:
        lines += ['set_property top $original_top [current_fileset]']
    else:
        lines += ['set_property top [file rootname [file tail $wrapper]] [current_fileset]']
    for path in args.xdc:lines += ['add_files -fileset constrs_1 '+literal(path)]
    lines += ['update_compile_order -fileset sources_1', 'launch_runs synth_1 -jobs 2',
        'wait_on_run synth_1',
        'if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Platform synthesis failed"}',
        'open_run synth_1', 'report_utilization -file platform_utilization.rpt',
        'report_timing_summary -file platform_timing.rpt', 'write_checkpoint -force platform_synth.dcp']
    if args.implement:
        lines += ['close_design', 'launch_runs impl_1 -to_step write_bitstream -jobs 2', 'wait_on_run impl_1',
            'if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Platform implementation failed"}',
            'open_run impl_1', 'report_timing_summary -file platform_routed_timing.rpt',
            'write_hw_platform -fixed -include_bit -force platform.xsa']
    lines += ['puts PL_PLATFORM_PASS', 'exit']
    (output/'build.tcl').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    environment = os.environ.copy();environment.setdefault('PROCESSOR_ARCHITECTURE', 'AMD64')
    with (output/'build.log').open('w', encoding='utf-8') as log:
        run = subprocess.run([args.tool, '-mode', 'batch', '-nojournal', '-nolog', '-source', 'build.tcl'],
            cwd=output, stdout=log, stderr=subprocess.STDOUT, env=environment)
    log_text = (output/'build.log').read_text(encoding='utf-8', errors='replace')
    if run.returncode or 'PL_PLATFORM_PASS' not in log_text or not (output/'platform_synth.dcp').is_file():
        print(log_text[-7000:]);return run.returncode or 1
    result = dict(part=part, kernel=args.kernel, scope=('original_project' if args.project else 'original_bd') if (args.bd_tcl or args.project) else 'PS_compatibility_shell',
        implemented=args.implement, additive_integration=True, preserved_original_control_address=True)
    (output/'summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2));return 0


if __name__ == '__main__':sys.exit(main())
