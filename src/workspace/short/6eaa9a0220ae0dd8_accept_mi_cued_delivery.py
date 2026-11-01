"""Local MI numerical/stream delivery check, without fitting or accuracy scoring."""
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

from mi_comparison_models import torch, EEGNetSmall, normalized_tensor, network_logits
import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'pynq_guardianloop'
sys.path.insert(0, str(RUNTIME))
from mi_cued import CuedMISession
from mi_eegnet_portable import OfflineEEGNet
from mi_features import CHANNELS

HERE = Path(__file__).resolve().parent
OUT = HERE / 'output/mi_cued_delivery_20261002'
ORIGINAL = HERE / 'output/mi_model_comparison_20261001'
CHECKPOINT = ORIGINAL / 'network_checkpoints/s01_seed42.pt'
WAVES = ORIGINAL / 'waveforms.npy'
BENCH = HERE / 'output/accepted_bench_load_20260927/bench_input.npz'
FORMAL = Path('D:/ican/handoff/GuardianLoop_FROZEN_20261001.zip')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                      allow_nan=False) + '\n', encoding='utf-8')


class Clock:
    def __init__(self):
        self.value = 100.

    def __call__(self):
        return self.value


def replay(model, raw, sequences, name):
    clock = Clock()
    session = CuedMISession(model, source='replay', clock=clock, log_path=OUT/(name+'.jsonl'))
    candidates, rejected, durations, trials = 0, 0, [], 0
    last_id = None
    for start in range(0, len(raw), 50):
        if start % 2000 == 750:
            if session.trial and session.trial['state'] in ('active','awaiting_presentation'):
                session.command(dict(action='stop', id=session.trial['id']))
            target = ('left','right','rest')[trials % 3]
            state = session.command(dict(action='start', target=target))
            trials += 1
            session.command(dict(action='presented', id=state['id'],
                                 browser_onset_ms=100, browser_send_ms=101))
        clock.value += .2
        before = time.perf_counter()
        state = session.feed(raw[start:start+50], sequences[start:start+50])
        durations.append((time.perf_counter()-before)*1000)
        if state['result'] is not None and state['id'] != last_id:
            candidates += 1
            last_id = state['id']
        if state['state'] == 'rejected' and state['id'] != last_id:
            rejected += 1
            last_id = state['id']
        if state['state'] == 'active':
            session.command(dict(action='heartbeat',id=state['id']))
        if start % 2000 == 1750 and session.trial:
            session.command(dict(action='stop',id=session.trial['id']))
    session.disconnect('replay_eof')
    final = session.snapshot()
    assert final['result'] is None and final['source'] == 'replay'
    return dict(source='replay', input_samples=len(raw), trials=trials,
                candidate_trials=candidates, rejected_trials=rejected,
                eof_result_withdrawn=True, classification_accuracy_scored=False,
                pc_batch_p95_ms=float(np.quantile(durations,.95)),
                pc_batch_max_ms=max(durations), batch_samples=50,
                timing_scope='Windows PC, unpaced logical replay, NOT ARM/PL load')


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    OUT = parser.parse_args().output.resolve()
    OUT.mkdir(exist_ok=False)
    paths = [Path(__file__), HERE/'MI_CUED_DELIVERY_PLAN.md'] + [RUNTIME/name for name in
             ('mi_eegnet_portable.py','mi_cued.py','mi_cued_server.py','mi_cued.html',
              'test_mi_cued.py','test_mi_eegnet_portable.py','test_mi_cued_browser.cjs',
              'cyton_sqi.py','mi_features.py')]
    source_hashes = {str(path):digest(path) for path in paths}
    inputs = {str(path):digest(path) for path in (CHECKPOINT,WAVES,BENCH,FORMAL)}
    provenance = json.loads((ORIGINAL/'provenance.json').read_text(encoding='utf-8'))
    assert inputs[str(WAVES)] == provenance['cache_sha256']['waveforms.npy']
    assert inputs[str(FORMAL)] == provenance['frozen_package_sha256_before']
    snapshot = OUT/'code_snapshot'
    snapshot.mkdir()
    for path in paths:
        shutil.copy2(path, snapshot/path.name)
    save('lock.json',dict(at_local=datetime.now().isoformat(),source_sha256=source_hashes,
                         input_sha256=inputs, model_choice='s01_seed42 fixed before conversion; not score-selected',
                         logit_atol=1e-4,classes_must_match=True,accuracy_scored=False,board_accessed=False))
    torch.set_num_threads(1)
    checkpoint = torch.load(CHECKPOINT,map_location='cpu',weights_only=False)
    assert checkpoint['metadata']['target']==1 and checkpoint['metadata']['seed']==42
    assert not checkpoint['metadata']['promotion_gate_passed'] and not checkpoint['metadata']['control_enabled']
    metadata = dict(status='offline_plumbing_only', channels=list(CHANNELS), window_samples=500,
                    sample_rate_hz=250, control_enabled=False, production_eligible=False,
                    promotion_gate_passed=False, config=checkpoint['config'],
                    source_checkpoint_sha256=digest(CHECKPOINT), source_metadata=checkpoint['metadata'],
                    source_preprocessing='Cho per-trial CAR/512to250 FIR/notch/1-45/8-30, cue +0.5..2.5 s',
                    live_equivalence_verified=False, arm_runtime_verified=False)
    tensors = {key:value.numpy() for key,value in checkpoint['state_dict'].items()
               if not key.endswith('.num_batches_tracked')}
    model_path = OUT/'experimental_eegnet.npz'
    np.savez(model_path, **tensors, source_mean=checkpoint['source_mean'],
             source_scale=checkpoint['source_scale'], metadata=json.dumps(metadata))
    portable = OfflineEEGNet(model_path,allow_experimental=True)
    expected_model = EEGNetSmall(checkpoint['config'])
    expected_model.load_state_dict(checkpoint['state_dict'])
    expected_model.eval()
    waves = np.load(WAVES,mmap_mode='r',allow_pickle=False)
    assert waves.shape == (6080,8,500)
    actual, expected = [], []
    begin = time.perf_counter()
    with threadpool_limits(limits=1):
        for start in range(0,len(waves),16):
            block = np.asarray(waves[start:start+16])
            actual.append(portable.logits(block))
            normalized = normalized_tensor(block,np.asarray(checkpoint['source_mean']),
                                           np.asarray(checkpoint['source_scale']),'cpu')
            expected.append(network_logits(expected_model,normalized))
            if start % 800 == 0:
                print('NUMERICAL_WINDOWS',start+len(block),'/',len(waves),flush=True)
        actual, expected = np.concatenate(actual),np.concatenate(expected)
        error = float(np.max(np.abs(actual-expected)))
        classes_exact = bool(np.array_equal(actual.argmax(1),expected.argmax(1)))
        save('numerical.json',dict(windows=len(waves),max_logit_error=error,declared_atol=1e-4,
                                  classes_exact=classes_exact,pc_elapsed_seconds=time.perf_counter()-begin,
                                  labels_read=False,accuracy_scored=False))
        np.savez_compressed(OUT/'logits.npz',portable=actual,torch_reference=expected)
        assert error <= 1e-4 and classes_exact
        times = []
        for block in waves[:40]:
            before = time.perf_counter()
            portable.logits(block[None])
            times.append((time.perf_counter()-before)*1000)
        save('pc_inference_timing.json',dict(windows=40,median_ms=float(np.median(times)),
             p95_ms=float(np.quantile(times,.95)),max_ms=max(times),model_bytes=model_path.stat().st_size,
             blas_threads=1,scope='Windows PC only; not Z15 throughput or service-load evidence'))
        with np.load(BENCH,allow_pickle=False) as data:
            bench = data['recorded'].copy()
            sequences = data['recorded_seq'].astype(np.int64)%256
        assert bench.shape==(39000,8)
        bench_report = replay(portable,bench,sequences,'bench156')
        samples = np.arange(12000)
        synthetic = 10*np.sin(2*np.pi*samples[:,None]/250*np.arange(8,16)[None])
        synthetic_report = replay(portable,synthetic,samples%256,'synthetic48')
    for path, sha in source_hashes.items():
        assert digest(Path(path))==sha and digest(snapshot/Path(path).name)==sha
    for path, sha in inputs.items():
        assert digest(Path(path))==sha
    save('acceptance.json',dict(passed=True,completed_at_local=datetime.now().isoformat(),
         numerical_windows=6080,classes_exact=classes_exact,max_logit_error=error,
         bench=bench_report,synthetic=synthetic_report,formal_package_unchanged=True,
         new_accuracy_result=False,new_training=False,arm_exported=False,board_accessed=False,
         production_eligible=False,control_enabled=False,experimental_artifact_sha256=digest(model_path)))
    print('MI_CUED_LOCAL_ACCEPTED',error,classes_exact,bench_report,synthetic_report,flush=True)


if __name__ == '__main__':
    main()
