"""Train-only band selection and a bounded EEGNet-style PyTorch model."""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')

from dataclasses import dataclass
import hashlib
import time

import numpy as np
import torch
from torch import nn
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.feature_selection import mutual_info_classif
from sklearn.preprocessing import StandardScaler

from mi_spatial_development import METHODS
from mi_spatial import projected_features

FB_INDICES = METHODS['FBCSP_LDA'][0]


def split_people(people, target):
    if len(set(people)) != 30 or target not in people:
        raise ValueError('Exactly30 distinct original training people required')
    source = [p for p in people if p != target]
    source.sort(key=lambda p: hashlib.sha256(f'mi-comparison-20261001:{target}:{p}'.encode()).digest())
    validation = sorted(source[:3])
    training = sorted(source[3:])
    return training, validation


@dataclass
class SelectedFB:
    filters: np.ndarray
    selected_positions: np.ndarray
    band_mutual_information: np.ndarray
    scaler: StandardScaler
    classifier: LinearDiscriminantAnalysis


def fit_selected_fb(covariances, labels, base_filters, selection):
    if covariances.ndim != 4 or covariances.shape[1:] != (7, 8, 8) or set(labels) != {0, 1}:
        raise ValueError('Frozen bands and both source classes required')
    values = projected_features(covariances[:, FB_INDICES], base_filters)
    information = mutual_info_classif(values, labels, discrete_features=False,
                                     n_neighbors=selection['neighbors'], random_state=selection['seed'])
    scores = information.reshape(5, 2).mean(axis=1)
    positions = np.lexsort((np.array(FB_INDICES), -scores))[:selection['selected_whole_bands']]
    positions = np.sort(positions)
    selected = values.reshape(len(values), 5, 2)[:, positions].reshape(len(values), -1)
    scaler = StandardScaler().fit(selected)
    classifier = LinearDiscriminantAnalysis(solver='lsqr', shrinkage='auto').fit(scaler.transform(selected), labels)
    return SelectedFB(base_filters.copy(), positions, scores, scaler, classifier)


def selected_fb_scores(covariances, fitted):
    values = projected_features(covariances[:, FB_INDICES], fitted.filters)
    selected = values.reshape(len(values), 5, 2)[:, fitted.selected_positions].reshape(len(values), -1)
    scores = ((selected - fitted.scaler.mean_) / fitted.scaler.scale_) @ fitted.classifier.coef_[0]
    scores += fitted.classifier.intercept_[0]
    expected = fitted.classifier.decision_function(fitted.scaler.transform(selected))
    np.testing.assert_allclose(scores, expected, rtol=1e-10, atol=1e-10)
    predicted = (scores > 0).astype(int)
    np.testing.assert_array_equal(predicted, fitted.classifier.predict(fitted.scaler.transform(selected)))
    return predicted, scores, float(np.max(np.abs(scores - expected)))


class EEGNetSmall(nn.Module):
    """Architecture inspired by ARL EEGNet, independently implemented in PyTorch.

    Full completed2s window only: SAME convolutions do not claim samplewise causality.
    Keras BatchNorm/constraint semantics mapped explicitly; no pretrained weights.
    """
    def __init__(self, config):
        super().__init__()
        f1, d, f2 = config['F1'], config['D'], config['F2']
        temporal, separable = config['temporal_kernel'], config['separable_kernel']
        bn = dict(eps=config['bn_eps'], momentum=config['bn_torch_momentum'])
        self.temporal = nn.Conv2d(1, f1, (1, temporal), bias=False)
        spatial = nn.Conv2d(f1, f1*d, (8, 1), groups=f1, bias=False)
        self.temporal_pad = nn.ZeroPad2d(((temporal-1)//2, temporal//2, 0, 0))
        self.block1 = nn.Sequential(nn.BatchNorm2d(f1, **bn), spatial,
                                    nn.BatchNorm2d(f1*d, **bn), nn.ELU(),
                                    nn.AvgPool2d((1, config['pools'][0])), nn.Dropout(config['dropout']))
        self.block2 = nn.Sequential(nn.ZeroPad2d(((separable-1)//2, separable//2, 0, 0)),
                                    nn.Conv2d(f1*d, f1*d, (1, separable), groups=f1*d, bias=False),
                                    nn.Conv2d(f1*d, f2, (1, 1), bias=False),
                                    nn.BatchNorm2d(f2, **bn), nn.ELU(),
                                    nn.AvgPool2d((1, config['pools'][1])), nn.Dropout(config['dropout']))
        self.dense = nn.Linear(f2*(500//config['pools'][0]//config['pools'][1]), 2)
        self.spatial_max_norm, self.dense_max_norm = config['spatial_max_norm'], config['dense_max_norm']
        for layer in self.modules():
            if isinstance(layer, (nn.Conv2d, nn.Linear)):
                nn.init.xavier_uniform_(layer.weight)
                if layer.bias is not None:
                    nn.init.zeros_(layer.bias)

    def forward(self, values):
        if values.ndim != 4 or tuple(values.shape[1:]) != (1, 8, 500):
            raise ValueError('N x1 x8 x500 fixed completed-window input required')
        return self.dense(self.block2(self.block1(self.temporal(self.temporal_pad(values)))).flatten(1))

    @torch.no_grad()
    def constrain(self):
        for weight, bound in ((self.block1[1].weight, self.spatial_max_norm), (self.dense.weight, self.dense_max_norm)):
            norms = weight.flatten(1).norm(dim=1).clamp_min(1e-12)
            factors = (bound/norms).clamp(max=1)
            weight.mul_(factors.reshape((-1,)+(1,)*(weight.ndim-1)))


def configure_torch(config):
    torch.set_num_threads(config['torch_cpu_threads'])
    torch.use_deterministic_algorithms(config['deterministic_algorithms'])
    torch.backends.cudnn.benchmark = config['cudnn_benchmark']
    torch.backends.cudnn.deterministic = config['deterministic_algorithms']
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def channel_scaler(training_waveforms):
    values = np.asarray(training_waveforms)
    if values.ndim != 3 or values.shape[1:] != (8, 500) or not np.isfinite(values).all():
        raise ValueError('Finite N x8 x500 training waveforms required')
    mean = values.mean(axis=(0, 2), dtype=np.float64)
    variance = np.mean((values.astype(np.float64)-mean[None, :, None])**2, axis=(0, 2))
    if not np.isfinite(variance).all() or np.any(variance <= 1e-12):
        raise ValueError('Degenerate training-channel scale; no silent imputation')
    return mean, np.sqrt(variance)


def normalized_tensor(values, mean, scale, device):
    result = ((values.astype(np.float64)-mean[None, :, None])/scale[None, :, None]).astype(np.float32)
    if not np.isfinite(result).all():
        raise ValueError('Invalid standardized waveform; no clipping or trial deletion')
    return torch.from_numpy(result[:, None]).to(device)


@torch.inference_mode()
def network_logits(model, values, batch_size=256):
    model.eval()
    result = torch.cat([model(values[i:i+batch_size]) for i in range(0, len(values), batch_size)])
    if not torch.isfinite(result).all():
        raise ValueError('Nonfinite network logits')
    return result.cpu().numpy()


def mean_person_ba(labels, predictions, people):
    results = []
    for person in np.unique(people):
        selected = people == person
        if set(labels[selected]) != {0, 1}:
            raise ValueError('Both classes required for every validation person')
        results.append(np.mean([np.mean(predictions[selected & (labels == cls)] == cls) for cls in (0, 1)]))
    return float(np.mean(results))


def train_network(train_x, train_y, validation_x, validation_y, validation_people, config, seed, device, progress=None):
    """No target EEG/labels in this API; returns a frozen source-validation checkpoint."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = EEGNetSmall(config).to(device)
    labels = torch.as_tensor(train_y, dtype=torch.long, device=device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'],
                                 betas=tuple(config['betas']), weight_decay=config['weight_decay'])
    best_ba, best_epoch, best_state, history = -1.0, 0, None, []
    start = time.monotonic()
    for epoch in range(1, config['epochs_max']+1):
        model.train()
        order = torch.randperm(len(train_x), device=device)
        for offset in range(0, len(order), config['batch_size']):
            selected = order[offset:offset+config['batch_size']]
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.cross_entropy(model(train_x[selected]), labels[selected])
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite loss; no numerical fallback')
            loss.backward()
            optimizer.step()
            model.constrain()
        logits = network_logits(model, validation_x)
        ba = mean_person_ba(validation_y, logits.argmax(axis=1), validation_people)
        history.append({'epoch': epoch, 'source_validation_mean_person_ba': ba})
        if ba > best_ba:
            best_ba, best_epoch = ba, epoch
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
        if progress is not None and epoch % 10 == 0:
            progress(epoch, best_epoch, best_ba, time.monotonic()-start)
        if epoch-best_epoch >= config['early_stop_patience']:
            break
    model.load_state_dict(best_state)
    model.eval()
    return model, {'seed': seed, 'best_epoch': best_epoch, 'completed_epochs': epoch,
                   'source_validation_mean_person_ba': best_ba, 'history': history,
                   'pc_fit_seconds': time.monotonic()-start,
                   'parameter_count': sum(p.numel() for p in model.parameters())}
