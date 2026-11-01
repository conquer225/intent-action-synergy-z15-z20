import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/system_runtime'))
from guardianloop_system.device_link import DeviceLink, service_eye, from_config
from test_eye_devices import EyeDeviceController


class Peer:
    def __init__(self, reject_enable=False, hold_enable=False, hand_ready_after=1):
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0)); self.listener.listen(1)
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        self.rows = []; self.closed = threading.Event(); self.done = threading.Event()
        self.reject_enable = reject_enable; self.hold_enable = hold_enable
        self.hand_ready_after=hand_ready_after;self.status_queries=0
        self.thread = threading.Thread(target=self.run, daemon=True); self.thread.start()

    def run(self):
        try:
            while not self.done.is_set():
                try: sock, _ = self.listener.accept(); break
                except socket.timeout: continue
            else: return
            with sock:
                sock.settimeout(.1); pending = b''
                while not self.done.is_set():
                    try: data = sock.recv(4096)
                    except socket.timeout: continue
                    if not data: break
                    pending += data
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        row = json.loads(line); self.rows.append(row)
                        if row['action'] == 'enable' and self.hold_enable: continue
                        if row['action']=='status':self.status_queries+=1
                        ready=self.hand_ready_after is not None and self.status_queries>=self.hand_ready_after
                        ok = not (row['action'] == 'enable' and (self.reject_enable or (row['device']=='hand' and not ready)))
                        reply = json.dumps(dict(v=1, seq=row['seq'], ok=ok,
                                                error='' if ok else 'neutral_pending_retry',
                                                **({'status':{'hand':dict(actuator_ready=ready,radio_ready=True,poses_ready=True,radio_link=ready,pressure_valid=ready)}} if row['action']=='status' else {}))).encode()+b'\n'
                        sock.sendall(reply[:4]); sock.sendall(reply[4:])
        except OSError: pass
        finally: self.closed.set()

    def close(self):
        self.done.set(); self.listener.close(); self.thread.join(1)


class LinkTests(unittest.TestCase):
    def test_hand_waits_for_new_receiver_feedback_before_single_enable(self):
        peer=Peer(hand_ready_after=2);link=DeviceLink('127.0.0.1',peer.port)
        try:
            link.service(True);self.assertTrue(link.request('hand','enable'))
            self.wait(link,lambda:not link.snapshot()['pending'])
            self.assertEqual(link.snapshot()['enabled'],'hand')
            actions=[r['action'] for r in peer.rows if r['action']!='heartbeat']
            self.assertEqual(actions,['hello','mode','status','status','enable'])
        finally:link.close();peer.close()

    def test_missing_hand_feedback_never_sends_enable_or_motion(self):
        peer=Peer(hand_ready_after=None);link=DeviceLink('127.0.0.1',peer.port)
        try:
            link.service(True);link.request('hand','enable')
            self.wait(link,lambda:not link.snapshot()['pending'])
            self.assertIsNone(link.snapshot()['enabled'])
            self.assertGreaterEqual(peer.status_queries,1)
            self.assertFalse(any(r['action'] in ('enable','open','close') for r in peer.rows))
        finally:link.close();peer.close()

    def test_cancel_during_hand_readiness_cannot_enable_later(self):
        peer=Peer(hand_ready_after=None);link=DeviceLink('127.0.0.1',peer.port)
        try:
            link.service(True);link.request('hand','enable')
            self.wait(link,lambda:peer.status_queries>0)
            link.stop('page_transition');self.assertTrue(peer.closed.wait(.4))
            self.assertFalse(any(r['action']=='enable' for r in peer.rows))
        finally:link.close();peer.close()

    def test_debug_hold_configuration_is_explicit_and_boolean(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'eye_devices.json'
            row=dict(version=1,s3_host='192.168.50.45',s3_port=9000,debug_hold=True)
            path.write_text(json.dumps(row),encoding='utf-8')
            link=from_config(path)
            try:self.assertTrue(link.snapshot()['debug_hold'])
            finally:link.close()
            for bad in ('true',1,None):
                row['debug_hold']=bad;path.write_text(json.dumps(row),encoding='utf-8')
                with self.assertRaises(ValueError):from_config(path)

    def test_debug_hold_keeps_enable_without_display_renewal_or_valid_gaze_but_pause_stops(self):
        peer=Peer();link=DeviceLink('127.0.0.1',peer.port,debug_hold=True)
        try:
            now=time.monotonic();controller=EyeDeviceController(link,now)
            controller._enter('pendulum_balance',now)
            eye=SimpleNamespace(control_enabled=True,last_valid=now)
            service_eye(link,controller,eye,now)
            self.assertTrue(link.request('pendulum','enable'))
            self.wait(link,lambda:link.snapshot()['enabled']=='pendulum')
            # No display renewal for more than twice the normal lease.
            time.sleep(.7)
            self.assertTrue(link.snapshot()['connected'])
            self.assertEqual(link.snapshot()['enabled'],'pendulum')
            self.assertTrue(link.snapshot()['debug_hold'])
            self.assertTrue(link.request('pendulum','stop'))
            self.wait(link,lambda:not link.snapshot()['pending'])
            eye.last_valid=None
            service_eye(link,controller,eye,time.monotonic())
            self.assertTrue(link.request('pendulum','stop'))
            self.wait(link,lambda:not link.snapshot()['pending'])
            self.assertTrue(any(r['action']=='stop' for r in peer.rows))
            service_eye(link,controller,eye,time.monotonic(),blocked=True)
            self.assertTrue(peer.closed.wait(.4))
            self.assertIsNone(link.snapshot()['enabled'])
            self.assertFalse(link.request('pendulum','start'))
        finally:link.close();peer.close()

    def wait(self, link, condition, timeout=3):
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            link.service(True)
            if condition(): return
            time.sleep(.01)
        self.fail('condition timed out: '+repr(link.snapshot()))

    def test_real_tcp_enable_motion_then_ui_stall_closes_lease(self):
        peer = Peer(); link = DeviceLink('127.0.0.1', peer.port)
        try:
            link.service(True); self.assertTrue(link.request('hand', 'enable'))
            self.wait(link, lambda: link.snapshot()['enabled'] == 'hand')
            self.assertTrue(link.request('hand', 'close'))
            self.wait(link, lambda: not link.snapshot()['pending'])
            commands = [(r['device'], r['action']) for r in peer.rows if r['action'] not in ('heartbeat','status')]
            self.assertEqual(commands, [('all', 'hello'), ('hand', 'mode'), ('hand', 'enable'), ('hand', 'close')])
            self.assertTrue(all(r['source'] == 'eye' for r in peer.rows))
            self.assertEqual(peer.rows[1]['mode'], 'network')
            self.assertTrue(peer.closed.wait(.8))
            self.assertIsNone(link.snapshot()['enabled'])
            self.assertFalse(link.request('hand', 'close'))
            count = len(peer.rows); time.sleep(.15)
            self.assertEqual(len(peer.rows), count)
        finally: link.close(); peer.close()

    def test_business_rejection_is_shown_without_automatic_enable_retry(self):
        peer = Peer(reject_enable=True); link = DeviceLink('127.0.0.1', peer.port)
        try:
            link.service(True); link.request('pendulum', 'enable')
            self.wait(link, lambda: not link.snapshot()['pending'])
            self.assertIsNone(link.snapshot()['enabled'])
            self.assertIn('neutral_pending_retry', link.snapshot()['message'])
            self.assertEqual(sum(r['action'] == 'enable' for r in peer.rows), 1)
        finally: link.close(); peer.close()

    def test_navigation_cancels_inflight_enable_without_post_cancel_motion(self):
        peer = Peer(hold_enable=True); link = DeviceLink('127.0.0.1', peer.port)
        try:
            link.service(True); link.request('hand', 'enable')
            self.wait(link, lambda: any(r['action'] == 'enable' for r in peer.rows))
            before = time.monotonic(); link.stop('page_transition')
            self.assertLess(time.monotonic()-before, .05)
            self.assertTrue(peer.closed.wait(.4))
            self.assertIsNone(link.snapshot()['enabled'])
            self.assertFalse(link.request('hand', 'close'))
            self.assertFalse(any(r['action'] == 'close' for r in peer.rows))
        finally: link.close(); peer.close()

    def test_controller_to_tcp_and_gaze_loss_requires_new_enable(self):
        peer=Peer();link=DeviceLink('127.0.0.1',peer.port)
        try:
            now=time.monotonic();controller=EyeDeviceController(link,now)
            def choose(region):
                nonlocal now
                controller.presented(controller.page_id,now);now+=1.3
                self.assertTrue(controller.choose(region,now))
            choose(0);choose(0)
            eye=SimpleNamespace(control_enabled=True,last_valid=now)
            service_eye(link,controller,eye,now)
            choose(0)
            self.wait(link,lambda:link.snapshot()['enabled']=='hand')
            controller.device_update(now);choose(2)
            self.wait(link,lambda:not link.snapshot()['pending'])
            self.assertTrue(any(r['action']=='close' for r in peer.rows))
            service_eye(link,controller,eye,now+1)
            self.assertTrue(peer.closed.wait(.4))
            self.assertIsNone(controller.snapshot(now+1)['devices']['enabled'])
            self.assertEqual(controller.labels()[0],'张开')
            eye.last_valid=now+1;service_eye(link,controller,eye,now+1)
            self.assertFalse(link.snapshot()['connected'])
            self.assertEqual(sum(r['action']=='enable' for r in peer.rows),1)
        finally:link.close();peer.close()

    def test_paused_display_revokes_control_even_with_fresh_eye_samples(self):
        peer=Peer();link=DeviceLink('127.0.0.1',peer.port)
        try:
            now=time.monotonic();controller=EyeDeviceController(link,now)
            controller._enter('hand',now)
            eye=SimpleNamespace(control_enabled=True,last_valid=now)
            service_eye(link,controller,eye,now);link.request('hand','enable')
            self.wait(link,lambda:link.snapshot()['enabled']=='hand')
            service_eye(link,controller,eye,now,blocked=True)
            self.assertTrue(peer.closed.wait(.4))
            self.assertIsNone(link.snapshot()['enabled'])
            self.assertFalse(link.request('hand','close'))
        finally:link.close();peer.close()

    def test_peer_disconnect_revokes_enable_during_continuous_eye_service(self):
        # Exercise both worker/watchdog orderings on the public TCP interface.
        for attempt in range(20):
            with self.subTest(attempt=attempt):
                peer=Peer();link=DeviceLink('127.0.0.1',peer.port)
                try:
                    link.service(True);link.request('hand','enable')
                    self.wait(link,lambda:link.snapshot()['enabled']=='hand')
                    peer.close()
                    deadline=time.monotonic()+.16
                    while time.monotonic()<deadline:
                        link.service(True);time.sleep(.002)
                    self.assertFalse(link.snapshot()['connected'])
                    self.assertIsNone(link.snapshot()['enabled'])
                    self.assertFalse(link.request('hand','close'))
                    self.assertEqual(sum(row['action']=='enable' for row in peer.rows),1)
                finally:link.close();peer.close()


if __name__ == '__main__': unittest.main()
