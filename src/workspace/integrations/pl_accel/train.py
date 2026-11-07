"""Train CSP and a squared-hinge linear SVM, then export the PL integer ABI."""
import argparse
import hashlib
from pathlib import Path

import numpy as np
from scipy import optimize, signal

from .eeg import BANDS, EEGModel, EEGReference
from .fixed import quantize_samples_uv


def trial_features(trials_uv, model):
    output = []
    for trial in trials_uv:
        windows = EEGReference(model).feed(quantize_samples_uv(trial))
        if not windows or not windows[-1]['valid']:
            raise ValueError('each trial must produce a finite, energetic, unclipped window')
        output.append(windows[-1]['features'])
    return np.asarray(output, np.int32)


def train_model(trials_uv, labels, *, window=500, hop=125, feature_count=4, regularization=1.):
    x, labels = np.asarray(trials_uv, np.float64), np.asarray(labels)
    if (x.ndim != 3 or x.shape[2] != 8 or x.shape[1] < window or labels.shape != (len(x),)
            or not np.isfinite(x).all() or labels.dtype.kind not in 'iu'
            or set(labels.tolist()) != {0, 1} or min(np.bincount(labels)) < 2
            or not 1 <= feature_count <= 6 or regularization <= 0):
        raise ValueError('expected labeled [trial,sample,8] microvolt data, two classes and >=2 trials/class')
    sos = np.asarray([signal.butter(2, band, btype='bandpass', fs=250, output='sos') for band in BANDS])
    q_sos = np.rint(sos[:, :, [0, 1, 2, 4, 5]]*2**28).astype(np.int32)
    csp = []
    for band in range(3):
        # Estimate CSP from the same quantized coefficient transfer function.
        coefficients = np.column_stack((q_sos[band, :, :3]/2**28, np.ones(2), q_sos[band, :, 3:]/2**28))
        filtered = signal.sosfilt(np.ascontiguousarray(coefficients), x, axis=1)
        covariance = []
        for trial in filtered:
            centered = trial-trial.mean(axis=0)
            cov = centered.T @ centered
            cov /= max(np.trace(cov), 1e-12)
            covariance.append(cov)
        covariance = np.asarray(covariance)
        a, b = [covariance[labels == value].mean(axis=0)+np.eye(8)*1e-3 for value in (0, 1)]
        eigenvalues, eigenvectors = np.linalg.eigh(a+b)
        whitening = (eigenvectors/np.sqrt(eigenvalues)).T
        _, vectors = np.linalg.eigh(whitening @ a @ whitening.T)
        weights = (vectors[:, [0, -1]].T @ whitening)
        weights *= .875/np.max(np.abs(weights))
        csp.append(np.rint(weights*2**14).astype(np.int32))
    base = EEGModel(q_sos, np.asarray(csp), np.zeros(6, np.int32), 0, window=window, hop=hop)
    features = trial_features(x, base).astype(np.float64)/4096
    mu, sd = features.mean(axis=0), np.maximum(features.std(axis=0), 1e-3)
    means = [features[labels == value].mean(axis=0) for value in (0, 1)]
    within = sum(features[labels == value].var(axis=0) for value in (0, 1))
    fisher = (means[1]-means[0])**2 / np.maximum(within, 1e-8)
    selected = np.sort(np.argsort(fisher, kind='stable')[-feature_count:])
    z = (features[:, selected]-mu[selected])/sd[selected]
    target = labels.astype(np.float64)*2-1

    def loss(theta):
        weight, bias = theta[:-1], theta[-1]
        margin = np.maximum(0, 1-target*(z @ weight+bias))
        derivative = -2*regularization*target*margin/len(z)
        return (.5*weight @ weight+regularization*np.mean(margin**2),
                np.r_[weight+z.T @ derivative, derivative.sum()])

    fit = optimize.minimize(loss, np.zeros(feature_count+1), jac=True, method='L-BFGS-B',
                            options=dict(maxiter=1000, ftol=1e-12))
    if not fit.success:
        raise ValueError('linear SVM optimization failed: '+fit.message)
    folded = np.zeros(6)
    folded[selected] = fit.x[:-1]/sd[selected]
    bias = float(fit.x[-1]-folded @ mu)
    scale = min(1., (2**23-1)/max(np.max(np.abs(folded))*4096, 1.))
    weights = np.rint(folded*scale*4096).astype(np.int32)
    bias_q24 = int(round(bias*scale*2**24))
    scores = np.rint(features*4096).astype(np.int64) @ weights.astype(np.int64)+bias_q24
    metadata = dict(training_trials=len(x), selected_features=selected.tolist(),
                    training_accuracy=float(np.mean((scores >= 0) == labels)),
                    classifier='L2 squared-hinge linear SVM', regularization=regularization,
                    training_window_policy='reset_per_trial_final_window',
                    training_input_sha256=hashlib.sha256(x.astype('<f8').tobytes()+labels.astype('<i4').tobytes()).hexdigest())
    return EEGModel(q_sos, np.asarray(csp), weights, bias_q24, window=window, hop=hop, metadata=metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='NPZ: trials_uv [N,T,8], labels [N], 0=left/1=right')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--window', type=int, default=500)
    parser.add_argument('--hop', type=int, default=125)
    parser.add_argument('--features', type=int, default=4)
    args = parser.parse_args()
    with np.load(args.input, allow_pickle=False) as data:
        model = train_model(data['trials_uv'], data['labels'], window=args.window,
                            hop=args.hop, feature_count=args.features)
    model.save(args.output)
    print('EXPORTED', args.output, model.identity)


if __name__ == '__main__':
    main()
