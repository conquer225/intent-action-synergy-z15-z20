"""Simulate the candidate's generated reset IP and reject corrupted BD contracts."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess

from reset_contract import reset_parameters, reset_failures

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--build', required=True)
    p.add_argument('--vivado-bin', required=True)
    args = p.parse_args()
    build, bin_dir = Path(args.build).resolve(), Path(args.vivado_bin).resolve()
    if 'vivado v2025.2 ' not in subprocess.run(
            [str(bin_dir/'vivado.bat'), '-version'], capture_output=True,
            text=True, timeout=30).stdout.lower():
        raise ValueError('Vivado 2025.2 required')
    bd = build/'project/pl_filter_candidate_dma.srcs/sources_1/bd/filter_candidate/filter_candidate.bd'
    gen = build/'project/pl_filter_candidate_dma.gen/sources_1/bd/filter_candidate'
    wrapper = gen/'ip/filter_candidate_pf_shell_reset_0/synth/filter_candidate_pf_shell_reset_0.vhd'
    vendor, = gen.glob('ipshared/*/hdl/proc_sys_reset_v5_0_vh_rfs.vhd')
    design = json.loads(bd.read_text())['design']
    params = reset_parameters(wrapper.read_text())
    failures = reset_failures(design, params)
    if failures:
        raise ValueError(failures)
    # Mutations ensure the new checks catch the actual old bug and other missing wires.
    rejected = []
    for label, endpoint, target in (
            ('old_aux_tied_low', 'pf_shell_reset/aux_reset_in', 'pf_shell_zero/dout'),
            ('debug_tied_high', 'pf_shell_reset/mb_debug_sys_rst', 'pf_shell_one/dout'),
            ('locked_tied_low', 'pf_shell_reset/dcm_locked', 'pf_shell_zero/dout'),
            ('dma_reset_missing', 'pf_dma/axi_resetn', None),
            ('interconnect_reset_missing', 'pf_memory/S01_ARESETN', None),
            ('reset_clock_missing', 'pf_shell_reset/slowest_sync_clk', None),
            ('ps_reset_missing', 'pf_shell_reset/ext_reset_in', None)):
        changed = copy.deepcopy(design)
        for net in changed['nets'].values():
            if endpoint in net['ports']:
                net['ports'].remove(endpoint)
        if target:
            next(n for n in changed['nets'].values() if target in n['ports'])['ports'].append(endpoint)
        if not reset_failures(changed, params):
            raise AssertionError('Mutation not rejected: '+label)
        rejected.append(label)
    for key in params:
        altered = dict(params)
        altered[key] = 1 if key.endswith('HIGH') else 8
        if not reset_failures(design, altered):
            raise AssertionError('Parameter mutation not rejected: '+key)
        rejected.append(key)
    for name in ('pf_shell_zero', 'pf_shell_one'):
        changed = copy.deepcopy(design)
        field = changed['components'][name]['parameters']['CONST_VAL']
        field['value'] = str(1-int(field['value']))
        if not reset_failures(changed, params):
            raise AssertionError('Constant mutation not rejected: '+name)
        rejected.append(name)
    out = build/'reset_regression'
    out.mkdir()
    (out/'vendor_reset_lib').mkdir()
    (out/'xsim.ini').write_text('proc_sys_reset_v5_0_17=./vendor_reset_lib\n', encoding='ascii')
    tb = HERE/'reset_shell_regression_tb.vhd'
    glbl = bin_dir.parent/'data/verilog/src/glbl.v'
    commands = [
        ('xvhdl.bat', ['--initfile', 'xsim.ini', '--work', 'proc_sys_reset_v5_0_17', str(vendor)]),
        ('xvhdl.bat', ['--initfile', 'xsim.ini', str(wrapper)]),
        ('xvhdl.bat', ['--initfile', 'xsim.ini', '--2008', str(tb)]),
        ('xvlog.bat', [str(glbl)]),
        ('xelab.bat', ['--initfile', 'xsim.ini', 'reset_shell_regression_tb', 'glbl',
                       '-L', 'proc_sys_reset_v5_0_17', '-L', 'xpm', '-L', 'unisims_ver',
                       '-s', 'reset_regression']),
        ('xsim.bat', ['reset_regression', '-runall'])]
    for i, (tool, arguments) in enumerate(commands):
        result = subprocess.run([str(bin_dir/tool), *arguments], cwd=out,
                                capture_output=True, text=True, timeout=120)
        log = result.stdout+result.stderr
        (out/f'{i}_{tool}.log').write_text(log, encoding='utf-8')
        print(log, flush=True)
        if result.returncode or 'ERROR:' in log or 'Failure:' in log or 'Fatal:' in log:
            raise RuntimeError(tool+' failed')
    marker = 'RESET_REGRESSION_PASS startup=1 repeated=3 synchronous_edges=PASS min_16_cycles=PASS'
    if marker not in log or log.count('RESET_PULSE_PASS') != 3:
        raise AssertionError('Incomplete reset simulation')
    files = [bd, wrapper, vendor, tb, HERE/'reset_contract.py', Path(__file__).resolve(),
             *sorted(out.glob('*.log'))]
    audit = dict(passed=True, tool_version='2025.2', reset_parameters=params,
                 negative_tests_rejected=rejected, startup_release=True, repeated_resets=3,
                 scope='Generated reset IP functional simulation and saved BD connectivity; not DMA transaction recovery or physical timing',
                 sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    (out/'reset_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
