import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("serial_control", Path(__file__).parents[1] / "serial_control.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeConnection:
    def __init__(self, lines):
        self.lines = iter(lines)
        self.writes = []
        self.closed = False

    def open(self):
        pass

    def close(self):
        self.closed = True

    def write(self, data):
        self.writes.append(data)

    def flush(self):
        pass

    def readline(self):
        return next(self.lines, b"")


class SerialControlTests(unittest.TestCase):
    def run_action(self, responses):
        connection = FakeConnection([])
        with patch.object(MODULE.sys, "argv", ["serial_control", "--command", "NEXT", "--allow-action"]), \
             patch.object(MODULE, "check_port"), \
             patch.object(MODULE.serial, "Serial", return_value=connection), \
             patch.object(MODULE, "request", side_effect=responses) as requested, \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                MODULE.main()
                error = None
            except (RuntimeError, TimeoutError) as caught:
                error = caught
        self.assertTrue(connection.closed)
        return [call.args[1] for call in requested.call_args_list], error

    @staticmethod
    def ready_identity(**changes):
        value = {"product": MODULE.PRODUCT, "ready": True, "busy": False,
                 "motor_gpio_enabled": False, "wifi_enabled": False}
        value.update(changes)
        return value

    def test_exact_spare_identity(self):
        port = SimpleNamespace(device="COM17", vid=0x303A, pid=0x1001,
                               serial_number="28:84:85:60:CD:9C")
        with patch.object(MODULE.list_ports, "comports", return_value=[port]):
            MODULE.check_port()

    def test_wrong_device_does_not_open_port(self):
        port = SimpleNamespace(device="COM17", vid=0x303A, pid=0x1001,
                               serial_number="30:ED:A0:A2:E4:24")
        with patch.object(MODULE.list_ports, "comports", return_value=[port]), \
             patch.object(MODULE.serial, "Serial") as opened:
            with self.assertRaises(RuntimeError):
                MODULE.check_port()
            opened.assert_not_called()

    def test_missing_or_duplicate_port_rejected(self):
        for ports in [[], [SimpleNamespace(device="COM17"), SimpleNamespace(device="COM17")]]:
            with patch.object(MODULE.list_ports, "comports", return_value=ports):
                with self.assertRaises(RuntimeError):
                    MODULE.check_port()

    def test_action_needs_explicit_flag_before_serial(self):
        with patch.object(MODULE.sys, "argv", ["serial_control", "--command", "NEXT"]), \
             patch.object(MODULE.serial, "Serial") as opened, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                MODULE.main()
            opened.assert_not_called()

    def test_status_filters_unknown_identity(self):
        connection = FakeConnection([b"not json\n", b'{"product":"other"}\n',
                                     b'{"product":"guardianloop-eye-mouse-0.1.0","ready":false}\n'])
        result = MODULE.request(connection, "STATUS")
        self.assertFalse(result["ready"])
        self.assertEqual(connection.writes, [b"STATUS\n"])

    def test_selftest_and_stop_are_single_requests(self):
        for command, response in [("SELFTEST", b'{"selftest_passed":true}\n'),
                                  ("STOP", b'{"result":"stopped_and_disarmed"}\n')]:
            connection = FakeConnection([response])
            MODULE.request(connection, command)
            self.assertEqual(connection.writes, [(command + "\n").encode()])

    def test_timeout_does_not_retry_input(self):
        connection = FakeConnection([b"bad\n"])
        with patch.object(MODULE, "monotonic", side_effect=[0, 0.5, 2]):
            with self.assertRaises(TimeoutError):
                MODULE.request(connection, "NEXT", timeout=1)
        self.assertEqual(connection.writes, [b"NEXT\n"])

    def test_not_ready_busy_or_wrong_mode_never_arm(self):
        for changes in [{"ready": False}, {"busy": True}, {"motor_gpio_enabled": True}, {"wifi_enabled": True}]:
            commands, error = self.run_action([self.ready_identity(**changes)])
            self.assertIsInstance(error, RuntimeError)
            self.assertEqual(commands, ["STATUS"])

    def test_one_action_then_stop(self):
        commands, error = self.run_action([self.ready_identity(), {"result": "armed"},
                                          {"result": "action_accepted"}, {"busy": False},
                                          {"result": "stopped_and_disarmed"}])
        self.assertIsNone(error)
        self.assertEqual(commands, ["STATUS", "ARM", "NEXT", "STATUS", "STOP"])

    def test_network_product_requires_wifi_and_never_accepts_motor_output(self):
        commands, error = self.run_action([
            self.ready_identity(product=MODULE.NETWORK_PRODUCT, wifi_enabled=True),
            {"result": "armed"}, {"result": "action_accepted"}, {"busy": False},
            {"result": "stopped_and_disarmed"}])
        self.assertIsNone(error)
        self.assertEqual(commands[-1], "STOP")

    def test_arm_failure_stops_without_sending_action(self):
        commands, error = self.run_action([self.ready_identity(), {"result": "ble_not_ready"},
                                          {"result": "stopped_and_disarmed"}])
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(commands, ["STATUS", "ARM", "STOP"])

    def test_action_timeout_stops_without_retry(self):
        commands, error = self.run_action([self.ready_identity(), {"result": "armed"},
                                          TimeoutError("simulated response lost"),
                                          {"result": "stopped_and_disarmed"}])
        self.assertIsInstance(error, TimeoutError)
        self.assertEqual(commands, ["STATUS", "ARM", "NEXT", "STOP"])


if __name__ == "__main__":
    unittest.main()
