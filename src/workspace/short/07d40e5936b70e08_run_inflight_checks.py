"""Audit vendor-IP warnings and test filter/adapter reset boundaries offline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'pl_filter_candidate'
ROOT = HERE.parents[1]
sys.path.insert(0, str(BASE))
from reset_contract import reset_failures, reset_parameters


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--build', required=True)
    parser.add_argument('--route', required=True)
    parser.add_argument('--simulation', required=True)
    parser.add_argument('--vivado-bin', required=True)
    args = parser.parse_args()
    out, build, route, simulation = (Path(value).resolve() for value in
                                      (args.output,args.build,args.route,args.simulation))
    if out.exists():
        raise FileExistsError(out)
    passed_sim = json.loads((simulation/'simulation_audit.json').read_text())
    if not passed_sim['passed'] or any(sha(Path(path)) != digest for path,digest in
                                     passed_sim['sha256'].items()):
        raise ValueError('Baseline pipelined simulation evidence changed')
    bd = build/'project/pl_filter_candidate_dma.srcs/sources_1/bd/filter_candidate/filter_candidate.bd'
    wrapper = build/'project/pl_filter_candidate_dma.gen/sources_1/bd/filter_candidate/ip/filter_candidate_pf_shell_reset_0/synth/filter_candidate_pf_shell_reset_0.vhd'
    reference = HERE.parent/'output/pl_dma_reset_fixed_v2025_2_20260927'
    reference_bd = reference/'project/pl_filter_candidate_dma.srcs/sources_1/bd/filter_candidate/filter_candidate.bd'
    reference_wrapper = reference/'project/pl_filter_candidate_dma.gen/sources_1/bd/filter_candidate/ip/filter_candidate_pf_shell_reset_0/synth/filter_candidate_pf_shell_reset_0.vhd'
    if sha(bd) != sha(reference_bd) or sha(wrapper) != sha(reference_wrapper):
        raise ValueError('PS/DMA/reset BD or generated reset wrapper changed')
    params = reset_parameters(wrapper.read_text())
    failures = reset_failures(json.loads(bd.read_text())['design'], params)
    if failures:
        raise ValueError(failures)
    drc = (route/'drc.rpt').read_text()
    method = (route/'methodology.rpt').read_text()
    checks = re.findall(r'^(REQP-(?:1839|1840))#\d+ Warning\n(.+?)(?=^Related violations:)',
                        drc, re.M|re.S)
    if len(checks) != 12 or any('/GEN_MM2S_FULL.' not in detail or
                                '/I_DATA_FIFO/' not in detail or
                                '/pf_memory/s00_couplers/' not in detail or
                                'empty_fwft_i_reg' not in detail for _,detail in checks):
        raise ValueError('BRAM asynchronous-control warning pattern changed')
    if len(re.findall(r'^LUTAR-1#\d+ Warning', method, re.M)) != 3:
        raise ValueError('FIFO asynchronous-reset warning pattern changed')
    out.mkdir(parents=True)
    for name in ('vectors.txt','coeff.hex'):
        shutil.copy2(simulation/name, out/name)
    sources = [HERE/'primary_sos_core.sv', BASE/'primary_sos_axis.sv',
               BASE/'primary_filter_top.sv', HERE/'inflight_stream_reset_tb.sv']
    commands = [('xvlog.bat',['--sv', *map(str,sources)]),
                ('xelab.bat',['inflight_stream_reset_tb','-s','inflight_stream_reset_sim']),
                ('xsim.bat',['inflight_stream_reset_sim','-runall'])]
    logs = []
    for tool, args_ in commands:
        result = subprocess.run([str(Path(args.vivado_bin)/tool), *args_],
                                cwd=out, text=True, capture_output=True, timeout=300)
        output = result.stdout+result.stderr
        log_path = out/(tool+'.log')
        log_path.write_text(output, encoding='utf-8')
        logs.append(log_path)
        if result.returncode or 'ERROR:' in output or 'Fatal:' in output:
            raise RuntimeError(tool+' failed; see '+str(log_path))
    marker = 'INFLIGHT_STREAM_RESET_PASS soft=1 external=1 partial_words=12 recovered_words=160 stale=0'
    if marker not in output:
        raise ValueError('In-flight stream reset/recovery was not completed')
    tests = [('original',BASE,'test_primary_filter_dma.py',11),
             ('inflight',HERE,'test_dma_inflight_reset.py',3)]
    for label, directory, pattern, count in tests:
        result = subprocess.run([sys.executable,'-m','unittest','discover','-s',
                                 str(directory),'-p',pattern,'-v'],
                                cwd=ROOT, text=True, capture_output=True, timeout=120)
        text = result.stdout+result.stderr
        log_path = out/(label+'_unittest.log')
        log_path.write_text(text, encoding='utf-8')
        logs.append(log_path)
        if result.returncode or f'Ran {count} tests' not in text or '\nOK' not in text:
            raise RuntimeError(label+' adapter tests failed')
    files = [bd,wrapper,reference_bd,reference_wrapper,route/'drc.rpt',
             route/'methodology.rpt',simulation/'simulation_audit.json',
             out/'vectors.txt',out/'coeff.hex',BASE/'reset_contract.py', BASE/'primary_filter_dma.py',
             BASE/'test_primary_filter_dma.py',HERE/'test_dma_inflight_reset.py',
             Path(__file__).resolve(),*sources,*logs]
    audit = {'passed':True,'tool_version':'2025.2','part':'xc7z015clg485-2',
             'vendor_warning_counts':{'REQP-1839':8,'REQP-1840':4,'LUTAR-1':3},
             'software_tests':14,'filter_stream_reset_scenarios':2,
             'filter_stream_recovered_words':160,
             'limitations':['No AXI DMA or interconnect vendor RTL in the new stream test',
                            'No actual AXI memory transactions or board reset',
                            'DRC warnings remain; no waiver or production approval'],
             'sha256':{str(f):sha(f) for f in dict.fromkeys(files)}}
    (out/'audit.json').write_text(json.dumps(audit,indent=2), encoding='utf-8')
    print('INFLIGHT_AUDIT_PASS software=14 stream_scenarios=2 bram_warnings=12 lut_reset_warnings=3')


if __name__ == '__main__':
    main()
