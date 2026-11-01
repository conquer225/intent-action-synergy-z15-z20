"""Audit the local 8-channel ViFormerNet checkpoint for Z15 deployment.

This script does not train or alter the source project.  It loads the trusted
local checkpoint, reconstructs the model, checks eager/TorchScript numerical
agreement, and records desktop CPU/GPU latency and artifact sizes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import tempfile
import time
from pathlib import Path

import numpy as np
import torch


DEFAULT_ROOT = Path(
    r"D:\ican\整理\2026计设\2026039959-02 素材与源码\2026039959-素材源码\ViFormerNet"
)


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("local_viformer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_model(module, checkpoint: dict) -> torch.nn.Module:
    hp = checkpoint["hyperparams"]
    model = module.VIGConformerRegressionModel(
        num_channels=int(checkpoint["num_channels"]),
        d_model=int(hp["d_model"]),
        num_conformer_blocks=int(hp["num_conformer_blocks"]),
        n_head=int(hp["n_head"]),
        conv_kernel_size=int(hp["conv_kernel_size"]),
        expansion_factor=int(hp["expansion_factor"]),
        dropout=float(hp["model_dropout"]),
        use_region_hierarchy=True,
        use_dual_branch=True,
        region_groups=checkpoint["virtual_region_groups"],
        region_pool_mode="mean",
    )
    # Lazy layers must be materialized before state_dict loading.
    model.eval()
    with torch.inference_mode():
        model(torch.zeros(1, 8, 5), return_aux=True, return_ord=True)
    model.load_state_dict(checkpoint["model_state_dict"])
    return model.eval()


class DeploymentOutput(torch.nn.Module):
    """Expose only the scalar PERCLOS estimate needed by the board."""

    def __init__(self, model: torch.nn.Module):
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)


def benchmark(model: torch.nn.Module, sample: torch.Tensor, repeats: int) -> dict:
    latencies = []
    with torch.inference_mode():
        for _ in range(20):
            model(sample)
        if sample.is_cuda:
            torch.cuda.synchronize()
        for _ in range(repeats):
            start = time.perf_counter_ns()
            model(sample)
            if sample.is_cuda:
                torch.cuda.synchronize()
            latencies.append((time.perf_counter_ns() - start) / 1e6)
    return {
        "median_ms": statistics.median(latencies),
        "p95_ms": float(np.percentile(latencies, 95)),
        "mean_ms": statistics.mean(latencies),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("audit.json"))
    parser.add_argument("--repeats", type=int, default=300)
    args = parser.parse_args()

    source = args.root / "Ablation" / "ViFormerNet(9subject)(all).py"
    checkpoint_path = args.root / "route_b_8ch_model.pth"
    module = load_module(source)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    base = DeploymentOutput(build_model(module, checkpoint)).eval()
    sample = torch.linspace(-2.0, 2.0, 40, dtype=torch.float32).reshape(1, 8, 5)

    with torch.inference_mode():
        reference = base(sample)
    # PyTorch switches MultiheadAttention to an inference fast path after the
    # first invocation, so its automatic graph-to-graph trace check is noisy.
    # We verify the actual output numerically below instead.
    traced = torch.jit.trace(base, sample, strict=False, check_trace=False)
    traced = torch.jit.freeze(traced.eval())
    with torch.inference_mode():
        traced_output = traced(sample)

    with tempfile.TemporaryDirectory() as directory:
        trace_path = Path(directory) / "viformer_8ch_trace.pt"
        traced.save(str(trace_path))
        trace_bytes = trace_path.stat().st_size

    parameter_count = sum(p.numel() for p in base.parameters())
    parameter_bytes = sum(p.numel() * p.element_size() for p in base.parameters())
    result = {
        "checkpoint": str(checkpoint_path),
        "channels": checkpoint["virtual_channel_names"],
        "input_shape": [1, 8, 5],
        "parameters": parameter_count,
        "fp32_parameter_bytes": parameter_bytes,
        "checkpoint_bytes": checkpoint_path.stat().st_size,
        "torchscript_bytes": trace_bytes,
        "torchscript_max_abs_error": float(torch.max(torch.abs(reference - traced_output))),
        "desktop_cpu": benchmark(traced, sample, args.repeats),
        "cuda_available": torch.cuda.is_available(),
    }
    if torch.cuda.is_available():
        gpu_model = DeploymentOutput(build_model(module, checkpoint)).eval().cuda()
        result["desktop_gpu"] = benchmark(gpu_model, sample.cuda(), args.repeats)
        result["gpu_name"] = torch.cuda.get_device_name(0)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
