"""Run only xvlog/xelab/xsim; this never invokes synthesis or board tools."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    p.add_argument('--vivado-bin', required=True)
    p.add_argument('--suite', choices=('core','axis','control'), default='core')
    p.add_argument('--audit-tag', default='', help='Separate evidence name for an extended test')
    args = p.parse_args()
    out = Path(args.output).resolve()
    if args.audit_tag and not re.fullmatch('[a-z0-9_-]+',args.audit_tag):
        raise ValueError('Use a simple alphanumeric audit tag')
    suffix = '_'+args.audit_tag if args.audit_tag else ''
    destination = out/(('rtl' if args.suite=='core' else args.suite)+suffix+'_audit.json')
    if destination.exists():
        raise FileExistsError(destination)
    numerical = json.loads((out/'numerical.json').read_text())
    protocol = numerical['protocol']
    if not numerical['passed'] or (protocol['data_bits'],protocol['input_fraction_bits'],
                                  protocol['coeff_bits'],protocol['coeff_fraction_bits']) != (40,16,34,31):
        raise ValueError('RTL requires the passed 40/16 data, 34/31 coefficient contract')
    sources = [HERE/'primary_sos_core.sv',HERE/'primary_sos_tb.sv']
    expected_words = numerical['rtl_vector_words']
    top = 'primary_sos_tb'
    if args.suite == 'axis':
        groups = []
        for line in (out/'vectors.txt').read_text().splitlines():
            if line.startswith('1 '):
                groups.append([])
            groups[-1].append(line)
        if len(groups) != 9:
            raise ValueError('Expected 8 normal cases plus saturation stress')
        # Complete 80-word frames only; overflow/fail-closed is separate from bit parity.
        lines = [line for group in groups[:8] for line in group[:len(group)//80*80]]
        (out/'axis_vectors.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
        expected_words = len(lines)
        sources = [HERE/'primary_sos_core.sv',HERE/'primary_sos_axis.sv',HERE/'primary_sos_axis_tb.sv']
        top = 'primary_sos_axis_tb'
    if args.suite == 'control':
        sources = [HERE/name for name in ('primary_sos_core.sv','primary_sos_axis.sv',
                                         'primary_filter_top.sv','primary_filter_top_tb.sv')]
        top = 'primary_filter_top_tb'
        expected_words = 160
    snapshot = top+'_sim'
    commands = [('xvlog.bat',['--sv',*map(str,sources)]),
                ('xelab.bat',[top,'-s',snapshot]),
                ('xsim.bat',[snapshot,'-runall'])]
    for name, arguments in commands:
        result = subprocess.run([str(Path(args.vivado_bin)/name),*arguments],cwd=out,
                                capture_output=True,text=True,timeout=120)
        text = result.stdout+result.stderr
        (out/(args.suite+suffix+'_'+name+'.stdout.log')).write_text(text,encoding='utf-8')
        print(text,flush=True)
        if result.returncode or 'ERROR:' in text or 'Fatal:' in text:
            raise RuntimeError(name+' failed; see log')
    patterns = {
        'core':r'RTL_PASS words=(\d+) max_processing_cycles=(\d+) reset_abort=PASS backpressure=PASS saturation=PASS',
        'axis':r'AXIS_PASS words=(\d+) frames=(\d+) malformed=4 reset_abort=PASS backpressure=PASS overflow=PASS',
        'control':r'CONTROL_PASS words=(\d+) frames=(\d+) reset_abort=PASS fault_status=PASS recovery=PASS'}
    pattern = patterns[args.suite]
    match = re.search(pattern,text)
    if not match or int(match[1]) != expected_words:
        raise RuntimeError('Missing or incomplete bit-exact RTL PASS')
    files = [HERE/'fixed_sos.py',HERE/'validate_fixed.py',*sources,
             out/'coeff.hex',out/'vectors.txt',out/'sos_float.npy',out/'numerical.json']
    if args.suite=='axis':
        files.append(out/'axis_vectors.txt')
    audit = dict(passed=True,suite=args.suite,words=int(match[1]),
                 scope='RTL functional simulation only; no synthesis/resources/timing/DMA/inference guarantee',
                 sha256={str(path):sha(path) for path in files})
    audit['processing_cycles' if args.suite=='core' else 'frames'] = int(match[2])
    destination.write_text(json.dumps(audit,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
