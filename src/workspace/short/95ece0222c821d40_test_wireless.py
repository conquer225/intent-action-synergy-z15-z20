import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from eye_gate import EyeGate
from network_receiver import decode_response, ReceiverError, PRODUCT


class EyeGateTests(unittest.TestCase):
    @staticmethod
    def event(now, x=.5, **extra):
        return dict(kind="horizontal_gaze", valid=True, monotonic_ns=round(now * 1e9), x=x, **extra)

    def feed(self, gate, start, x, count):
        return [gate.update(self.event(start + i * .05, x), start + i * .05)
                for i in range(count)]

    def ready(self):
        gate = EyeGate()
        self.feed(gate, 10, .5, 16)
        gate.arm(10.75)
        return gate

    def test_default_disabled_and_center_required(self):
        gate = EyeGate()
        self.assertFalse(any(self.feed(gate, 10, .8, 40)))
        with self.assertRaises(ValueError):
            gate.arm(11.95)

    def test_one_direction_only_once_until_center(self):
        gate = self.ready()
        actions = self.feed(gate, 10.8, .8, 80)
        self.assertEqual(actions.count("NEXT"), 1)
        self.assertFalse(any(self.feed(gate, 14.8, .2, 30)))
        self.feed(gate, 16.3, .5, 16)
        self.assertEqual(self.feed(gate, 17.1, .2, 30).count("PREV"), 1)

    def test_invalid_stale_future_and_nan_disarm(self):
        for event in [dict(kind="gaze", valid=True, monotonic_ns=11_000_000_000, x=.8),
                      dict(kind="horizontal_gaze", valid=False, monotonic_ns=11_000_000_000, x=.8),
                      self.event(9, .8), self.event(12, .8), self.event(11, float("nan"))]:
            gate = self.ready()
            self.assertIsNone(gate.update(event, 11))
            self.assertFalse(gate.armed)

    def test_duplicate_samples_do_not_complete_dwell(self):
        gate = self.ready()
        event = self.event(10.8, .8)
        self.assertIsNone(gate.update(event, 10.8))
        for _ in range(100):
            self.assertIsNone(gate.update(event, 10.81))

    def test_gap_disarms_and_rest_does_not_trigger(self):
        gate = self.ready()
        self.assertFalse(any(self.feed(gate, 10.8, .5, 30)))
        gate.update(self.event(13, .8), 13)
        self.assertFalse(gate.armed)


class WireTests(unittest.TestCase):
    def setUp(self):
        self.key = bytes(range(32))
        self.value = dict(product=PRODUCT, nonce="abcd", motor_gpio_enabled=False,
                          boot_id="0123456789abcdef", last_sequence=1, network_mode="virtual",
                          ble_ready=True, busy=False)

    def encode(self, value):
        body = json.dumps(value).encode()
        return body + b"|" + hmac.new(self.key, body, hashlib.sha256).hexdigest().encode()

    def test_response_authentication_and_nonce(self):
        self.assertEqual(decode_response(self.encode(self.value), self.key, "abcd"), self.value)
        with self.assertRaises(ReceiverError):
            decode_response(self.encode(self.value), self.key, "wrong")
        with self.assertRaises(ReceiverError):
            decode_response(self.encode(self.value), bytes(32), "abcd")

    def test_wrong_identity_mode_or_motor_output_rejected(self):
        for changes in [dict(product="wheelchair"), dict(motor_gpio_enabled=True),
                        dict(network_mode="unknown"), dict(last_sequence=True), dict(boot_id="short")]:
            with self.assertRaises(ReceiverError):
                decode_response(self.encode(dict(self.value, **changes)), self.key, "abcd")

    def test_modified_and_oversize_replies_rejected(self):
        packet = self.encode(self.value)
        with self.assertRaises(ReceiverError):
            decode_response(packet.replace(b"virtual", b"hid"), self.key, "abcd")
        with self.assertRaises(ReceiverError):
            decode_response(b"x" * 1025, self.key, "abcd")


if __name__ == "__main__":
    unittest.main()
