"""Build EEG NPU replicas; report teacher agreement separately from accuracy."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from z20_compute.reference_models import linear_parameters, fatigue_labels
from z20_compute.training import ModelBundle, Dataset, _integer_model, train_mlp, classification_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', type=Path, default=Path('artifacts/headless/lemon_features.json'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/headless/models'))
    parser.add_argument('--epochs', type=int, default=300)
    args = parser.parse_args()
    records = json.loads(args.features.read_text(encoding='utf-8'))['records']
    legacy = Path('../../multimodal/vendor/runtime')
    report = dict(scope='original model agreement; wearer accuracy unmeasured', tasks={})
    rng = np.random.default_rng(20261025)
    x = np.array([r['features'] for r in records if r['task'] == 'emotion'])
    with np.load(legacy/'seed_shadow_weights.npz', allow_pickle=False) as weights:
        w, b = weights['weight'], weights['bias']
        if weights['classes'].tolist() != [-1, 0, 1]: raise ValueError('unexpected emotion labels')
    parameters = linear_parameters(w, b)
    calibration = x[:max(1, len(x)//2)]
    integer, input_scale, score_scale = _integer_model(parameters, calibration)
    model = ModelBundle('emotion', np.zeros(180), np.ones(180), parameters, integer,
        input_scale, score_scale, source='original SEED linear classifier: '+
        hashlib.sha256((legacy/'seed_shadow_weights.npz').read_bytes()).hexdigest(), source_kind='public')
    model.save(args.output/'emotion')
    truth = np.argmax(x @ w.T+b, axis=1)
    report['tasks']['emotion'] = dict(version=model.version, recorded_windows=len(x),
        calibration_windows=len(calibration), recorded_teacher_agreement=classification_metrics(
            truth, [model.predict(row).class_id for row in x]),
        held_out_teacher_agreement=classification_metrics(truth[len(calibration):],
            [model.predict(row).class_id for row in x[len(calibration):]]),
        teacher_class_counts=np.bincount(truth, minlength=3).tolist())
    teacher = json.loads((legacy/'cyton_fatigue_overlap4.json').read_text(encoding='utf-8'))
    # These are explicit teacher feature-space probes, never labelled human EEG.
    # One generated probe is one independent group; held-out probes use fresh RNG draws.
    probes = np.concatenate([rng.normal(0, scale, (1500, 20)) for scale in (.2, 1., 3., 8.)])
    labels = fatigue_labels(teacher, probes)
    splits = np.array(['train']*4000+['validation']*1000+['test']*1000)
    order = rng.permutation(len(probes)); probes, labels = probes[order], labels[order]
    dataset = Dataset(probes, labels, np.array(['probe-%d'%i for i in range(len(probes))]), splits,
        source='original HGB teacher on synthetic classifier-input probes; thresholds 0.35/0.70',
        source_kind='synthetic')
    model, training_report = train_mlp(dataset, 'fatigue', epochs=args.epochs)
    model.save(args.output/'fatigue')
    x = np.array([r['features'] for r in records if r['task'] == 'fatigue'])
    truth = fatigue_labels(teacher, x)
    actual = np.array([r['baseline']['level'] for r in records if r['task'] == 'fatigue'])
    if not np.array_equal(truth, actual): raise ValueError('teacher no longer matches original runtime')
    report['tasks']['fatigue'] = dict(version=model.version, recorded_windows=len(x),
        teacher_class_counts=np.bincount(truth, minlength=3).tolist(),
        recorded_teacher_agreement=classification_metrics(truth, [model.predict(row).class_id for row in x]),
        probe_training=training_report, deployable=model.deployable,
        scope='teacher distillation on explicit synthetic feature probes; recorded EEG is held out')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'agreement.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
