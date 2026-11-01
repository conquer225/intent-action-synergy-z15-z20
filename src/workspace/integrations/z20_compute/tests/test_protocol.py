"""Wire behavior: TCP segmentation must not change the EEG record."""
import struct
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.protocol import Decoder, Message, encode


class ProtocolTests(unittest.TestCase):
    def test_fragmented_and_coalesced_records_preserve_sample_order(self):
        first = Message("eeg", "session-a", 7, 1000, {
            "sample_rate_hz": 250,
            "channels": ["F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2"],
            "samples": [[-1.25, 2, 3, 4, 5, 6, 7, 8]],
        })
        second = Message("command", "session-a", 8, 1001, {"op": "set_mode", "mode": "face"})
        wire = encode(first) + encode(second)
        decoder = Decoder()
        records = []
        for part in (wire[:1], wire[1:3], wire[3:31], wire[31:]):
            records.extend(decoder.feed(part))
        self.assertEqual(records, [first, second])
        self.assertEqual(records[0].body["samples"][0][0], -1.25)

    def test_invalid_records_are_rejected_at_wire_boundary(self):
        for message in [
            Message("shell", "a", 1, 0, {"command": "anything"}),
            Message("command", "a", -1, 0, {"op": "set_mode", "mode": "face"}),
            Message("command", "a", 1, 0, {"op": "set_mode", "mode": "unknown"}),
            Message("eeg", "a", 1, 0, {"sample_rate_hz": 250, "channels": ["F3"], "samples": [[0]]}),
            Message("result", "a", 1, 0, {"task": "face", "model_version": "v1", "valid": True,
                    "class_id": 3, "scores": [0, 1, 2], "state": "prediction"}),
        ]:
            with self.subTest(message=message), self.assertRaises(ValueError):
                encode(message)
        value = dict(version=1, kind="command", session="a", sequence=True,
                     captured_ns=0, body={"op": "set_mode", "mode": "face"})
        payload = json.dumps(value).encode()
        with self.assertRaises(ValueError):
            Decoder().feed(struct.pack("!I", len(payload)) + payload)

    def test_length_nan_and_truncated_eof_are_rejected(self):
        for length in [0, 65537]:
            with self.subTest(length=length), self.assertRaises(ValueError):
                Decoder().feed(struct.pack("!I", length))
        d = Decoder()
        d.feed(b"\x00\x00\x00\x10{")
        with self.assertRaises(ValueError):
            d.finish()
        bad = b'{"version":1,"kind":"ping","session":"a","sequence":0,"captured_ns":0,"body":{"x":NaN}}'
        with self.assertRaises(ValueError):
            Decoder().feed(struct.pack("!I", len(bad)) + bad)


if __name__ == "__main__":
    unittest.main()
