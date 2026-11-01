"""Strict participant-grouped LOSO audit of the 8-channel ViFormer architecture.

Uses the exact 8x5 deployable DE feature layout already cached by
``evaluate_channel_sets.py``.  One development participant per fold is used
for early stopping and class-threshold selection; the held-out participant is
never used during fitting or tuning.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


REFERENCE_DIR = Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")
VIFORMER_ROOT = Path(r"D:\ican\整理\2026计设\2026039959-02 素材与源码\2026039959-素材源码\ViFormerNet")
if str(REFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(REFERENCE_DIR))

from fatigue_reference import SOURCE_CHANNEL_ORDER_17, perclos_to_class, ratio_to_class, tune_ratio_thresholds
from train_seedvig_8ch_calibrated_loso import CALIBRATION_WINDOWS, calibrate_recording, smooth_features
from validate_seedvig_loso import DEFAULT_DATASET_ROOT, discover_pairs, participant_id


CHANNELS_8 = ("FT7", "FT8", "CP1", "CP2", "P1", "PZ", "PO3", "O1")
REGIONS_8 = [[0, 1], [2, 3], [4, 5], [6], [7]]
CHANNELS_17 = tuple(SOURCE_CHANNEL_ORDER_17)
REGIONS_17 = [[0, 1, 2, 3, 4, 5], [6, 7], [8, 9, 10], [11, 12, 13], [14, 15, 16]]


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("strict_viformer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def build_model(module, device: torch.device, channels: tuple[str, ...], regions: list[list[int]]) -> nn.Module:
    model = module.VIGConformerRegressionModel(
        num_channels=len(channels),
        d_model=64,
        num_conformer_blocks=4,
        n_head=4,
        conv_kernel_size=5,
        expansion_factor=4,
        dropout=0.3,
        use_region_hierarchy=True,
        use_dual_branch=True,
        region_groups=regions,
        region_pool_mode="mean",
    ).to(device)
    with torch.no_grad():
        model(torch.zeros(1, len(channels), 5, device=device), return_aux=True, return_ord=True)
    return model


def arrays(names: list[str], recordings: dict) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.concatenate([recordings[name]["x"] for name in names]).astype(np.float32),
        np.concatenate([recordings[name]["y"] for name in names]).astype(np.float32),
    )


def normalize(train: np.ndarray, *others: np.ndarray):
    mean = train.mean(axis=0, keepdims=True)
    std = train.std(axis=0, keepdims=True)
    std[std < 1e-6] = 1.0
    return ((train - mean) / std, *[(item - mean) / std for item in others])


def ordinal(y: np.ndarray) -> np.ndarray:
    return np.column_stack((y >= 0.35, y >= 0.70)).astype(np.float32)


def predict(model: nn.Module, x: np.ndarray, device: torch.device, batch_size: int) -> np.ndarray:
    loader = DataLoader(torch.from_numpy(x), batch_size=batch_size, shuffle=False)
    output = []
    model.eval()
    with torch.inference_mode():
        for batch in loader:
            output.append(model(batch.to(device)).detach().cpu().numpy())
    return np.clip(np.concatenate(output), 0.0, 1.0)


def metrics(y: np.ndarray, prediction: np.ndarray, predicted_class: np.ndarray) -> dict:
    return {
        "pearson": float(pearsonr(y, prediction).statistic),
        "spearman": float(spearmanr(y, prediction).statistic),
        "rmse": float(np.sqrt(mean_squared_error(y, prediction))),
        "mae": float(mean_absolute_error(y, prediction)),
        "accuracy": float(accuracy_score(perclos_to_class(y), predicted_class)),
        "macro_f1": float(f1_score(perclos_to_class(y), predicted_class, labels=[0, 1, 2], average="macro", zero_division=0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--cache", type=Path, default=Path(__file__).with_name("cache_all17"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--channel-mode", choices=("8", "17"), default="8")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--fold-limit", type=int, default=0, help="0 means all folds")
    args = parser.parse_args()

    channels, regions = ((CHANNELS_8, REGIONS_8) if args.channel_mode == "8" else
                         (CHANNELS_17, REGIONS_17))
    if args.output is None:
        name = "viformer_strict_loso.json" if args.channel_mode == "8" else "viformer_strict_loso_17ch.json"
        args.output = Path(__file__).with_name(name)

    seed_all(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    module = load_module(VIFORMER_ROOT / "Ablation" / "ViFormerNet(9subject)(all).py")
    pairs = discover_pairs(args.dataset_root)
    all_channels = list(SOURCE_CHANNEL_ORDER_17)
    columns = []
    for channel in channels:
        index = all_channels.index(channel)
        columns.extend(range(index * 5, index * 5 + 5))

    groups: dict[str, list[str]] = {}
    recordings = {}
    for name, _, _ in pairs:
        groups.setdefault(participant_id(name), []).append(name)
        cache_path = args.cache / f"{name}.npz"
        if not cache_path.exists():
            raise FileNotFoundError(f"Run evaluate_channel_sets.py first: {cache_path}")
        with np.load(cache_path, allow_pickle=False) as item:
            selected = item["features"][:, columns]
            calibrated, _, _ = calibrate_recording(selected)
            recordings[name] = {
                "x": smooth_features(calibrated[CALIBRATION_WINDOWS:]).reshape(-1, len(channels), 5),
                "y": item["perclos"][CALIBRATION_WINDOWS:],
            }

    participant_ids = sorted(groups, key=int)
    if args.fold_limit:
        participant_ids = participant_ids[: args.fold_limit]
    fold_results = []
    all_y, all_prediction, all_classes = [], [], []
    for fold_index, held_out in enumerate(participant_ids, 1):
        available = [pid for pid in sorted(groups, key=int) if pid != held_out]
        # Threshold optimization needs all three classes. Select only from
        # development participants that contain them; the held-out participant
        # remains completely untouched.
        eligible_validation = []
        for pid in available:
            candidate_y = np.concatenate([recordings[name]["y"] for name in groups[pid]])
            if len(np.unique(perclos_to_class(candidate_y))) == 3:
                eligible_validation.append(pid)
        if not eligible_validation:
            raise RuntimeError("No development participant contains all three classes")
        validation = eligible_validation[(int(held_out) - 1) % len(eligible_validation)]
        train_names = [name for name in recordings if participant_id(name) not in (held_out, validation)]
        validation_names = groups[validation]
        test_names = groups[held_out]
        train_x, train_y = arrays(train_names, recordings)
        val_x, val_y = arrays(validation_names, recordings)
        test_x, test_y = arrays(test_names, recordings)
        train_x, val_x, test_x = normalize(train_x, val_x, test_x)

        seed_all(1000 + int(held_out))
        model = build_model(module, device, channels, regions)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
        mse = nn.MSELoss()
        bce = nn.BCEWithLogitsLoss()
        dataset = TensorDataset(torch.from_numpy(train_x), torch.from_numpy(train_y), torch.from_numpy(ordinal(train_y)))
        loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, drop_last=False)
        best_state, best_rmse, stale, trained_epochs = None, float("inf"), 0, 0

        for epoch in range(args.epochs):
            model.train()
            for batch_x, batch_y, batch_ord in loader:
                batch_x, batch_y, batch_ord = batch_x.to(device), batch_y.to(device), batch_ord.to(device)
                optimizer.zero_grad(set_to_none=True)
                pred, aux, logits = model(batch_x, return_aux=True, return_ord=True)
                loss = mse(pred, batch_y) + 0.1 * mse(aux, batch_y) + 0.05 * bce(logits, batch_ord)
                loss.backward()
                optimizer.step()
            trained_epochs = epoch + 1
            val_prediction = predict(model, val_x, device, args.batch_size)
            val_rmse = float(np.sqrt(mean_squared_error(val_y, val_prediction)))
            if val_rmse < best_rmse - 1e-4:
                best_rmse = val_rmse
                best_state = copy.deepcopy(model.state_dict())
                stale = 0
            else:
                stale += 1
                if stale >= args.patience:
                    break

        if best_state is None:
            raise RuntimeError("No model checkpoint selected")
        model.load_state_dict(best_state)
        val_prediction = predict(model, val_x, device, args.batch_size)
        thresholds = tune_ratio_thresholds(val_prediction, perclos_to_class(val_y))
        test_prediction = predict(model, test_x, device, args.batch_size)
        test_classes = ratio_to_class(test_prediction, thresholds)
        result = metrics(test_y, test_prediction, test_classes)
        result.update({"held_out": held_out, "validation": validation, "epochs": trained_epochs, "thresholds": list(thresholds)})
        fold_results.append(result)
        all_y.append(test_y)
        all_prediction.append(test_prediction)
        all_classes.append(test_classes)
        print(f"fold {fold_index:02d}/{len(participant_ids):02d} test={held_out} val={validation} epochs={trained_epochs} f1={result['macro_f1']:.3f} pcc={result['pearson']:.3f}", flush=True)

    y = np.concatenate(all_y)
    prediction = np.concatenate(all_prediction)
    classes = np.concatenate(all_classes)
    payload = {
        "status": "complete" if not args.fold_limit else "partial_audit",
        "protocol": "participant-grouped outer LOSO; separate development participant for early stopping and threshold tuning; 120 s calibration excluded",
        "channels": list(channels),
        "architecture": f"dual-branch ViFormerNet/Conformer, {len(channels)} channels, d_model=64, 4 blocks",
        "device": str(device),
        "folds": fold_results,
        "aggregate": metrics(y, prediction, classes),
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["aggregate"], indent=2))
    print(f"Saved: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
