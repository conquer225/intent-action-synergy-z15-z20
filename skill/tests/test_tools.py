"""Exercise the portable command-line interfaces with independent fixtures."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bit_fixture(part="7z020clg400"):
    # Synthetic header for parser tests only; never a programmable bitstream.
    data = bytes.fromhex("00090ff00ff00ff00ff0000001")
    for tag, value in ((b"a", b"fixture\0"), (b"b", part.encode()+b"\0"),
                       (b"c", b"2026/11/01\0"), (b"d", b"00:00:00\0")):
        data += tag+struct.pack(">H", len(value))+value
    return data+b"e"+struct.pack(">I", 4)+bytes.fromhex("aa995566")


class ToolTests(unittest.TestCase):
    def run_tool(self, name, *args):
        result = subprocess.run([sys.executable, str(ROOT/"scripts"/name),
                                 *map(str, args)], capture_output=True, text=True,
                                encoding="utf-8", timeout=15)
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def overlay_fixture(self, folder):
        root = Path(folder)
        bit = bit_fixture()
        hwh = (b'<SYSTEM><SYSTEMINFO DEVICE="7z020" PACKAGE="clg400"/>'
               b'<MODULES><MODULE INSTANCE="dma_0" FULLNAME="/dma_0"/></MODULES></SYSTEM>')
        (root/"demo.bit").write_bytes(bit)
        (root/"demo.hwh").write_bytes(hwh)
        manifest = dict(schema_version=1, build_id="independent-fixture",
                        target_part="7z020clg400", required_ips=["dma_0"],
                        bit=dict(path="demo.bit", sha256=digest(bit)),
                        hwh=dict(path="demo.hwh", sha256=digest(hwh)))
        path = root/"manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, manifest

    def test_matching_overlay_passes_static_check_without_claiming_board_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = self.overlay_fixture(folder)
            code, report = self.run_tool("check_overlay.py", path, "--part", "xc7z020clg400")
        self.assertEqual(code, 0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["bit_part"], "7z020clg400")
        self.assertFalse(report["board_executed"])

    def test_wrong_package_corrupted_file_and_missing_ip_are_rejected(self):
        for fault in ("package", "digest", "ip"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                path, manifest = self.overlay_fixture(folder)
                if fault == "package":
                    data = bit_fixture("7z020clg484")
                    (Path(folder)/"demo.bit").write_bytes(data)
                    manifest["bit"]["sha256"] = digest(data)
                elif fault == "digest":
                    (Path(folder)/"demo.bit").write_bytes(b"corrupt")
                else:
                    manifest["required_ips"] = ["not_present"]
                path.write_text(json.dumps(manifest), encoding="utf-8")
                code, report = self.run_tool("check_overlay.py", path, "--part", "7z020clg400")
                self.assertEqual(code, 1)
                self.assertFalse(report["passed"])

    def test_hwh_package_is_checked_even_when_its_new_hash_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            path, manifest = self.overlay_fixture(folder)
            hwh = (Path(folder)/"demo.hwh").read_bytes().replace(b"clg400", b"clg484")
            (Path(folder)/"demo.hwh").write_bytes(hwh)
            manifest["hwh"]["sha256"] = digest(hwh)
            path.write_text(json.dumps(manifest), encoding="utf-8")
            code, report = self.run_tool("check_overlay.py", path, "--part", "7z020clg400")
        self.assertEqual(code, 1)
        self.assertFalse(report["passed"])

    def golden_fixture(self, folder):
        # Literal outputs from the project's independent two-input diagnostic.
        record = dict(case_id="worked-2", source="synthetic:worked-diagnostic",
                      input_sha256=digest(bytes([3, 254])),
                      model_sha256=digest(b"independent-worked-model-fixture"),
                      quantization_id="int8-int32-relu-half-up-sat127-v1",
                      backend="PS_integer_reference", values=[3, 125, -3])
        golden, actual = Path(folder)/"golden.jsonl", Path(folder)/"actual.jsonl"
        golden.write_text(json.dumps(record)+"\n", encoding="utf-8")
        record["backend"] = "fixture_hardware_adapter"
        actual.write_text(json.dumps(record)+"\n", encoding="utf-8")
        return golden, actual, record

    def test_same_input_golden_output_matches_every_integer(self):
        with tempfile.TemporaryDirectory() as folder:
            golden, actual, _ = self.golden_fixture(folder)
            code, report = self.run_tool("compare_golden.py", golden, actual)
        self.assertEqual(code, 0)
        self.assertEqual(report["compared_cases"], 1)
        self.assertEqual(report["compared_values"], 3)
        self.assertTrue(report["passed"])
        self.assertFalse(report["board_executed"])

    def test_golden_rejects_altered_input_model_or_a_single_integer(self):
        for fault in ("input_sha256", "model_sha256", "quantization_id", "source", "values"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                golden, actual, record = self.golden_fixture(folder)
                record[fault] = [3, 124, -3] if fault == "values" else (
                    "0"*64 if fault.endswith("sha256") else "different")
                actual.write_text(json.dumps(record)+"\n", encoding="utf-8")
                code, report = self.run_tool("compare_golden.py", golden, actual)
                self.assertEqual(code, 1)
                self.assertFalse(report["passed"])
                self.assertEqual(report["errors"][0]["kind"], "value" if fault == "values" else "identity")

    def trace_fixture(self):
        return [dict(event="connect", at_ms=0, session="A", epoch=0),
                dict(event="result", at_ms=10, session="A", epoch=0, sequence=0,
                     accepted=True, valid=True, source="recorded:fixture"),
                dict(event="display", at_ms=11, session="A", epoch=0, sequence=0,
                     valid=True, source="recorded:fixture"),
                dict(event="mode", at_ms=20, session="A", epoch=1),
                dict(event="result", at_ms=21, session="A", epoch=0, sequence=1,
                     accepted=False, valid=True, source="recorded:fixture"),
                dict(event="display", at_ms=22, valid=False, class_id=None, scores=None),
                dict(event="disconnect", at_ms=30, session="A"),
                dict(event="connect", at_ms=31, session="B", epoch=0),
                dict(event="result", at_ms=32, session="B", epoch=0, sequence=0,
                     accepted=True, valid=True, source="recorded:new"),
                dict(event="display", at_ms=33, session="B", epoch=0, sequence=0,
                     valid=True, source="recorded:new")]

    def run_trace(self, rows, ttl=100):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"trace.jsonl"
            path.write_text("".join(json.dumps(row)+"\n" for row in rows), encoding="utf-8")
            return self.run_tool("check_session_trace.py", path, "--ttl-ms", ttl)

    def test_valid_trace_rejects_old_mode_and_clears_display_before_reconnect(self):
        code, report = self.run_trace(self.trace_fixture())
        self.assertEqual(code, 0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["display_checks"], 3)
        self.assertEqual(report["accepted_results"], 2)
        self.assertFalse(report["board_executed"])

    def test_display_rejects_boolean_in_place_of_epoch_or_sequence(self):
        for field in ("epoch", "sequence"):
            with self.subTest(field=field):
                rows = self.trace_fixture()
                rows[2][field] = False
                code, report = self.run_trace(rows)
                self.assertEqual(code, 1)
                self.assertFalse(report["passed"])

    def test_session_audit_detects_old_session_old_mode_and_duplicate_acceptance(self):
        for fault in ("session", "epoch", "sequence"):
            with self.subTest(fault=fault):
                rows = self.trace_fixture()
                if fault == "sequence":
                    repeated = dict(rows[1], at_ms=10.5)
                    rows.insert(2, repeated)
                else:
                    rows[4]["accepted"] = True
                    if fault == "session":
                        rows[4]["session"] = "retired-session"
                code, report = self.run_trace(rows)
                self.assertEqual(code, 1)
                self.assertFalse(report["passed"])

    def test_heartbeat_does_not_make_an_expired_result_fresh(self):
        rows = self.trace_fixture()[:3]
        rows.append(dict(event="heartbeat", at_ms=109, session="A"))
        rows.append(dict(rows[2], at_ms=110))
        code, report = self.run_trace(rows)
        self.assertEqual(code, 1)
        self.assertEqual(report["errors"][0]["kind"], "display_expired_result")

    def test_disconnect_or_invalid_result_clears_current_display(self):
        for fault in ("disconnect", "invalid_result", "invalid_payload"):
            with self.subTest(fault=fault):
                rows = self.trace_fixture()[:3]
                if fault == "disconnect":
                    rows.append(dict(event="disconnect", at_ms=12, session="A"))
                elif fault == "invalid_result":
                    rows.append(dict(rows[1], at_ms=12, sequence=1, valid=False))
                else:
                    rows.append(dict(event="display", at_ms=12, valid=False, class_id=1))
                if fault != "invalid_payload":
                    rows.append(dict(rows[2], at_ms=13))
                code, report = self.run_trace(rows)
                self.assertEqual(code, 1)
                self.assertFalse(report["passed"])

    def test_trace_clock_regression_is_an_input_error(self):
        rows = self.trace_fixture()
        rows[-1]["at_ms"] = 1
        code, report = self.run_trace(rows)
        self.assertEqual(code, 2)
        self.assertIn("regressed", report["error"])

    def test_golden_handles_case_order_and_float_tolerance_without_rounding_int64(self):
        with tempfile.TemporaryDirectory() as folder:
            golden, actual, record = self.golden_fixture(folder)
            second = dict(record, case_id="large-int", values=[9007199254740993])
            golden.write_text(json.dumps(record)+"\n"+json.dumps(second)+"\n", encoding="utf-8")
            actual.write_text(json.dumps(second)+"\n"+json.dumps(record)+"\n", encoding="utf-8")
            code, _ = self.run_tool("compare_golden.py", golden, actual)
            self.assertEqual(code, 0)
            second["values"] = [9007199254740992]
            actual.write_text(json.dumps(second)+"\n"+json.dumps(record)+"\n", encoding="utf-8")
            code, _ = self.run_tool("compare_golden.py", golden, actual)
            self.assertEqual(code, 1)
            golden.write_text(json.dumps(dict(record, values=[1.0]))+"\n", encoding="utf-8")
            actual.write_text(json.dumps(dict(record, values=[1.0001]))+"\n", encoding="utf-8")
            code, _ = self.run_tool("compare_golden.py", golden, actual, "--atol", "0.001")
            self.assertEqual(code, 0)

    def test_golden_rejects_empty_duplicate_nonfinite_and_missing_cases(self):
        for fault in ("empty", "duplicate", "nan", "missing"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                golden, actual, record = self.golden_fixture(folder)
                if fault == "empty":
                    actual.write_text("", encoding="utf-8")
                elif fault == "duplicate":
                    actual.write_text((json.dumps(record)+"\n")*2, encoding="utf-8")
                elif fault == "nan":
                    record["values"] = [float("nan")]
                    actual.write_text(json.dumps(record)+"\n", encoding="utf-8")
                else:
                    record["case_id"] = "another-case"
                    actual.write_text(json.dumps(record)+"\n", encoding="utf-8")
                code, report = self.run_tool("compare_golden.py", golden, actual)
                self.assertEqual(code, 1 if fault == "missing" else 2)
                self.assertFalse(report["passed"])

    def test_overlay_rejects_path_escape_and_truncated_header_even_with_matching_hash(self):
        for fault in ("escape", "header"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                path, manifest = self.overlay_fixture(folder)
                if fault == "escape":
                    manifest["bit"]["path"] = "../outside.bit"
                else:
                    data = bit_fixture()[:-1]
                    (Path(folder)/"demo.bit").write_bytes(data)
                    manifest["bit"]["sha256"] = digest(data)
                path.write_text(json.dumps(manifest), encoding="utf-8")
                code, report = self.run_tool("check_overlay.py", path, "--part", "7z020clg400")
                self.assertEqual(code, 2)
                self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
