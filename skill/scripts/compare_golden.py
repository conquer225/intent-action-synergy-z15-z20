"""Compare all numeric outputs only after checking input/model/quantization identity."""
import argparse
import json
import math
from pathlib import Path
import re
import sys

IDENTITY = ("input_sha256", "model_sha256", "quantization_id", "source")


def reject_constant(value):
    raise ValueError("non-finite JSON number: "+value)


def load_records(path):
    records = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line, parse_constant=reject_constant)
        if not isinstance(item, dict):
            raise ValueError("record must be a JSON object at line "+str(number))
        for name in ("case_id", "source", "quantization_id", "backend"):
            if not isinstance(item.get(name), str) or not item[name].strip():
                raise ValueError("missing "+name+" at line "+str(number))
        for name in ("input_sha256", "model_sha256"):
            if not isinstance(item.get(name), str) or not re.fullmatch("[0-9a-f]{64}", item[name]):
                raise ValueError("invalid "+name+" at line "+str(number))
        values = item.get("values")
        if (not isinstance(values, list) or not values
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)):
            raise ValueError("values must be a nonempty flat finite numeric vector")
        if item["case_id"] in records:
            raise ValueError("duplicate case_id: "+item["case_id"])
        records[item["case_id"]] = item
    if not records:
        raise ValueError("empty record file")
    return records


def compare(golden_path, actual_path, *, atol=0.0, rtol=0.0, actual_backend=None):
    if not all(math.isfinite(v) and v >= 0 for v in (atol, rtol)):
        raise ValueError("tolerances must be finite and nonnegative")
    golden, actual = load_records(golden_path), load_records(actual_path)
    errors, compared_cases, compared_values = [], 0, 0
    if set(golden) != set(actual):
        errors.append(dict(kind="case_set", missing=sorted(set(golden)-set(actual)),
                           extra=sorted(set(actual)-set(golden))))
    for name in sorted(set(golden) & set(actual)):
        reference, observed = golden[name], actual[name]
        fields = [key for key in IDENTITY if reference[key] != observed[key]]
        if fields:
            errors.append(dict(case_id=name, kind="identity", fields=fields))
            continue
        if actual_backend is not None and observed["backend"] != actual_backend:
            errors.append(dict(case_id=name, kind="backend", actual=observed["backend"]))
            continue
        if len(reference["values"]) != len(observed["values"]):
            errors.append(dict(case_id=name, kind="length"))
            continue
        compared_cases += 1
        for index, (expected, value) in enumerate(zip(reference["values"], observed["values"])):
            compared_values += 1
            # Exact integers stay integers; converting INT64 to float can hide a difference of one.
            equal = (value == expected) if atol == 0 and rtol == 0 else abs(value-expected) <= atol+rtol*abs(expected)
            if not equal:
                errors.append(dict(case_id=name, kind="value", index=index,
                                   expected=expected, actual=value))
    return dict(passed=not errors, scope="offline_output_comparison", board_executed=False,
                compared_cases=compared_cases, compared_values=compared_values,
                atol=atol, rtol=rtol, actual_backends=sorted(set(v["backend"] for v in actual.values())),
                errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("golden", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument("--atol", type=float, default=0.)
    parser.add_argument("--rtol", type=float, default=0.)
    parser.add_argument("--actual-backend")
    args = parser.parse_args()
    try:
        report = compare(args.golden, args.actual, atol=args.atol, rtol=args.rtol,
                         actual_backend=args.actual_backend)
        code = 0 if report["passed"] else 1
    except (OSError, ValueError, OverflowError) as exc:
        report, code = dict(passed=False, scope="offline_output_comparison",
                            board_executed=False, error=str(exc)), 2
    print(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
