"""HDMI page leases: required monitoring stays on; optional lanes fail closed."""
import json
import math
from pathlib import Path
import time

PAGES = frozenset(('home','drive','speed','media','video','video_nav','video_rate',
                   'speech','music','music_offer'))


def tasks_for(page):
    if page not in PAGES:
        raise ValueError('Unknown system page')
    return dict(filter_quality=True, emotion=True, fatigue=True, mi_virtual=True,
                ssvep_candidate=page=='drive', seed_candidate=False)


class PageLease:
    def __init__(self, path, clock=time.monotonic, *, mode='scripted_hdmi_replay',
                 standalone_tasks=()):
        if mode not in ('scripted_hdmi_replay','live_readonly_hdmi'):
            raise ValueError('Unsupported page lease mode')
        self.path=Path(path);self.clock=clock;self.checked=-math.inf
        self.mode=mode;self.standalone_tasks=frozenset(standalone_tasks)
        if not self.standalone_tasks.issubset(('ssvep_candidate','seed_candidate')):
            raise ValueError('Only optional candidates have standalone scheduling')
        self.missing=False
        self.page='home';self.valid=False;self.tasks=tasks_for('home')

    def enabled(self, task):
        now=self.clock()
        if now-self.checked>=.25:
            self.checked=now;self.valid=False;self.page='home'
            self.missing=False
            try:
                if self.path.stat().st_size>4096:raise ValueError('Oversize page lease')
                data=json.loads(self.path.read_text())
                stamp=data['updated_monotonic']
                if (data['mode']!=self.mode or data['physical_output_enabled'] is not False
                        or type(stamp) not in (int,float) or not math.isfinite(stamp)
                        or not 0<=now-stamp<=2 or data['page'] not in PAGES):
                    raise ValueError('Invalid page lease')
                self.page=data['page'];self.valid=True
            except FileNotFoundError:
                self.missing=True
            except (OSError,ValueError,KeyError,TypeError):
                pass  # Missing/expired control input deliberately closes optional lanes.
            self.tasks=tasks_for(self.page)
        if task not in self.tasks:raise ValueError('Unknown scheduled task')
        if task not in ('ssvep_candidate','seed_candidate'):return True
        return (self.missing and task in self.standalone_tasks) or (self.valid and self.tasks[task])


class ScheduledLane:
    """Wrap a resettable synchronous lane, not a process's final close method."""
    def __init__(self,lane,path,task,**lease_options):
        self.lane=lane;self.lease=PageLease(path,**lease_options);self.task=task
        self.enabled=True;self.suspended_packets=0;self.transitions=0

    def __getattr__(self,name):return getattr(self.lane,name)

    @property
    def gaps(self):return self.lane.gaps

    @gaps.setter
    def gaps(self,value):self.lane.gaps=value

    def refresh(self):
        enabled=self.lease.enabled(self.task)
        if enabled!=self.enabled:
            self.lane.disconnect('page_task_resumed' if enabled else 'page_task_suspended')
            self.enabled=enabled;self.transitions+=1
        return enabled

    def packet(self,*args,**kwargs):
        if not self.refresh():
            self.suspended_packets+=1
            return []
        return self.lane.packet(*args,**kwargs)

    def idle(self,*args,**kwargs):
        if self.refresh():return self.lane.idle(*args,**kwargs)


class ScheduledSink:
    """Paused candidates don't copy or enqueue each incoming raw packet."""
    def __init__(self,sink,path,task,**lease_options):
        self.sink=sink;self.lease=PageLease(path,**lease_options);self.task=task;self.suppressed=0

    def __getattr__(self,name):return getattr(self.sink,name)

    def offer(self,*args):
        if not self.lease.enabled(self.task):
            self.suppressed+=1
            return True
        return self.sink.offer(*args)
