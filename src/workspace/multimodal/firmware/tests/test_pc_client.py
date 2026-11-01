"""Run with: py -3 -m unittest discover -s tests -p test_pc_client.py -v."""
from __future__ import annotations

import importlib
import contextlib
import io
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from pc_client import (ClientError, ControlClient, MAX_FRAME_BYTES, encode_frame,
                       load_script, main, parse_console_command, run_script, validate_command)
from mock_server import MockControlServer


def wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true before deadline")


class RawServer:
    """One localhost connection to exercise TCP fragmentation and bad ACKs."""
    def __init__(self, handler):
        self.handler = handler
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(1)
        self.port = self.listener.getsockname()[1]
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        try:
            with self.listener.accept()[0] as sock:
                sock.settimeout(1)
                self.handler(sock)
        except (OSError, ClientError):
            pass
        except Exception as exc:
            self.error = exc

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.listener.close()
        self.thread.join(timeout=1)
        if self.error:
            raise self.error


class ValidationTests(unittest.TestCase):
    def test_disabled_hand_input_configuration_schema(self):
        self.assertEqual(validate_command("hand", "input", input="contact")["input"], "contact")
        self.assertEqual(parse_console_command("hand input contact"),("hand","input",{"input":"contact"}))
        self.assertEqual(validate_command("pendulum","mode",mode="tilt_test")["mode"],"tilt_test")
        for device, action, fields in (("pendulum","input",{"input":"contact"}),
                                      ("hand","input",{"input":"other"}),
                                      ("hand","open",{"input":"contact"})):
            with self.assertRaises(ValueError): validate_command(device, action, **fields)
    def test_schema_is_checked_before_transmission(self):
        for values in ([0] * 5, [0] * 5 + [181], [False] * 6, [1.5] * 6):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_command("hand", "pose", angles=values)
        for device, action, fields in (([], "enable", {}), ("all", "enable", {}), ("hand", "start", {}),
                                       ("pendulum", "mode", {"mode": "glove"}),
                                       ("hand", "enable", {"mode": "network"}),
                                       ("all", "heartbeat", {"unexpected": True})):
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_command(device, action, **fields)
        self.assertEqual(validate_command("hand", "pose", angles=[0, 30, 60, 90, 120, 180])["angles"][-1], 180)

    def test_frame_limit_includes_newline(self):
        frame = encode_frame({"value": "x" * (MAX_FRAME_BYTES - 13)})
        self.assertEqual(len(frame), MAX_FRAME_BYTES)
        with self.assertRaises(ValueError):
            encode_frame({"value": "x" * (MAX_FRAME_BYTES - 12)})
        self.assertTrue(frame.endswith(b"\n"))

    def test_console_and_script_require_explicit_actions(self):
        self.assertEqual(parse_console_command("hand pose 1 2 3 4 5 6"),
                         ("hand", "pose", {"angles": [1, 2, 3, 4, 5, 6]}))
        self.assertEqual(parse_console_command("estop"), ("all", "estop", {}))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "script.json"
            path.write_text('[{"device":"hand","action":"mode","mode":"network"},'
                            '{"wait_ms":10}]', encoding="utf-8")
            self.assertEqual(len(load_script(path)), 2)
            for script in ('[{"device":"hand","action":"pose","angles":[1]}]',
                           '[{"device":"all","action":"heartbeat"}]',
                           '[{"wait_ms":true}]',
                           '[{"device":"hand","action":"open","action":"close"}]'):
                path.write_text(script, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_script(path)

    def test_gui_import_has_no_window_or_display_dependency(self):
        module = importlib.import_module("pc_gui")
        self.assertTrue(callable(module.main))


class SessionTests(unittest.TestCase):
    def test_idle_session_keeps_lease_and_sequence_is_strict(self):
        with MockControlServer() as server:
            with ControlClient("127.0.0.1", server.port) as client:
                self.assertTrue(client.send("hand", "mode", mode="network")["ok"])
                self.assertTrue(client.send("hand", "enable")["ok"])
                self.assertTrue(client.send("hand", "close")["ok"])
                time.sleep(0.65)  # Deliberately longer than the 500 ms firmware lease.
                self.assertTrue(client.connected)
                self.assertTrue(server.status["hand"]["enabled"])
                ack = client.send("all", "status")
                self.assertEqual(ack["status"]["hand"]["pressures"], [100, 200, 300, 400, 500])
                self.assertEqual(client.latest_status["hand"]["angles"], [120] * 6)
            wait_for(lambda: not server.status["hand"]["enabled"])
            packets = list(server.packets)
            self.assertEqual(packets[0]["action"], "hello")
            self.assertEqual(packets[-1]["action"], "estop")
            self.assertGreaterEqual(sum(p["action"] == "heartbeat" for p in packets), 4)
            self.assertEqual([p["seq"] for p in packets], list(range(1, len(packets) + 1)))
            self.assertTrue(all(len(encode_frame(p)) <= MAX_FRAME_BYTES for p in packets))

    def test_disconnect_does_not_reconnect_or_replay(self):
        with MockControlServer() as server:
            client = ControlClient("127.0.0.1", server.port)
            try:
                client.connect()
                client.send("pendulum", "mode", mode="network")
                client.send("pendulum", "enable")
                client.send("pendulum", "start")
                server.disconnect_all()
                wait_for(lambda: not client.connected)
                wait_for(lambda: not server.status["pendulum"]["enabled"])
                count = len(server.packets)
                time.sleep(0.15)
                self.assertEqual(len(server.packets), count)
                self.assertEqual(server.sessions_started, 1)
                with self.assertRaises(ClientError):
                    client.send("pendulum", "start")
                client.connect()  # Explicit reconnect performs hello only.
                reconnect_packets = server.packets[count:]
                self.assertEqual(reconnect_packets[0]["seq"], 1)
                self.assertEqual(reconnect_packets[0]["action"], "hello")
                self.assertFalse(server.status["pendulum"]["enabled"])
                refused = client.send("pendulum", "start")
                self.assertFalse(refused["ok"])
                self.assertEqual(refused["error"], "disabled")
                self.assertEqual(sum(p["action"] == "enable" for p in server.packets), 1)
            finally:
                client.close()

    def test_missed_heartbeat_ack_closes_even_with_telemetry(self):
        with MockControlServer(ack_heartbeats=False) as server:
            client = ControlClient("127.0.0.1", server.port)
            try:
                client.connect()
                client.send("hand", "mode", mode="network")
                client.send("hand", "enable")
                wait_for(lambda: not client.connected, timeout=0.8)
                self.assertIn("ACK timeout", client.last_error)
                wait_for(lambda: not server.status["hand"]["enabled"])
                count = len(server.packets)
                time.sleep(0.2)
                self.assertEqual(len(server.packets), count)
                self.assertEqual(server.sessions_started, 1)
            finally:
                client.close()

    def test_context_exception_stops_and_closes(self):
        with MockControlServer() as server:
            with self.assertRaisesRegex(RuntimeError, "caller failed"):
                with ControlClient("127.0.0.1", server.port) as client:
                    client.send("hand", "mode", mode="network")
                    client.send("hand", "enable")
                    raise RuntimeError("caller failed")
            wait_for(lambda: not server.status["hand"]["enabled"])
            self.assertFalse(client.connected)
            self.assertEqual(server.packets[-1]["action"], "estop")

    def test_rejected_script_does_not_continue(self):
        with MockControlServer() as server:
            with self.assertRaises(ClientError):
                with ControlClient("127.0.0.1", server.port) as client, contextlib.redirect_stdout(io.StringIO()):
                    run_script(client, [{"device": "hand", "action": "close"},
                                        {"device": "pendulum", "action": "start"}])
            self.assertFalse(any(p["action"] == "start" for p in server.packets))
            self.assertEqual(server.packets[-1]["action"], "estop")

    def test_unexpected_disconnect_preserves_local_and_other_owner(self):
        with MockControlServer() as server:
            first = ControlClient("127.0.0.1", server.port, "pc")
            second = ControlClient("127.0.0.1", server.port, "eye")
            try:
                first.connect()
                second.connect()
                first.send("hand", "mode", mode="emg")
                first.send("hand", "enable")
                second.send("pendulum", "mode", mode="network")
                second.send("pendulum", "enable")
                first.close(safe_stop=False)  # Emulate TCP loss, without intentional all-estop.
                wait_for(lambda: "pc" not in server._owners)
                self.assertTrue(server.status["hand"]["enabled"])
                self.assertTrue(server.status["pendulum"]["enabled"])
                self.assertTrue(second.connected)
            finally:
                first.close()
                second.close()

    def test_cli_script_rehearsal_is_local_and_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "script.json"
            path.write_text('[{"device":"hand","action":"mode","mode":"network"},'
                            '{"device":"hand","action":"enable"},'
                            '{"device":"hand","action":"open"},'
                            '{"wait_ms":120},{"device":"all","action":"status"}]', encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["--simulate", "--source", "brain", "--script", str(path)])
            self.assertEqual(result, 0)
            self.assertIn("SIMULATION: localhost only", output.getvalue())

    def test_other_source_cannot_move_owned_device(self):
        with MockControlServer() as server:
            with ControlClient("127.0.0.1", server.port, "pc") as owner:
                owner.send("hand", "mode", mode="network")
                owner.send("hand", "enable")
                with ControlClient("127.0.0.1", server.port, "eye") as other:
                    ack = other.send("hand", "close")
                    self.assertFalse(ack["ok"])
                    self.assertEqual(ack["error"], "source_not_owner")
                    self.assertTrue(other.send("all", "estop")["ok"])

    def test_same_source_second_connection_is_rejected(self):
        with MockControlServer() as server:
            with ControlClient("127.0.0.1", server.port) as first:
                second = ControlClient("127.0.0.1", server.port)
                try:
                    with self.assertRaises(ClientError):
                        second.connect()
                    self.assertTrue(first.connected)
                finally:
                    second.close()

    def test_split_and_coalesced_frames_include_unsolicited_telemetry(self):
        def handler(sock):
            with sock.makefile("rb") as reader:
                packet = json.loads(reader.readline())
                ack = encode_frame({"v": 1, "seq": packet["seq"], "ok": True, "error": ""})
                sock.sendall(ack[:5])
                time.sleep(0.02)
                sock.sendall(ack[5:] + encode_frame({"v": 1, "type": "telemetry", "status": {"fixture": 7}}))
                while True:
                    raw = reader.readline()
                    if not raw:
                        return
                    packet = json.loads(raw)
                    sock.sendall(encode_frame({"v": 1, "seq": packet["seq"], "ok": True}))
        with RawServer(handler) as server:
            with ControlClient("127.0.0.1", server.port) as client:
                wait_for(lambda: client.latest_status.get("fixture") == 7)
                self.assertTrue(client.send("all", "status")["ok"])

    def test_oversized_or_duplicate_ack_is_fail_closed(self):
        payloads = (b"x" * MAX_FRAME_BYTES,
                    b'{"v":1,"seq":1,"seq":1,"ok":true}\n',
                    b'{"v":1,"seq":9,"ok":true}\n')
        for payload in payloads:
            def handler(sock, response=payload):
                sock.recv(2048)
                sock.sendall(response)
                time.sleep(0.1)
            with self.subTest(payload=payload[:40]), RawServer(handler) as server:
                client = ControlClient("127.0.0.1", server.port)
                try:
                    with self.assertRaises(ClientError):
                        client.connect()
                    self.assertFalse(client.connected)
                finally:
                    client.close()


if __name__ == "__main__":
    unittest.main()
