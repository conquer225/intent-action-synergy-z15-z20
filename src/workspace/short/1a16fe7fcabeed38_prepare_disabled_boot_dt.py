"""Append a disabled candidate node to a local live-DT snapshot, never to Z15."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

HERE = Path(__file__).resolve().parent
NODE = '/amba/dma-owner@40400000'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path, required=True)
    args = p.parse_args()
    live = args.snapshot / 'live_dt'
    for prop in ('#address-cells', '#size-cells'):
        if struct.unpack('>I', (live / 'amba' / prop).read_bytes())[0] != 1:
            raise ValueError('Template requires amba address/size cells = 1')
    source = args.snapshot / 'candidate_disabled_boot.dts'
    base = subprocess.run(['dtc', '-I', 'fs', '-O', 'dts', str(live)],
                          capture_output=True, text=True, check=True)
    source.write_text(base.stdout + '\n&{/amba} {\n' +
                      (HERE / 'candidate_static_node.dtsi').read_text() + '\n};\n')
    dtb = args.snapshot / 'candidate_disabled_boot.dtb'
    compiled = subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(dtb), str(source)],
                              capture_output=True, text=True, check=True)
    (args.snapshot / 'dtc_snapshot_warnings.log').write_text(base.stderr + compiled.stderr)
    status = subprocess.check_output(['fdtget', str(dtb), NODE, 'status'], text=True).strip()
    reg = subprocess.check_output(['fdtget', '-t', 'x', str(dtb), NODE, 'reg'], text=True).strip()
    compatible = subprocess.check_output(['fdtget', str(dtb), NODE, 'compatible'], text=True).strip()
    if status != 'disabled' or reg != '40400000 10000 41200000 10000' or compatible != 'guardianloop,z15-filter-dma-owner-v1':
        raise ValueError('Disabled boot DT contract mismatch')
    print(json.dumps({'status': 'LOCAL_DISABLED_DT_SYNTAX_PASS',
                      'candidate_status': status, 'reg': reg,
                      'scope': 'syntax fixture only, not an approved boot image',
                      'warnings_logged': bool(base.stderr or compiled.stderr)}))


if __name__ == '__main__':
    main()
