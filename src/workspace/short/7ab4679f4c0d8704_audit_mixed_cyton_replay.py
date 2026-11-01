"""Audit isolated mixed replay using metadata and decisions, not EEG labels."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "output/mixed_cyton_replay_20260927"


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    manifest = load("manifest.json")
    cases = {item["label"]: item for item in manifest["cases"]}
    baseline = load("recorded-baseline-primary_results.json")
    candidate = load("recorded-candidate-primary_results.json")
    repeated = load("recorded-candidate-repeat-primary_results.json")
    repeated_report = load("recorded-candidate-repeat-report.json")
    rows = [json.loads(line) for line in
            (ROOT / "mixed-candidate-monitor.jsonl").read_text(encoding="utf-8").splitlines()]
    mixed = cases["mixed-candidate"]["report"]

    def status(row):
        return row.get("primary") or {}

    def shadow(row):
        return row.get("ssvep") or {}

    gap = [r for r in rows if status(r).get("reason") == "STREAM_IDLE"
           and shadow(r).get("state") == "no_data"]
    rail = [r for r in rows if shadow(r).get("state") == "signal_invalid"
            and shadow(r).get("reason") == "nonfinite_or_adc_rail"]
    warm_after_rail = [r for r in rows if shadow(r).get("packets_seen", 0) >= 8750
                       and shadow(r).get("state") == "warmup"]
    recovered = [r for r in rows if shadow(r).get("packets_seen", 0) >= 8750
                 and shadow(r).get("state") == "candidate_only"]
    first_recovered = min((shadow(r).get("packets_seen") for r in recovered), default=None)
    checks = {
        "recorded_primary_decisions_exactly_equal": baseline == candidate,
        "recorded_repeat_primary_decisions_exactly_equal": baseline == repeated,
        "recorded_transport_fully_consumed": all(
            cases[key]["report"]["packets_consumed"] == 6250
            for key in ("recorded-baseline", "recorded-candidate")),
        "recorded_repeat_transport_fully_consumed": repeated_report["packets_consumed"] == 6250,
        "mixed_transport_fully_consumed": mixed["packets_consumed"] == 17500,
        "mixed_queue_p95_under_500_ms": mixed["packet_input_age_p95_ms"] < 500,
        "mixed_queue_max_under_3000_ms": mixed["packet_input_age_max_ms"] < 3000,
        "short_gap_clears_primary_and_ssvep": bool(gap) and all(
            not status(r).get("valid") and not shadow(r).get("valid")
            and shadow(r).get("frequency_hz") is None for r in gap),
        "rail_clears_ssvep_candidate": bool(rail) and all(
            not shadow(r).get("valid") and shadow(r).get("frequency_hz") is None
            and shadow(r).get("control_enabled") is False for r in rail),
        "rail_primary_not_valid": bool(rail) and all(not status(r).get("valid") for r in rail),
        "post_rail_warmup_observed": bool(warm_after_rail),
        "post_rail_candidate_after_660_fresh_samples": first_recovered is not None
        and first_recovered >= 8750 + 660,
        "mixed_not_live_and_never_control": all(
            shadow(r).get("source") == "replay" and not shadow(r).get("control_enabled")
            and status(r).get("source") == "offline_replay_not_live"
            for r in rows if shadow(r) and status(r)),
        "production_service_unchanged": manifest.get("production_before")
        == manifest.get("production_after"),
    }
    result = {"checks": checks, "all_passed": all(checks.values()),
              "gap_rows": len(gap), "rail_rows": len(rail),
              "post_rail_warmup_rows": len(warm_after_rail),
              "first_recovered_packet": first_recovered,
              "recorded_primary_outputs": len(baseline),
              "mixed_packet_age_p95_ms": mixed["packet_input_age_p95_ms"],
              "mixed_packet_age_max_ms": mixed["packet_input_age_max_ms"],
              "recorded_baseline_p95_ms": cases["recorded-baseline"]["report"]["packet_input_age_p95_ms"],
              "recorded_candidate_p95_ms": cases["recorded-candidate"]["report"]["packet_input_age_p95_ms"],
              "recorded_candidate_repeat_p95_ms": repeated_report["packet_input_age_p95_ms"]}
    (ROOT / "audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
