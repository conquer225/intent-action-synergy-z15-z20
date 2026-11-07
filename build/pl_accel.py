"""Build either PL extension into a short external workspace with Vitis HLS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', choices=('eeg', 'map'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tool', default=os.environ.get('VITIS_HLS', 'vitis_hls'))
    parser.add_argument('--cosim', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root/'src/workspace/integrations/pl_accel/hls'
    output = args.output.resolve()
    if output.is_relative_to(root) or any(ord(c) > 127 for c in str(output)):
        raise ValueError('build output must be an external ASCII path')
    if (output/'build.tcl').exists():
        raise ValueError('choose a fresh build directory to preserve existing evidence')
    output.mkdir(parents=True, exist_ok=True)
    files = [source/(args.kernel+'.cpp'), source/(args.kernel+'_tb.cpp'), source/(args.kernel+'_vectors.h')]
    if args.kernel == 'eeg':
        files.append(source/'log_table.h')
    for path in files:
        shutil.copyfile(path, output/path.name)
    top, part = ('z15_fbcsp', 'xc7z015clg485-2') if args.kernel == 'eeg' else ('z20_map', 'xc7z020clg400-2')
    tcl = ['open_project -reset kernel', 'set_top '+top,
           'add_files '+args.kernel+'.cpp', 'add_files -tb '+args.kernel+'_tb.cpp',
           'open_solution -reset solution -flow_target vivado', 'set_part '+part,
           'create_clock -period 10 -name default', 'config_compile -pipeline_loops 0',
           'csim_design', 'csynth_design']
    if args.cosim:
        tcl += ['cosim_design -rtl verilog -trace_level none']
    tcl += ['export_design -format ip_catalog -rtl verilog', 'exit']
    (output/'build.tcl').write_text('\n'.join(tcl)+'\n', encoding='ascii')
    identity = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (output/'identity.json').write_text(json.dumps(dict(top=top, part=part, clock_ns=10,
         source_sha256=identity), indent=2)+'\n', encoding='utf-8')
    environment = os.environ.copy()
    if os.name == 'nt':
        # Some automation hosts omit this standard Windows loader variable.
        environment.setdefault('PROCESSOR_ARCHITECTURE', 'AMD64')
    with (output/'build.log').open('w', encoding='utf-8') as log:
        run = subprocess.run([args.tool, '-f', 'build.tcl'], cwd=output, stdout=log,
                             stderr=subprocess.STDOUT, env=environment)
    report = output/'kernel/solution/syn/report'/ (top+'_csynth.xml')
    log_text = (output/'build.log').read_text(encoding='utf-8', errors='replace')
    packages = list((output/'kernel/solution/impl/ip').glob('*.zip'))
    if (run.returncode or not report.is_file() or 'ERROR:' in log_text or not packages
            or (args.cosim and 'co-simulation finished: PASS' not in log_text)):
        print(log_text[-10000:])
        print('HLS result:', run.returncode, 'synthesis report:', report.is_file())
        return run.returncode or 1
    tree = ET.parse(report)
    resources = tree.find('.//AreaEstimates/Resources')
    available = tree.find('.//AreaEstimates/AvailableResources')
    for field in ('LUT', 'FF', 'DSP', 'BRAM_18K'):
        if int(resources.findtext(field)) > int(available.findtext(field)):
            raise ValueError('kernel exceeds target capacity: '+field)
    result = dict(top=top, part=part, source_sha256=identity, cosim=args.cosim,
                  resources={e.tag: e.text for e in resources}, report=str(report))
    (output/'summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
