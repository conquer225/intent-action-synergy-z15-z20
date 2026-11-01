"""Audit the isolated rebuild; bus-side success never qualifies DDR deployment."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

BASE = Path('D:/ican/codex_project/eeg_apps_z15/output/pl_reset_closure_20260928')
OLD = BASE.parent / 'pl_smartconnect_isolated_20260928'
EXPLICIT = BASE.parent / 'pl_protocol_explicit_20260928'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def design(path):
    return json.loads(path.read_text())['design']


def main():
    imported = BASE / 'project/pl_filter_candidate_dma.srcs/sources_1/bd/inputs/filter_candidate.bd'
    before, after = design(BASE / 'inputs/filter_candidate.bd'), design(imported)
    differences = []
    for name, old_component in before['components'].items():
        new_component = after['components'][name]
        if old_component['vlnv'] != new_component['vlnv']:
            differences.append(f'{name}:vlnv')
        if old_component.get('parameters', {}) != new_component.get('parameters', {}):
            differences.append(f'{name}:parameters')
    for key in ('nets', 'interface_nets', 'addressing'):
        if before[key] != after[key]:
            differences.append(key)
    if differences:
        raise ValueError(f'Unexpected semantic BD changes: {differences}')
    hwh_files = list((BASE / 'project').rglob('hw_handoff/filter_candidate.hwh'))
    if len(hwh_files) != 1:
        raise ValueError('Expected one top-level HWH')
    hwh = ET.parse(hwh_files[0]).getroot()
    if hwh.get('VIVADOVERSION') != '2025.2':
        raise ValueError('HWH tool version mismatch')
    modules = {module.get('INSTANCE'): module for module in hwh.findall('./MODULES/MODULE')}
    expected_parameters = {
        'pf_dma': {'C_BASEADDR': '0x40400000', 'C_HIGHADDR': '0x4040FFFF',
                   'C_INCLUDE_SG': '0', 'C_M_AXI_MM2S_DATA_WIDTH': '64', 'C_M_AXI_S2MM_DATA_WIDTH': '64'},
        'pf_control': {'C_BASEADDR': '0x41200000', 'C_HIGHADDR': '0x4120FFFF'},
        'pf_axi_sc': {'NUM_SI': '2', 'NUM_MI': '1'},
    }
    for name, expected in expected_parameters.items():
        parameters = {item.get('NAME'): item.get('VALUE') for item in modules[name].findall('./PARAMETERS/PARAMETER')}
        for key, value in expected.items():
            if parameters.get(key) != value:
                raise ValueError(f'HWH contract mismatch: {name}.{key}')
    rtl = json.loads((BASE / 'rtl_sim/simulation_audit.json').read_text())
    if not rtl['passed']:
        raise ValueError('RTL tests failed')
    for path, digest in rtl['sha256'].items():
        if sha(Path(path)) != digest:
            raise ValueError(f'RTL evidence changed: {path}')
    for name in ('primary_sos_core.sv', 'primary_sos_axis.sv', 'primary_filter_top.sv'):
        matching = [path for path in rtl['sha256'] if Path(path).name == name]
        if len(matching) != 1 or sha(BASE / 'inputs' / name) != rtl['sha256'][matching[0]]:
            raise ValueError(f'Frozen source does not match simulated RTL: {name}')
    shadow = {}
    for case in ('normal_drain', 'transient_stall', 'blocked'):
        trace = BASE / f'export/xsim/{case}_bus_observation.log'
        args = [sys.executable, str(BASE / 'inputs/verify_hp0_axi_write_trace.py'), str(trace), str(BASE / 'inputs/vectors.txt')]
        if case == 'blocked':
            args.append('--blocked')
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        shadow[case] = result.stdout.strip()
    strict = (BASE / 'export/xsim/normal_drain_strict.log').read_text(errors='replace')
    strict_mismatch = re.search(r'VIP_DDR_MISMATCH frame=(\d+) words=(\d+) first_bad=(\d+)', strict)
    if not strict_mismatch or 'DDR golden mismatch: full acceptance blocked' not in strict:
        raise ValueError('Expected stock DDR strict failure not recorded; review manually')
    route = BASE / 'route'
    methodology = (route / 'methodology.rpt').read_text()
    drc = (route / 'drc.rpt').read_text()
    timing = (route / 'timing_summary.rpt').read_text()
    status = (route / 'route_status.rpt').read_text()
    utilization = (route / 'utilization.rpt').read_text()
    if 'Vivado v.2025.2' not in methodology or 'Checks found: 0' not in methodology:
        raise ValueError('Methodology checks are not zero under 2025.2')
    for rule in ('LUTAR-1', 'REQP-1839', 'REQP-1840', 'PDCN-1569'):
        if rule in methodology + drc:
            raise ValueError(f'Reset rule remains: {rule}')
    if re.search(r'\|\s+(?:Critical Warning|Error)\s+\|', drc):
        raise ValueError('Routed DRC has critical/error violations')
    timing_match = re.search(r'WNS\(ns\).*\n\s*-+.*\n\s*([^\n]+)', timing)
    if not timing_match:
        raise ValueError('Timing summary not found')
    numbers = timing_match[1].split()
    wns, tns, setup_failed = float(numbers[0]), float(numbers[1]), int(numbers[2])
    whs, ths, hold_failed = float(numbers[4]), float(numbers[5]), int(numbers[6])
    if min(wns, whs) < 0 or tns or ths or setup_failed or hold_failed:
        raise ValueError('Timing failed')
    for check in ('no_clock', 'unconstrained_internal_endpoints'):
        if f'checking {check} (0)' not in timing:
            raise ValueError(f'Timing coverage failed: {check}')
    def net_count(label):
        return int(re.search(re.escape(label) + r'\.*\s*:\s*(\d+)', status)[1])
    routable, routed, errors = (net_count(label) for label in
                               ('# of routable nets', '# of fully routed nets', '# of nets with routing errors'))
    if not routable or routed != routable or errors:
        raise ValueError('Route incomplete')
    def used(label):
        match = re.search(r'\|\s*' + re.escape(label) + r'\s*\|\s*(\d+)', utilization)
        if not match:
            raise ValueError(f'Missing utilization row: {label}')
        return int(match[1])
    resources = {name: used(label) for name, label in
                 [('lut', 'Slice LUTs'), ('ff', 'Slice Registers'), ('dsp', 'DSPs'), ('bram_tile', 'Block RAM Tile')]}
    forbidden = [str(path) for path in (BASE / 'project').rglob('*') if path.suffix.lower() in ('.bit', '.bin', '.mcs')]
    if forbidden:
        raise ValueError(f'Forbidden programming artifacts: {forbidden}')
    preserved = {
        EXPLICIT / 'project/pl_filter_candidate_dma.srcs/sources_1/bd/filter_candidate/filter_candidate.bd':
            '10e5ac3c9fcea478f66457af57984b289385d667ea5bb270e6a0b6624636c0e0',
        OLD / 'route/routed.dcp': '12b86d785b20ee05fb9e8bb0e96088df6b3195c2750173426c7016e473023b2d',
        OLD / 'project/pl_filter_candidate_dma.srcs/sources_1/bd/filter_candidate/filter_candidate.bd':
            '87806f300863fdedd008fdd1d5217e9b19f33d7fbf6ff9d95858d0dcb41cc66d',
    }
    for path, digest in preserved.items():
        if sha(path) != digest:
            raise ValueError(f'Original evidence changed: {path}')
    files = [*sorted((BASE / 'inputs').glob('*')), imported, route / 'routed.dcp',
             *sorted(route.glob('*.rpt')), *sorted((BASE / 'synthesis_reports').glob('*')),
             *sorted((BASE / 'export/xsim').glob('*observation.log')), BASE / 'export/xsim/normal_drain_strict.log',
             *sorted((BASE / 'project').rglob('hw_handoff/filter_candidate.hwh'))]
    audit = dict(tool_version='2025.2', part='xc7z015clg485-2', clock_mhz=50,
                 reset_warning_closed=True, fresh_project=True, semantic_bd_changes=differences,
                 rtl=rtl['results'], shadow=shadow, stock_ddr_strict_pass=False,
                 stock_ddr_mismatch=dict(zip(('frame', 'words', 'first_bad'), map(int, strict_mismatch.groups()))),
                 wns_ns=wns, whs_ns=whs, routed_nets=routed, resources=resources,
                 methodology_checks=0, drc_checks=int(re.search(r'Checks found:\s*(\d+)', drc)[1]),
                 programming_artifacts=forbidden, deployment_qualified=False,
                 board_actions='none', original_hashes_unchanged=True,
                 hwh_contract=expected_parameters,
                 sha256={str(path): sha(path) for path in files if path.is_file()})
    (BASE / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in audit.items() if key != 'sha256'}, indent=2))


if __name__ == '__main__':
    main()
