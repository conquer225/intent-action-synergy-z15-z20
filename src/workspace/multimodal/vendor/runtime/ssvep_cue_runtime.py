"""Acquisition-owned SSVEP cue state; the public web service only relays it."""
import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from ssvep_cued import CuedSSVEPSession
from ssvep_free import FreeSSVEPSession
from cyton_trial_recorder import CONTROL_PATH
from ssvep_recording import SSVEPRecordingControl
from ssvep_study import SSVEPStudy

BACKEND_HOST = '127.0.0.1'
BACKEND_PORT = 9105
LOG_PATH = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq/ssvep_cued_trials.jsonl')


def unavailable(reason):
    return dict(state='unavailable', accepted=False, result=None, observed_hz=None,
                streak=0, reason=reason, source='live', state_owner='acquisition',
                observation_mode='producer_callbacks', control_enabled=False)


class SSVEPCueRuntime:
    def __init__(self, log_path=LOG_PATH, port=BACKEND_PORT, clock=time.monotonic,
                 record_status_path=None, input_transport='direct_main_loop', record_command_path=CONTROL_PATH):
        self.clock = clock
        self.session = CuedSSVEPSession(clock=clock, log_path=log_path,
                                       observation_mode='producer_callbacks')
        self.free_session = FreeSSVEPSession(clock=clock,
            log_path=Path(log_path).with_name('ssvep_free_events.jsonl') if log_path else None)
        self.command_lock = threading.RLock()
        self.free_failed = False
        self.latest = None
        self.record_status_path = record_status_path
        self.record_command_path = record_command_path
        self.recording_control = None
        self.study = SSVEPStudy(Path(log_path).parent/'ssvep_studies', clock) if log_path else None
        self.input_transport = input_transport
        self.failed = False
        self.closed = False
        self.server = ThreadingHTTPServer((BACKEND_HOST, port), self._handler())
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       name='ssvep-cue-control', daemon=True)
        self.thread.start()

    def _stale(self, event):
        stamp, lag = event.get('updated_monotonic'), event.get('input_age_seconds')
        return (type(stamp) not in (int, float) or type(lag) not in (int, float)
                or not math.isfinite(stamp) or not math.isfinite(lag) or lag < 0
                or self.clock() < stamp or self.clock()-stamp+lag > .5)

    def observe(self, event):
        with self.command_lock:
            self._observe(event)

    def _observe(self, event):
        self.latest = event
        if not self.free_failed:
            try:
                recording = self._recording_context()
                self.free_session.check_raw_recording(recording['trial_id'] if recording else None)
                self.free_session.observe(event, self._stale(event))
            except OSError:
                self.free_failed = True
                print('SSVEP_FREE_DISABLED: audit I/O failed; primary acquisition continues', flush=True)
        if not self.failed:
            try:
                recording = self._recording_context()
                self.session.check_raw_recording(recording['trial_id'] if recording else None)
                self.session.observe({'live': event, 'stale': self._stale(event)})
                self._maintain_recording()
            except OSError:
                self.failed = True
                print('SSVEP_CUE_DISABLED: audit log I/O failed; primary acquisition continues', flush=True)

    def snapshot(self):
        with self.command_lock:
            if self.failed:
                return unavailable('cue_audit_io_failed')
            recording = self._recording_context()
            self.session.check_raw_recording(recording['trial_id'] if recording else None)
            self._maintain_recording()
            return dict(self.session.snapshot(), source='live', state_owner='acquisition',
                        raw_recording_supported=self.record_status_path is not None,
                        raw_recording=recording, recording_control=self._recording_view(), input=self.input_snapshot())

    def input_snapshot(self):
        event = self.latest
        if event is None:
            return dict(ready=False, state='no_data', reason='startup', age_seconds=None)
        stale = self._stale(event)
        ready = (not stale and event.get('source') == 'live' and event.get('valid') is True
                 and event.get('state') == 'candidate_only'
                 and (event.get('quality') or {}).get('hard_bad') is False)
        stamp, lag = event.get('updated_monotonic'), event.get('input_age_seconds')
        age = (self.clock()-stamp+lag if type(stamp) in (int, float) and type(lag) in (int, float)
               else float('nan'))
        scores = event.get('scores') if ready else None
        ranked = sorted(scores, reverse=True) if scores else []
        return dict(ready=ready, state='ready' if ready else ('no_data' if stale else event.get('state')),
            reason=event.get('reason') or ('input_expired' if stale else event.get('state')),
            age_seconds=round(age, 4) if math.isfinite(age) and age >= 0 else None,
            warmup_samples=event.get('warmup_samples', 0), required_samples=event.get('required_samples', 660),
            quality=event.get('quality'), scores=scores, frequency_hz=event.get('frequency_hz') if ready else None,
            top_score=ranked[0] if ranked else None, margin=ranked[0]-ranked[1] if len(ranked)>1 else None,
            input_transport=self.input_transport)

    def _recording_context(self):
        if self.record_status_path is None:
            return None
        if self.recording_control is None:
            self.recording_control = SSVEPRecordingControl(self.record_status_path,
                self.record_command_path, self.clock, self.session.log_path)
        return self.recording_control.context()

    def _maintain_recording(self):
        if self.recording_control is not None:
            control = self.recording_control
            session = self.free_session if control.kind == 'free' else self.session
            view = session.snapshot()
            if (self.study and self.study.pending and control.kind == 'free'
                    and self.study.pending['session_id'] == view.get('id')
                    and view['state'] == 'stopped'):
                self.study.stopped(view.get('reason'))
            control.maintain(view['state'] in ('active','awaiting_presentation'))
            if (self.study and self.study.pending and control.kind == 'free'
                    and control.owned is None):
                self.study.finish(control.metadata())

    def _recording_view(self):
        return self.recording_control.snapshot() if self.recording_control else dict(state='idle')

    def command(self, request):
        with self.command_lock:
            if (request.get('action') in ('start', 'record_start') and self.recording_control
                    and self.recording_control.owned and self.recording_control.kind == 'free'):
                raise ValueError('请先结束自由选择原始录制')
            if (request.get('action') == 'start' and self.free_session.snapshot()['state']
                    in ('active', 'awaiting_presentation')):
                raise ValueError('请先停止自由选择 SSVEP 会话')
            return self._cue_command(request)

    def free_snapshot(self):
        with self.command_lock:
            if self.free_failed:
                return unavailable('free_audit_io_failed')
            recording = self._recording_context()
            self.free_session.check_raw_recording(recording['trial_id'] if recording else None)
            self._maintain_recording()
            return dict(self.free_session.snapshot(), input=self.input_snapshot(),
                        raw_recording_supported=self.record_status_path is not None,
                        raw_recording=recording, recording_control=self._recording_view(),
                        study=self.study.snapshot() if self.study else {'state':'unsupported'})

    def free_command(self, request):
        with self.command_lock:
            if self.free_failed:
                raise OSError('Free SSVEP audit unavailable')
            action = request.get('action')
            if action in ('start', 'record_start', 'study_create'):
                if self.session.snapshot()['state'] in ('active', 'awaiting_presentation'):
                    raise ValueError('请先停止有提示 SSVEP 会话')
                if (self.recording_control and self.recording_control.owned
                        and (self.recording_control.kind != 'free' or action != 'start')):
                    raise ValueError('已有待关闭的原始录制，不能覆盖')
            if action in ('start', 'record_start'):
                event = self.latest
                if (event is None or self._stale(event) or event.get('source') != 'live'
                        or event.get('valid') is not True or event.get('state') != 'candidate_only'
                        or (event.get('quality') or {}).get('hard_bad') is not False):
                    raise ValueError('需要新鲜且 O1/O2 硬质量合格的真实 EEG；未启动')
            try:
                if any(k in request for k in ('target_hz', 'selected_hz', 'result')):
                    raise ValueError('自由选择接口不能接收期望答案')
                if action == 'study_create':
                    if request.get('consent') is not True or self.study is None:
                        raise ValueError('需要主动确认并支持板端计划保存')
                    if self.free_session.snapshot()['state'] in ('active', 'awaiting_presentation'):
                        raise ValueError('请先停止自由选择会话')
                    self.study.create()
                    return self.free_snapshot()
                if action in ('record_start', 'record_cancel', 'record_status'):
                    self._recording_context()
                    control = self.recording_control
                    if control is None:
                        raise ValueError('当前采集不支持原始录制')
                    if action == 'record_start':
                        if request.get('consent') is not True:
                            raise ValueError('必须主动确认录制与闪烁注意事项')
                        if self.free_session.snapshot()['state'] in ('active', 'awaiting_presentation'):
                            raise ValueError('请先停止自由选择会话')
                        study = (self.study.context(request['study_id'])
                                 if request.get('study_id') and self.study else None)
                        if request.get('study_id') and study is None:
                            raise ValueError('当前采集不支持独立计划')
                        control.start_free(request.get('frequencies'), study)
                        if study:
                            self.study.reserve(study, control.owned)
                    elif action == 'record_cancel':
                        if control.kind == 'free':
                            control.stop()
                    return self.free_snapshot()
                recording = self._recording_context()
                control = self.recording_control
                if action == 'start':
                    if request.get('require_raw_recording') is True and (
                            control is None or control.kind != 'free' or control.phase != 'ready'):
                        raise ValueError('同步原始录制尚未就绪；未启动闪烁')
                    if self.study and self.study.pending:
                        if (request.get('require_raw_recording') is not True
                                or request.get('frequencies') != [8,10,12,14]):
                            raise ValueError('计划采集必须使用四角及同步原始录制')
                self.free_session.command(request, raw_recording=recording)
                if action == 'start' and control and control.owned:
                    control.attached = True
                    if self.study and self.study.pending:
                        self.study.attach(self.free_session.snapshot()['id'])
                if action == 'presented' and self.study and self.study.pending:
                    self.study.presented()
                return self.free_snapshot()
            except OSError:
                self.free_failed = True
                if self.recording_control and self.recording_control.kind == 'free':
                    self.recording_control.stop()
                raise

    def _cue_command(self, request):
        if self.failed:
            raise OSError('SSVEP cue audit is unavailable')
        event = self.latest
        action = request.get('action')
        if action in ('start','record_start') and (
                event is None or self._stale(event) or event.get('source') != 'live'
                or event.get('state') != 'candidate_only' or event.get('valid') is not True
                or (event.get('quality') or {}).get('hard_bad') is not False):
            raise ValueError('需要持续接收且硬质量合格的真实 EEG，试次尚未启动')
        if action in ('record_start','record_cancel','record_status'):
            self._recording_context()
            if self.recording_control is None:
                raise ValueError('当前采集不支持原始录制')
            if action == 'record_start':
                if request.get('consent') is not True:
                    raise ValueError('必须主动确认录制与闪烁注意事项')
                if any(s.snapshot()['state'] in ('active','awaiting_presentation') for s in (self.session,self.free_session)):
                    raise ValueError('请先停止当前 SSVEP 会话')
                self.recording_control.start(request.get('target_hz'))
            elif action == 'record_cancel':
                if self.recording_control.kind == 'cue':
                    self.recording_control.stop()
            return self.snapshot()
        try:
            request = dict(request)
            request.pop('raw_recording', None)
            if request.get('action') == 'start':
                request['raw_recording'] = self._recording_context()
                if request.get('require_raw_recording') is True and request['raw_recording'] is None:
                    raise ValueError('未启动同步原始录制。普通演示请取消“必须同步录制”；需留存原始数据时，先启动板端 SSVEP 录制再开始。试次未启动')
                if (request.get('require_raw_recording') is True and self.recording_control
                        and self.recording_control.owned is not None
                        and self.recording_control.phase != 'ready'):
                    raise ValueError('原始录制仍在准备，尚未收到完整首批样本')
            result = self.session.command(request)
            if action == 'start' and self.recording_control and self.recording_control.owned:
                self.recording_control.attached = True
            self._maintain_recording()
        except OSError:
            self.failed = True
            raise
        return dict(result, source='live', state_owner='acquisition',
                    raw_recording_supported=self.record_status_path is not None,
                    raw_recording=self._recording_context(), recording_control=self._recording_view(), input=self.input_snapshot())

    def _handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def reply(self, code, payload):
                raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path not in ('/api/ssvep-cue', '/api/ssvep-free'):
                    self.reply(404, {'error': 'Unknown endpoint'}); return
                try:
                    payload = owner.free_snapshot() if self.path == '/api/ssvep-free' else owner.snapshot()
                    code = 200
                except OSError:
                    if self.path == '/api/ssvep-free':
                        owner.free_failed = True
                    else:
                        owner.failed = True
                    code, payload = 503, unavailable('cue_audit_io_failed')
                self.reply(code, payload)

            def do_POST(self):
                expected = 'http://%s:%s' % owner.server.server_address
                if self.path not in ('/api/ssvep-cue', '/api/ssvep-free'):
                    self.reply(404, {'error': 'Unknown endpoint'}); return
                if self.headers.get('Origin') != expected:
                    self.reply(403, {'error': 'Same-origin request required'}); return
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    self.reply(415, {'error': 'JSON object required'}); return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 4096:
                        raise ValueError('Body must be 1..4096 bytes')
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError('JSON object required')
                    payload = owner.free_command(payload) if self.path == '/api/ssvep-free' else owner.command(payload)
                    code = 200
                except (ValueError, TypeError) as error:
                    code, payload = 400, {'error': str(error)}
                except OSError:
                    if self.path == '/api/ssvep-free':
                        owner.free_failed = True
                    else:
                        owner.failed = True
                    code, payload = 503, unavailable('cue_audit_io_failed')
                self.reply(code, payload)

        return Handler

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.recording_control:
            self.recording_control.stop()
        self.observe(dict(source='live', state='no_data', valid=False,
                          updated_monotonic=self.clock(), input_age_seconds=0.0))
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class SSVEPCueBridge:
    def __init__(self, port=BACKEND_PORT):
        self.backend = 'http://%s:%s' % (BACKEND_HOST, port)
        self.opener = build_opener(ProxyHandler({}))

    def _request(self, command=None, endpoint='/api/ssvep-cue'):
        data = None if command is None else json.dumps(command, allow_nan=False).encode('utf-8')
        headers = {} if data is None else {'Content-Type': 'application/json', 'Origin': self.backend}
        try:
            with self.opener.open(Request(self.backend+endpoint, data=data,
                                          headers=headers), timeout=.8) as response:
                raw = response.read(65537)
        except HTTPError as error:
            if error.code == 400:
                with error:
                    payload = json.loads(error.read(65536))
                raise ValueError(payload.get('error', 'SSVEP command rejected'))
            error.close()
            raise OSError('SSVEP cue backend unavailable')
        if len(raw) > 65536:
            raise ValueError('SSVEP response exceeds limit')
        result = json.loads(raw)
        if (not isinstance(result, dict) or result.get('source') != 'live'
                or result.get('state_owner') != 'acquisition'
                or result.get('observation_mode') != 'producer_callbacks'
                or result.get('control_enabled') is not False):
            raise ValueError('SSVEP cue backend identity mismatch')
        json.dumps(result, allow_nan=False)
        return result

    def command(self, request):
        return self._request(request)

    def free_command(self, request):
        return self._request(request, '/api/ssvep-free')

    def free_snapshot(self):
        try:
            return self._request(endpoint='/api/ssvep-free')
        except (OSError, URLError, ValueError, TypeError):
            return unavailable('free_backend_unavailable')

    def snapshot(self):
        try:
            return self._request()
        except (OSError, URLError, ValueError, TypeError):
            return unavailable('cue_backend_unavailable')
