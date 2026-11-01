"""Bind the isolated simulation, full synthesis and route outputs before report audit."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--simulation', required=True)
    parser.add_argument('--build', required=True)
    parser.add_argument('--route', required=True)
    args = parser.parse_args()
    sim, build, route = (Path(s).resolve() for s in
                         (args.simulation, args.build, args.route))
    destination = route/'execution_audit.json'
    if destination.exists():
        raise FileExistsError(destination)
    sim_audit_file = sim/'simulation_audit.json'
    sim_audit = json.loads(sim_audit_file.read_text())
    if not sim_audit['passed'] or sim_audit['tool_version'] != '2025.2':
        raise ValueError('Pipelined RTL simulation did not pass')
    for name, digest in sim_audit['sha256'].items():
        if sha(Path(name)) != digest:
            raise ValueError('Golden vector/RTL source changed after simulation: '+name)
    project = build/'project/pl_filter_candidate_dma.xpr'
    xpr = project.read_text()
    if (str(project).replace('\\','/') not in xpr or
            '../../../pl_filter_pipeline_candidate/primary_sos_core.sv' not in xpr or
            '../../../pl_filter_candidate/primary_sos_core.sv' in xpr):
        raise ValueError('Project does not reference only the pipelined core')
    bd_name = 'project/pl_filter_candidate_dma.srcs/sources_1/bd/filter_candidate/filter_candidate.bd'
    old_bd = ROOT/'output/pl_dma_reset_fixed_v2025_2_20260927'/bd_name
    new_bd = build/bd_name
    if sha(old_bd) != sha(new_bd):
        raise ValueError('Copied PS/DMA/reset block design differs from baseline')
    synth_log = (build/'synthesis.log').read_text(errors='replace')
    route_log = Path(str(route)+'.log').read_text(errors='replace')
    if ('PRIMARY_PIPELINE_SYNTHESIS_ONLY_COMPLETE' not in synth_log or
            'PRIMARY_PIPELINE_ROUTE_ONLY_COMPLETE' not in route_log or
            "synth_design Complete!" not in
            (build/'synthesis_reports/run_status.txt').read_text()):
        raise ValueError('Synthesis or implementation incomplete')
    if ('A full resynthesis will be run' not in synth_log or
            str(HERE/'primary_sos_core.sv').replace('\\','/') not in synth_log):
        raise ValueError('Cannot confirm full synthesis of the isolated core')
    if any(line.startswith(('ERROR:', 'CRITICAL WARNING:')) for log in
           (synth_log, route_log) for line in log.splitlines()):
        raise ValueError('Tool error or critical warning in execution logs')
    if list(build.rglob('*.bit')) or list(route.rglob('*.bit')):
        raise ValueError('Unexpected bitstream in candidate')
    sources = [sim_audit_file, project, old_bd, new_bd,
               build/'project/pl_filter_candidate_dma.runs/synth_1/filter_candidate_wrapper.dcp',
               HERE/'primary_sos_core.sv', HERE/'synthesize_candidate.tcl',
               HERE/'implement_candidate.tcl', Path(__file__).resolve(),
               build/'synthesis.log', *sorted((build/'synthesis_reports').glob('*.rpt'))]
    evidence = {'implementation_completed':True, 'returncode':0,
                'tool_version':'2025.2', 'source_unchanged':True,
                'bitstream_generated':False, 'board_modified':False,
                'sha256':{str(path):sha(path) for path in sources},
                'scope':'Isolated pipelined candidate; no bitstream, board test or production approval'}
    destination.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print('Pipelined candidate execution evidence bound')


if __name__ == '__main__':
    main()
