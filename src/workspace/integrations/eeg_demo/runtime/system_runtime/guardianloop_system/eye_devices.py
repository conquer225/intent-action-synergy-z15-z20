"""Opt-in device menus using the original presentation and gaze selection gates."""
from .core import SystemController, TITLES, LABELS

DEVICE_LABELS = {
    'equipment': ('灵巧手', '倒立摆', '速度与方向'),
    'hand': ('张开', '停止操作', '闭合'),
    'pendulum_menu': ('平衡启停', '返回设备', '左右单圈'),
    'pendulum_balance': ('启动平衡', '停止操作', '停止平衡'),
    'pendulum_turn': ('左转一圈', '停止操作', '右转一圈'),
}
TITLES.update(equipment='设备与方向', hand='眼控灵巧手', pendulum_menu='眼控倒立摆',
              pendulum_balance='倒立摆平衡', pendulum_turn='倒立摆短动作')
LABELS.update(DEVICE_LABELS)
ACTIVE_LABELS = {
    'hand': DEVICE_LABELS['hand'],
    'pendulum_balance': DEVICE_LABELS['pendulum_balance'],
    'pendulum_turn': DEVICE_LABELS['pendulum_turn'],
}


class EyeDeviceController(SystemController):
    def __init__(self, link, now=0., **options):
        self.device_link = link
        self.device_enabled = None
        self.return_pending = False
        self.entry_pending = False
        super().__init__(now, **options)

    def _stop(self, now, reason):
        super()._stop(now, reason)
        self.device_link.stop(reason)
        self.device_enabled = None
        self.entry_pending = False

    def _enter(self, page, now):
        if page == 'music_offer' and self.page in DEVICE_LABELS:
            self._event('心情提示保留，继续当前设备操作', now)
            return
        self.return_pending = False
        return super()._enter(page, now)

    def service_device_entry(self, now, allowed):
        """A selected device prepares once, only after a fresh live presentation."""
        if not allowed:
            self.entry_pending = False
            return
        if (not self.entry_pending or self.return_pending or self.page not in ACTIVE_LABELS
                or self.presented_page != self.page_id or now < self.read_until):
            return
        self.entry_pending = False
        target = 'hand' if self.page == 'hand' else 'pendulum'
        accepted = self.device_link.request(target, 'enable')
        self._event('正在连接设备；就绪后选择动作' if accepted else '连接未提交，请重新选择动作',
                    now, device=target)

    def device_update(self, now):
        enabled = self.device_link.snapshot()['enabled']
        if enabled != self.device_enabled:
            self.device_enabled = enabled
            # A changed enable state needs a fresh presentation before any motion.
            self.page_id += 1
            self.selection.clear_pending()
            self.last_selection = None
            self.read_until = now + self.read_seconds

    def labels(self):
        if self.page == 'home':
            old = super().labels()
            return ('设备与方向', old[1], old[2])
        if self.page in ACTIVE_LABELS:
            if self.return_pending:
                left, _, right = ACTIVE_LABELS[self.page]
                return (left, '返回设备' if self.page == 'hand' else '返回倒立摆', right)
            return ACTIVE_LABELS[self.page]
        return super().labels()

    def device_presentation(self):
        devices = self.device_link.snapshot()
        if self.page not in ACTIVE_LABELS:
            pendulum = self.page == 'pendulum_menu'
            return dict(badge='选择功能' if pendulum else '选择设备',
                        status=('当前无设备控制', '左中右停留确认', 'PS_KEY1 暂停'),
                        hint='确认功能后自动准备连接' if pendulum else '选中设备后查看可用动作',
                        message='选择平衡启停或左右单圈' if pendulum else '选择要操作的设备')
        target = 'hand' if self.page == 'hand' else 'pendulum'
        ready = devices.get('connected') and devices.get('enabled') == target
        badge = ('已停止' if self.return_pending else '可操作' if ready else
                 '连接中' if devices.get('pending') or self.entry_pending else '未就绪')
        name = '灵巧手' if target == 'hand' else '倒立摆'
        status = (name + (' 已连接' if devices.get('connected') else ' 未连接'),
                  '等待回执' if devices.get('pending') else '动作需注视确认', '中区先停，再确认返回')
        if self.return_pending:
            hint = '控制已撤销；换区后确认中区返回，侧区可重新连接'
            message = '停止请求已发出；当前页面保留'
        elif ready:
            hint = '注视约 1.4 秒确认动作 | PS_KEY1 随时暂停'
            message = str(devices.get('message', ''))
        elif devices.get('pending') or self.entry_pending:
            hint = '正在准备控制；就绪后换区选择动作，不会补执行旧动作'
            message = '正在连接设备，等待确认'
        else:
            hint = '选择左区或右区重新连接；确认就绪后，再次选择动作'
            message = str(devices.get('message', '连接未建立'))
        return dict(badge=badge, status=status, hint=hint, message=message)

    def choose(self, region, now):
        if type(region) is not int or not 0 <= region <= 2:
            raise ValueError('Invalid region')
        if self.page not in DEVICE_LABELS and not (self.page == 'home' and region == 0):
            return super().choose(region, now)
        if (not self.tick(now) or self.presented_page != self.page_id or now < self.read_until):
            return False
        page, page_id = self.page, self.page_id
        if page == 'home':
            self._enter('equipment', now)
        elif page == 'equipment':
            self._enter(('hand', 'pendulum_menu', 'speed')[region], now)
            self.entry_pending = self.page in ACTIVE_LABELS
        elif page == 'pendulum_menu':
            self._enter(('pendulum_balance', 'equipment', 'pendulum_turn')[region], now)
            self.entry_pending = self.page in ACTIVE_LABELS
        elif region == 1:
            if self.return_pending:
                self._enter('equipment' if page == 'hand' else 'pendulum_menu', now)
            else:
                self._stop(now, '用户停止设备控制')
                self.return_pending = True
                self.page_id += 1
                self.read_until = now + self.read_seconds
                self.selection.clear_pending()
                self._event('已请求停止；换区后再次确认中区可返回', now)
        else:
            target = 'hand' if page == 'hand' else 'pendulum'
            self.return_pending = False
            self.entry_pending = False
            if self.device_enabled != target:
                # Reconnection never stores/replays the requested movement.
                accepted = self.device_link.request(target, 'enable')
            else:
                actions = {'hand': ('open', 'close'),
                           'pendulum_balance': ('start', 'stop'),
                           'pendulum_turn': ('left', 'right')}
                accepted = self.device_link.request(target, actions[page][region // 2])
            if not accepted:
                self._event('设备请求未提交：等待回执后重新选择动作',now,device=target)
                return False
            self._event('正在连接设备；就绪后请重新选择动作' if self.device_enabled != target
                        else '设备请求已提交，等待回执', now, device=target)
        self.last_selection = dict(page_id=page_id, region=region, monotonic=now,
                                   action=self.last_action)
        return True

    def snapshot(self, now):
        view = super().snapshot(now)
        view['devices'] = self.device_link.snapshot()
        view['device_control_configured'] = True
        view['physical_output_enabled'] = bool(view['devices']['enabled'])
        view['device_control_mode'] = 'native_eye_over_c3_lan'
        view['device_navigation'] = dict(return_pending=self.return_pending,
            entry_pending=self.entry_pending,stop_keeps_page=True)
        # The separate acquisition lease still disables EEG/SSVEP device output.
        return view
