"""Audit observed receiver/display events using one local monotonic clock."""
import argparse
import json
import math
from pathlib import Path
import sys


def nonnegative_integer(value):
    return type(value) is int and value >= 0


def audit(path, ttl_ms):
    if not math.isfinite(ttl_ms) or ttl_ms <= 0:
        raise ValueError("ttl-ms must be finite and positive")
    session, epoch, sequence, latest = None, 0, -1, None
    seen_sessions, errors = set(), []
    previous_time, accepted_results, display_checks, events = -1., 0, 0, 0
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("event must be an object at line "+str(number))
        now = event.get("at_ms")
        if (type(now) not in (int, float) or not math.isfinite(now)
                or now < 0 or now < previous_time):
            raise ValueError("local monotonic time regressed or is invalid at line "+str(number))
        previous_time, events = now, events+1
        kind = event.get("event")
        error = None
        if kind == "connect":
            name, version = event.get("session"), event.get("epoch")
            if not isinstance(name, str) or not name or not nonnegative_integer(version):
                raise ValueError("connect needs session and nonnegative epoch")
            if name in seen_sessions:
                error = "reused_session"
            else:
                seen_sessions.add(name)
                session, epoch, sequence, latest = name, version, -1, None
        elif kind in ("mode", "disconnect", "heartbeat"):
            if session is None or event.get("session") != session:
                error = "lifecycle_session"
            elif kind == "mode":
                if not nonnegative_integer(event.get("epoch")):
                    raise ValueError("mode needs a nonnegative epoch")
                if event["epoch"] <= epoch:
                    error = "nonincreasing_epoch"
                else:
                    epoch, sequence, latest = event["epoch"], -1, None
            elif kind == "disconnect":
                session, sequence, latest = None, -1, None
            # A heartbeat never refreshes the age of a prediction.
        elif kind == "result":
            if type(event.get("accepted")) is not bool or type(event.get("valid")) is not bool:
                raise ValueError("result needs boolean accepted and valid")
            if event["accepted"]:
                if session is None or event.get("session") != session:
                    error = "accepted_old_session"
                elif event.get("epoch") != epoch or not nonnegative_integer(event.get("epoch")):
                    error = "accepted_old_epoch"
                elif not nonnegative_integer(event.get("sequence")) or event["sequence"] <= sequence:
                    error = "accepted_nonincreasing_sequence"
                elif event["valid"] and (not isinstance(event.get("source"), str) or not event["source"]):
                    raise ValueError("accepted valid result needs a source")
                else:
                    sequence = event["sequence"]
                    latest = event if event["valid"] else None
                    accepted_results += 1
        elif kind == "display":
            display_checks += 1
            if type(event.get("valid")) is not bool:
                raise ValueError("display needs boolean valid")
            if event["valid"]:
                if any(not nonnegative_integer(event.get(key)) for key in ("epoch", "sequence")):
                    error = "display_invalid_identity"
                elif session is None or latest is None:
                    error = "display_without_current_result"
                elif any(event.get(key) != latest.get(key) for key in ("session", "epoch", "sequence", "source")):
                    error = "display_identity"
                elif now-latest["at_ms"] >= ttl_ms:
                    error = "display_expired_result"
            elif event.get("class_id") is not None or event.get("scores") is not None:
                error = "invalid_display_retains_classification"
        else:
            raise ValueError("unknown event at line "+str(number))
        if error:
            errors.append(dict(line=number, kind=error))
    if not events or not display_checks:
        raise ValueError("trace must include events and at least one observed display state")
    return dict(passed=not errors, scope="offline_observed_session_trace", board_executed=False,
                ttl_ms=ttl_ms, events=events, display_checks=display_checks,
                accepted_results=accepted_results, errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--ttl-ms", type=float, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.trace, args.ttl_ms)
        code = 0 if report["passed"] else 1
    except (OSError, ValueError, OverflowError) as exc:
        report, code = dict(passed=False, scope="offline_observed_session_trace",
                            board_executed=False, error=str(exc)), 2
    print(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
