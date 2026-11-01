"""Read-only preparation gates. The acquisition backend repeats the EEG gate."""


def hdmi_preflight(system, backend, *, available=True):
    checks = [
        (available, 'HDMI 四角程序未就绪'),
        (system.get('page') == 'drive', '先在主页选择速度，再进入方向页'),
        (system.get('reading') is False, '等待方向页呈现并读完提示'),
        (not (system.get('alerts') or {}).get('fatigue'), '疲劳警示仍锁定'),
        (system.get('direction_armed') is True, '先点击“启用虚拟方向”'),
        (backend.get('policy') == 'ssvep-hdmi-experimental-v1', '等待板端 HDMI 识别接口'),
        ((backend.get('input') or {}).get('ready') is True,
         '脑电未就绪：'+str((backend.get('input') or {}).get('reason') or '无新鲜 O1/O2 数据')),
        (not system.get('stimulus_enabled'), '四角测试已经运行'),
        (not (system.get('hdmi_stimulus') or {}).get('preparing'), '正在准备同步原始录制'),
    ]
    eye=system.get('eye') or {}
    checks.append((eye.get('phase', eye.get('state')) not in
                   ('connecting','positioning','collect','compute','verification'),
                   '先完成或停止眼控标定'))
    reasons=[reason for passed,reason in checks if not passed]
    return dict(ready=not reasons, reasons=reasons,
                reason=reasons[0] if reasons else '准备就绪；确认后才启动，尚未闪烁',
                raw_recording_supported=backend.get('raw_recording_supported') is True,
                physical_output_enabled=False)
