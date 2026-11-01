"""Frozen base shared-RMS entry using the existing cue-locked virtual controller."""
import hashlib
from pathlib import Path
import time

import numpy as np

from mi_cued import CuedMISession, WINDOW_SAMPLES, hard_quality
from mi_cued_server import make_handler as base_handler
from mi_eegnet_rms import OfflineEEGNet
from mi_features import CHANNELS

MODEL_SHA256 = '363daf3b68da6e80495319052447ec83e06b9e3e327a1bd0ff9e6023a5b54221'


class RMSVirtualSession(CuedMISession):
    def __init__(self, model, *, source='live', clock=time.monotonic, log_path=None):
        super().__init__(model, source=source, clock=clock, log_path=log_path)

    def snapshot(self):
        with self.lock:
            state = super().snapshot()
            invalid = []
            ready = state['input_state'] == 'ready' and self.model is not None
            if ready:
                sqi = hard_quality(self.raw[-WINDOW_SAMPLES:])
                bad = (sqi[:, 0] > 100) | (sqi[:, 1] >= .8) | (sqi[:, 2] > 0)
                invalid = [name for name, flag in zip(CHANNELS, bad) if flag]
                ready = not bool(np.any(bad))
            state['quality'] = dict(ready=ready, invalid_channels=invalid,
                                    reason='signal_invalid' if invalid else
                                    ('hard_gates_pass' if ready else state['input_state']))
            state['candidate_model'] = dict(name='fixed8_shared_rms_eegnet', sha256=MODEL_SHA256,
                                           input_transform='fixed8_shared_window_rms_v1',
                                           personal_head_enabled=False, promoted=False)
            return state

    def command(self, request):
        with self.lock:
            if request.get('action') == 'start':
                if set(request) - {'action', 'target', 'virtual_control'}:
                    raise ValueError('Start cannot specify data, labels or model answers')
                if request.get('target') != 'rest' and not self.snapshot()['quality']['ready']:
                    raise ValueError('Fresh warmed-up hard-quality-passing input required')
            return super().command(request)


def create_session(model_path, *, source, log_path):
    path = Path(model_path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError('Frozen base RMS checksum mismatch')
    if source == 'live' and log_path is None:
        raise ValueError('Live virtual control requires an audit log')
    return RMSVirtualSession(OfflineEEGNet(path, allow_experimental=True), source=source, log_path=log_path)


def page_bytes(*, integrated=False):
    page = Path(__file__).with_name('mi_cued.html').read_text(encoding='utf-8')
    replacements = {
        '左右手运动想象 · 有提示交互': '基础 RMS 运动想象 · 隔离虚拟控制',
        '实验模型未晋升正式版。': '使用冻结基础 RMS 模型；个人适配头已停用，未晋升正式版。',
        "let trialId = null, epoch = 0, pending = false, polling = false;":
            "let trialId = null, epoch = 0, pending = false, polling = false, canStart = false;",
        "for (const target of ['left','right','rest']) el(target).disabled = active || pending;":
            "for (const target of ['left','right','rest']) el(target).disabled = active || pending || (target !== 'rest' && !canStart);",
        "el('virtualEnabled').disabled = active || pending;":
            "el('virtualEnabled').disabled = active || pending || !canStart;",
        "function render(data) {":
            "function render(data) {\n  canStart = data.input_state === 'ready' && data.quality?.ready === true;",
        "'；模型：' + data.model_status;":
            "'；质量：' + (data.quality?.reason || '未知') + '；基础 RMS，个人适配：关闭';",
        "function stopTrial(reason = 'user_stopped') {":
            "function stopTrial(reason = 'user_stopped') {\n  if (reason === 'network_error') canStart = false;",
        'setInterval(poll, 400);': 'buttons(false);\nsetInterval(poll, 400);',
    }
    for old, new in replacements.items():
        if page.count(old) != 1:
            raise ValueError('Review base page insertion: ' + old)
        page = page.replace(old, new, 1)
    if integrated:
        page = page.replace('基础 RMS 运动想象 · 隔离虚拟控制', '基础 RMS 运动想象 · 虚拟控制')
        page = page.replace('实验入口可由正式网页代理或隔离回放服务提供，是否开启由ARM配置决定；',
                            'MI实验入口已安装到正式ARM程序，模型未晋升；启用由板端配置决定，虚拟动作需主动勾选；')
        page = page.replace('</main>', '<p><a href="/">返回主网页</a></p></main>')
    return page.encode('utf-8')


def make_handler(session, multitask=None):
    page = page_bytes(integrated=True)

    class Handler(base_handler(session, multitask=multitask)):
        def do_GET(self):
            if self.path in ('/', '/mi-cued'):
                self.reply(200, page, 'text/html; charset=utf-8')
            else:
                super().do_GET()
    return Handler
