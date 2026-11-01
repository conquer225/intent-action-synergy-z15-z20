"""Verify source evidence and implement a saved candidate, never create a bitstream."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--build', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--vivado-bin', required=True)
    args = p.parse_args()
    build, out = Path(args.build).resolve(), Path(args.output).resolve()
    if out.exists():
        raise FileExistsError(out)
    audit_path = build/'synthesis_reports/synthesis_audit.json'
    audit = json.loads(audit_path.read_text())
    if not (audit['synthesis_completed'] and audit['reset_regression_passed']
            and audit['tool_version'] == '2025.2' and not audit['critical_warnings']):
        raise ValueError('Require successful 2025.2 synthesis and reset regression')
    for evidence in (audit, json.loads((build/'reset_regression/reset_audit.json').read_text()),
                     json.loads((build/'contract_after_synth.json').read_text())):
        for name, digest in evidence['sha256'].items():
            if sha(Path(name)) != digest:
                raise ValueError('Evidence changed: '+name)
    dcp = build/'project/pl_filter_candidate_dma.runs/synth_1/filter_candidate_wrapper.dcp'
    script = HERE/'implement_candidate.tcl'
    sources = {str(f):sha(f) for f in (dcp, script, Path(__file__).resolve(), audit_path)}
    command = [str(Path(args.vivado_bin)/'vivado.bat'), '-mode', 'batch', '-source', str(script),
               '-log', str(out)+'.log', '-journal', str(out)+'.jou', '-tclargs', str(dcp), str(out)]
    result = subprocess.run(command, cwd=out.parent, timeout=1800)
    if not out.exists():
        raise RuntimeError('Implementation did not create output; see adjacent log')
    log = Path(str(out)+'.log').read_text(errors='replace')
    unchanged = all(sha(Path(f)) == digest for f, digest in sources.items())
    bits = list(out.rglob('*.bit'))
    completed = result.returncode == 0 and 'PRIMARY_FILTER_ROUTE_ONLY_COMPLETE' in log
    data = dict(implementation_completed=completed, returncode=result.returncode,
                tool_version='2025.2', source_unchanged=unchanged, bitstream_generated=bool(bits),
                board_modified=False, sha256=sources,
                scope='Execution/provenance only; timing and DRC require report review')
    (out/'execution_audit.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    if not completed or not unchanged or bits:
        raise RuntimeError('Implementation incomplete or evidence/scope check failed')


if __name__ == '__main__':
    main()
