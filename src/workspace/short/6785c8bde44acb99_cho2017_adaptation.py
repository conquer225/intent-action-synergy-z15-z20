"""Fixed pre-cue ratios and prefix-only covariance alignment; no parameter search."""
from dataclasses import dataclass

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.preprocessing import StandardScaler

from mi_spatial_development import spatial_filters
from mi_spatial import projected_features

METHODS = ('CSP_LDA', 'ERD_LDA', 'EA_CSP_LDA', 'EA_CSP_ERD_LDA')
PREFIX_TRIALS = 60


def log_power_ratio(baseline_variance, task_variance):
    baseline = np.asarray(baseline_variance, dtype=np.float64)
    task = np.asarray(task_variance, dtype=np.float64)
    if baseline.shape != task.shape or baseline.ndim != 3 or baseline.shape[1:] != (7, 8):
        raise ValueError('Matching N x 7 x 8 band/channel variances required')
    if not np.isfinite(baseline).all() or not np.isfinite(task).all() or np.any(baseline < 0) or np.any(task < 0):
        raise ValueError('Finite nonnegative variance required')
    return np.log(np.maximum(task[:, :2], 1e-12) / np.maximum(baseline[:, :2], 1e-12)).reshape(len(task), 16)


def alignment_reference(covariances, original_order):
    """Labels are deliberately not an input. Only the original first 60 trials count."""
    values = np.asarray(covariances, dtype=np.float64)
    order = np.asarray(original_order)
    if values.ndim != 3 or values.shape[1:] != (8, 8) or order.shape != (len(values),):
        raise ValueError('Person-specific N x 8 x 8 covariance and order required')
    if not np.issubdtype(order.dtype, np.integer) or len(np.unique(order)) != len(order):
        raise ValueError('Unique integral original trial orders required')
    selected = np.flatnonzero((order >= 0) & (order < PREFIX_TRIALS))
    if len(selected) != PREFIX_TRIALS or not np.array_equal(np.sort(order[selected]), np.arange(PREFIX_TRIALS)):
        raise ValueError('All original first 60 trials required')
    # Sorting also makes the floating-point summation order independent of storage order.
    prefix = values[selected[np.argsort(order[selected])]]
    if not np.isfinite(prefix).all():
        raise ValueError('Non-finite calibration covariance')
    np.testing.assert_allclose(prefix, prefix.transpose(0, 2, 1), atol=1e-10, rtol=1e-10)
    np.testing.assert_allclose(np.trace(prefix, axis1=1, axis2=2), 1, atol=1e-10)
    if np.linalg.eigvalsh(prefix).min() < -1e-10:
        raise ValueError('Calibration covariance must be positive semidefinite')
    mean = prefix.mean(axis=0)
    regularized = .9 * mean + .1 * np.eye(8) / 8
    eigenvalues, vectors = np.linalg.eigh(regularized)
    if eigenvalues.min() <= 0:
        raise ValueError('Non-positive regularized reference')
    whitening = (vectors / np.sqrt(eigenvalues)) @ vectors.T
    return regularized, whitening


def align_covariances(covariances, whitening):
    values = np.asarray(covariances, dtype=np.float64)
    matrix = np.asarray(whitening, dtype=np.float64)
    if values.ndim != 3 or values.shape[1:] != (8, 8) or matrix.shape != (8, 8):
        raise ValueError('N x 8 x 8 covariance and 8 x 8 whitening required')
    if not np.isfinite(values).all() or not np.isfinite(matrix).all():
        raise ValueError('Non-finite alignment input')
    result = matrix @ values @ matrix.T
    result = (result + result.transpose(0, 2, 1)) / 2
    trace = np.trace(result, axis1=1, axis2=2)
    if np.any(trace <= 1e-12):
        raise ValueError('Zero-energy aligned trial')
    return result / trace[:, None, None]


@dataclass
class Fitted:
    method: str
    filters: np.ndarray
    scaler: StandardScaler
    classifier: LinearDiscriminantAnalysis


def features(covariances, ratios, method, filters):
    if method not in METHODS:
        raise ValueError('Method outside the four locked conditions')
    if covariances.ndim != 4 or covariances.shape[1:] != (7, 8, 8) or ratios.shape != (len(covariances), 16):
        raise ValueError('Matching frozen covariance and 16 ratio features required')
    if method == 'ERD_LDA':
        return ratios
    csp = projected_features(covariances[:, [2]], filters)
    return np.concatenate([csp, ratios], axis=1) if method == 'EA_CSP_ERD_LDA' else csp


def fit(covariances, ratios, labels, method):
    if method not in METHODS or set(labels) != {0, 1}:
        raise ValueError('Locked method and both source-person classes required')
    filters = (np.empty((0, 4, 8)) if method == 'ERD_LDA'
               else spatial_filters(covariances, labels, 'CSP_LDA'))
    values = features(covariances, ratios, method, filters)
    if not np.isfinite(values).all():
        raise ValueError('Non-finite training feature')
    scaler = StandardScaler().fit(values)
    classifier = LinearDiscriminantAnalysis(solver='lsqr', shrinkage='auto').fit(scaler.transform(values), labels)
    return Fitted(method, filters, scaler, classifier)


def predict(covariances, ratios, fitted):
    values = features(covariances, ratios, fitted.method, fitted.filters)
    standardized = (values - fitted.scaler.mean_) / fitted.scaler.scale_
    actual = standardized @ fitted.classifier.coef_[0] + fitted.classifier.intercept_[0]
    expected = fitted.classifier.decision_function(fitted.scaler.transform(values))
    np.testing.assert_allclose(actual, expected, atol=1e-10, rtol=1e-10)
    labels = (actual > 0).astype(int)
    np.testing.assert_array_equal(labels, fitted.classifier.predict(fitted.scaler.transform(values)))
    return labels, actual, float(np.max(np.abs(actual - expected)))
