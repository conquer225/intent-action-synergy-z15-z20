"""Audit the r8 exported hardware contract and unchanged recognition sources."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from verify_release import main as verify_payloads
    verify_payloads()
    baseline = json.loads((ROOT / 'report/recognition_baseline_r7.json').read_text())
    for name, digest in baseline.items():
        assert sha(ROOT / name) == digest, 'Recognition baseline changed: ' + name
    rollback = ROOT / 'rollback/r7-video1'
    rollback_digest = (rollback / 'SHA256.txt').read_text().split()[0]
    assert sha(rollback / 'BOOT.BIN') == rollback_digest, 'Rollback BOOT mismatch'
    assert sha(ROOT / 'build/BOOT.BIN') != rollback_digest, 'r8 BOOT still contains r7'
    expected = {
        'axi_vdma_0': {'C_BASEADDR': 0x43000000, 'C_NUM_FSTORES': 3,
                       'C_INCLUDE_INTERNAL_GENLOCK': 1, 'C_S2MM_GENLOCK_MODE': 2,
                       'C_MM2S_GENLOCK_MODE': 3, 'C_INCLUDE_MM2S': 1,
                       'C_INCLUDE_S2MM': 1, 'C_S_AXIS_S2MM_TDATA_WIDTH': 24,
                       'C_M_AXIS_MM2S_TDATA_WIDTH': 24},
        'axi_vdma_1': {'C_BASEADDR': 0x43010000, 'C_NUM_FSTORES': 2,
                       'C_INCLUDE_INTERNAL_GENLOCK': 0, 'C_S2MM_GENLOCK_MODE': 0,
                       'C_INCLUDE_MM2S': 0, 'C_INCLUDE_S2MM': 1,
                       'C_S_AXIS_S2MM_TDATA_WIDTH': 24},
        'live_osd_0': {'C_BASEADDR': 0x43C00000, 'WIDTH': 1280,
                       'HEIGHT': 720, 'PIXEL_HZ': 75000000},
        'v_vid_in_axi4s_0': {'C_M_AXIS_TDATA_WIDTH': 24},
        'v_vid_snapshot': {'C_M_AXIS_TDATA_WIDTH': 24},
    }
    with zipfile.ZipFile(ROOT / 'hardware/ps_eye_auto.xsa') as z:
        hwh = ET.fromstring(z.read('system.hwh'))
    modules = {m.get('INSTANCE'): m for m in hwh.findall('.//MODULE')}
    for name, settings in expected.items():
        params = {p.get('NAME'): p.get('VALUE')
                  for p in modules[name].findall('./PARAMETERS/PARAMETER')}
        for key, value in settings.items():
            assert int(params[key], 0) == value, (name, key, params.get(key))
    header = (ROOT / 'bsp/include/xparameters.h').read_text()
    for name, value in {'XPAR_AXIVDMA_0_BASEADDR': 0x43000000,
                        'XPAR_AXIVDMA_1_BASEADDR': 0x43010000,
                        'XPAR_AXIVDMA_0_NUM_FSTORES': 3,
                        'XPAR_AXIVDMA_1_NUM_FSTORES': 2,
                        'XPAR_AXIVDMA_0_S2MM_GENLOCK_MODE': 2,
                        'XPAR_AXIVDMA_0_MM2S_GENLOCK_MODE': 3,
                        'XPAR_LIVE_OSD_0_BASEADDR': 0x43C00000}.items():
        m = re.search(r'^#define\s+' + name + r'\s+(\w+)', header, re.M)
        assert m and int(m[1].rstrip('UuLl'), 0) == value, name
    timing = (ROOT / 'report/timing_summary.txt').read_text()
    assert 'All user specified timing constraints are met.' in timing
    assert 'checking unconstrained_internal_endpoints (0)' in timing
    skew = (ROOT / 'report/bus_skew.txt').read_text()
    slacks = [float(x) for x in re.findall(r'Slack \(MET\) :\s+([0-9.]+)ns', skew)]
    assert slacks and 'VIOLATED' not in skew
    assert b'r8-live-osd' in (ROOT / 'build/ps_eye_auto.elf').read_bytes()
    make = (ROOT / 'build/Makefile').read_text()
    assert '$(SRC)/video_live.c' in make and '$(SRC)/video_io.c' not in make
    source_paths = [p for folder in ('src/app', 'hardware/source/rtl')
                    for p in (ROOT / folder).rglob('*') if p.is_file()]
    source_paths += [ROOT / f for f in (
        'hardware/source/live_osd_cdc.xdc', 'hardware/source/system.bd',
        'hardware/source/pin.xdc', 'build/Makefile', 'build/add_live_osd.tcl',
        'build/create_hardware.tcl', 'build/check_live_osd_timing.tcl',
        'build/implement_hardware.tcl', 'build/finalize_live_osd.tcl',
        'build/create_platform.tcl', 'bsp/include/xparameters.h')]
    report = {'version': 'r8-live-osd', 'board_tested': False,
              'recognition_baseline_files': len(baseline),
              'hwh_contract': expected, 'bus_skew_paths': len(slacks),
              'minimum_bus_skew_slack_ns': min(slacks),
              'cdc_review': 'Custom held-data handshake audited; raw CDC/methodology warnings retained. See live_osd_r8.md.',
              'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p)
                                for p in sorted(source_paths)},
              'artifact_sha256': {f: sha(ROOT / f) for f in (
                  'build/BOOT.BIN', 'build/ps_eye_auto.elf',
                  'hardware/ps_eye_auto.bit', 'hardware/ps_eye_auto.xsa',
                  'hardware/fsbl.elf', 'hardware/ps7_init.tcl', 'bsp/lib/libxil.a')}}
    (ROOT / 'report/live_osd_verification.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'PASS r8 HWH/BSP/boot/timing contract; {len(baseline)} recognition files unchanged')


if __name__ == '__main__':
    main()
