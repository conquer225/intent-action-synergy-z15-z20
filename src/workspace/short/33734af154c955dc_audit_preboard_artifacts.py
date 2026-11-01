"""Audit saved evidence only. Does not run Vivado or contact/program the board."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
APP = HERE.parents[1]
CANDIDATE = APP / 'output/pl_protocol_explicit_20260928'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rules(text):
    return {name: {'severity': severity, 'count': int(count)}
            for name, severity, count in re.findall(
                r'\|\s*([A-Z]+-\d+)\s*\|\s*(Warning|Advisory|Error|Critical Warning)\s*\|[^\n]*?\|\s*(\d+)\s*\|', text)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    snapshot = json.loads((args.output / 'board/board_snapshot.json').read_text())
    dt = {k: base64.b64decode(v) for k, v in snapshot['device_tree'].items()}
    props = {k: v.decode(errors='replace').rstrip('\0').split('\0')
             for k, v in dt.items() if k.endswith('compatible')}
    report = (CANDIDATE / 'route/timing_summary.rpt').read_text()
    timing = re.search(r'\n\s*(4\.627)\s+0\.000\s+0\s+\d+\s+(0\.049)\s+0\.000\s+0\s+\d+', report)
    if not timing or 'Vivado v.2025.2' not in report:
        raise ValueError('Saved timing report no longer matches the audited checkpoint')
    routed = CANDIDATE / 'route/routed.dcp'
    if sha(routed) != '532d268db44c93d81e26687f218c2ea4c77935a62aba2cc91fd13f18eec1e93f':
        raise ValueError('Routed checkpoint changed; repeat the candidate review')
    xpr = CANDIDATE / 'project/pl_filter_candidate_dma.xpr'
    design = ET.parse(xpr).getroot()
    source_paths = []
    for element in design.findall("./FileSets/FileSet[@Name='sources_1']/File"):
        source = element.attrib['Path'].replace('$PPRDIR', str(xpr.parent))
        source = source.replace('$PSRCDIR', str(xpr.parent / 'pl_filter_candidate_dma.srcs'))
        source = source.replace('$PGENDIR', str(xpr.parent / 'pl_filter_candidate_dma.gen'))
        source_paths.append(Path(source).resolve())
    part = design.find("./Configuration/Option[@Name='Part']").attrib['Val']
    hwh = args.output / 'board/recovery/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.hwh'
    current_dma = ET.parse(hwh).find(".//MODULE[@INSTANCE='axi_dma_0']")
    if current_dma is None:
        raise ValueError('Current saved HWH has no expected axi_dma_0')
    current_params = {n.attrib['NAME']: n.attrib['VALUE']
                      for n in current_dma.findall('./PARAMETERS/PARAMETER')}
    artifacts = source_paths + [xpr, routed, HERE / 'gldma_owner.ko',
        HERE / 'candidate_static_node.dtsi', HERE / 'gldma_owner.c', HERE / 'gldma_guard.h',
        HERE / 'gldma_board_check.c', args.output / 'gldma_board_check_arm',
        args.output / 'vectors/golden_frames.bin',
        args.output / 'vectors/vectors_manifest.json']
    artifacts += list((CANDIDATE / 'route').glob('*.rpt'))
    forbidden = [str(x) for x in CANDIDATE.rglob('*')
                 if x.is_file() and x.suffix.lower() in ('.bit', '.bin', '.mcs')]
    hwh_paths = list(CANDIDATE.rglob('*.hwh'))
    if len(hwh_paths) != 1:
        raise ValueError('Expected exactly one generated candidate BD HWH')
    candidate_hwh = ET.parse(hwh_paths[0])
    dma = candidate_hwh.find(".//MODULE[@INSTANCE='pf_dma']")
    gpio = candidate_hwh.find(".//MODULE[@INSTANCE='pf_control']")
    if dma is None or gpio is None:
        raise ValueError('Generated HWH missing DMA/control')
    candidate_params = {n.attrib['NAME']: n.attrib['VALUE']
                        for n in dma.findall('./PARAMETERS/PARAMETER')}
    for key, value in {'C_INCLUDE_MM2S': '1', 'C_INCLUDE_S2MM': '1',
                       'C_INCLUDE_SG': '0', 'C_M_AXIS_MM2S_TDATA_WIDTH': '64',
                       'C_S_AXIS_S2MM_TDATA_WIDTH': '64',
                       'C_M_AXI_MM2S_DATA_WIDTH': '64', 'C_M_AXI_S2MM_DATA_WIDTH': '64',
                       'C_M_AXI_MM2S_ADDR_WIDTH': '32', 'C_M_AXI_S2MM_ADDR_WIDTH': '32'}.items():
        if candidate_params.get(key) != value:
            raise ValueError('Candidate HWH DMA parameter mismatch: ' + key)
    ranges = {node.attrib['INSTANCE']: node.attrib for node in candidate_hwh.findall('.//MEMRANGE')
              if node.attrib.get('MASTERBUSINTERFACE') == 'M_AXI_GP0'}
    for instance, address in (('pf_dma', 0x40400000), ('pf_control', 0x41200000)):
        node = ranges[instance]
        if int(node['BASEVALUE'], 16) != address or int(node['HIGHVALUE'], 16) != address + 0xffff:
            raise ValueError('Candidate HWH MMIO map mismatch')
    ddr_ranges = {node.attrib['MASTERBUSINTERFACE']: node.attrib
                  for node in candidate_hwh.findall('.//MEMRANGE')
                  if node.attrib.get('MASTERBUSINTERFACE') in ('M_AXI_MM2S', 'M_AXI_S2MM')}
    for direction in ('M_AXI_MM2S', 'M_AXI_S2MM'):
        node = ddr_ranges[direction]
        if (node['SLAVEBUSINTERFACE'] != 'S_AXI_HP0' or
                int(node['BASEVALUE'], 16) != 0 or int(node['HIGHVALUE'], 16) != 0x3fffffff):
            raise ValueError('Candidate HWH HP0 map mismatch')
    artifacts += hwh_paths
    bundle = args.output / 'candidate_bundle'
    bundle.mkdir(exist_ok=True)
    frozen = {}
    sources = [HERE / name for name in (
        'gldma_owner.c', 'gldma_owner.ko', 'gldma_uapi.h', 'gldma_policy.h',
        'gldma_guard.h', 'gldma_board_check.c', 'gldma_status.c',
        'candidate_static_node.dtsi')]
    sources += [args.output / 'gldma_board_check_arm',
                args.output / 'gldma_status_arm', args.output / 'vectors/golden_frames.bin',
                args.output / 'vectors/vectors_manifest.json', args.output / 'RUNBOOK.md']
    for path in sources:
        target = bundle / path.name
        if target.exists() and sha(target) != sha(path):
            raise ValueError('Frozen candidate changed; create a new reviewed bundle: ' + path.name)
        if not target.exists():
            shutil.copyfile(path, target)
        frozen[path.name] = sha(target)
    (bundle / 'SHA256.json').write_text(json.dumps(frozen, indent=2), encoding='utf-8')
    artifacts += sources
    result = {
        'status': 'PREPARATION_COMPLETE_BOARD_GATE_BLOCKED',
        'scope': 'saved report review and current live DT snapshot; no new hardware run',
        'tool': 'Vivado 2025.2', 'part': part,
        'timing_ns': {'wns': float(timing[1]), 'whs': float(timing[2])},
        'drc': rules((CANDIDATE / 'route/drc.rpt').read_text()),
        'methodology': rules((CANDIDATE / 'route/methodology.rpt').read_text()),
        'candidate_bit_files': forbidden,
        'candidate_generated_hwh': {'path': str(hwh_paths[0]),
            'status': 'BD metadata verified; no bitstream pairing proven',
            'dma': {k: candidate_params[k] for k in ('C_INCLUDE_MM2S', 'C_INCLUDE_S2MM',
                     'C_M_AXIS_MM2S_TDATA_WIDTH', 'C_S_AXIS_S2MM_TDATA_WIDTH')},
            'control_map': ranges, 'hp0_map': ddr_ranges},
        'live_dt': {'model': dt['model'].decode().rstrip('\0'),
                    'memory_reg_hex': dt['memory/reg'].hex(),
                    'amba_ranges_hex': dt['amba/ranges'].hex(),
                    'candidate_nodes': [k for k, values in props.items()
                        if 'guardianloop,z15-filter-dma-owner-v1' in values],
                    'dma_ranges_properties': {k: v.hex() for k,v in dt.items() if k.endswith('dma-ranges')},
                    'dma_coherent_properties': [k for k in dt if k.endswith('dma-coherent')]},
        'recovery_files_verified': len(snapshot['backup_verified']),
        'frozen_candidate_bundle': frozen,
        'current_saved_hwh_dma': {k: current_params[k] for k in (
            'C_INCLUDE_MM2S', 'C_INCLUDE_S2MM', 'C_M_AXIS_MM2S_TDATA_WIDTH', 'C_BASEADDR')},
        'unknowns': ['actual currently programmed PL identity',
            'physical HP0 coherent DDR readback and in-flight lifetime',
            'approved LUTAR-1 resolution', 'candidate bit/HWH pairing and controlled boot order'],
        'sha256': {str(path): sha(path) for path in artifacts},
    }
    if result['methodology'].get('LUTAR-1', {}).get('count') != 1:
        raise ValueError('Re-review methodology report')
    if forbidden:
        raise ValueError('Unexpected candidate bit/HWH artifact; manually review provenance')
    (args.output / 'artifact_audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'wns_ns': timing[1], 'whs_ns': timing[2],
                      'remaining_LUTAR_1': 1, 'candidate_dt_nodes': len(result['live_dt']['candidate_nodes']),
                      'recovery_files': result['recovery_files_verified'],
                      'current_saved_hwh_dma': result['current_saved_hwh_dma']}))


if __name__ == '__main__':
    main()
