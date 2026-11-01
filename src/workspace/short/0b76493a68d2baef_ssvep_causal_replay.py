"""Finite, isolated RAW Wang-recording replay, explicitly not live Cyton EEG.

No network, serial, GPIO, DMA, overlay, service, or production-status writes.
Identical file runs on PC and ARM; coefficients are frozen on PC beforehand.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy

from ssvep_stream import SSVEPStream


def fault_checks(raw, config, sos):
    checks = {}
    stream = SSVEPStream(config, sos)
    stream.push(raw[:700], 0)
    checks["had_result_before_gap"] = stream.latest is not None
    stream.push(raw[:100], 705)
    checks["gap_clears_result"] = stream.latest is None and stream.reset_reason == "sample_discontinuity"
    checks["gap_warmup_no_result"] = not stream.push(raw[100:659], 805)
    events = stream.push(raw[659:660], 1364)
    checks["gap_recovers_at_new_full_window"] = len(events) == 1 and events[0]["window_start_index"] == 865
    stream.disconnect()
    checks["disconnect_clears_result"] = stream.latest is None and stream.status == "no_data"
    invalid = raw[:10].copy()
    invalid[3,6] = np.nan
    stream.push(invalid, 0)
    checks["nonfinite_clears_result"] = stream.latest is None and stream.status == "signal_invalid"
    stream.reset("flat_test")
    flat = stream.push(np.zeros((700,8)),0)
    checks["flat_rejected"] = len(flat) == 1 and flat[0]["target_index"] is None
    if not all(checks.values()):
        raise AssertionError(checks)
    return checks


def run(input_path, protocol, coefficients, output, paced=False):
    config = json.loads(protocol.read_text(encoding="utf-8"))
    sos = np.load(coefficients, allow_pickle=False)
    raw = np.load(input_path, allow_pickle=False)["raw"]
    if raw.ndim != 3 or raw.shape[-1] != 8:
        raise ValueError("Expected trial x samples x fixed eight channels")
    output.mkdir(parents=True, exist_ok=True)
    all_filtered, all_scores, endpoints, predictions = [], [], [], []
    chunks_ms, decode_push_ms = [], []
    feed_lateness_ms, completion_lateness_ms = [], []
    filter_seconds, decode_seconds = 0.0, 0.0
    total_cpu = time.process_time()
    began = time.perf_counter()
    for trial, samples in enumerate(raw):
        stream = SSVEPStream(config, sos)
        filtered = []
        for first in range(0, len(samples), config["batch_samples"]):
            batch_end = min(first + config["batch_samples"], len(samples))
            due = began + (trial * raw.shape[1] + batch_end) / config["sample_rate_hz"]
            if paced:
                delay = due - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                feed_lateness_ms.append(max(0.0,1000 * (time.perf_counter() - due)))
            tick = time.perf_counter()
            events = stream.push(samples[first:first + config["batch_samples"]], first)
            elapsed_ms = 1000 * (time.perf_counter() - tick)
            if paced:
                completion_lateness_ms.append(max(0.0,1000 * (time.perf_counter() - due)))
            chunks_ms.append(elapsed_ms)
            if events:
                decode_push_ms.append(elapsed_ms)
            filtered.append(stream.last_filtered.copy())
            for event in events:
                all_scores.append(event["scores"] if event["scores"] is not None else [np.nan] * len(config["frequencies_hz"]))
                endpoints.append([trial, event["window_start_index"], event["window_end_index_exclusive"]])
                predictions.append(event["target_index"] if event["target_index"] is not None else -1)
                if event["control_enabled"] or event["source"] != "replay_candidate":
                    raise AssertionError("Replay must not enable control")
        all_filtered.append(np.concatenate(filtered))
        filter_seconds += stream.filter_seconds
        decode_seconds += stream.decode_seconds
    wall_seconds = time.perf_counter() - began
    cpu_seconds = time.process_time() - total_cpu
    faults = fault_checks(raw[0], config, sos)
    chunk_array = np.array(chunks_ms)
    nominal_batch_ms = 1000 * config["batch_samples"] / config["sample_rate_hz"]
    backlog = 0.0
    max_backlog = 0.0
    for latency in chunks_ms:
        backlog = max(0.0, backlog + latency - nominal_batch_ms)
        max_backlog = max(max_backlog, backlog)
    report = {
        "mode":"isolated_recorded_replay_not_live", "source_dataset":"Wang2016", "control_enabled":False,
        "processor":"CPU/ARM software only; no PL used", "trials":len(raw),
        "recorded_seconds":float(len(raw) * raw.shape[1] / config["sample_rate_hz"]),
        "wall_compute_seconds":wall_seconds, "process_cpu_seconds":cpu_seconds,
        "filter_seconds":filter_seconds, "cca_decode_seconds":decode_seconds,
        "chunks":len(chunks_ms), "decisions":len(predictions),
        "chunk_latency_ms":{"p50":float(np.median(chunk_array)), "p95":float(np.quantile(chunk_array,.95)),
                            "p99":float(np.quantile(chunk_array,.99)), "max":float(chunk_array.max())},
        "decode_push_ms_p95":float(np.quantile(decode_push_ms,.95)),
        "chunks_over_nominal_40ms":int(np.count_nonzero(chunk_array > nominal_batch_ms)),
        "simulated_queue_max_backlog_ms":max_backlog,
        "paced_at_sample_rate":paced,
        "timing_limit":"Recorded-sample replay only, not a UART/network/display deadline guarantee; external live services remain active. Queue simulation includes push only.",
        "fault_checks":faults,
        "versions":{"python":sys.version,"numpy":np.__version__,"scipy":scipy.__version__,"platform":platform.platform()},
    }
    if paced:
        report["paced_feed_lateness_ms"] = {"p95":float(np.quantile(feed_lateness_ms,.95)), "max":float(np.max(feed_lateness_ms))}
        report["paced_completion_lateness_ms"] = {"p95":float(np.quantile(completion_lateness_ms,.95)),
                                                  "max":float(np.max(completion_lateness_ms)), "last":completion_lateness_ms[-1]}
        report["completion_over_hop_200ms"] = int(np.count_nonzero(np.array(completion_lateness_ms) > 1000*config["hop_samples"]/config["sample_rate_hz"]))
    if sys.platform.startswith("linux"):
        import resource
        report["peak_process_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    np.savez_compressed(output / "arrays.npz", filtered=np.stack(all_filtered), scores=np.array(all_scores),
                        endpoints=np.array(endpoints), predictions=np.array(predictions), chunk_latency_ms=chunk_array)
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--coefficients", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--paced", action="store_true")
    args = parser.parse_args()
    run(args.input,args.protocol,args.coefficients,args.output,args.paced)
