"""Bounded same-origin bridge to the acquisition-owned loopback MI process."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from mi_service_config import CONFIG_PATH, BACKEND_PORT, CHANNELS, MODEL_SHA256, enabled

BACKEND = 'http://127.0.0.1:%s' % BACKEND_PORT
DISABLED_PAGE = ('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>左右手运动想象 · 默认关闭</title><main><h1>左右手运动想象 · 实验入口</h1>
<p>固定八通道：F3、F4、C3、C4、T7、T8、O1、O2。</p>
<p>默认关闭：不会启动MI模型或工作进程，不会生成预测，永不驱动外设。</p>
<button disabled>想象左手</button><button disabled>想象右手</button><button disabled>休息</button>
<p>开启需要在板端明确修改实验配置并重启采集服务；网页不能自行开启。</p>
<p>模型仍未晋升，不能把工程验收或模型分数当作佩戴准确率。</p>
<p><a href="/">返回主网页</a></p></main></html>''').encode('utf-8')


def unavailable(reason, active=False):
    return dict(id=None, state='disabled' if not active else 'rejected', target=None,
                reason=reason, result=None, source='live', input_state='no_data',
                received_samples=0, channels=list(CHANNELS), enabled=active,
                control_enabled=False, production_eligible=False,
                model_status='experimental_unpromoted',
                onset_alignment='server_receipt_watermark_not_optical_sync')


class MIWebBridge:
    def __init__(self, config_path=CONFIG_PATH):
        self.config_path = config_path
        self.opener = build_opener(ProxyHandler({}))

    def active(self):
        return enabled(self.config_path)

    def page(self):
        try:
            active = self.active()
        except (OSError, ValueError):
            active = False
        if not active:
            return DISABLED_PAGE
        from mi_rms_live_virtual import page_bytes
        return page_bytes(integrated=True)

    def request(self, command=None):
        try:
            active = self.active()
        except (OSError, ValueError):
            return (200 if command is None else 409), unavailable('mi_configuration_invalid')
        if not active:
            return (200 if command is None else 409), unavailable('mi_disabled')
        data = None if command is None else json.dumps(command, allow_nan=False).encode('utf-8')
        headers = {} if data is None else {'Content-Type': 'application/json', 'Origin': BACKEND}
        request = Request(BACKEND + '/api/mi-cue', data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=.8) as response:
                body = response.read(65537)
            if len(body) > 65536:
                raise ValueError('MI response exceeds limit')
            result = json.loads(body)
            if (not isinstance(result, dict) or result.get('channels') != list(CHANNELS)
                    or result.get('source') != 'live' or result.get('control_enabled') is not False
                    or result.get('production_eligible') is not False
                    or result.get('model_status') != 'experimental_unpromoted'):
                raise ValueError('MI backend identity mismatch')
            model = result.get('candidate_model')
            if (not isinstance(model, dict) or model.get('sha256') != MODEL_SHA256
                    or model.get('name') != 'fixed8_shared_rms_eegnet'
                    or model.get('input_transform') != 'fixed8_shared_window_rms_v1'
                    or model.get('personal_head_enabled') is not False or model.get('promoted') is not False):
                raise ValueError('Wrong RMS model or unexpected personal head')
            prediction = result.get('result')
            if prediction is not None and (not isinstance(prediction, dict)
                    or prediction.get('source') != 'live' or prediction.get('control_enabled') is not False):
                raise ValueError('MI prediction identity mismatch')
            json.dumps(result, allow_nan=False)
            return 200, dict(result, enabled=True)
        except HTTPError as error:
            # A rejected trial command must not return a prior candidate.
            error.close()
            return (400 if error.code == 400 else 503), unavailable('mi_command_rejected', True)
        except (OSError, URLError, ValueError, TypeError):
            return (200 if command is None else 503), unavailable('mi_backend_unavailable', True)
