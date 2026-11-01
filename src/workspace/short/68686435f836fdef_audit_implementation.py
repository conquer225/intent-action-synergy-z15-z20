"""Distinguish successful routing from timing closure and production readiness."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    args = p.parse_args()
    out = Path(args.output).resolve()
    destination = out/'implementation_audit.json'
    if destination.exists():
        raise FileExistsError(destination)
    execution = json.loads((out/'execution_audit.json').read_text())
    if not execution['implementation_completed'] or not execution['source_unchanged']:
        raise ValueError('Implementation did not finish with unchanged input')
    for name, digest in execution['sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError('Execution input changed: '+name)
    summary = (out/'timing_summary.rpt').read_text()
    columns = ('wns_ns', 'tns_ns', 'setup_failing_endpoints', 'setup_total_endpoints',
               'whs_ns', 'ths_ns', 'hold_failing_endpoints', 'hold_total_endpoints',
               'wpws_ns', 'tpws_ns', 'pulse_failing_endpoints', 'pulse_total_endpoints')
    lines = summary.splitlines()
    index = next(i for i, s in enumerate(lines) if 'WNS(ns)' in s and 'WPWS(ns)' in s)
    values = lines[index+2].split()
    if len(values) != len(columns):
        raise ValueError('Unexpected timing report layout')
    timing = {k:(float(v) if k.endswith('_ns') else int(v)) for k, v in zip(columns, values)}
    route = (out/'route_status.rpt').read_text()
    def count(label):
        match = re.search(re.escape(label)+r'\.+\s*:\s*(\d+)', route)
        if not match:
            raise ValueError('Missing route status: '+label)
        return int(match[1])
    route_status = {k:count(v) for k, v in (
        ('routable', '# of routable nets'), ('fully_routed', '# of fully routed nets'),
        ('errors', '# of nets with routing errors'))}
    checks = {name:int(n) for name,n in re.findall(r'^\d+\. checking (\w+) \((\d+)\)',
                                                   (out/'check_timing.rpt').read_text(), re.M)}
    if not checks:
        raise ValueError('Missing timing constraint checks')
    def drc_rows(filename):
        return [dict(rule=m[0], severity=m[1].strip(), count=int(m[2])) for m in re.findall(
            r'^\|\s*([A-Z]+-\d+)\s*\|\s*([^|]+)\|[^|]+\|\s*(\d+)\s*\|',
            (out/filename).read_text(), re.M)]
    resources = {}
    for line in (out/'utilization.rpt').read_text().splitlines():
        cells = [s.strip() for s in line.split('|')[1:-1]]
        if cells and cells[0].rstrip('* ') in ('Slice LUTs', 'Slice Registers', 'DSPs', 'Block RAM Tile'):
            resources[cells[0].rstrip('* ')] = cells[1:]
    timing_met = (timing['wns_ns'] >= 0 and timing['whs_ns'] >= 0 and timing['wpws_ns'] >= 0
                  and all(timing[k] == 0 for k in ('setup_failing_endpoints',
                             'hold_failing_endpoints', 'pulse_failing_endpoints')))
    files = [out/'execution_audit.json', out/'routed.dcp', *sorted(out.glob('*.rpt')),
             out/'timing_metrics.txt', Path(str(out)+'.log'), Path(__file__).resolve()]
    result = dict(tool_version='2025.2', implementation_completed=True,
                  fully_routed=route_status['routable']==route_status['fully_routed'] and route_status['errors']==0,
                  route_status=route_status, timing=timing, timing_met=timing_met,
                  constraint_checks=checks, utilization_raw_rows=resources,
                  drc=drc_rows('drc.rpt'), methodology=drc_rows('methodology.rpt'),
                  bitstream_generated=bool(list(out.rglob('*.bit'))), board_modified=False,
                  approved_for_production=False,
                  scope='Post-route static analysis only; not DMA reset functional validation or measured acceleration',
                  sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    if result['bitstream_generated']:
        raise ValueError('Unauthorized bitstream found')
    destination.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='sha256'}, indent=2))


if __name__ == '__main__':
    main()
