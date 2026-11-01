"""Three-region eye menus and separate top-level modes share one selection state."""
from collections import deque
from . import vendor
from selection import Selection

MEDIA_PAGES=frozenset(('more','speech','media','video','video_nav','video_rate','music'))
EYE_PAGES=MEDIA_PAGES|frozenset(('home','devices','actions','pend_start','turns','auxiliary'))

class Menu:
    read_seconds=1.2
    def __init__(self,tasks,origin='live'):
        self.tasks=tasks;self.origin=origin;self.selection=Selection();self.page='home';self.interaction_mode='eye'
        self.last_selection=None;self.presented_at=None;self.epoch=0;self.message='PL_KEY0切换模式；PL_KEY1停止'
        self.media=None;self.monitor_labels={};self.timeline=deque(maxlen=128)
        self.raw=deque(maxlen=500);self.rms=None;self.pressed=None;self.signal_state='waiting';self.brain_reason='等待输入'
        self.scores=None;self.status={};self.benchmark=None
    @property
    def ssvep_active(self):return self.interaction_mode=='eeg' and (self.page=='ssvep_devices' or self.page=='actions' and self.tasks.mode=='brain')
    def _clear_mi(self):pass # Original EyeInputs compatibility; no MI actuator effects.
    def _stop(self,now,reason):
        self.tasks.estop();self.message=reason;self.timeline.append(reason)
    def _enter(self,page,now):
        if page!=self.page:
            self.tasks.estop()
            if self.media and self.page in MEDIA_PAGES and page not in MEDIA_PAGES:self.media.stop()
        self.page=page;self.selection.clear_pending();self.presented_at=None;self.epoch+=1
    def switch_mode(self,mode,now):
        if mode not in ('eye','emg','eeg'):raise ValueError('unknown interaction mode')
        self.tasks.close()
        if self.media:self.media.stop()
        self.interaction_mode=mode;self._enter({'eye':'home','emg':'emg','eeg':'eeg'}[mode],now)
        self.scores=None;self.message='已切换模式，执行端保持停止'
    def select(self,mode,device,now):
        self.tasks.select(mode,device)
        if mode!='mpu':self.interaction_mode={'eye':'eye','brain':'eeg','contact':'emg'}[mode]
        self._enter('emg' if mode=='contact' else 'mpu' if mode=='mpu' else 'actions',now)
        if mode=='mpu':self.message='保持MPU静止，PS_KEY0置零；再按一次启用；PL_KEY1停止'
    def page_to(self,page,now):
        if page not in ('operate','process','technical','devices','actions','auxiliary','emg','mpu','eeg','mi','ssvep_devices'):raise ValueError('unknown page')
        self.tasks.estop();self._enter('home' if page=='operate' else page,now)
    def presented(self,now):
        if self.presented_at is None:self.presented_at=now
    def labels(self):
        if self.page in MEDIA_PAGES:return self.media.labels(self.page) if self.media else {'more':['交流表达','多媒体','返回主页']}.get(self.page,['','','返回'])
        if self.page in ('home','devices'):return ['灵巧手','倒立摆','表达与媒体']
        if self.page=='auxiliary':return ['MPU倒立摆','信号过程','返回主页']
        if self.page=='turns':return ['左动作','右动作','返回']
        if self.page=='pend_start':return ['启摆','停止','返回']
        if self.page=='emg':return ['灵巧手开合','原始信号','辅助入口']
        if self.page in ('eeg','mi'):return ['情绪与疲劳','运动想象','SSVEP控制']
        if self.page=='ssvep_devices':return ['灵巧手','倒立摆','返回脑电','停止']
        if self.page in ('actions','turns','pend_start') and not self.tasks.enabled:
            return ['启用控制','查看过程','返回','停止'] if self.tasks.mode=='brain' else ['启用控制','查看过程','返回']
        if self.tasks.mode=='brain':return ['张开','闭合','返回脑电','停止'] if self.tasks.device=='hand' else ['启摆','左动作','右动作','停止']
        if self.tasks.device=='hand':return ['张开','闭合','返回']
        return ['启停','左右动作','返回']
    def gaze(self,event,now):
        if (self.interaction_mode!='eye' or self.page not in EYE_PAGES or self.presented_at is None
            or now-self.presented_at<self.read_seconds or self.media and self.page in MEDIA_PAGES and self.media.paused):
            self.selection.clear_pending();return False
        if not isinstance(event,dict) or type(event.get('monotonic_ns')) is not int or event['monotonic_ns']/1e9<self.presented_at+self.read_seconds:
            self.selection.clear_pending();return False
        if self.page=='video' and type(event.get('x')) in (int,float) and 1/3<=event['x']<=2/3:
            self.selection.update_horizontal(event,now);return False
        if not self.selection.update_horizontal(event,now):return False
        self.last_selection=self.selection.selected;self.choose(self.last_selection,now);return True
    def choose(self,n,now):
        if type(n) is not int or not 0<=n<3:raise ValueError('three-region menu required')
        if self.interaction_mode!='eye' or self.page not in EYE_PAGES:return
        if self.page in ('home','devices'):
            if n==2:self._enter('more',now)
            else:self.select('eye',('hand','pendulum')[n],now)
            return
        if self.page in MEDIA_PAGES:
            if self.page=='more' and n==2:self._enter('home',now);return
            if not self.media:self.message='媒体目录未配置；选择返回主页';return
            destination=self.media.choose(self.page,n,now)
            if destination!=self.page:self._enter(destination,now)
            self.message=self.media.detail;return
        if self.page=='auxiliary':
            if n==0:self.select('mpu','pendulum',now)
            else:self._enter(('mpu','process','home')[n],now)
            return
        if self.page in ('actions','turns','pend_start') and not self.tasks.enabled:
            if n==0:
                self.tasks.enable();self.presented_at=None;self.selection.clear_pending();self.epoch+=1
                self.message='已启用，请阅读动作选项后重新选择'
            elif n==1:self.page_to('process',now)
            else:self._enter('home' if self.page=='actions' else 'actions',now)
            return
        if n==2 and self.page in ('actions','turns','pend_start'):
            self._enter('home' if self.page=='actions' else 'actions',now);return
        if self.page=='actions' and self.tasks.device=='pendulum':
            self._enter(('pend_start','turns')[n],now);return
        if self.page=='pend_start' and n==1:self._stop(now,'倒立摆已停止');return
        action=('open','close')[n] if self.tasks.device=='hand' else ('left','right')[n] if self.page=='turns' else 'start'
        if not self.tasks.enabled:self.message='执行端尚未启用；输入 enable 启用';return
        self.tasks.action(action);self.timeline.append('指令：'+action+'；网络ACK已接收')
    def brain_choice(self,n,now):
        if not self.ssvep_active or type(n) is not int or not 0<=n<4:return
        if n==3:self._stop(now,'脑控已停止');return
        if self.page=='ssvep_devices':
            if n<2:self.select('brain',('hand','pendulum')[n],now)
            else:self.tasks.close();self._enter('eeg',now)
        elif self.page=='actions':
            if not self.tasks.enabled:
                if n==0:self.tasks.enable();self.presented_at=None;self.epoch+=1
                else:self.tasks.close();self._enter('eeg',now)
                return
            if self.tasks.device=='hand' and n==2:self.tasks.close();self._enter('eeg',now);return
            if self.tasks.enabled:self.tasks.action(('open','close')[n] if self.tasks.device=='hand' else ('start','left','right')[n])
    def pause(self,now):
        self.tasks.estop()
        if self.media and self.page in MEDIA_PAGES:
            self._enter(self.media.pause(self.page),now);self.message=self.media.detail
        else:
            self.selection.toggle_pause();self.message='眼控已暂停' if self.selection.paused else '眼控已继续；执行端保持停止'
    def snapshot(self,now):
        v=self.selection.view(now);labels=self.labels()
        page='brain' if self.ssvep_active else 'operate' if self.page in EYE_PAGES else self.page
        return dict(origin=self.origin,page=page,menu_page=self.page,interaction_mode=self.interaction_mode,
                    mode=self.tasks.mode,device=self.tasks.device,enabled=self.tasks.enabled,title=self.page,
                    labels=labels,hover=v.hover,progress=v.progress,message=self.message,raw=list(self.raw),rms=self.rms,
                    pressed=self.pressed,signal_state=self.signal_state,timeline=list(self.timeline),scores=self.scores,
                    brain_reason=self.brain_reason,angles=self.status.get('hand',{}).get('angles'),
                    pendulum_state=self.status.get('pendulum',{}).get('state'),benchmark=self.benchmark,epoch=self.epoch,
                    media=self.media.snapshot() if self.media else None)
