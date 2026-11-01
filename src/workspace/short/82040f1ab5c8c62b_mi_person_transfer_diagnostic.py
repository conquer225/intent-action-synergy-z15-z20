"""Original30 blocked personal-vs-transfer diagnosis, never cross-day or deployment."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import time

from mi_comparison_models import (EEGNetSmall, channel_scaler, normalized_tensor,
                                  network_logits, train_network, configure_torch, torch)
import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from mi_model_comparison import load_run, save_prediction, FROZEN

HERE = Path(__file__).resolve().parent
OUTPUT = HERE/'output/mi_person_transfer_diagnostic_20261002'
PROTOCOL = HERE/'mi_person_transfer_protocol.json'
SOURCES = ('mi_person_transfer_diagnostic.py', 'mi_person_transfer_protocol.json',
           'MI_PERSON_TRANSFER_PLAN.md', 'test_mi_person_transfer.py')
NEURAL = ('PERSON_ONLY', 'CROSS_MATCHED80')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def personal_indices(subjects, order, target):
    own = subjects == target
    fit = np.flatnonzero(own & (order < 80))
    val = np.flatnonzero(own & (order >= 80) & (order < 120))
    test = np.flatnonzero(own & (order >= 120))
    if len(fit) != 80 or len(val) != 40 or len(test) not in (80, 120):
        raise ValueError('Complete original200/240 chronological trials required')
    return fit, val, test


def balanced_subset(labels, subjects, eligible, count_per_class, rng):
    eligible = np.asarray(eligible, dtype=int)
    people = np.unique(subjects[eligible])
    base, remainder = divmod(count_per_class, len(people))
    if base < 1 or len(np.unique(eligible)) != len(eligible):
        raise ValueError('Budget must include both classes of every person, distinct indices')
    selected = []
    for label in (0, 1):
        extras = set(rng.permutation(people)[:remainder].tolist())
        for person in people:
            candidates = eligible[(subjects[eligible] == person) & (labels[eligible] == label)]
            quota = base + int(person in extras)
            if len(candidates) < quota:
                raise ValueError('Insufficient class/person trials for declared budget')
            selected.extend(rng.choice(candidates, quota, replace=False).tolist())
    return np.array(sorted(selected), dtype=int)


@torch.inference_mode()
def features(model, x):
    model.eval()
    values = model.block2(model.block1(model.temporal(model.temporal_pad(x)))).flatten(1)
    result = values.cpu().numpy().astype(np.float64)
    if result.shape != (len(x), 240) or not np.isfinite(result).all():
        raise ValueError('Finite N x240 frozen features required')
    return result


def metric(labels, pred):
    matrix = np.zeros((2, 2), dtype=int)
    np.add.at(matrix, (labels, pred), 1)
    if np.any(matrix.sum(1) == 0):
        raise ValueError('Both target classes required')
    ba = float(np.mean(np.diag(matrix)/matrix.sum(1)))
    f1 = float(np.mean([2*matrix[i,i]/(matrix[i,:].sum()+matrix[:,i].sum()) for i in (0,1)]))
    return ba, f1, matrix.tolist()


def old_checkpoint(original, person, seed):
    return original/'network_checkpoints'/f's{person:02d}_seed{seed}.pt'


def new_checkpoint(output, case, method):
    suffix = '.npz' if method == 'SOURCE_PERSON_HEAD' else '.pt'
    return output/'models'/f's{case["person"]:02d}_{method}_seed{case["seed"]}{suffix}'


def prepare(output):
    p = read(PROTOCOL)
    original = HERE/p['original_run']
    old, stats, waves, folds = load_run(original)
    if p['participants'] != old['participants'] or p['channels'] != old['channels'] or p['seeds'] != old['eegnet']['seeds']:
        raise ValueError('Original people/montage/seeds changed')
    if digest(original/'results.json') != p['original_results_sha256']:
        raise ValueError('Original scored reference changed')
    manifest = read(original/'trial_manifest.json')
    if len(manifest) != 6080 or len(waves) != 6080:
        raise ValueError('Complete original30 cache required')
    audit, cases, trial_hashes = [], [], []
    for i, row in enumerate(manifest):
        if (row['subject'], row['label'], row['original_order']) != (int(stats['subjects'][i]), int(stats['labels'][i]), int(stats['order'][i])):
            raise ValueError('Cache/manifest identity mismatch')
        trial_hashes.append(hashlib.sha256(waves[i].tobytes()).hexdigest())
    if len(set(trial_hashes)) != len(waves):
        raise ValueError('Exact duplicated waveform trials; diagnose before training')
    for fold in folds:
        person = fold['target']
        own = np.flatnonzero(stats['subjects'] == person)
        np.testing.assert_array_equal(stats['order'][own], np.arange(len(own)))
        keys = np.array([manifest[i]['original_sequence_key'] for i in own])
        if not np.all(np.diff(keys) > 0):
            raise ValueError('Original keys not strictly ascending')
        blocks = []
        for offset in range(0, len(own), 40):
            group = own[offset:offset+40]
            counts = np.bincount(stats['labels'][group], minlength=2).tolist()
            if counts != [20,20]:
                raise ValueError('Chronological40 block not20/20; cannot pretend verified run')
            blocks.append({'original_orders': [offset,offset+40], 'class_counts':counts})
        fitting, validation, test = personal_indices(stats['subjects'], stats['order'], person)
        audit.append({'person':person, 'trials':len(own), 'chronological40_blocks':blocks,
                      'raw_run_ids_verified':False, 'test_trials':len(test)})
        for seed in p['seeds']:
            rng = np.random.default_rng(20261002+1000*person+seed)
            source_fit = np.flatnonzero(np.isin(stats['subjects'], fold['fit_people']))
            source_val = np.flatnonzero(np.isin(stats['subjects'], fold['validation_people']))
            matched_fit = balanced_subset(stats['labels'], stats['subjects'], source_fit, 40, rng)
            matched_val = balanced_subset(stats['labels'], stats['subjects'], source_val, 20, rng)
            cases.append({'person':person, 'seed':seed, 'personal_fit':fitting.tolist(),
                          'personal_validation':validation.tolist(), 'test':test.tolist(),
                          'matched_fit':matched_fit.tolist(), 'matched_validation':matched_val.tolist(),
                          'original_source_fold':fold})
    output.mkdir(parents=True, exist_ok=False)
    (output/'code_snapshot').mkdir()
    (output/'models').mkdir()
    sources = {str(HERE/name):digest(HERE/name) for name in SOURCES}
    for name in SOURCES:
        shutil.copy2(HERE/name, output/'code_snapshot'/name)
    save(output/'protocol.json', p)
    save(output/'case_manifest.json', cases)
    save(output/'input_audit.json', {'people':audit, 'all_trials':len(waves),
         'author_flags':sum(row['voltage_bad'] or row['emg_bad'] for row in manifest),
         'exact_duplicate_trials':0, 'scored_trials':sum(row['test_trials'] for row in audit),
         'same_parent_recording_exception':'Deliberate temporal-block diagnosis; not participant-independent or cross-day testing',
         'raw_mat_opened':False, 'actual_run_ids_known':False})
    inputs = [original/name for name in ('waveforms.npy','statistics.npz','trial_manifest.json','fold_manifest.json','results.json')]
    inputs += list((original/'network_checkpoints').glob('*'))
    inputs += list((original/'fold_predictions').glob('s*_C2_EEGNet_SMALL_seed*.npz'))
    inputs += [Path('D:/ican/datasets/Cho2017/source_docs')/name for name in ('readme.txt','readme_100295.txt','author_fulltext.xml')]
    save(output/'lock.json', {'declared_at_local':datetime.now().isoformat(), 'source_sha256':sources,
         'input_sha256':{str(path):digest(path) for path in inputs},
         'case_manifest_sha256':digest(output/'case_manifest.json'),
         'frozen_package_sha256':digest(FROZEN), 'confirmation_eeg_read':False, 'board_accessed':False})
    print('PREPARED 90cases;180neural fits+90heads;2480 common test trials;original30 only', flush=True)


def load(output):
    lock = read(output/'lock.json')
    for path, expected in {**lock['source_sha256'], **lock['input_sha256']}.items():
        if digest(path) != expected:
            raise ValueError('Locked input/code changed: '+path)
    if digest(output/'case_manifest.json') != lock['case_manifest_sha256'] or read(output/'protocol.json') != read(PROTOCOL):
        raise ValueError('Cases or protocol changed')
    p = read(output/'protocol.json')
    old, stats, waves, folds = load_run(HERE/p['original_run'])
    return p, old, stats, waves, read(output/'case_manifest.json')


def source_model(path):
    c = torch.load(path, map_location='cpu', weights_only=True)
    model = EEGNetSmall(c['config'])
    model.load_state_dict(c['state_dict'])
    return c, model


def train(output):
    if (output/'target_access.json').exists() or (output/'source_freeze.json').exists():
        raise RuntimeError('Frozen/scored run cannot be refitted')
    p, old, stats, waves, cases = load(output)
    configure_torch(old['compute'])
    if not torch.cuda.is_available():
        raise RuntimeError('Declared CUDA unavailable')
    device = old['compute']['device']
    started = time.monotonic()
    for case in cases:
        for method in NEURAL:
            path = new_checkpoint(output, case, method)
            if path.exists():
                if not path.with_suffix('.json').exists():
                    raise RuntimeError('Partial model must be diagnosed, not overwritten')
                continue
            fkey, vkey = ('personal_fit','personal_validation') if method == 'PERSON_ONLY' else ('matched_fit','matched_validation')
            fitting, validation = np.array(case[fkey]), np.array(case[vkey])
            mean, scale = channel_scaler(waves[fitting])
            xfit = normalized_tensor(waves[fitting], mean, scale, device)
            xval = normalized_tensor(waves[validation], mean, scale, device)
            model, history = train_network(xfit, stats['labels'][fitting], xval, stats['labels'][validation],
                stats['subjects'][validation], old['eegnet'], case['seed'], device)
            history.update(method=method, person=case['person'], fit_indices=fitting.tolist(),
                           validation_indices=validation.tolist(), no_test_forward=True)
            torch.save({'state_dict':{key:value.cpu() for key,value in model.state_dict().items()},
                'config':old['eegnet'], 'source_mean':mean.tolist(), 'source_scale':scale.tolist(),
                'case':case, 'method':method}, path)
            save(path.with_suffix('.json'), history)
        path = new_checkpoint(output, case, 'SOURCE_PERSON_HEAD')
        if not path.exists():
            c, model = source_model(old_checkpoint(HERE/p['original_run'], case['person'], case['seed']))
            before = {key:value.clone() for key,value in model.state_dict().items()}
            fitting = np.array(case['personal_fit'])
            xfit = normalized_tensor(waves[fitting], np.array(c['source_mean']), np.array(c['source_scale']), 'cpu')
            fit_features = features(model, xfit)
            with threadpool_limits(limits=1):
                scaler = StandardScaler().fit(fit_features)
                classifier = LinearDiscriminantAnalysis(solver='lsqr', shrinkage='auto').fit(scaler.transform(fit_features), stats['labels'][fitting])
            if classifier.classes_.tolist() != [0,1]:
                raise ValueError('Head class convention changed')
            scores = ((fit_features-scaler.mean_)/scaler.scale_)@classifier.coef_[0]+classifier.intercept_[0]
            np.testing.assert_allclose(scores, classifier.decision_function(scaler.transform(fit_features)), rtol=1e-12, atol=1e-12)
            for key,value in model.state_dict().items():
                torch.testing.assert_close(value, before[key], rtol=0, atol=0)
            np.savez_compressed(path, mean=scaler.mean_,scale=scaler.scale_,coef=classifier.coef_[0],
                intercept=classifier.intercept_[0],fit_features=fit_features,fit_indices=fitting,
                source_checkpoint_sha256=digest(old_checkpoint(HERE/p['original_run'],case['person'],case['seed'])))
            save(path.with_suffix('.json'), {'case':case, 'fit_indices':fitting.tolist(),
                'learned_trunk_and_BN_unchanged':True, 'validation_used_for_selection':False,
                'feature_dimensions':240, 'head':'LDA lsqr shrinkage=auto', 'test_forwarded':False})
        print('FROZEN_SOURCE_CASE', case['person'], case['seed'], 'elapsed',round(time.monotonic()-started,1), flush=True)
    files = list((output/'models').glob('*'))
    if len(files) != 540:
        raise ValueError('Expected270 models plus270 metadata')
    save(output/'source_freeze.json', {'at_local':datetime.now().isoformat(), 'fitted_models':270,
         'files':{str(path):digest(path) for path in files}, 'elapsed_pc_seconds':time.monotonic()-started,
         'late_test_forwarded':False})


def frozen(output):
    freeze = read(output/'source_freeze.json')
    if freeze['fitted_models'] != 270 or freeze['late_test_forwarded']:
        raise ValueError('Incomplete source freeze')
    for path, expected in freeze['files'].items():
        if digest(path) != expected:
            raise ValueError('Frozen model changed: '+path)
    return freeze


def prediction(output, case, method):
    return output/'fold_predictions'/f's{case["person"]:02d}_{method}_seed{case["seed"]}.npz'


def head_scores(output, p, waves, case, indices):
    c, model = source_model(old_checkpoint(HERE/p['original_run'],case['person'],case['seed']))
    x = normalized_tensor(waves[indices],np.array(c['source_mean']),np.array(c['source_scale']),'cpu')
    values = features(model,x)
    with np.load(new_checkpoint(output,case,'SOURCE_PERSON_HEAD'),allow_pickle=False) as head:
        return ((values-head['mean'])/head['scale'])@head['coef']+float(head['intercept'])


def evaluate(output):
    if (output/'results.json').exists():
        raise RuntimeError('Completed result preserved')
    p, old, stats, waves, cases = load(output)
    freeze = frozen(output)
    configure_torch(old['compute'])
    if not (output/'target_access.json').exists():
        save(output/'target_access.json', {'at_local':datetime.now().isoformat(),'source_freeze_at_local':freeze['at_local']})
    for case in cases:
        indices = np.array(case['test'])
        for method in p['methods']:
            if prediction(output,case,method).exists():
                continue
            if method == 'CROSS_ORIGINAL':
                path = HERE/p['original_run']/'fold_predictions'/f's{case["person"]:02d}_C2_EEGNet_SMALL_seed{case["seed"]}.npz'
                with np.load(path,allow_pickle=False) as old_pred:
                    selected = np.isin(old_pred['indices'],indices)
                    np.testing.assert_array_equal(old_pred['indices'][selected],indices)
                    scores = old_pred['scores'][selected].copy()
                predicted = scores.argmax(1)
            elif method == 'SOURCE_PERSON_HEAD':
                scores = head_scores(output,p,waves,case,indices)
                predicted = (scores>0).astype(int)
            else:
                c, model = source_model(new_checkpoint(output,case,method))
                model = model.to(old['compute']['device'])
                x = normalized_tensor(waves[indices],np.array(c['source_mean']),np.array(c['source_scale']),old['compute']['device'])
                scores = network_logits(model,x)
                predicted = scores.argmax(1)
            if not np.isfinite(scores).all():
                raise ValueError('Nonfinite output; no silent exclusion')
            save_prediction(output,case['person'],method,case['seed'],indices,stats['labels'][indices],scores,predicted,
                            {'case':case,'method':method,'control_enabled':False})
        print('TEST_CASE',case['person'],case['seed'],flush=True)
    summarize(output,p,stats,cases)


def summarize(output,p,stats,cases):
    methods, hashes = {}, {}
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0,30,(10000,30))
    for method in p['methods']:
        rows = []
        for person in p['participants']:
            repetitions = []
            for case in [c for c in cases if c['person']==person]:
                path = prediction(output,case,method)
                with np.load(path,allow_pickle=False) as saved:
                    np.testing.assert_array_equal(saved['indices'],case['test'])
                    np.testing.assert_array_equal(saved['labels'],stats['labels'][saved['indices']])
                    ba,f1,matrix = metric(saved['labels'],saved['predictions'])
                    repetitions.append({'seed':case['seed'],'ba':ba,'macro_f1':f1,'confusion':matrix})
                hashes[str(path)] = digest(path)
            rows.append({'person':person,'trials':len(case['test']), 'ba':float(np.mean([r['ba'] for r in repetitions])),
                         'macro_f1':float(np.mean([r['macro_f1'] for r in repetitions])), 'per_seed':repetitions})
        values = np.array([r['ba'] for r in rows])
        methods[method] = {'mean_person_ba':float(values.mean()),'between_person_sd':float(values.std(ddof=1)),
            'mean_lowest8_ba':float(np.sort(values)[:8].mean()),'mean_person_f1':float(np.mean([r['macro_f1'] for r in rows])),
            'person95ci':np.quantile(values[draws].mean(1),[.025,.975]).tolist(),'per_person':rows}
    comparisons = {}
    for candidate,reference,primary in [('PERSON_ONLY','CROSS_ORIGINAL',True),('SOURCE_PERSON_HEAD','CROSS_ORIGINAL',True),
                                       ('PERSON_ONLY','CROSS_MATCHED80',False),('SOURCE_PERSON_HEAD','PERSON_ONLY',False)]:
        delta = np.array([r['ba'] for r in methods[candidate]['per_person']])-np.array([r['ba'] for r in methods[reference]['per_person']])
        tail = .0125 if primary else .025
        ci = np.quantile(delta[draws].mean(1),[tail,1-tail]).tolist()
        comparisons[candidate+'_minus_'+reference] = {'mean_gain':float(delta.mean()),'paired_ci':ci,
            'coverage':1-2*tail,'primary':primary,'people_improved':int((delta>1e-12).sum()),'people_declined':int((delta< -1e-12).sum()),
            'diagnostic_headroom_gate':bool(primary and delta.mean()>=.05 and ci[0]>0), 'per_person_delta':delta.tolist()}
    manifest = read(HERE/p['original_run']/'trial_manifest.json')
    unique_test = sorted({i for case in cases for i in case['test']})
    result = {'scope':p['scope'],'methods':methods,'comparisons':comparisons,'scored_unique_trials':len(unique_test),
        'scored_author_flags':sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique_test),
        'prediction_sha256':hashes,'source_freeze_at':read(output/'source_freeze.json')['at_local'],
        'completed_at_local':datetime.now().isoformat(),'confirmation_eeg_read':False,'board_accessed':False,
        'deployment_authorized':False,'control_enabled':False}
    save(output/'results.json',result)
    print(json.dumps({'means':{m:v['mean_person_ba'] for m,v in methods.items()},'comparisons':comparisons},indent=2),flush=True)


def verify(output):
    p,old,stats,waves,cases = load(output)
    frozen(output)
    configure_torch(old['compute'])
    result = read(output/'results.json')
    checks, max_error = 0,0.
    for case in cases:
        indices = np.array(case['test'])
        for method in p['methods']:
            path = prediction(output,case,method)
            if digest(path) != result['prediction_sha256'][str(path)]:
                raise ValueError('Prediction changed')
            if method == 'SOURCE_PERSON_HEAD':
                scores = head_scores(output,p,waves,case,indices)
                predicted = (scores>0).astype(int)
                fit_indices = np.array(case['personal_fit'])
                c,model = source_model(old_checkpoint(HERE/p['original_run'],case['person'],case['seed']))
                values = features(model,normalized_tensor(waves[fit_indices],np.array(c['source_mean']),np.array(c['source_scale']),'cpu'))
                with np.load(new_checkpoint(output,case,method),allow_pickle=False) as head:
                    np.testing.assert_array_equal(head['fit_indices'],fit_indices)
                    np.testing.assert_array_equal(head['fit_features'],values)
                    scaler = StandardScaler().fit(values)
                    np.testing.assert_array_equal(scaler.mean_,head['mean'])
                    np.testing.assert_array_equal(scaler.scale_,head['scale'])
                    with threadpool_limits(limits=1):
                        classifier = LinearDiscriminantAnalysis(solver='lsqr',shrinkage='auto').fit(scaler.transform(values),stats['labels'][fit_indices])
                    np.testing.assert_allclose(head['coef'],classifier.coef_[0],rtol=0,atol=1e-12)
                    np.testing.assert_allclose(head['intercept'],classifier.intercept_[0],rtol=0,atol=1e-12)
            else:
                checkpoint = old_checkpoint(HERE/p['original_run'],case['person'],case['seed']) if method=='CROSS_ORIGINAL' else new_checkpoint(output,case,method)
                c,model = source_model(checkpoint)
                scores = network_logits(model,normalized_tensor(waves[indices],np.array(c['source_mean']),np.array(c['source_scale']),'cpu'))
                predicted = scores.argmax(1)
                if method in NEURAL:
                    h = read(checkpoint.with_suffix('.json'))
                    mean,scale = channel_scaler(waves[h['fit_indices']])
                    np.testing.assert_array_equal(mean,c['source_mean'])
                    np.testing.assert_array_equal(scale,c['source_scale'])
                    first = int(np.argmax([r['source_validation_mean_person_ba'] for r in h['history']]))+1
                    if first != h['best_epoch']:
                        raise ValueError('Not earliest source-only best epoch')
                    v = np.array(h['validation_indices'])
                    val_logits = network_logits(model,normalized_tensor(waves[v],mean,scale,'cpu'))
                    per_person = [metric(stats['labels'][v][stats['subjects'][v]==person],val_logits.argmax(1)[stats['subjects'][v]==person])[0] for person in np.unique(stats['subjects'][v])]
                    np.testing.assert_allclose(np.mean(per_person),h['source_validation_mean_person_ba'],rtol=0,atol=1e-14)
            with np.load(path,allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['indices'],indices)
                np.testing.assert_array_equal(saved['labels'],stats['labels'][indices])
                np.testing.assert_array_equal(predicted,saved['predictions'])
                np.testing.assert_allclose(scores,saved['scores'],rtol=2e-5,atol=2e-5)
                max_error=max(max_error,float(np.max(np.abs(scores-saved['scores']))))
            checks+=len(indices)
        print('VERIFY_CASE',case['person'],case['seed'],flush=True)
    if digest(FROZEN) != read(output/'lock.json')['frozen_package_sha256']:
        raise ValueError('Formal package changed')
    save(output/'verification.json',{'passed':True,'predictions_cpu_recomputed':checks,'classes_exact':True,
        'max_abs_score_error':max_error,'180_scalers_and_source_selection_checked':True,'90_heads_reconstructed':True,
        'formal_package_unchanged':True,'results_sha256':digest(output/'results.json'),'at_local':datetime.now().isoformat()})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','train','evaluate','verify'))
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args()
    {'prepare':prepare,'train':train,'evaluate':evaluate,'verify':verify}[args.action](args.output)
