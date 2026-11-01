"""Latest-state HDMI-to-ESP bench link, isolated from rendering and acquisition."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from urllib.request import ProxyHandler, build_opener

from bench_network_bridge import ReceiverError, DIRECTIONS
from upload_server import write_json


POLICY = 'guardianloop-unified-wheelchair-bench-v1'
PHONE_LEASE_SECONDS = .75
RECEIVER_ROOT = Path('/home/xilinx/wheelchair_virtual_20261006')


def launch(base, python, *, motor_test=False):
    env = dict(os.environ)
    env['PYTHONPATH'] = str(base/'system_runtime/wheelchair_ssvep')+os.pathsep+env.get('PYTHONPATH', '')
    profile = ['--motor-test'] if motor_test else []
    return subprocess.Popen([python, str(base/'wheelchair_link.py'), *profile, '--base', str(base),
        '--config', str(RECEIVER_ROOT/'receiver_private.json')], env=env)


def read_status(path, now, *, motor_test=False):
    try:
        row = json.loads(Path(path).read_text())
        stamp = row['updated_monotonic']
        if (row['policy'] == POLICY and row['physical_output_enabled'] is motor_test
                and type(stamp) in (int, float) and math.isfinite(stamp)
                and 0 <= now-stamp <= 3):
            return row
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return dict(policy=POLICY, state='unavailable', reason='link_not_running_or_stale',
                sent=False, direction='stop', physical_output_enabled=False)


def control_gate(player, now):
    if not isinstance(player, dict):
        return 'display_unavailable'
    stamp = player.get('updated_monotonic')
    if (type(stamp) not in (int, float) or not math.isfinite(stamp)
            or not 0 <= now-stamp <= 1):
        return 'display_status_stale'
    system = player.get('system')
    if not isinstance(system, dict) or system.get('mode') != 'live_readonly_hdmi':
        return 'not_live_unified_display'
    if system.get('page') != 'drive':
        return 'not_direction_page'
    if system.get('force_stopped') is not False or 'fatigue' in system.get('alerts', {}):
        return 'stop_or_fatigue_lock'
    if (system.get('direction_armed') is not True or system.get('reading') is not False
            or system.get('eye_only') is not False):
        return 'direction_not_armed'
    if (system.get('stimulus_enabled') is not True
            or (system.get('hdmi_stimulus') or {}).get('active') is not True):
        return 'stimulus_not_active'
    return None


class UnifiedLink:
    def __init__(self, bridge):
        self.bridge = bridge
        self.failed_window = None

    def step(self, player, snapshot, now, request_seconds=0, stop_pending=False):
        reason = 'manual_stop_pending' if stop_pending else control_gate(player, now)
        system = (player.get('system') or {}) if isinstance(player, dict) else {}
        if not reason and (not isinstance(snapshot, dict)
                or snapshot.get('display_page_id') != system.get('page_id')):
            reason = 'display_page_mismatch'
        window = None
        if isinstance(snapshot, dict):
            window = (snapshot.get('id'), (snapshot.get('decision') or {}).get('window_end_index_exclusive'))
        if not reason and self.failed_window is not None:
            old_session, old_end = self.failed_window
            if (window[0] == old_session and type(window[1]) is int and type(old_end) is int
                    and window[1] <= old_end):
                reason = 'waiting_for_new_window_after_link_failure'
        result = self.bridge.observe(None if reason else snapshot, now, request_seconds,
                                     origin='unified_live_hdmi')
        if result.get('sent') is not True and window is not None:
            self.failed_window = window
        elif not reason and result.get('sent') is True:
            self.failed_window = None
        state = ('offline' if result.get('sent') is not True else
                 'sent' if result['direction'] != 'stop' else 'stopped')
        if result.get('reason') == 'local_permit_required':
            state = 'permit_required'
        return dict(result, policy=POLICY, state=state, source_gate=reason,
                    updated_monotonic=now, physical_output_enabled=self.bridge.receiver.motor_test,
                    speed_supported=False, replay_allowed=False)


class ManualControl:
    """Foreground phone intent owns manual motion; STOP suspends EEG arbitration."""
    def __init__(self,boot,*,motor_test=False,ignore_id=None):
        self.motor_test=motor_test
        self.boot=boot
        self.last_id=ignore_id
        self.mode='ssvep'
        self.direction='stop'
        self.deadline=0.
        self.result=None
        self.manual_boot=None
        self.ready_at=0.

    def step(self,receiver,command,player,now,stop_pending=False):
        new=(command.get('boot')==self.boot and isinstance(command.get('id'),str)
             and command['id'] and command['id']!=self.last_id)
        if new:
            value=command.get('value');stamp=command.get('queued_monotonic')
            if (type(value) is not str or value not in DIRECTIONS|{'ssvep'} or type(stamp) not in (int,float)
                    or not math.isfinite(stamp) or not 0<=now-stamp<=1):
                new=False
            else:
                self.last_id=command['id'];self.result=None
                self.mode='ssvep' if value=='ssvep' else 'manual'
                self.direction='stop' if value=='ssvep' else value
                self.deadline=stamp+.25
                self.manual_boot=None
                self.ready_at=now+.35
                if self.motor_test and self.direction!='stop':
                    try:
                        if receiver is None:raise ReceiverError('receiver_not_on_z15_hotspot')
                        receiver.stop()
                        self.result=dict(state='preparing',direction='stop',sent=True,reason='neutral_before_direction')
                    except ReceiverError as error:
                        self.direction='stop'
                        self.result=dict(state='offline',direction='stop',sent=False,reason=str(error))
        if stop_pending:
            self.mode='manual';self.direction='stop';self.result=None
        if self.mode=='ssvep' and not new:return None
        system=player.get('system') or {}
        blocked='fatigue' in system.get('alerts',{})
        heartbeat=command.get('heartbeat_monotonic')
        fresh=(command.get('id')==self.last_id and type(heartbeat) in (int,float)
               and math.isfinite(heartbeat) and 0<=now-heartbeat<=PHONE_LEASE_SECONDS)
        expired=not fresh if self.motor_test else now>=self.deadline
        if self.direction!='stop' and (expired or blocked):
            self.direction='stop';self.result=None
        if (self.motor_test and self.direction!='stop' and now>=self.ready_at
                and command.get('heartbeat_confirmed') is True):
            try:
                if receiver is None:raise ReceiverError('receiver_not_on_z15_hotspot')
                if self.manual_boot is None:self.manual_boot=receiver.begin_manual()
                self.result=receiver.send_direction(self.direction,manual_boot=self.manual_boot)
                if self.result.get('sent') is not True:raise ReceiverError('Manual lease lost; select a direction again')
                self.result['state']='sent'
            except ReceiverError as error:
                self.direction='stop';self.manual_boot=None
                if receiver is not None and receiver.verified:
                    try:receiver.stop()
                    except ReceiverError:pass
                self.result=dict(state='offline',direction='stop',sent=False,reason=str(error))
        elif self.result is None:
            if receiver is None:
                self.result=dict(state='offline',direction='stop',sent=False,reason='receiver_not_on_z15_hotspot')
                self.direction='stop'
            else:
                try:
                    if self.direction=='stop':
                        receiver.stop()
                        self.result=dict(state='stopped',direction='stop',sent=True,
                            reason='fatigue_lock' if blocked else 'priority_stop_pending' if stop_pending else
                                   'phone_heartbeat_expired' if expired and command.get('value')!='stop' else 'manual_stop')
                        self.manual_boot=None
                    else:
                        self.result=receiver.send_direction(self.direction)
                        self.result['state']='sent' if self.result.get('sent') else 'permit_required'
                except ReceiverError as error:
                    self.result=dict(state='offline',direction='stop',sent=False,reason=str(error))
                    self.direction='stop'
        return dict(self.result,policy=POLICY,control_mode=self.mode,
            command_id=self.last_id,updated_monotonic=now,physical_output_enabled=self.motor_test,
            motor_gpio_enabled=self.motor_test,speed_supported=False,replay_allowed=False,
            continuous_manual=self.motor_test,phone_lease_ms=750 if self.motor_test else None)


def receiver_address(mac):
    rows = json.loads(subprocess.check_output(
        ['ip', '-j', 'neigh', 'show', 'dev', 'wlan0'], text=True, timeout=1))
    matches = {row['dst'] for row in rows if row.get('lladdr', '').lower() == mac
               and set(row.get('state', [])) & {'REACHABLE', 'STALE', 'DELAY', 'PROBE', 'PERMANENT'}}
    if len(matches) != 1:
        return None
    return 'http://' + matches.pop()


def read_player(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def pending_stop(player, command):
    return (command.get('session_id') == player.get('session_id')
            and command.get('action') == 'force_stop'
            and not (command.get('id') == (player.get('command_receipt') or {}).get('id')
                     and (player.get('command_receipt') or {}).get('state') == 'applied'))


class PriorityStop:
    def __init__(self):
        self.acknowledged = None

    def pending(self, player, command, navigation):
        identity = (command.get('session_id'), command.get('id'))
        if (command.get('action') != 'force_stop' or not identity[1]
                or identity[0] != player.get('session_id')):
            return False
        if identity == self.acknowledged:
            return False
        receipt = player.get('command_receipt') or {}
        if not pending_stop(player, command):
            self.acknowledged = identity
            return False
        issued = command.get('queued_monotonic')
        later = navigation.get('queued_monotonic')
        # PlayerCommands consumes the STOP lane before any later navigation.
        if (navigation.get('session_id') == identity[0] and navigation.get('id')
                and navigation.get('id') == receipt.get('id') and receipt.get('state') == 'applied'
                and navigation.get('action') != 'force_stop'
                and type(issued) in (int, float) and math.isfinite(issued)
                and type(later) in (int, float) and math.isfinite(later) and later > issued):
            self.acknowledged = identity
            return False
        return True


def main():
    # SSVEP keeps its existing bounded tickets; only explicit phone intent opens a manual lease.
    from bench_network_bridge import BenchReceiver, NetworkBridge, ReceiverError, load_config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--receiver-mac', default='30:ed:a0:a2:e4:24')
    parser.add_argument('--motor-test', action='store_true')
    args = parser.parse_args()
    if re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', args.receiver_mac) is None:
        parser.error('Use the previously verified receiver MAC')
    os.sched_setaffinity(0, {0})
    os.setpriority(os.PRIO_PROCESS,0,0)
    _, key = load_config(args.config)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    player_path = Path('/dev/shm')/(args.base.name+'-player-status.json')
    stop_path = Path('/dev/shm')/(args.base.name+'-player-stop.json')
    navigation_path = Path('/dev/shm')/(args.base.name+'-player-command.json')
    priority_stop = PriorityStop()
    output = Path('/dev/shm')/(args.base.name+'-wheelchair-link.json')
    manual_path=Path('/dev/shm')/(args.base.name+'-wheelchair-manual.json')
    manual=ManualControl(Path('/proc/sys/kernel/random/boot_id').read_text().strip(),motor_test=args.motor_test,
                         ignore_id=read_player(manual_path).get('id'))
    opener = build_opener(ProxyHandler({}))
    receiver = link = None
    next_discovery = next_idle = 0.
    try:
        while not stop.is_set():
            started = time.monotonic()
            if started >= next_discovery and manual.direction=='stop':
                address = receiver_address(args.receiver_mac)
                if address is None:
                    if receiver and receiver.verified:
                        try: receiver.stop()
                        except ReceiverError: pass
                    receiver = link = None
                elif receiver is None or receiver.base_url != address:
                    receiver = BenchReceiver(address, key, motor_test=args.motor_test)
                    link = UnifiedLink(NetworkBridge(receiver))
                next_discovery = time.monotonic()+2
            player=read_player(player_path)
            stop_pending=priority_stop.pending(player,read_player(stop_path),read_player(navigation_path))
            manual_row=manual.step(receiver,read_player(manual_path),player,time.monotonic(),stop_pending)
            if manual_row is not None:
                if receiver:manual_row['receiver_url']=receiver.base_url
                write_json(output,manual_row);stop.wait(.1);continue
            if link is None:
                write_json(output, dict(policy=POLICY, state='offline', reason='receiver_not_on_z15_hotspot',
                    updated_monotonic=time.monotonic(), sent=False, direction='stop',
                    physical_output_enabled=args.motor_test, motor_gpio_enabled=args.motor_test,
                    speed_supported=False, replay_allowed=False))
                stop.wait(.5)
                continue
            player = read_player(player_path)
            pending = read_player(stop_path)
            stop_pending = priority_stop.pending(player, pending, read_player(navigation_path))
            gate = control_gate(player, time.monotonic())
            if gate and not stop_pending and started < next_idle:
                stop.wait(.1)
                continue
            snapshot = None
            if not gate and not stop_pending:
                try:
                    with opener.open('http://127.0.0.1:9105/api/ssvep-hdmi', timeout=.25) as response:
                        raw = response.read(65537)
                    if len(raw) > 65536: raise ValueError('Oversize SSVEP snapshot')
                    snapshot = json.loads(raw)
                except (OSError, ValueError, TimeoutError):
                    snapshot = None
            now = time.monotonic()
            # Re-read stop/page state after the potentially slow EEG API request.
            player = read_player(player_path)
            pending = read_player(stop_path)
            stop_pending = priority_stop.pending(player, pending, read_player(navigation_path))
            row = link.step(player, snapshot, now, now-started, stop_pending)
            row['control_mode']='ssvep'
            row['updated_monotonic'] = time.monotonic()
            row['receiver_url'] = receiver.base_url
            write_json(output, row)
            next_idle = time.monotonic()+.7
            stop.wait(.1)
    finally:
        if receiver and receiver.verified:
            try: receiver.stop()
            except ReceiverError: pass
        write_json(output, dict(policy=POLICY, state='stopped', reason='bridge_service_stopped',
            updated_monotonic=time.monotonic(), sent=False, direction='stop',
            physical_output_enabled=args.motor_test, motor_gpio_enabled=args.motor_test,
            speed_supported=False, replay_allowed=False))


if __name__ == '__main__':
    main()
