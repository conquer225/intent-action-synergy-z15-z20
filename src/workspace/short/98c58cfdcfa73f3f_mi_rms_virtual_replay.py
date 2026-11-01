"""Private shared-RMS virtual control server; recorded input only, no PL or serial."""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import threading

from mi_cued import CuedMISession
from mi_cued_replay import feed_recording, load_recording
from mi_cued_server import make_handler
from mi_eegnet_rms import OfflineEEGNet


ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def page_bytes():
    page = (ROOT / 'mi_cued.html').read_text(encoding='utf-8')
    changes = {
        '左右手运动想象 · 有提示交互': '共享 RMS 运动想象 · 隔离虚拟控制回放',
        '<p>想象提示侧手掌反复握拳，不真实用力，不必调节情绪。每次先等数据热身，提示后收集0.5–2.5秒窗口；模型未通过正式晋升。</p>':
            '<p>本页只用已有台架记录测试闭环，不需要你想象或佩戴。提示后仍收集0.5–2.5秒窗口；答案来自模型，不来自提示。</p>',
        '<section>': (ROOT / 'mi_rms_virtual_page.html').read_text(encoding='utf-8') + '\n<section>',
        '</html>': '<script>\n' + (ROOT / 'mi_rms_virtual_ui.js').read_text(encoding='utf-8') + '\n</script>\n</html>',
    }
    for old, new in changes.items():
        expected = 3 if old == '<section>' else 1
        if page.count(old) != expected:
            raise ValueError('Base page changed; review RMS page insertion: ' + old)
        page = page.replace(old, new, 1)
    return page.encode('utf-8')


class RMSReplayApp:
    def __init__(self, model, raw, sequences, *, model_sha256, input_sha256,
                 log_path=None, feeder=feed_recording):
        self.session = CuedMISession(model, source='replay', log_path=log_path)
        self.raw, self.sequences, self.feeder = raw, sequences, feeder
        self.model_info = dict(name='fixed8_shared_rms_eegnet',
                               input_transform='fixed8_shared_window_rms_v1',
                               sha256=model_sha256, personal_accuracy_validated=False)
        self.state_lock = threading.Lock()
        self.action_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker = None
        self.record = dict(state='idle', run=0, samples_sent=0, total_samples=len(raw),
                           duration_seconds=len(raw)/250, input_sha256=input_sha256,
                           input_kind='recorded_bench_load_not_labeled_MI', error=None,
                           auto_repeat=False)

    def snapshot(self):
        with self.state_lock:
            record = dict(self.record)
        return dict(self.session.snapshot(), replay=record, candidate_model=dict(self.model_info))

    def feed(self, raw, seq, *, received_monotonic=None):
        state = self.session.feed(raw, seq, received_monotonic=received_monotonic)
        with self.state_lock:
            self.record['samples_sent'] += len(raw)
        return state

    def disconnect(self, reason='replay_eof'):
        stopped = self.stop_event.is_set()
        self.session.disconnect('replay_stopped' if stopped else reason)
        with self.state_lock:
            if self.record['state'] != 'error':
                self.record['state'] = 'stopped' if stopped else 'eof'

    def _run(self):
        try:
            self.feeder(self, self.raw, self.sequences, self.stop_event)
        except Exception as error:
            # A worker failure must be visible and withdraw the old control.
            with self.state_lock:
                self.record.update(state='error', error=type(error).__name__ + ': ' + str(error))
            self.session.disconnect('replay_error')
            raise

    def _stop(self):
        self.stop_event.set()
        self.session.disconnect('replay_stopped')
        if self.worker is not None:
            self.worker.join(timeout=2)
            if self.worker.is_alive():
                raise OSError('Replay worker did not stop; restart refused')
        with self.state_lock:
            self.record['state'] = 'stopped'

    def command(self, request):
        with self.action_lock:
            action = request.get('action')
            if action in ('replay_start', 'replay_stop'):
                if set(request) != {'action'}:
                    raise ValueError('Replay commands cannot specify data, speed or model answers')
                if action == 'replay_stop':
                    self._stop()
                else:
                    with self.state_lock:
                        running = self.record['state'] == 'running'
                    if running:
                        raise ValueError('Stop the current replay before restarting')
                    self._stop()
                    self.session.disconnect('replay_restarted')
                    self.stop_event = threading.Event()
                    with self.state_lock:
                        self.record.update(state='running', samples_sent=0,
                                           run=self.record['run']+1, error=None)
                    self.worker = threading.Thread(target=self._run, daemon=True)
                    self.worker.start()
            else:
                if action == 'start':
                    state = self.snapshot()
                    if state['replay']['state'] != 'running' or state['input_state'] != 'ready':
                        raise ValueError('Start replay and wait for fresh warmed-up input first')
                self.session.command(request)
            return self.snapshot()

    def close(self):
        with self.action_lock:
            self._stop()


def handler_for(app):
    base = make_handler(app)
    page = page_bytes()

    class Handler(base):
        def do_GET(self):
            if self.path in ('/', '/mi-cued'):
                self.reply(200, page, 'text/html; charset=utf-8')
            else:
                super().do_GET()

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--allow-experimental', action='store_true')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-file', type=Path, required=True)
    parser.add_argument('--audit-log', type=Path, required=True)
    args = parser.parse_args()
    if not args.allow_experimental:
        parser.error('Explicit experimental opt-in is required')
    if args.ready_file.exists() or args.audit_log.exists():
        parser.error('Fresh readiness and audit paths required')
    raw, seq = load_recording(args.input)
    model = OfflineEEGNet(args.model, allow_experimental=True)
    app = RMSReplayApp(model, raw, seq, model_sha256=digest(args.model),
                       input_sha256=digest(args.input), log_path=args.audit_log)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(app))

    def terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    ready = dict(pid=os.getpid(), port=server.server_address[1], source='replay',
                 control_enabled=False, production_eligible=False,
                 model_sha256=digest(args.model), input_sha256=digest(args.input))
    args.ready_file.write_text(json.dumps(ready, indent=2) + '\n', encoding='utf-8')
    print('RMS_VIRTUAL_READY', json.dumps(ready), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.server_close()


if __name__ == '__main__':
    main()
