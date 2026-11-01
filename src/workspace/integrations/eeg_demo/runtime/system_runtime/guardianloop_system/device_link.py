"""Bounded device work; a fresh display/gaze lease owns each eye TCP session."""
import threading
import time
import json
import ipaddress

from .c3_client import ControlClient, ClientError


class LeaseClient(ControlClient):
    def revoke(self):
        """Close the socket now, without waiting for ACKs or joining its thread."""
        session = self._session
        if session is not None:
            self._abort(session, 'eye control lease revoked')


class DeviceLink:
    lease_seconds = .30

    def __init__(self, host, port=9000, debug_hold=False):
        # Validate configuration before starting any threads or network I/O.
        LeaseClient(host, port, source='eye')
        if type(debug_hold) is not bool:raise ValueError('debug_hold must be boolean')
        self.debug_hold=debug_hold
        self.host, self.port = host, port
        self.lock = threading.RLock()
        self.wake = threading.Event(); self.done = threading.Event()
        self.client = None; self.job = None; self.generation = 0
        self.last_service = -float('inf'); self.allowed = False
        self.view = dict(connected=False, enabled=None, pending=False,
                         message='等待注视启用', last_ack=None, stop_confirmed=False, ever_enabled=False)
        self.worker = threading.Thread(target=self._run, name='eye-device-command', daemon=True)
        self.watchdog = threading.Thread(target=self._watch, name='eye-device-lease', daemon=True)
        self.worker.start(); self.watchdog.start()

    def service(self, allowed):
        with self.lock:
            self.last_service = time.monotonic()
            self.allowed = allowed is True
            if not self.allowed and (self.view['pending'] or self.client is not None):
                self.stop('眼控暂停或注视失效')

    def request(self, device, action):
        actions = {'hand': ('enable', 'open', 'close'),
                   'pendulum': ('enable', 'start', 'stop', 'left', 'right')}
        if device not in actions or action not in actions[device]:
            raise ValueError('Unknown eye device action')
        with self.lock:
            if (self.done.is_set() or not self.allowed
                    or (not self.debug_hold and time.monotonic()-self.last_service > self.lease_seconds)
                    or self.view['pending']):
                return False
            if action != 'enable' and self.view['enabled'] != device:
                return False
            self.job = (self.generation, device, action, time.monotonic())
            self.view.update(pending=True, message='等待设备回执', stop_confirmed=False)
            self.wake.set()
            return True

    def stop(self, reason='停止控制'):
        with self.lock:
            active = bool(self.client and self.client.connected) or self.view['pending'] or self.view['enabled']
            self.generation += 1; self.job = None; self.allowed = False
            self.view.update(enabled=None, pending=False, connected=False)
            if active:
                self.view.update(message=str(reason)+'；已关闭控制会话', stop_confirmed=False)
            if self.client is not None:
                self.client.revoke()
            self.wake.set()

    def snapshot(self):
        with self.lock:
            view = dict(self.view)
            view['connected'] = bool(self.client and self.client.connected)
            view['debug_hold'] = self.debug_hold
            view['hardware_motion_verified'] = False
            view['stop_method'] = 'TCP session close; firmware disconnect/lease protection'
            return view

    def _current(self, generation):
        return (not self.done.is_set() and generation == self.generation and self.allowed
                and (self.debug_hold or time.monotonic()-self.last_service <= self.lease_seconds))

    def _send(self, generation, device, action, **fields):
        # Cancellation and transmission serialize at the actual wire write.
        # _request waits outside this lock, so stop never waits for a device ACK.
        with self.lock:
            if not self._current(generation):
                raise ClientError('request cancelled')
            client = self.client
            session = client._session if client is not None else None
            if session is None or not client.connected:
                raise ClientError('disconnected')
            pending = client._transmit(session, device, action, **fields)
        if not pending.event.wait(client.ack_timeout+.1):
            client.revoke()
            raise ClientError('ACK timeout')
        if pending.error or pending.response is None:
            raise ClientError(pending.error or 'ACK missing')
        reply = pending.response
        if reply['ok'] is not True:
            raise ClientError(reply.get('error') or 'request rejected')
        return reply

    def _wait_hand_ready(self, generation):
        # MODE clears stale RF feedback and starts the firmware's bounded
        # safe-open synchronization. Read its new ACK before the single ENABLE.
        deadline=time.monotonic()+.45
        while True:
            reply=self._send(generation,'hand','status')
            hand=(reply.get('status') or {}).get('hand') or {}
            if all(hand.get(k) is True for k in
                   ('radio_ready','poses_ready','radio_link','pressure_valid','actuator_ready')):
                return
            if time.monotonic()>=deadline:
                raise ClientError('手端未就绪：未收到有效射频回执，请检查接收板供电和无线连接')
            if self.done.wait(.02):raise ClientError('request cancelled')

    def _watch(self):
        while not self.done.wait(.02):
            with self.lock:
                if self.client is not None or self.view['pending'] or self.view['enabled']:
                    if (self.allowed or self.view['pending'] or self.view['enabled']) and not self._current(self.generation):
                        self.stop('显示或眼控租约过期')
                    elif self.view['enabled'] and not (self.client and self.client.connected):
                        self.stop('设备连接中断，需重新注视启用')

    def _run(self):
        while not self.done.is_set():
            self.wake.wait(.05); self.wake.clear()
            with self.lock:
                job, self.job = self.job, None
                old = self.client if self.client and not self.client.connected else None
                if old is not None:
                    # Revoke acknowledged enable before detaching a dead client.
                    # Otherwise the watchdog can lose the only disconnect evidence.
                    if self.view['enabled']:
                        self.stop('设备连接中断，需重新注视启用')
                        job = None
                    self.client = None
            if old is not None: old.close(safe_stop=False)
            if job is None: continue
            generation, device, action, queued = job
            try:
                with self.lock:
                    if not self._current(generation) or time.monotonic()-queued > self.lease_seconds:
                        continue
                    client = self.client
                    if action == 'enable' and client is None:
                        client = LeaseClient(self.host, self.port, source='eye')
                        self.client = client
                if action == 'enable':
                    if not client.connected: client.connect()
                    self._send(generation, device, 'mode', mode='network')
                    if device=='hand':self._wait_hand_ready(generation)
                reply = self._send(generation, device, action)
                with self.lock:
                    if self._current(generation):
                        words={'enable':'设备就绪，请换区选择动作','open':'张开指令已确认',
                               'close':'闭合指令已确认','start':'启动平衡指令已确认',
                               'stop':'停止平衡指令已确认','left':'左转指令已确认','right':'右转指令已确认'}
                        self.view.update(pending=False, connected=True, last_ack=reply,
                                         message=words[action])
                        if action == 'enable':
                            self.view.update(enabled=device,ever_enabled=True)
            except (OSError, ValueError, ClientError) as error:
                with self.lock:
                    if generation == self.generation:
                        self.stop('设备拒绝或通信失败：'+str(error)+'；选择侧区重新连接')
        with self.lock:
            client, self.client = self.client, None
        if client is not None: client.close(safe_stop=False)

    def close(self):
        self.stop('眼控控制结束'); self.done.set(); self.wake.set()
        self.worker.join(3); self.watchdog.join(1)


def from_config(path):
    if not path.is_file(): return None
    if path.stat().st_size > 4096: raise ValueError('Oversize eye device configuration')
    row = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(row, dict) or not {'version','s3_host','s3_port'}<=set(row)
            or set(row)-{'version','s3_host','s3_port','debug_hold'}
            or type(row.get('debug_hold',False)) is not bool
            or type(row['version']) is not int or row['version'] != 1
            or type(row['s3_port']) is not int or row['s3_port'] != 9000):
        raise ValueError('Invalid eye device configuration')
    address = ipaddress.ip_address(row['s3_host'])
    if address.version != 4 or not address.is_private or address.is_loopback or address.is_unspecified:
        raise ValueError('S3 host must be a private LAN IPv4 address')
    return DeviceLink(str(address), row['s3_port'],debug_hold=row.get('debug_hold',False))


def service_eye(link, controller, eye, now, blocked=False):
    """No calibrated, fresh native eye input means no actuator control lease."""
    valid = (not blocked and eye is not None and eye.control_enabled and eye.last_valid is not None
             and 0 <= now-eye.last_valid <= controller.selection.stale_seconds
             and controller.page in ('hand', 'pendulum_balance', 'pendulum_turn'))
    entry_allowed = valid
    if link.debug_hold:
        valid=not blocked and controller.page in ('hand','pendulum_balance','pendulum_turn')
    link.service(valid)
    controller.device_update(now)
    controller.service_device_entry(now, entry_allowed)
