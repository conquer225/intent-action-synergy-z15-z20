"""Evaluate the packaged ViFormerNet checkpoints on their own documented split."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import scipy.io as sio
import torch
from scipy.stats import pearsonr
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split


ROOT = Path(r"D:\ican\整理\2026计设\2026039959-02 素材与源码\2026039959-素材源码\ViFormerNet")
SOURCE = ROOT / "Ablation" / "ViFormerNet(9subject)(all).py"
DATA = ROOT / "Ablation" / "10subject.mat"
CHANNELS_8 = [0, 1, 6, 7, 8, 9, 11, 14]
REGIONS_17 = [[0, 1, 2, 3, 4, 5], [6, 7], [8, 9, 10], [11, 12, 13], [14, 15, 16]]
REGIONS_8 = [[0, 1], [2, 3], [4, 5], [6], [7]]


def load_module():
    spec = importlib.util.spec_from_file_location("packaged_viformer", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build(module, checkpoint, channels, regions):
    params = checkpoint["hyperparams"]
    model = module.VIGConformerRegressionModel(
        num_channels=channels,
        d_model=params["d_model"],
        num_conformer_blocks=params["num_conformer_blocks"],
        n_head=params["n_head"],
        conv_kernel_size=params["conv_kernel_size"],
        expansion_factor=params["expansion_factor"],
        dropout=params["model_dropout"],
        use_region_hierarchy=True,
        use_dual_branch=True,
        region_groups=regions,
        region_pool_mode="mean",
    )
    with torch.no_grad():
        model(torch.zeros(1, channels, 5), return_aux=True, return_ord=True)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model


def evaluate(module, features, labels, checkpoint_path, regions):
    _, test_x, _, test_y = train_test_split(features, labels, test_size=0.1, random_state=42)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    normalized = np.zeros_like(test_x, dtype=np.float32)
    for ch, scaler in enumerate(checkpoint["scalers"]):
        normalized[:, ch, :] = scaler.transform(test_x[:, ch, :])
    model = build(module, checkpoint, normalized.shape[1], regions)
    with torch.inference_mode():
        prediction = model(torch.from_numpy(normalized)).numpy()
    true_class = module.perclos_to_class(test_y, [0.35, 0.7])
    predicted_class = module.perclos_to_class(prediction, checkpoint["thresholds"])
    return {
        "pearson": float(pearsonr(test_y, prediction).statistic),
        "rmse": float(np.sqrt(mean_squared_error(test_y, prediction))),
        "mae": float(mean_absolute_error(test_y, prediction)),
        "accuracy": float(accuracy_score(true_class, predicted_class)),
        "macro_f1": float(f1_score(true_class, predicted_class, labels=[0, 1, 2], average="macro", zero_division=0)),
        "thresholds": [float(value) for value in checkpoint["thresholds"]],
    }


def main():
    module = load_module()
    data = sio.loadmat(DATA)
    raw = data["X"].astype(np.float32)
    labels = data["Y"].astype(np.float32).ravel()
    features_17 = module.extract_band_de_features(raw, fs=200, window_len=1600).astype(np.float32)
    outputs = {
        "packaged_17ch": evaluate(module, features_17, labels, ROOT / "Ablation" / "10all.pth", REGIONS_17),
        "packaged_8ch": evaluate(module, features_17[:, CHANNELS_8, :], labels, ROOT / "route_b_8ch_model.pth", REGIONS_8),
    }
    import json
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
