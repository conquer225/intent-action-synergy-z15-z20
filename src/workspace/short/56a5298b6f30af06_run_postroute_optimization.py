"""Optimize a verified routed candidate, preserving its failing baseline."""
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
    p.add_argument('--baseline', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--vivado-bin', required=True)
    args = p.parse_args()
    baseline, out = Path(args.baseline).resolve(), Path(args.output).resolve()
    if out.exists():
        raise FileExistsError(out)
    audit_file = baseline/'implementation_audit.json'
    audit = json.loads(audit_file.read_text())
    if not audit['fully_routed'] or audit['tool_version'] != '2025.2':
        raise ValueError('Require a fully routed Vivado 2025.2 baseline')
    for name, digest in audit['sha256'].items():
        if sha(Path(name)) != digest:
            raise ValueError('Baseline evidence changed: '+name)
    dcp = baseline/'routed.dcp'
    script = HERE/'optimize_routed_candidate.tcl'
    sources = {str(f):sha(f) for f in (dcp, script, audit_file, Path(__file__).resolve())}
    command = [str(Path(args.vivado_bin)/'vivado.bat'), '-mode', 'batch', '-source', str(script),
               '-log', str(out)+'.log', '-journal', str(out)+'.jou', '-tclargs', str(dcp), str(out)]
    result = subprocess.run(command, cwd=out.parent, timeout=1800)
    if not out.exists():
        raise RuntimeError('No output; see adjacent execution log')
    log = Path(str(out)+'.log').read_text(errors='replace')
    completed = result.returncode == 0 and 'PRIMARY_FILTER_POST_ROUTE_OPT_COMPLETE' in log
    unchanged = all(sha(Path(f)) == digest for f, digest in sources.items())
    bits = list(out.rglob('*.bit'))
    evidence = dict(implementation_completed=completed, returncode=result.returncode,
                    tool_version='2025.2', source_unchanged=unchanged,
                    bitstream_generated=bool(bits), board_modified=False, sha256=sources,
                    scope='Post-route optimization execution only; separate timing/DRC audit required')
    (out/'execution_audit.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    if not completed or not unchanged or bits:
        raise RuntimeError('Optimization incomplete or input/scope check failed')


if __name__ == '__main__':
    main()
