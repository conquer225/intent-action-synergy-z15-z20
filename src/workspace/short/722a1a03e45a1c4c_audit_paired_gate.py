"""Audit the frozen two-ARM/two-PL full-loop replay promotion gate.

This reads captured reports only; it never talks to the board or changes the
production service. The criteria are frozen in PL_PAIRED_GATE_PLAN_20260930.md.
"""

import argparse
import json
import statistics
from pathlib import Path


RUNS = ("arm_replay_80s_paired_a1", "arm_replay_80s_paired_a2",
        "pl_replay_80s_paired_p1", "pl_replay_80s_paired_p2")
EXPECTED_PACKETS = 20_000
QUALITY_TOLERANCE = 0.01
MAX_INPUT_AGE_MS = 500.0
REQUIRED_IMPROVEMENT = 0.10


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def signature(result):
    sqi = result.get("sqi") or {}
    return {
        "state": result.get("state"),
        "reason": result.get("reason"),
        "valid": result.get("valid"),
        "signal_quality": result.get("signal_quality"),
        "bad_channels": sqi.get("bad_channels"),
        "usable_channels": sqi.get("usable_channels"),
        "calibration_current": result.get("calibration_current"),
        "emotion_state": (result.get("emotion") or {}).get("state"),
    }


def compare_outputs(reference, candidate):
    if len(reference) != len(candidate):
        return {"pass": False, "lengths": [len(reference), len(candidate)]}
    mismatches = []
    max_quality_difference = 0.0
    for index, (left, right) in enumerate(zip(reference, candidate)):
        left_result, right_result = left["result"], right["result"]
        if signature(left_result) != signature(right_result):
            mismatches.append(index)
        left_quality = (left_result.get("sqi") or {}).get("quality", [])
        right_quality = (right_result.get("sqi") or {}).get("quality", [])
        if len(left_quality) != len(right_quality):
            mismatches.append(index)
            continue
        if left_quality:
            max_quality_difference = max(
                max_quality_difference,
                max(abs(a - b) for a, b in zip(left_quality, right_quality)),
            )
    return {
        "pass": not mismatches and max_quality_difference <= QUALITY_TOLERANCE,
        "windows_including_start_stop": len(reference),
        "signature_mismatch_indices": sorted(set(mismatches)),
        "max_abs_sqi_quality_difference": round(max_quality_difference, 6),
    }


def audit(directory):
    captures = {}
    for name in RUNS:
        report = read_json(directory / f"{name}_report.json")
        stages = read_json(directory / f"{name}_stages.json")["stages"]
        results = read_json(directory / f"{name}_primary_results.json")
        filter_wall = sum(
            stages.get(key, {}).get("wall_s", 0.0)
            for key in ("primary_filter", "pl_primary_filter")
        )
        captures[name] = {
            "backend": report["filter_backend"],
            "packets_consumed": report["packets_consumed"],
            "packets_expected": report["packets_expected"],
            "input_age_p95_ms": report["packet_input_age_p95_ms"],
            "input_age_max_ms": report["packet_input_age_max_ms"],
            "total_cpu_s": report["parent_cpu_seconds"] + report["children_cpu_seconds"],
            "wall_s": report["wall_seconds"],
            "filter_stage_wall_s": filter_wall,
            "ssvep_packet_stage_wall_s": stages["ssvep_packet"]["wall_s"],
            "ssvep_quality_stage_wall_s": stages["ssvep_quality"]["wall_s"],
            "ssvep_cca_stage_wall_s": stages["ssvep_cca_scores"]["wall_s"],
            "monitor_errors": report["monitor_errors"],
            "remaining_children": report["remaining_children"],
            "error": report["error"],
            "clean_run": (
                report["packets_consumed"] == EXPECTED_PACKETS
                and report["packets_expected"] == EXPECTED_PACKETS
                and not report["monitor_errors"]
                and not report["remaining_children"]
                and not report["error"]
            ),
            "results": results,
        }
    baseline = {
        key: statistics.median(captures[name][key] for name in RUNS[:2])
        for key in ("input_age_p95_ms", "input_age_max_ms", "total_cpu_s",
                    "wall_s", "filter_stage_wall_s")
    }
    reference = captures[RUNS[0]]["results"]
    comparisons = {
        name: compare_outputs(reference, captures[name]["results"])
        for name in RUNS[1:]
    }
    pl_decisions = {}
    for name in RUNS[2:]:
        run = captures[name]
        pl_decisions[name] = {
            "input_age_p95_improvement_fraction": (
                baseline["input_age_p95_ms"] - run["input_age_p95_ms"]
            ) / baseline["input_age_p95_ms"],
            "cpu_improvement_fraction": (
                baseline["total_cpu_s"] - run["total_cpu_s"]
            ) / baseline["total_cpu_s"],
            "input_age_max_within_limit": run["input_age_max_ms"] <= MAX_INPUT_AGE_MS,
            "output_parity": comparisons[name]["pass"],
        }
        pl_decisions[name]["promotion_metrics_pass"] = (
            run["clean_run"]
            and pl_decisions[name]["input_age_p95_improvement_fraction"] >= REQUIRED_IMPROVEMENT
            and pl_decisions[name]["cpu_improvement_fraction"] >= REQUIRED_IMPROVEMENT
            and pl_decisions[name]["input_age_max_within_limit"]
            and pl_decisions[name]["output_parity"]
        )
    for run in captures.values():
        del run["results"]
    return {
        "criteria": {
            "minimum_fractional_improvement_each_pl_run": REQUIRED_IMPROVEMENT,
            "max_input_age_ms": MAX_INPUT_AGE_MS,
            "max_abs_sqi_quality_difference": QUALITY_TOLERANCE,
            "expected_packets": EXPECTED_PACKETS,
        },
        "runs": captures,
        "arm_two_run_median": baseline,
        "output_comparisons_against_arm_a1": comparisons,
        "pl_decisions": pl_decisions,
        "promote_pl_filter": all(item["promotion_metrics_pass"] for item in pl_decisions.values()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reports_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.reports_dir)
    serialized = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
