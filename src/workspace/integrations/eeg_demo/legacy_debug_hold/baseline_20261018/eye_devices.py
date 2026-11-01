"""Opt-in device menus using the original presentation and gaze selection gates."""
from .core import SystemController, TITLES, LABELS

DEVICE_LABELS = {
    'equipment': ('灵巧手', '倒立摆', '速度与方向'),
    'hand': ('启用灵巧手', '停止并返回', '保持停止'),
    'pendulum_menu': ('平衡控制', '停止并返回', '左右短动作'),
    'pendulum_balance': ('启用倒立摆', '停止并返回', '保持停止'),
    'pendulum_turn': ('启用倒立摆', '停止并返回', '保持停止'),
}
TITLES.update(equipment='设备与方向', hand='眼控灵巧手', pendulum_menu='眼控倒立摆',
              pendulum_balance='倒立摆平衡', pendulum_turn='倒立摆短动作')
LABELS.update(DEVICE_LABELS)
ACTIVE_LABELS = {
    'hand': ('张开', '停止并返回', '闭合'),
    'pendulum_balance': ('启动平衡', '停止并返回', '停止平衡'),
    'pendulum_turn': ('左转一圈', '停止并返回', '右转一圈'),
}


class EyeDeviceController(SystemController):
    def __init__(self, link, now=0., **options):
        self.device_link = link
        self.device_enabled = None
        super().__init__(now, **options)

    def _stop(self, now, reason):
        super()._stop(now, reason)
        self.device_link.stop(reason)
        self.device_enabled = None

    def device_update(self, now):
        enabled = self.device_link.snapshot()['enabled']
        if enabled != self.device_enabled:
            self.device_enabled = enabled
            # Enable ACK changes available commands: require a newly presented page.
            self.page_id += 1
            self.selection.clear_pending()
            self.last_selection = None
            self.read_until = now + self.read_seconds

    def labels(self):
        if self.page == 'home':
            old = super().labels()
            return ('设备与方向', old[1], old[2])
        if self.page in ACTIVE_LABELS:
            target = 'hand' if self.page == 'hand' else 'pendulum'
            if self.device_enabled == target:
                return ACTIVE_LABELS[self.page]
        return super().labels()

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
        elif page == 'pendulum_menu':
            self._enter(('pendulum_balance', 'equipment', 'pendulum_turn')[region], now)
        elif region == 1:
            self._enter('equipment' if page == 'hand' else 'pendulum_menu', now)
        else:
            target = 'hand' if page == 'hand' else 'pendulum'
            if self.device_enabled != target:
                if region == 0:
                    self.device_link.request(target, 'enable')
                else:
                    self.device_link.stop('gaze_stop')
            else:
                actions = {'hand': ('open', 'close'),
                           'pendulum_balance': ('start', 'stop'),
                           'pendulum_turn': ('left', 'right')}
                self.device_link.request(target, actions[page][region // 2])
            self._event('设备请求已提交，等待回执', now, device=target)
        self.last_selection = dict(page_id=page_id, region=region, monotonic=now,
                                   action=self.last_action)
        return True

    def snapshot(self, now):
        view = super().snapshot(now)
        view['devices'] = self.device_link.snapshot()
        view['device_control_configured'] = True
        view['physical_output_enabled'] = bool(view['devices']['enabled'])
        view['device_control_mode'] = 'native_eye_over_c3_lan'
        # The separate acquisition lease still disables EEG/SSVEP device output.
        return view
