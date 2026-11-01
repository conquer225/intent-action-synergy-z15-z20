"""Read-only ARM check of offline MI covariance-to-score math, not live inference."""
import base64
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import shlex
import sys

import numpy as np

from deploy_startup import CONFIGS, LEDGER, PROD, PYTHON, connect, digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'eeg_apps_z15/output/mi_spatial_dev_20261001'
sys.path.insert(0, str(ROOT / 'pynq_guardianloop'))
from mi_spatial import linear_scores

REMOTE = '''
import base64,io,json,sys,time,types
import numpy as np
payload=json.load(sys.stdin)
constants=types.ModuleType('mi_features')
constants.CHANNELS=payload['channels']
constants.WINDOW_SAMPLES=750
sys.modules['mi_features']=constants
namespace={}
exec(compile(payload['source'],'isolated-mi-spatial','exec'),namespace)
arrays=np.load(io.BytesIO(base64.b64decode(payload['arrays'])),allow_pickle=False)
args=[arrays[k] for k in ('covariances','filters','mean','scale','coef','intercept')]
score=namespace['linear_scores'](*args)
np.testing.assert_allclose(score,arrays['expected'],atol=1e-9,rtol=1e-9)
assert np.array_equal(score>=0,arrays['expected']>=0)
timings=[]
for index in range(300):
    start=time.perf_counter()
    namespace['linear_scores'](args[0][index%len(score):index%len(score)+1],*args[1:])
    timings.append((time.perf_counter()-start)*1000)
print(json.dumps({'numpy_version':np.__version__,'trials':len(score),
 'max_abs_score_error':float(np.max(np.abs(score-arrays['expected']))),
 'classes_equal':True,'single_covariance_to_score_ms_median':float(np.median(timings)),
 'single_covariance_to_score_ms_p95':float(np.percentile(timings,95)),
 'single_covariance_to_score_ms_max':float(np.max(timings)),
 'benchmark_scope':'precomputed covariances to spatial log variance and LDA score ONLY',
 'not_measured':['continuous filtering','covariance extraction','acquisition','quality gating','end-to-end latency'],
 'live_prediction_enabled':False,'control_enabled':False},allow_nan=False))
'''


def fingerprint(client, ledger):
    paths = [PROD + '/' + name for name in ledger['release_files']]
    paths += list(CONFIGS.values()) + ['/boot/BOOT.BIN', '/boot/image.ub', '/boot/boot.scr']
    with client.open_sftp() as sftp:
        return {path: digest(sftp, path) for path in paths}


def paired_interval(first, second):
    assert [r['subject'] for r in first] == [r['subject'] for r in second]
    difference = np.array([a['balanced_accuracy'] - b['balanced_accuracy']
                           for a, b in zip(first, second)])
    rng = np.random.default_rng(20261001)
    means = difference[rng.integers(0, len(difference), size=(10000, len(difference)))].mean(axis=1)
    return {'mean_difference': float(difference.mean()),
            'paired_subject_bootstrap_95_ci': np.quantile(means, [.025, .975]).tolist(),
            'subjects_improved': int((difference > 0).sum()),
            'subjects_declined': int((difference < 0).sum()),
            'subjects_tied': int((difference == 0).sum())}


def main():
    target = OUT / 'component_audit.json'
    if target.exists():
        raise RuntimeError('Audit exists; preserve the existing record')
    development = json.loads((OUT / 'development.json').read_text(encoding='utf-8'))
    cross = development['cross_subject']
    report = {'created_at_local': datetime.now().isoformat(),
              'paired_development_FBCSP_minus_C3_C4_power': paired_interval(
                  cross['FBCSP_LDA']['per_subject'], cross['C3_C4_power']['per_subject']),
              'promotion_gate_passed': False, 'control_enabled': False}
    with np.load(OUT / 'trial_covariances.npz', allow_pickle=False) as trials:
        selected = trials['subjects'] >= 71
        covariances = trials['covariances'][selected][:, [0, 3, 4, 5, 6]]
        report['development_label_counts'] = np.bincount(trials['labels'][selected], minlength=2).tolist()
        report['development_subjects'] = sorted(np.unique(trials['subjects'][selected]).tolist())
    with np.load(OUT / 'cross_development_model.npz', allow_pickle=False) as model:
        metadata = json.loads(str(model['metadata']))
        assert metadata['method'] == 'FBCSP_LDA' and metadata['promotion_gate_passed'] is False
        arrays = {key: model[key] for key in ('filters', 'mean', 'scale', 'coef', 'intercept')}
    expected = linear_scores(covariances, **arrays)
    memory = io.BytesIO()
    np.savez_compressed(memory, covariances=covariances, expected=expected, **arrays)
    source = (ROOT / 'pynq_guardianloop/mi_spatial.py').read_text(encoding='utf-8')
    payload = json.dumps({'source': source, 'channels': metadata['channels'],
                          'arrays': base64.b64encode(memory.getvalue()).decode('ascii')})
    report['portable_source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
    client = connect()
    try:
        ledger = json.loads(LEDGER.read_text(encoding='utf-8'))
        before = fingerprint(client, ledger)
        stdin, stdout, stderr = client.exec_command(
            'OPENBLAS_NUM_THREADS=1 ' + shlex.quote(PYTHON) + ' -c ' + shlex.quote(REMOTE), timeout=30)
        stdin.write(payload)
        stdin.flush()
        stdin.channel.shutdown_write()
        output, errors = stdout.read().decode(), stderr.read().decode()
        status = stdout.channel.recv_exit_status()
        after = fingerprint(client, ledger)
        report['protected_file_hashes_before'] = before
        report['protected_file_hashes_after'] = after
        report['protected_files_unchanged'] = before == after
        if status != 0:
            raise RuntimeError('ARM component check failed: ' + errors + output)
        if before != after:
            raise RuntimeError('Formal release files changed during read-only check')
        report['arm_component'] = json.loads(output)
        report['remote_file_writes'] = False
        report['usb_pl_services_or_boot_operated'] = False
    finally:
        client.close()
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('paired_development_FBCSP_minus_C3_C4_power',
                     'development_label_counts', 'arm_component', 'protected_files_unchanged')}, indent=2))


if __name__ == '__main__':
    main()
