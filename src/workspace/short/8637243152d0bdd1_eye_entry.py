"""Three observed selections before menu control; not an accuracy estimate."""
from dataclasses import replace

from selection import Selection


class EyeEntryCheck:
    targets=(1,0,2)
    names=('左区','中区','右区')

    def __init__(self,read_seconds=1.2):
        self.selection=Selection()
        self.read_seconds=read_seconds
        self.rows=[];self.presented_at=None;self.failed=False

    @property
    def complete(self):
        return len(self.rows)==3 and not self.failed

    def detail(self):
        if self.complete:return '三次快速功能检查通过，正在进入菜单（不是准确率验收）'
        if self.failed:return '快速功能检查未通过，请重新检查位置并标定'
        return '快速功能检查 %d/3：请看%s，选中后自动换区（不是准确率验收）'%(
            len(self.rows)+1,self.names[self.targets[len(self.rows)]])

    def presented(self,view,now):
        if (not self.complete and not self.failed and self.presented_at is None
            and view.phase=='selection' and view.detail==self.detail()):
            self.presented_at=now

    def update(self,event,now):
        if self.complete or self.failed:return False
        source=event.get('monotonic_ns')
        if (self.presented_at is None or now<self.presented_at+self.read_seconds
            or type(source) is not int or source/1e9<self.presented_at+self.read_seconds):
            self.selection.clear_pending();return False
        if not self.selection.update_horizontal(event,now):return False
        target=self.targets[len(self.rows)];region=self.selection.selected
        self.rows.append(dict(target=target,selected=region,correct=region==target,
            presented_monotonic=self.presented_at,confirmed_monotonic=now,
            response_ms=1000*(now-self.presented_at)))
        self.failed=region!=target;self.presented_at=None
        return self.complete

    def view(self,now):
        return replace(self.selection.view(now),point=len(self.rows),detail=self.detail())

    def snapshot(self):
        return dict(planned=3,completed=len(self.rows),passed=self.complete,
            failed=self.failed,trials=list(self.rows),accuracy_estimate=False,
            timing_origin='HDMI presentation acknowledgement, not optical measurement')
