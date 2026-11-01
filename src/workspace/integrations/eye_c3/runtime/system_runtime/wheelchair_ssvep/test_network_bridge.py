import copy
from email.message import Message
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from bench_network_bridge import (BenchReceiver, NetworkBridge, PRODUCT, MOTOR_PRODUCT, ReceiverError,
                                  receiver_url, require_bench)
from dry_run_bridge import demo_snapshot


def bench_state(**changes):
    state = dict(firmware=PRODUCT, motor_gpio_enabled=False, mode="bench_only",
                 current_motor_state="not_observed", armed=True, driver_fault=False,
                 software_estop_latched=False, requested_direction="stop", lease_ms=300,
                 max_burst_ms=1000, ok=True, boot_id="0123456789abcdef",
                 sequence="0000000000000001",manual_lease_ms=500,manual_active=False)
    state.update(changes)
    return state


class Response:
    def __init__(self, value, status=200):
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        self.data = json.dumps(value).encode() if not isinstance(value, bytes) else value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.data[:limit]


class Opener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeReceiver:
    verified = True
    motor_test = False

    def __init__(self):
        self.calls = []
        self.fails = False

    def stop(self):
        self.calls.append("stop")
        if self.fails:
            raise ReceiverError("unavailable")

    def begin_manual(self):
        self.calls.append('manual_arm')
        if self.fails:raise ReceiverError('unavailable')
        return '0123456789abcdef'

    def send_direction(self, direction, *, manual_boot=None):
        self.calls.append(direction)
        if self.fails:
            raise ReceiverError("unavailable")
        return {"direction": direction, "reason": "virtual_command_accepted", "sent": True}


class NetworkTests(unittest.TestCase):
    def test_motor_profile_is_opt_in_and_identity_must_match(self):
        state=bench_state(firmware=MOTOR_PRODUCT,motor_gpio_enabled=True,mode='remote_control')
        self.assertEqual(require_bench(state,motor_test=True),state)
        for row,enabled in ((state,False),(bench_state(),True),
                (dict(state,firmware=PRODUCT),True),(dict(state,motor_gpio_enabled=False),True)):
            with self.subTest(row=row,enabled=enabled),self.assertRaises(ReceiverError):
                require_bench(row,motor_test=enabled)

    def test_motor_profile_uses_same_ticket_and_local_permission(self):
        state=bench_state(firmware=MOTOR_PRODUCT,motor_gpio_enabled=True,mode='remote_control')
        client=BenchReceiver('http://192.168.50.72','a'*64,motor_test=True)
        client.opener=Opener([Response(dict(state,armed=False))])
        self.assertFalse(client.send_direction('forward')['sent'])
        self.assertEqual(len(client.opener.requests),1)
        client.opener=Opener([Response(state),Response(state),Response(dict(state,requested_direction='left'))])
        row=client.send_direction('left')
        self.assertEqual(row['reason'],'motor_command_accepted')
        self.assertEqual([r.method for r in client.opener.requests],['GET','POST','POST'])

    def test_motor_profile_rejects_synthetic_or_generic_source(self):
        receiver=FakeReceiver();receiver.motor_test=True
        row=NetworkBridge(receiver).observe(demo_snapshot(),1,origin='synthetic')
        self.assertEqual(receiver.calls,['stop']);self.assertEqual(row['direction'],'stop')
        self.assertTrue(row['motor_gpio_enabled'])

    def test_explicit_manual_arm_and_session_boot_binding(self):
        state=bench_state(firmware=MOTOR_PRODUCT,motor_gpio_enabled=True,mode='remote_control')
        active=dict(state,manual_active=True)
        client=BenchReceiver('http://192.168.50.72','a'*64,motor_test=True)
        client.opener=Opener([Response(dict(state,armed=False)),Response(active)])
        boot=client.begin_manual()
        self.assertEqual(boot,state['boot_id'])
        self.assertTrue(client.opener.requests[-1].full_url.endswith('/api/manual-arm'))
        client.opener=Opener([Response(active),Response(active),Response(dict(active,requested_direction='forward'))])
        self.assertTrue(client.send_direction('forward',manual_boot=boot)['sent'])
        for changed in (dict(active,boot_id='1111111111111111'),state):
            client.opener=Opener([Response(changed),Response(b'stop',202)])
            with self.assertRaises(ReceiverError):client.send_direction('forward',manual_boot=boot)
            self.assertTrue(client.opener.requests[-1].full_url.endswith('/api/stop'))
            self.assertFalse(any(r.full_url.endswith('/api/manual-arm') for r in client.opener.requests))

    def client(self, *responses):
        client = BenchReceiver("http://192.168.50.23", "a" * 64)
        client.opener = Opener(responses)
        return client

    def test_private_receiver_only(self):
        self.assertEqual(receiver_url("http://192.168.4.1/"), "http://192.168.4.1")
        for url in ("https://192.168.4.1", "http://127.0.0.1", "http://example.com",
                    "http://192.168.4.1/start", "http://192.168.4.1:22",
                    "http://user:pass@192.168.4.1", "http://192.168.4.1?key=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                receiver_url(url)

    def test_key_shape(self):
        for key in ("", "a" * 63, "A" * 64, True):
            with self.subTest(key=key), self.assertRaises(ValueError):
                BenchReceiver("http://192.168.4.1", key)

    def test_motor_enabled_and_wrong_identity_refused(self):
        for changes in ({"motor_gpio_enabled": True}, {"motor_gpio_enabled": 0},
                        {"firmware": "original"}, {"mode": "production"},
                        {"current_motor_state": "stopped"}, {"armed": 1},
                        {"driver_fault": None}, {"lease_ms": 500}):
            with self.subTest(changes=changes), self.assertRaises(ReceiverError):
                require_bench(bench_state(**changes))

    def test_enabled_receiver_never_receives_direction_post(self):
        client = self.client(Response(bench_state(motor_gpio_enabled=True)))
        with self.assertRaises(ReceiverError):
            client.send_direction("forward")
        self.assertEqual(len(client.opener.requests), 1)
        self.assertEqual(client.opener.requests[0].method, "GET")

    def test_unarmed_fault_or_estop_denies_without_ticket(self):
        for changes in ({"armed": False}, {"driver_fault": True}, {"software_estop_latched": True}):
            client = self.client(Response(bench_state(**changes)))
            result = client.send_direction("forward")
            self.assertFalse(result["sent"])
            self.assertEqual(len(client.opener.requests), 1)

    def test_direction_wire_and_auth_without_arm_route(self):
        for direction in ("forward", "backward", "left", "right"):
            client = self.client(Response(bench_state()), Response(bench_state()),
                                 Response(bench_state(requested_direction=direction)))
            result = client.send_direction(direction)
            self.assertTrue(result["sent"])
            requests = client.opener.requests
            self.assertEqual([row.full_url.rsplit("/", 1)[-1] for row in requests],
                             ["status", "ticket", "command"])
            self.assertEqual(requests[-1].data,
                             ("0123456789abcdef 0000000000000001 " + direction).encode())
            self.assertEqual(requests[-1].get_header("X-wc-key"), "a" * 64)
            self.assertNotIn("a" * 64, json.dumps(result))

    def test_invalid_ticket_never_sends_direction(self):
        for changes in ({"ok": False}, {"boot_id": "0000000000000000"},
                        {"sequence": "1"}, {"sequence": "z" * 16}):
            client = self.client(Response(bench_state()), Response(bench_state(**changes)))
            with self.subTest(changes=changes), self.assertRaises(ReceiverError):
                client.send_direction("left")
            self.assertEqual(len(client.opener.requests), 2)

    def test_ticket_request_elapsed_limit(self):
        client = self.client(Response(bench_state()), Response(bench_state()), Response(b"stop", 202))
        with patch("bench_network_bridge.time.monotonic", side_effect=[1, 1.251]):
            result = client.send_direction("right")
        self.assertEqual(result["reason"], "ticket_roundtrip_too_slow")
        self.assertTrue(client.opener.requests[-1].full_url.endswith("/api/stop"))

    def test_wrong_direction_ack_rejected(self):
        client = self.client(Response(bench_state()), Response(bench_state()),
                             Response(bench_state(requested_direction="left")))
        with self.assertRaises(ReceiverError):
            client.send_direction("right")

    def test_response_size_and_type(self):
        response = Response(bench_state())
        response.headers.replace_header("Content-Type", "text/html")
        for item in (Response(b"x" * 4097), response, Response(b"{invalid}")):
            with self.subTest(response=item), self.assertRaises(ReceiverError):
                self.client(item).status()

    def test_redirect_and_connection_failure_rejected(self):
        client = self.client(URLError("redirect rejected"))
        with self.assertRaises(ReceiverError):
            client.status()
        self.assertFalse(client.verified)

    def test_stop_ack_is_not_parking_feedback(self):
        client = self.client(Response(bench_state(armed=False)), Response(b"submitted", 202))
        result = client.stop()
        self.assertTrue(result["stop_request_submitted"])
        self.assertFalse(result["physical_stop_observed"])

    def test_four_frequency_mapping(self):
        receiver = FakeReceiver()
        bridge = NetworkBridge(receiver)
        for i, (hz, direction) in enumerate(((8, "forward"), (10, "backward"), (12, "left"), (14, "right"))):
            result = bridge.observe(demo_snapshot(hz, 1000 + i * 50), i * .2, origin="synthetic")
            self.assertEqual(result["direction"], direction)
            self.assertFalse(result["physical_motor_output_enabled"])
        self.assertEqual(receiver.calls, ["forward", "backward", "left", "right"])

    def test_no_data_bad_quality_and_stopped_submit_stop(self):
        bad = demo_snapshot()
        bad["input"]["quality"]["hard_bad"] = True
        for snapshot in (None, bad, demo_snapshot(accepted=False), demo_snapshot(state="stopped")):
            receiver = FakeReceiver()
            result = NetworkBridge(receiver).observe(snapshot, 0)
            self.assertEqual(result["direction"], "stop")
            self.assertEqual(receiver.calls, ["stop"])

    def test_old_windows_do_not_renew_forever(self):
        receiver = FakeReceiver()
        bridge = NetworkBridge(receiver)
        bridge.observe(demo_snapshot(), 1)
        result = bridge.observe(demo_snapshot(), 1.46)
        self.assertEqual(result["direction"], "stop")
        self.assertEqual(receiver.calls[-1], "stop")

    def test_source_request_latency_rejects_old_input(self):
        receiver = FakeReceiver()
        result = NetworkBridge(receiver).observe(demo_snapshot(), 1, request_seconds=.49)
        self.assertEqual(result["direction"], "stop")
        self.assertEqual(receiver.calls, ["stop"])

    def test_no_auto_arm_on_network_error(self):
        receiver = FakeReceiver()
        receiver.fails = True
        result = NetworkBridge(receiver).observe(demo_snapshot(), 1)
        self.assertFalse(result["sent"])
        self.assertFalse(result["stop_request_submitted"])
        self.assertEqual(receiver.calls, ["forward", "stop"])
        self.assertEqual(result["direction"], "stop")

    def test_does_not_modify_source_or_lower_quality_policy(self):
        snapshot = demo_snapshot()
        snapshot["decision"]["margin"] = .09
        original = copy.deepcopy(snapshot)
        receiver = FakeReceiver()
        result = NetworkBridge(receiver).observe(snapshot, 1)
        self.assertEqual(result["direction"], "stop")
        self.assertEqual(snapshot, original)


if __name__ == "__main__":
    unittest.main()
