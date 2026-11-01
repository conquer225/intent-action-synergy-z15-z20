"""Run the isolated pipelined RTL against the previously audited golden vectors."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'pl_filter_candidate'
GOLDEN = HERE.parent / 'output/pl_primary_filter_q31_20260927'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--vivado-bin', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    if out.exists():
        raise FileExistsError(out)
    old = json.loads((GOLDEN/'axis_overflow_audit.json').read_text())
    if not old['passed'] or any(sha(Path(path)) != digest for path, digest in old['sha256'].items()):
        raise ValueError('Previous numerical/AXIS golden evidence is incomplete or changed')
    out.mkdir(parents=True)
    for name in ('coeff.hex', 'vectors.txt', 'axis_vectors.txt'):
        shutil.copy2(GOLDEN/name, out/name)
    suites = {
        'core': ([HERE/'primary_sos_core.sv', HERE/'primary_sos_tb.sv'],
                 'primary_sos_tb', r'RTL_PASS words=(\d+) max_processing_cycles=(\d+)'),
        'axis': ([HERE/'primary_sos_core.sv', BASE/'primary_sos_axis.sv',
                  HERE/'primary_sos_axis_tb.sv'], 'primary_sos_axis_tb',
                 r'AXIS_PASS words=(\d+) frames=(\d+)'),
        'control': ([HERE/'primary_sos_core.sv', BASE/'primary_sos_axis.sv',
                     BASE/'primary_filter_top.sv', HERE/'primary_filter_top_tb.sv'],
                    'primary_filter_top_tb', r'CONTROL_PASS words=(\d+) frames=(\d+)')}
    results = {}
    sources = [Path(__file__).resolve(), GOLDEN/'axis_overflow_audit.json',
               *(out/name for name in ('coeff.hex','vectors.txt','axis_vectors.txt'))]
    for name, (rtl, top, pattern) in suites.items():
        sources.extend(rtl)
        commands = [('xvlog.bat', ['--sv', *map(str, rtl)]),
                    ('xelab.bat', [top, '-s', name+'_pipeline_sim']),
                    ('xsim.bat', [name+'_pipeline_sim', '-runall'])]
        for tool, parameters in commands:
            result = subprocess.run([str(Path(args.vivado_bin)/tool), *parameters],
                                    cwd=out, capture_output=True, text=True, timeout=600)
            output = result.stdout + result.stderr
            (out/f'{name}_{tool}.log').write_text(output, encoding='utf-8')
            if result.returncode or 'ERROR:' in output or 'Fatal:' in output:
                raise RuntimeError(f'{name} {tool} failed; see saved log')
        match = re.search(pattern, output)
        expected = {'core':81728, 'axis':81120, 'control':160}[name]
        if not match or int(match[1]) != expected:
            raise RuntimeError(f'{name} did not complete its full golden-vector suite')
        results[name] = {'words':int(match[1]), 'cycles_or_frames':int(match[2])}
        print(f'{name}: {results[name]}', flush=True)
    audit = {'passed':True, 'tool_version':'2025.2', 'results':results,
             'scope':'Bit-exact RTL functional simulation, including reset/overflow/backpressure; no timing claim',
             'sha256':{str(path):sha(path) for path in dict.fromkeys(sources)}}
    (out/'simulation_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
