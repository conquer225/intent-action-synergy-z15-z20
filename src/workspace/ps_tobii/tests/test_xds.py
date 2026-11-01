"""Captured-device regressions plus malformed data/action gating checks."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from xds import DecodeError, Tag, decode, gaze_columns, is4_sample

FIXTURES = Path(__file__).parent / "fixtures"


def tlv(kind, body):
    return struct.pack(">BI", kind, len(body)) + body


def u32(value):
    return tlv(2, struct.pack(">I", value))


def tag(code, *values):
    return tlv(5, struct.pack(">I", len(values) << 16 | code)) + b"".join(values)


def point(x, y):
    return tag(0x1f40, *(tlv(4, struct.pack(">q", round(v * 2**42))) for v in (x, y)))


def sample(**overrides):
    columns = {0x1b: u32(1), 0x1c: point(.5, .5), 0x16: u32(1), 0x15: u32(0), 7: u32(0), 13: u32(4)}
    for ident, value in overrides.items():
        ident = int(ident, 16)
        if value is None:
            columns.pop(ident, None)
        else:
            columns[ident] = value
    return b"\0\0" + tag(0x0bb8, *(tag(0x0bb9, u32(ident), value) for ident, value in columns.items()))


class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = bytes.fromhex((FIXTURES / "is4_no_face.hex").read_text())
        cls.schema = bytes.fromhex((FIXTURES / "is4_gaze_schema.hex").read_text())

    def test_actual_is4_fields_and_no_face_rejection(self):
        cols = gaze_columns(self.raw)
        self.assertEqual(len(cols), 23)
        self.assertEqual(cols[0x1b], 0)
        self.assertNotIn(0x1d, cols)
        result = is4_sample(self.raw)
        self.assertFalse(result["usable_candidate"])
        self.assertEqual((result["left_validity"], result["right_validity"]), (4, 4))
        self.assertEqual((result["left_pupil_mm"], result["right_pupil_mm"]), (-1, -1))

    def test_schema_confirms_validity_and_eye_order(self):
        outer = decode(self.schema)
        names = {item.values[0]: item.values[1] for item in outer.values if isinstance(item, Tag)}
        self.assertEqual(names[0x1b], "Relative Combined Gaze Validity")
        self.assertEqual(names[0x16], "Left Eye Detected")
        self.assertEqual(names[0x15], "Right Eye Detected")

    def test_all_truncations_reject_incomplete_samples(self):
        for size in range(len(self.raw)):
            with self.subTest(size=size), self.assertRaises(DecodeError):
                is4_sample(self.raw[:size])

    def test_trailing_bytes_and_bad_prefix_reject(self):
        for invalid in (self.raw + b"\0", b"\1\0" + self.raw[2:]):
            with self.assertRaises(DecodeError):
                decode(invalid)

    def test_excessive_nesting_rejects(self):
        nested = u32(1)
        for _ in range(10):
            nested = tag(0x0100, nested)
        with self.assertRaises(DecodeError):
            decode(b"\0\0" + nested)

    def test_invalid_lengths_reject(self):
        for value in (tlv(2, b"\0"), tlv(20, b"\0\0\0\2x"), tlv(21, b"\0\0\0\0x")):
            with self.assertRaises(DecodeError):
                decode(b"\0\0" + value)

    def test_missing_validity_and_untracked_eye_reject(self):
        self.assertTrue(is4_sample(sample())["on_screen_candidate"])
        for changes in ({"1b": None}, {"1b": u32(0)}, {"16": u32(0)}, {"07": u32(4)}, {"1c": None}):
            self.assertFalse(is4_sample(sample(**changes))["usable_candidate"])

    def test_off_screen_is_not_an_action(self):
        result = is4_sample(sample(**{"1c": point(1.5, .5)}))
        self.assertTrue(result["usable_candidate"])
        self.assertFalse(result["on_screen_candidate"])

    def test_new_column_does_not_mask_later_validity(self):
        result = is4_sample(sample(**{"99": u32(42)}))
        self.assertTrue(result["on_screen_candidate"])

    def test_duplicate_column_rejects(self):
        raw = b"\0\0" + tag(0x0bb8, tag(0x0bb9, u32(7), u32(0)), tag(0x0bb9, u32(7), u32(4)))
        with self.assertRaises(DecodeError):
            gaze_columns(raw)


if __name__ == "__main__":
    unittest.main()
