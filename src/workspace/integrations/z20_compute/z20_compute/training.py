"""One NumPy trainer and versioned artifacts for all four small classifiers."""
from dataclasses import dataclass
import hashlib
import json
import zipfile
from pathlib import Path
import numpy as np
from .npu import QuantizedMLP

DIMENSIONS = dict(emotion=180, fatigue=20, face=1024, sound=40)
LABELS = dict(emotion=("negative", "neutral", "positive"), fatigue=("awake", "mild", "severe"),
              face=("person_1", "person_2", "person_3"), sound=("clap", "whistle", "knock"))
PREPROCESSORS = dict(emotion="seed-causal-180-v1", fatigue="fatigue-calibrated-de20-v1",
                     face="roi-gray32-unit-v1", sound="pcm16k-fft1024-band20-meanstd-v1")


@dataclass
class Dataset:
    x: np.ndarray
    y: np.ndarray
    groups: np.ndarray
    splits: np.ndarray
    source: str
    source_kind: str

    def validate(self, task):
        n = len(self.x)
        if (task not in DIMENSIONS or self.x.shape != (n, DIMENSIONS[task])
                or not np.isfinite(self.x).all() or any(a.shape != (n,) for a in (self.y, self.groups, self.splits))
                or self.y.dtype.kind not in "iu" or not set(self.y.tolist()) <= {0, 1, 2}
                or self.source_kind not in ("synthetic", "recorded", "public") or not self.source):
            raise ValueError("dataset shape, labels or provenance invalid")
        if set(self.splits.tolist()) != {"train", "validation", "test"}:
            raise ValueError("explicit train/validation/test groups required")
        for group in np.unique(self.groups):
            if len(set(self.splits[self.groups == group].tolist())) != 1:
                raise ValueError("recording/session group leaked between splits")
        for split in ("train", "validation", "test"):
            if set(self.y[self.splits == split].tolist()) != {0, 1, 2}:
                raise ValueError("each split must contain all three known classes")

    def save(self, path):
        np.savez_compressed(path, x=self.x, y=self.y, groups=np.asarray(self.groups, dtype=str),
                            splits=np.asarray(self.splits, dtype=str), source=np.array(self.source),
                            source_kind=np.array(self.source_kind))

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            return cls(data["x"], data["y"], data["groups"], data["splits"],
                       str(data["source"].item()), str(data["source_kind"].item()))


@dataclass(frozen=True)
class Prediction:
    class_id: object
    scores: np.ndarray
    valid: bool
    state: str
    model_version: str
    backend: str


class ModelBundle:
    def __init__(self, task, mean, scale, float_parameters, integer, input_scale, score_scale,
                 *, source, source_kind, minimum_margin=0.):
        self.task, self.mean, self.scale = task, np.asarray(mean), np.asarray(scale)
        self.float_parameters, self.integer = tuple(float_parameters), integer
        self.input_scale, self.score_scale = float(input_scale), float(score_scale)
        self.source, self.source_kind, self.minimum_margin = source, source_kind, float(minimum_margin)
        dimension = DIMENSIONS[task]
        arrays = [self.mean, self.scale, *self.float_parameters]
        if (self.mean.shape != (dimension,) or self.scale.shape != (dimension,)
                or [a.shape for a in self.float_parameters] != [(32, dimension), (32,), (3, 32), (3,)]
                or np.any(self.scale <= 0) or not all(np.isfinite(a).all() for a in arrays)
                or integer.w1.shape != (32, dimension)
                or not np.isfinite([self.input_scale, self.score_scale, self.minimum_margin]).all()
                or min(self.input_scale, self.score_scale) <= 0 or self.minimum_margin < 0
                or source_kind not in ("synthetic", "recorded", "public") or not isinstance(source, str) or not source):
            raise ValueError("invalid model/preprocessing artifact")
        digest = hashlib.sha256()
        digest.update((task + PREPROCESSORS[task]).encode())
        for a in [*arrays, integer.w1, integer.b1, integer.w2, integer.b2]:
            digest.update(np.ascontiguousarray(a).tobytes())
        digest.update(str((integer.hidden_shift, self.input_scale, self.score_scale)).encode())
        digest.update(json.dumps(dict(source=source, source_kind=source_kind,
                                      minimum_margin=self.minimum_margin), sort_keys=True).encode())
        self.version = digest.hexdigest()[:24]

    @property
    def deployable(self):
        return self.source_kind in ("recorded", "public")

    def quantize_input(self, features):
        features = np.asarray(features, dtype=np.float64)
        if features.shape != self.mean.shape or not np.isfinite(features).all():
            raise ValueError("feature shape/values differ from trained model")
        normalized = (features-self.mean)/self.scale
        return np.clip(np.rint(normalized/self.input_scale), -128, 127).astype(np.int8)

    def predict(self, features, *, backend=None):
        values = self.quantize_input(features)
        raw = self.integer.infer(values) if backend is None else backend.infer(self.integer, values)
        raw = np.asarray(raw)
        if raw.shape != (3,) or raw.dtype != np.int32:
            raise ValueError("NPU returned invalid score vector")
        scores = raw.astype(np.float64)*self.score_scale
        ranked = np.sort(scores)
        margin = float(ranked[-1]-ranked[-2])
        valid = margin > 0 and margin >= self.minimum_margin
        return Prediction(int(np.argmax(scores)) if valid else None, scores, valid,
                          "prediction" if valid else "low_margin", self.version,
                          "PS_integer_reference" if backend is None else backend.name)

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory/"weights.npz"
        np.savez_compressed(path, mean=self.mean, scale=self.scale,
                            w1=self.float_parameters[0], b1=self.float_parameters[1],
                            w2=self.float_parameters[2], b2=self.float_parameters[3],
                            qw1=self.integer.w1, qb1=self.integer.b1, qw2=self.integer.w2, qb2=self.integer.b2)
        metadata = dict(format="z20-mlp-v1", task=self.task, version=self.version,
                        preprocessor=PREPROCESSORS[self.task], labels=LABELS[self.task],
                        hidden_shift=self.integer.hidden_shift, input_scale=self.input_scale,
                        score_scale=self.score_scale, minimum_margin=self.minimum_margin,
                        source=self.source, source_kind=self.source_kind,
                        weights_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (directory/"model.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, directory):
        directory = Path(directory)
        meta = json.loads((directory/"model.json").read_text(encoding="utf-8"))
        path = directory/"weights.npz"
        if meta.get("format") != "z20-mlp-v1" or path.stat().st_size > 4*1024*1024:
            raise ValueError("unsupported or oversized model artifact")
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta["weights_sha256"]:
            raise ValueError("model weights hash mismatch")
        if meta["preprocessor"] != PREPROCESSORS[meta["task"]] or tuple(meta["labels"]) != LABELS[meta["task"]]:
            raise ValueError("model label/preprocessor contract mismatch")
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 4*1024*1024:
                raise ValueError("expanded model artifact exceeds size limit")
        with np.load(path, allow_pickle=False) as data:
            integer = QuantizedMLP(data["qw1"], data["qb1"], data["qw2"], data["qb2"], hidden_shift=meta["hidden_shift"])
            model = cls(meta["task"], data["mean"], data["scale"],
                        [data[k] for k in ("w1", "b1", "w2", "b2")], integer,
                        meta["input_scale"], meta["score_scale"], source=meta["source"],
                        source_kind=meta["source_kind"], minimum_margin=meta["minimum_margin"])
        if model.version != meta["version"]:
            raise ValueError("model version does not match artifact")
        return model


def classification_metrics(truth, predicted):
    matrix = np.zeros((3, 3), dtype=np.int64)
    rejected = np.zeros(3, dtype=np.int64)
    if len(truth) != len(predicted):
        raise ValueError("prediction and label counts differ")
    for actual, estimate in zip(truth, predicted):
        if int(actual) not in (0, 1, 2) or (estimate is not None and int(estimate) not in (0, 1, 2)):
            raise ValueError("metric labels must be 0, 1 or 2")
        if estimate is None:
            rejected[int(actual)] += 1
        else:
            matrix[int(actual), int(estimate)] += 1
    diagonal = np.diag(matrix).astype(float)
    precision = diagonal/np.maximum(matrix.sum(axis=0), 1)
    recall = diagonal/np.maximum(matrix.sum(axis=1)+rejected, 1)
    f1 = 2*precision*recall/np.maximum(precision+recall, 1e-12)
    total = int(matrix.sum()+rejected.sum())
    return dict(samples=total, accuracy=float(diagonal.sum()/max(total, 1)),
                macro_f1=float(f1.mean()), balanced_accuracy=float(recall.mean()), confusion_matrix=matrix.tolist(),
                rejected_by_class=rejected.tolist(), coverage=float(matrix.sum()/max(total, 1)))


def _pow2_scale(maximum):
    return float(2.**np.ceil(np.log2(max(float(maximum)/127., 1e-12))))


def _integer_model(parameters, calibration):
    w1, b1, w2, b2 = parameters
    input_scale, w1_scale, w2_scale = [_pow2_scale(np.max(np.abs(a))) for a in (calibration, w1, w2)]
    hidden_max = np.maximum(calibration@w1.T+b1, 0).max()
    desired = _pow2_scale(hidden_max)
    shift = int(np.clip(np.ceil(np.log2(desired/(input_scale*w1_scale))), 0, 31))
    hidden_scale = input_scale*w1_scale*(2.**shift)
    def weight(a, scale):
        return np.clip(np.rint(a/scale), -128, 127).astype(np.int8)
    def bias(a, scale):
        rounded = np.rint(a/scale)
        if np.any(np.abs(rounded) > np.iinfo(np.int32).max):
            raise ValueError("bias exceeds accumulator range")
        return rounded.astype(np.int32)
    model = QuantizedMLP(weight(w1, w1_scale), bias(b1, input_scale*w1_scale),
                         weight(w2, w2_scale), bias(b2, hidden_scale*w2_scale), hidden_shift=shift)
    return model, input_scale, hidden_scale*w2_scale


def train_mlp(dataset, task, *, epochs=100, seed=7,group_balanced=False):
    dataset.validate(task)
    if not 1 <= epochs <= 10000:
        raise ValueError("invalid training epoch count")
    train, validation, test = [dataset.splits == name for name in ("train", "validation", "test")]
    weights=np.ones(len(dataset.x),float)
    if group_balanced:
        for split in (train,validation,test):
            for label in range(3):
                mask=split&(dataset.y==label);groups=np.unique(dataset.groups[mask])
                for group in groups:
                    indices=mask&(dataset.groups==group)
                    weights[indices]=1./(3*len(groups)*indices.sum())
    mean = np.average(dataset.x[train],axis=0,weights=weights[train])
    scale = np.sqrt(np.average((dataset.x[train]-mean)**2,axis=0,weights=weights[train]))
    scale[scale < 1e-6] = 1.
    features = (dataset.x-mean)/scale
    rng = np.random.default_rng(seed)
    dimension = DIMENSIONS[task]
    parameters = [rng.normal(0, np.sqrt(2/dimension), (32, dimension)), np.zeros(32),
                  rng.normal(0, np.sqrt(2/32), (3, 32)), np.zeros(3)]
    first, second = [np.zeros_like(a) for a in parameters], [np.zeros_like(a) for a in parameters]
    best, best_loss, step = None, float("inf"), 0
    indices = np.flatnonzero(train)
    for epoch in range(epochs):
        batches=1 if group_balanced else max(1,int(np.ceil(len(indices)/128)))
        for batch in np.array_split(rng.permutation(indices),batches):
            x, y = features[batch], dataset.y[batch]
            w1, b1, w2, b2 = parameters
            preactivation = x@w1.T+b1
            hidden = np.maximum(preactivation, 0)
            logits = hidden@w2.T+b2
            probability = np.exp(logits-logits.max(axis=1, keepdims=True))
            probability /= probability.sum(axis=1, keepdims=True)
            probability[np.arange(len(y)), y] -= 1
            probability *= (weights[batch]/weights[batch].sum())[:,None]
            dh = (probability@w2)*(preactivation > 0)
            gradients = [dh.T@x, dh.sum(axis=0), probability.T@hidden, probability.sum(axis=0)]
            step += 1
            for p, g, m, v in zip(parameters, gradients, first, second):
                m *= .9; m += .1*g
                v *= .999; v += .001*g*g
                p -= .01*(m/(1-.9**step))/(np.sqrt(v/(1-.999**step))+1e-8)
        w1, b1, w2, b2 = parameters
        logits = np.maximum(features[validation]@w1.T+b1, 0)@w2.T+b2
        logits -= logits.max(axis=1, keepdims=True)
        loss = float(np.average(np.log(np.exp(logits).sum(axis=1))-logits[np.arange(validation.sum()), dataset.y[validation]],weights=weights[validation]))
        if loss < best_loss:
            best_loss, best = loss, [p.copy() for p in parameters]
    integer, input_scale, score_scale = _integer_model(best, features[train])
    model = ModelBundle(task, mean, scale, best, integer, input_scale, score_scale,
                        source=dataset.source, source_kind=dataset.source_kind)
    report = dict(task=task, source=dataset.source, source_kind=dataset.source_kind,
                  split_by="recording/session group", epochs=epochs, seed=seed, version=model.version,
                  weighting='equal_class_then_source_recording' if group_balanced else 'equal_window')
    for split, mask in [("validation", validation), ("test", test)]:
        predicted = [model.predict(row).class_id for row in dataset.x[mask]]
        report[split] = classification_metrics(dataset.y[mask], predicted)
        w1, b1, w2, b2 = best
        floating = np.argmax(np.maximum(features[mask]@w1.T+b1, 0)@w2.T+b2, axis=1)
        report[split]["float_accuracy"] = float(np.mean(floating == dataset.y[mask]))
        report[split]["integer_float_agreement"] = float(np.mean(floating == predicted))
        report[split]['weighted_accuracy']=float(np.average(np.array(predicted)==dataset.y[mask],weights=weights[mask]))
    return model, report
