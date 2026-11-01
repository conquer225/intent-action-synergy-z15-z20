"""Collect synthesis-only evidence; never claim routed timing or device speedup."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--build',required=True)
    p.add_argument('--simulation',required=True)
    args = p.parse_args()
    build, sim = Path(args.build).resolve(), Path(args.simulation).resolve()
    reports = build/'synthesis_reports'
    output = reports/'synthesis_audit.json'
    if output.exists():
        raise FileExistsError(output)
    bd_audit = json.loads((build/'bd_audit.json').read_text())
    if not bd_audit['passed'] or '2025.2' not in bd_audit['tool_version']:
        raise ValueError('Passed 2025.2 BD validation required')
    reset_report = build/'reset_regression/reset_audit.json'
    reset_audit = json.loads(reset_report.read_text())
    if not reset_audit['passed'] or reset_audit['tool_version'] != '2025.2':
        raise ValueError('Generated reset IP regression must pass')
    for file, digest in reset_audit['sha256'].items():
        if hashlib.sha256(Path(file).read_bytes()).hexdigest() != digest:
            raise ValueError('Reset evidence changed: '+file)
    contract = json.loads((build/'contract_after_synth.json').read_text())
    if not contract['passed']:
        raise ValueError('Post-synthesis BD contract failed')
    for file, digest in contract['sha256'].items():
        if hashlib.sha256(Path(file).read_bytes()).hexdigest() != digest:
            raise ValueError('Contract evidence changed: '+file)
    for name in ('axis_audit.json','control_audit.json'):
        audit = json.loads((sim/name).read_text())
        if not audit['passed']:
            raise ValueError('Simulation failed')
        for file,digest in audit['sha256'].items():
            if hashlib.sha256(Path(file).read_bytes()).hexdigest()!=digest:
                raise ValueError('Source changed since simulation: '+file)
    log = (build/'synthesis.log').read_text(errors='replace')
    runlog = build/'project/pl_filter_candidate_dma.runs/synth_1/runme.log'
    synthlog = runlog.read_text(errors='replace')
    if 'PRIMARY_FILTER_SYNTHESIS_ONLY_COMPLETE' not in log or re.search(r'^ERROR:',log+synthlog,re.M):
        raise ValueError('Synthesis/report generation not complete or has errors')
    metrics = (reports/'timing_metrics.txt').read_text()
    if 'tool_version=2025.2' not in metrics:
        raise ValueError('Wrong report version')
    slacks = [float(x) for x in re.findall(r'^SLACK=([-\d.]+)$',metrics,re.M)]
    if not slacks:
        raise ValueError('Missing constrained setup paths')
    resource_rows = {}
    wanted = ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs')
    for line in (reports/'utilization.rpt').read_text().splitlines():
        cells = [s.strip() for s in line.split('|')[1:-1]]
        if cells and cells[0].rstrip('* ') in wanted:
            # Retain the raw row alongside named values so the original report remains authoritative.
            resource_rows[cells[0].rstrip('* ')] = cells[1:]
    bits = list(build.rglob('*.bit'))
    impl_logs = list((build/'project').glob('*.runs/impl_*/runme.log'))
    if bits or impl_logs:
        raise ValueError('Scope violation: bitstream or implementation run found')
    files = [build/'bd_audit.json',build/'contract_audit.json',build/'contract_after_synth.json',
             reset_report,build/'synthesis.log',runlog,
             sim/'axis_audit.json',sim/'control_audit.json',HERE/'synthesize_candidate.tcl',
             HERE/'audit_synthesis.py',*sorted(reports.glob('*.rpt')),*sorted(reports.glob('*.txt')),
             *sorted((build/'project').glob('*.runs/synth_1/*.dcp'))]
    result = dict(synthesis_completed=True,tool_version='2025.2',part='xc7z015clg485-2',
                  scope='Global candidate post-synthesis estimates, not placement/routing or hardware measurements',
                  worst_reported_setup_slack_ns=min(slacks),setup_estimate_met=min(slacks)>=0,
                  utilization_raw_rows=resource_rows,
                  critical_warnings=[s for s in (log+synthlog).splitlines() if s.startswith('CRITICAL WARNING:')],
                  implementation_run=False,bitstream_generated=False,board_programmed=False,
                  approved_for_production=False,
                  reset_regression_passed=True,
                  sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='sha256'},indent=2))


if __name__=='__main__':
    main()
