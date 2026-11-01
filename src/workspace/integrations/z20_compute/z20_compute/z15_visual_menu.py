"""Optional eye menu, hosted by the original controller and its presentation gates."""
import json,os,time
from pathlib import Path
from guardianloop_system.eye_devices import EyeDeviceController
from guardianloop_system.core import TITLES,LABELS

VISUAL_LABELS={
    'visual_sources':('选择歌曲','返回多媒体','Z20 展示'),
    'z20_menu':('上个模式','进入','下个模式'),
    'z20_active':('左侧操作','返回选择','右侧操作'),
}
MODE_LABELS=dict(fluid=('左侧注入','返回选择','右侧注入'),spectrum=('上段录音','返回选择','下段录音'),
    npu=('上一分类任务','返回选择','下一分类任务'),spatial=('拍摄并生成','返回选择','切换视图'))


def device_status_text(devices):
    if devices.get('pending'):return '等待设备回执；确认就绪后换区选择动作'
    if devices.get('enabled') and devices.get('connected'):
        name={'hand':'灵巧手','pendulum':'倒立摆'}.get(devices['enabled'],'设备')
        return name+'可操作；中区先停止，换区后再次确认可返回'
    message=str(devices.get('message',''))
    if message in ('','等待注视启用'):return '未就绪：选择侧区重新连接，就绪后再确认动作'
    return ('连接未建立；' if not devices.get('connected') else '未使能；')+message


class VisualEyeController(EyeDeviceController):
    def __init__(self,link,visual_client,now=0.,**options):
        self.visual_client=visual_client;self.visual_view={}
        TITLES.update(visual_sources='音乐与外接展示',z20_menu='选择 Z20 模式',z20_active='Z20 展示操作')
        LABELS.update(VISUAL_LABELS)
        super().__init__(link,now,**options)

    def labels(self):
        if self.page=='media':return ('观看视频','返回主页','音乐与 Z20')
        if self.page=='z20_active':return MODE_LABELS.get(self.visual_view.get('mode'),VISUAL_LABELS['z20_active'])
        return super().labels()

    def device_update(self,now):
        super().device_update(now)
        view=self.visual_client.snapshot();self.visual_view=view
        if self.page in ('z20_menu','z20_active') and view.get('connected'):
            wanted='z20_menu' if view.get('menu') else 'z20_active'
            if wanted!=self.page:self._enter(wanted,now)

    def _enter(self,page,now):
        if getattr(self,'page',None) in ('z20_menu','z20_active') and page not in ('z20_menu','z20_active'):
            self.visual_client.send('stop')
        return super()._enter(page,now)

    def _stop(self,now,reason):
        super()._stop(now,reason)
        if reason!='page_transition' and getattr(self,'page',None) in ('z20_menu','z20_active'):
            self.visual_client.send('stop')

    def choose(self,region,now):
        if type(region) is not int or not 0<=region<=2:raise ValueError('invalid region')
        if self.page not in VISUAL_LABELS and not (self.page=='media' and region==2):return super().choose(region,now)
        if not self.tick(now) or self.presented_page!=self.page_id or now<self.read_until:return False
        old_page=self.page_id
        if self.page=='media':self._enter('visual_sources',now)
        elif self.page=='visual_sources':
            if region==2:self.visual_client.send('back');self._enter('z20_menu',now)
            else:self._enter(('music','media')[region],now)
        else:
            name=('left','enter','right')[region] if self.page=='z20_menu' else ('left','back','right')[region]
            accepted=self.visual_client.send(name)
            self._event('已提交 Z20 操作' if accepted else 'Z20 未连接，操作未发送',now,physical_output_enabled=False)
        self.last_selection=dict(page_id=old_page,region=region,monotonic=now,action=self.last_action)
        return True


def attach_from_environment(original,link,base,**options):
    path=Path(os.environ.get('Z20_VISUAL_CONFIG',str(Path(base)/'z20_visual_config.json')))
    if not path.exists():return original
    if path.stat().st_size>4096:raise ValueError('visual config too large')
    row=json.loads(path.read_text(encoding='utf-8'))
    if row.get('enabled') is not True:return original
    from .z15_visual_client import Z15VisualClient
    client=Z15VisualClient(row['host'],row['token'])
    return VisualEyeController(link,client,time.monotonic(),**options)


from .z15_visual_patch import patch_hdmi as patch_system_hdmi
