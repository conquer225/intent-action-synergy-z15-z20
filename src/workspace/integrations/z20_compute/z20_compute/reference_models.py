"""Original classifier teachers and analytic linear-to-ReLU conversion."""
import numpy as np


def linear_parameters(weight, bias):
    weight, bias = np.asarray(weight, float), np.asarray(bias, float)
    if weight.shape != (3, 180) or bias.shape != (3,) or not all(
            np.isfinite(a).all() for a in (weight, bias)):
        raise ValueError('expected finite SEED linear weights')
    w1, b1 = np.zeros((32, 180)), np.zeros(32)
    w2, b2 = np.zeros((3, 32)), bias.copy()
    w1[:3], w1[3:6] = weight, -weight
    w2[:, :3], w2[:, 3:6] = np.eye(3), -np.eye(3)
    return w1, b1, w2, b2


def fatigue_scores(model, features):
    values = np.asarray(features, float)
    if values.ndim != 2 or values.shape[1] != 20 or not np.isfinite(values).all():
        raise ValueError('finite N by 20 fatigue classifier inputs required')
    estimate = np.full(len(values), float(model['baseline_prediction']))
    for tree in model['trees']:
        indices = np.zeros(len(values), dtype=int)
        active = np.arange(len(values))
        for _ in range(len(tree)):
            if not len(active): break
            nodes = np.array([tree[index] for index in indices[active]])
            leaf = nodes[:, 6].astype(bool)
            estimate[active[leaf]] += nodes[leaf, 0]
            active, nodes = active[~leaf], nodes[~leaf]
            if not len(active): break
            go_left = values[active, nodes[:, 1].astype(int)] <= nodes[:, 2]
            indices[active] = np.where(go_left, nodes[:, 3], nodes[:, 4]).astype(int)
        else:
            raise ValueError('cyclic or invalid teacher tree')
    return np.clip(estimate, 0., 1.)


def fatigue_labels(model, features):
    return np.searchsorted(np.asarray(model['thresholds']), fatigue_scores(model, features), side='right')
