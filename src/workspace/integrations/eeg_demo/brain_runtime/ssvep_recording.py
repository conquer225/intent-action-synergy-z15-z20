"""Bounded, acknowledgement-driven raw capture requested explicitly by the browser."""
import hashlib
import json
import math
from pathlib import Path
import secrets
import time

from cyton_trial_recorder import CONTROL_PATH, atomic_json, read_json, recording_command_lock
from ssvep_cued import FREQUENCIES


class SSVEPRecordingControl:
    def __init__(self, status_path, command_path=CONTROL_PATH, clock=time.monotonic, cue_log=None):
        self.status_path = Path(status_path)
        self.command_path = Path(command_path)
        self.clock = clock
        self.cue_log = str(cue_log) if cue_log else None
        self.owned = None
        self.phase = 'idle'
        self.error = None
        self.command_id = None
        self.requested_at = None
        self.attached = False
        self.capture_path = None
        self.kind = None

    def context(self):
        s = read_json(self.status_path)
        stamp = s.get('updated_monotonic')
        if (s.get('task') != 'ssvep' or s.get('state') != 'recording'
                or type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not 0 <= self.clock()-stamp <= 2):
            return None
        return {k:s.get(k) for k in ('trial_id','path','samples','elapsed_seconds')}

    def start(self, target):
        if type(target) not in (int, float) or target not in (*FREQUENCIES, 0):
            raise ValueError('无效的 SSVEP 提示目标')
        protocol = dict(schema='ssvep-browser-raw-v1', requested_targets=[target],
                        capture_kind='single_cued_trial')
        self._start(protocol, 'ssvep_cued_diagnostic', 'cue', allow_external=True)

    def start_free(self, frequencies, study=None):
        if frequencies not in ([8, 10, 12, 14], [10, 12]):
            raise ValueError('无效的自由选择频率布局')
        if study and frequencies != [8, 10, 12, 14]:
            raise ValueError('独立采集必须保持四角同时闪烁，包括中心休息段')
        protocol = dict(schema='ssvep-free-browser-raw-v1', stimulus_frequencies=frequencies,
                        capture_kind='four_corner_free_choice', study=study)
        self._start(protocol, 'ssvep_free_diagnostic', 'free', allow_external=False)

    def start_hdmi(self, frequencies):
        if frequencies != [8, 10, 12, 14]:
            raise ValueError('HDMI 录制必须保持核验过的四角布局')
        protocol = dict(schema='ssvep-hdmi-raw-v1', stimulus_frequencies=frequencies,
                        capture_kind='hdmi_four_corner_free_choice',
                        scan_events='ssvep_hdmi_events.jsonl',
                        scan_evidence_is_not_optical_measurement=True)
        self._start(protocol, 'ssvep_hdmi_diagnostic', 'hdmi', allow_external=False)

    def _start(self, protocol, condition, kind, allow_external):
        if self.owned is not None:
            raise ValueError('上次同步录制尚未结束；请稍候')
        with recording_command_lock(self.command_path):
            state = read_json(self.status_path)
            pending = read_json(self.command_path)
            if state.get('state') == 'recording':
                if allow_external and self.context() is not None:
                    self.phase = 'external'
                    return
                raise ValueError('已有其他或过期录制，不能覆盖；请先结束它')
            if pending.get('id') and pending['id'] != state.get('last_command'):
                raise ValueError('上一条录制命令尚未确认，未启动闪烁')
            token, identifier = secrets.token_hex(8), secrets.token_hex(8)
            protocol = dict(protocol, optical_onset_measured=False,
                            maximum_seconds=45,
                            alignment='same_boot_usb_receive_monotonic_not_optical',
                            candidate_stream_index_is_not_raw_row_index=True)
            checksum = hashlib.sha256(json.dumps(protocol,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            log_path = (str(Path(self.cue_log).with_name('ssvep_'+kind+'_events.jsonl'))
                        if kind in ('free', 'hdmi') and self.cue_log else self.cue_log)
            atomic_json(self.command_path, dict(id=token,action='start',trial_id=identifier,
                participant_id='SSVEP_browser',task='ssvep',phase='ssvep_diagnostic',
                condition=condition,stimulus_note='explicit_browser_checkbox',
                protocol=protocol,protocol_digest=checksum,cue_log_path=log_path,max_seconds=45))
        self.owned = identifier
        self.command_id = token
        self.requested_at = self.clock()
        self.attached = False
        self.capture_path = None
        self.kind = kind
        self.phase, self.error = 'starting', None

    def stop(self):
        if self.owned is None or self.phase == 'stopping':
            return
        with recording_command_lock(self.command_path):
            state = read_json(self.status_path)
            pending = read_json(self.command_path)
            if state.get('trial_id') == self.owned and state.get('state') == 'recording':
                if pending.get('id') and pending['id'] != state.get('last_command'):
                    return  # Retry on the next maintenance callback, never overwrite a command.
                token = secrets.token_hex(8)
                atomic_json(self.command_path,dict(id=token,action='stop',trial_id=self.owned))
                self.command_id, self.phase = token, 'stopping'
            elif pending.get('id') == self.command_id and state.get('last_command') != self.command_id:
                # Start can still be consumed. Retain ownership and close it after its ACK.
                self.phase = 'cancelling'
            else:
                self.owned = None
                self.phase = 'complete'

    def maintain(self, trial_active):
        if self.owned is None:
            return
        state = read_json(self.status_path)
        if self.phase == 'stopping':
            if state.get('last_command') == self.command_id:
                self.owned = None
                self.phase = 'complete' if state.get('state') == 'complete' else 'error'
                self.error = None if self.phase == 'complete' else str(state.get('detail'))
            return
        if state.get('last_command') == self.command_id:
            if state.get('state') == 'recording' and state.get('trial_id') == self.owned:
                self.capture_path = state.get('path')
                if self.phase == 'cancelling' or (self.attached and not trial_active):
                    self.stop()
                    return
                context = self.context()
                path = Path(context['path'])/'samples_i32le.bin' if context and context.get('path') else None
                if context and context.get('samples',0) >= 250 and path and path.exists() and path.stat().st_size >= 8000:
                    self.phase = 'ready'
            else:
                self.owned = None
                self.phase = 'error'
                self.error = str(state.get('detail') or '录制未开始或已结束')
                return
        if not self.attached and self.clock()-self.requested_at > 12:
            self.error = '录制启动超时；未启动闪烁'
            self.stop()

    def snapshot(self):
        return dict(state=self.phase, owned_trial_id=self.owned, error=self.error,
                    auto_stop_seconds=45)

    def metadata(self):
        return read_json(Path(self.capture_path)/'metadata.json') if self.capture_path else {}
