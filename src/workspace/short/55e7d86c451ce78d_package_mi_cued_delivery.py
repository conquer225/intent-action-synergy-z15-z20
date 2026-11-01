"""Freeze a PC-only functional MI package after numerical and regression checks."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'pynq_guardianloop'
APP_FILES = ('mi_cued.py', 'mi_cued.html', 'mi_cued_server.py', 'mi_cued_replay.py',
             'mi_eegnet_portable.py', 'cyton_sqi.py', 'mi_features.py',
             'test_mi_cued.py', 'test_mi_cued_replay.py', 'test_mi_eegnet_portable.py',
             'test_mi_cued_browser.cjs')
TESTS = ('test_mi_cued', 'test_mi_cued_replay', 'test_mi_eegnet_portable',
         'test_mi_candidate', 'test_ssvep_cued', 'test_seed_shadow_web',
         'test_guardianloop_startup')


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'eeg_apps_z15/output/mi_cued_delivery_20261002_final')
    parser.add_argument('--archive', type=Path, default=ROOT.parent/'handoff/GuardianLoop_MI_CUED_EXPERIMENTAL_20261002.zip')
    parser.add_argument('--node', type=Path, default=Path('C:/Program Files/nodejs/node.exe'))
    args = parser.parse_args()
    out = args.output.resolve()
    if args.archive.exists() or (out/'delivery_checks.json').exists():
        raise FileExistsError('Refuse to overwrite a frozen delivery')
    lock = json.loads((out/'lock.json').read_text(encoding='utf-8'))
    for path, expected in lock['source_sha256'].items():
        if digest(path) != expected or digest(out/'code_snapshot'/Path(path).name) != expected:
            raise ValueError('Frozen source mismatch: '+path)
    for path, expected in lock['input_sha256'].items():
        if digest(path) != expected:
            raise ValueError('Original input changed: '+path)
    accepted = json.loads((out/'acceptance.json').read_text(encoding='utf-8'))
    numerical = json.loads((out/'numerical.json').read_text(encoding='utf-8'))
    if (accepted['passed'] is not True or accepted['numerical_windows'] != 6080
            or accepted['classes_exact'] is not True
            or accepted['max_logit_error'] > lock['logit_atol']
            or any(accepted[key] is not False for key in
                   ('new_accuracy_result','new_training','arm_exported','board_accessed',
                    'production_eligible','control_enabled'))):
        raise ValueError('Numerical or eligibility check failed')
    model = out/'experimental_eegnet.npz'
    if digest(model) != accepted['experimental_artifact_sha256']:
        raise ValueError('Experimental artifact changed')
    with np.load(model, allow_pickle=False) as data:
        metadata = json.loads(str(data['metadata'].item()))
    if any(metadata[key] is not False for key in
           ('promotion_gate_passed','production_eligible','control_enabled')):
        raise ValueError('Experimental flags changed')

    env = dict(os.environ, PYTHONUTF8='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    commands = [(sys.executable, '-X','utf8','-m','unittest',*TESTS),
                (str(args.node), 'test_mi_cued_browser.cjs','mi_cued.html')]
    logs = ('unit_regression.log', 'browser_unit.log')
    test_runs = []
    for command, log in zip(commands, logs):
        run = subprocess.run(command, cwd=RUNTIME, env=env, capture_output=True, text=True, encoding='utf-8')
        output = run.stdout+run.stderr
        (out/log).write_text(output, encoding='utf-8')
        test_runs.append(dict(command=list(command), exit_code=run.returncode, log=log))
        if run.returncode:
            dump(out/'delivery_failure.json',dict(test_runs=test_runs))
            raise RuntimeError('Regression failed; see '+log)
    count = re.search(r'Ran (\d+) tests', (out/logs[0]).read_text(encoding='utf-8'))
    if count is None or int(count[1]) != 50:
        raise ValueError('Unexpected regression coverage')

    rows = [json.loads(line) for line in (out/'browser_replay.jsonl').read_text(encoding='utf-8').splitlines()]
    if not all(row['source']=='replay' and row['control_enabled'] is False for row in rows):
        raise ValueError('Browser replay mislabeled')
    targets = {row['trial_id']:row['target'] for row in rows if row['event']=='trial_start'}
    candidates = [row for row in rows if row['event']=='candidate']
    if ({targets[row['trial_id']] for row in candidates} != {'left','right'}
            or any(targets[row['trial_id']]=='rest' for row in candidates)
            or not any(row['event']=='withdraw' and row['reason']=='user_stopped' for row in rows)):
        raise ValueError('Incomplete manual browser coverage')

    checks = dict(passed=True, completed_at_local=datetime.now().isoformat(),
                  source_and_inputs_unchanged=True, regression_tests=50, test_runs=test_runs,
                  numerical_windows=6080, classes_exact=True,
                  max_logit_error=accepted['max_logit_error'],
                  manual_browser_candidates=len(candidates), rest_inference_calls=0,
                  board_accessed=False, arm_exported=False, production_eligible=False,
                  control_enabled=False, new_accuracy_result=False,
                  accuracy_promotion_gate_passed=False)
    dump(out/'delivery_checks.json',checks)

    files = { 'app/'+name: RUNTIME/name for name in APP_FILES }
    files['models/experimental_eegnet.npz'] = model
    files['recordings/bench_input.npz'] = ROOT/'eeg_apps_z15/output/accepted_bench_load_20260927/bench_input.npz'
    files['README.md'] = ROOT/'eeg_apps_z15/MI_CUED_CANDIDATE_README.md'
    files['MI_CUED_DELIVERY_PLAN.md'] = ROOT/'eeg_apps_z15/MI_CUED_DELIVERY_PLAN.md'
    for name in ('RESULTS.md','RUN_STATUS.md','acceptance.json','numerical.json',
                 'pc_inference_timing.json','delivery_checks.json',*logs,'browser_replay.jsonl',
                 'browser_left.png','browser_right.png','browser_rest.png'):
        files['evidence/'+name] = out/name
    manifest = dict(schema='mi-cued-experimental-package-v1',
                    status='PC_verified_only_not_ARM_deployed', channels=metadata['channels'],
                    model_choice=lock['model_choice'], production_eligible=False, control_enabled=False,
                    promotion_gate_passed=False, python=sys.version,
                    numpy=np.__version__, scipy=scipy.__version__,
                    runtime_dependencies=['numpy','scipy'], default_host='127.0.0.1',
                    source_model_sha256=lock['input_sha256'],
                    files={name:dict(sha256=digest(path),bytes=path.stat().st_size) for name,path in files.items()})
    dump(out/'MANIFEST.json',manifest)
    args.archive.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(args.archive,'x',ZIP_DEFLATED) as archive:
        for name,path in files.items():
            archive.write(path,name)
        archive.write(out/'MANIFEST.json','MANIFEST.json')
    with ZipFile(args.archive) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC failure')
        for name,expected in manifest['files'].items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=expected['sha256']:
                raise ValueError('ZIP file mismatch: '+name)
    for path,expected in lock['input_sha256'].items():
        if digest(path)!=expected:
            raise ValueError('Input changed during packaging: '+path)
    dump(out/'archive.json',dict(path=str(args.archive.resolve()),sha256=digest(args.archive),
                                bytes=args.archive.stat().st_size,crc_and_contents_verified=True))
    print('MI_CUED_PACKAGE_VERIFIED',str(args.archive),digest(args.archive),flush=True)


if __name__ == '__main__':
    main()
