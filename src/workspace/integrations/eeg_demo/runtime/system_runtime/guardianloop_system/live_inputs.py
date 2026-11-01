"""Read-only board APIs, sampled outside the display's frame loop."""
import json
from dataclasses import replace
import threading
import time
from urllib.request import build_opener, ProxyHandler


class BrainInputs:
    def __init__(self, clock=time.monotonic, fetch=None, hdmi_input=None, availability=None):
        self.clock=clock;self.lock=threading.Lock();self.stop=threading.Event()
        self.page='home';self.rows={};self.last_seq=None;self.reads=0
        self.fetch=fetch or self._fetch
        self.hdmi_input=hdmi_input
        self.availability=availability
        self.acquisition_owner=availability() if availability else None
        self.opener=build_opener(ProxyHandler({}))
        self.thread=threading.Thread(target=self._run,name='system-brain-readonly',daemon=True)
        self.thread.start()

    def _fetch(self, endpoint):
        port=9105 if endpoint=='ssvep-hdmi' else 9102
        with self.opener.open('http://127.0.0.1:'+str(port)+'/api/'+endpoint,timeout=.35) as response:
            if response.status!=200:raise ValueError('Unexpected status')
            raw=response.read(65537)
        if len(raw)>65536:raise ValueError('Oversize brain status')
        result=json.loads(raw)
        if not isinstance(result,dict):raise ValueError('Invalid brain status')
        return result

    def _sync_acquisition(self):
        if self.availability is None:return None
        owner=self.availability()
        with self.lock:
            if owner!=self.acquisition_owner:
                self.rows.clear();self.last_seq=None;self.acquisition_owner=owner
        return owner

    def _run(self):
        next_status=0.
        while not self.stop.is_set():
            owner=self._sync_acquisition()
            if self.availability is not None and owner is None:
                self.stop.wait(.15);continue
            now=self.clock()
            endpoints=['status','ssvep-hdmi'] if now>=next_status else []
            for endpoint in endpoints:
                started=self.clock()
                try:data=self.fetch(endpoint);error=None
                except (OSError,ValueError,TimeoutError) as exc:data={};error=type(exc).__name__
                if self.availability is not None and self._sync_acquisition()!=owner:continue
                with self.lock:
                    if self.availability is not None and (
                            owner!=self.acquisition_owner or self.availability()!=owner):continue
                    self.rows[endpoint]=(data,self.clock(),self.clock()-started,error);self.reads+=1
                if endpoint=='status':next_status=self.clock()+.7
            self.stop.wait(.15)

    def snapshot(self, now):
        owner=self._sync_acquisition()
        with self.lock:rows=dict(self.rows)
        # The polling thread can publish after the display loop sampled now.
        now=max(now,self.clock())
        available=self.availability is None or owner is not None
        if not available:rows={}
        data,stamp,_,error=rows.get('status',({},-float('inf'),0,'waiting'))
        fresh=not error and 0<=now-stamp<=1.5
        fatigue=data.get('fatigue',{}) if fresh else {}
        ready=fresh and data.get('stale') is False and fatigue.get('offline') is not True
        unavailable={'valid':False,'level':'unknown','state':'no_data'}
        if fresh and fatigue.get('calibration_retained') is True:
            unavailable.update(calibration_retained=True,
                calibration_current=fatigue.get('calibration_current',0),
                calibration_total=fatigue.get('calibration_total',15))
        hdmi,hstamp,_,herror=rows.get('ssvep-hdmi',({},-float('inf'),0,'waiting'))
        hdmi_fresh=not herror and 0<=now-hstamp<=1.5
        hdmi_identity=(hdmi.get('source')=='live' and hdmi.get('state_owner')=='acquisition'
                       and hdmi.get('control_enabled') is False)
        return dict(connected=fresh,state='live' if ready else 'no_data',acquisition_available=available,
                    fatigue=fatigue if ready else unavailable,
                    emotion=fatigue.get('emotion',{}) if ready else {'valid':False,'state':'no_data'},
                    source='live_board_api',updated_monotonic=stamp,transport_error=error,
                    ssvep_hdmi=hdmi if hdmi_fresh and hdmi_identity else {},
                    physical_output_enabled=False)

    def apply(self, controller, now):
        self.page=controller.page
        view=self.snapshot(now)
        if not view['acquisition_available']:
            controller.signal_lost(now)
            return view
        if view['state']!='live':
            # SSVEP has its own acquisition-owned fresh O1/O2 stream. An old
            # primary-monitoring window must not prevent starting that stream.
            independent_ready=(controller.page=='drive' and
                (view['ssvep_hdmi'].get('input') or {}).get('ready') is True)
            if independent_ready:
                if controller.monitor_labels:controller.monitoring_lost(now)
            elif controller.monitor_labels or controller.direction!='stop' or controller.direction_armed:
                controller.signal_lost(now)
        else:
            fatigue=view['fatigue'];seq=fatigue.get('seq',fatigue.get('window',fatigue.get('updated_at')))
            emotion=view['emotion']
            if (emotion.get('valid') is not True and controller.page=='music_offer'
                    and controller.monitor_labels.get('emotion',{}).get('source')=='GAMEEMO_condition'):
                controller._enter('home',now)
            for kind in ('emotion','fatigue'):
                if view[kind].get('valid') is True and kind in controller.monitor_labels:
                    controller.monitor_labels[kind]['received_at']=now
                elif view[kind].get('valid') is not True:
                    controller.monitor_labels.pop(kind,None)
            if emotion.get('valid') is not True:controller.alerts.pop('mood',None)
            if seq!=self.last_seq:
                self.last_seq=seq
                if fatigue.get('valid') is True:
                    level=fatigue.get('level','unknown')
                    controller.monitor('fatigue','severe_candidate' if level in (2,3,'high','severe','critical') else level,
                                       now,source='live_model_candidate',qualified=True)
                else:controller.monitor_labels.pop('fatigue',None)
                if emotion.get('valid') is True:
                    label=emotion.get('class_name',emotion.get('label','unknown'))
                    controller.monitor('emotion',label,now,source='GAMEEMO_condition',qualified=True)
                else:controller.monitor_labels.pop('emotion',None)
        if controller.page=='drive':
            # Native HDMI owns its session. A browser result is never substituted.
            row=self.hdmi_input(controller.page_id,now) if self.hdmi_input else None
            if (row and not row[3] and 0<=now-row[1]<=.45
                    and row[0].get('policy')=='ssvep-hdmi-experimental-v1'
                    and row[0].get('display_page_id')==controller.page_id):
                controller.ssvep(row[0],now,row[2]+max(0,now-row[1]))
            else:controller.ssvep(None,now)
        return view

    def close(self):
        self.stop.set();self.thread.join(timeout=2)
        if self.thread.is_alive():raise RuntimeError('Brain status poller did not stop')


class EyeInputs:
    """Original three-anchor native calibration and original dwell classifier."""
    def __init__(self,root):
        from calibration_worker import Worker
        from guide import Guide,DIRECTION_POINTS
        from tracking import Tracking
        self.worker=Worker(root,220,160,selection_test=True,relative=True)
        self.guide=Guide(points=DIRECTION_POINTS,collect_seconds=6)
        self.guide.phase='connecting';self.sent=None;self.compute_sent=False
        self.ready=False;self.samples=0;self.last_valid=None;self.error=None
        self.valid_samples=0;self.stale_samples=0;self.last_region=None
        self.last_packet=None
        self.tracking=Tracking();self.entry=None

    def confirm_position(self,now):
        event=self.tracking.event
        if self.guide.phase!='positioning':return False
        if (self.tracking.updated is None or now-self.tracking.updated>1.5 or not event
            or any(event[key]<=0 for key in ('left','right','pupil_left','pupil_right'))):
            self.guide.detail='尚无新鲜的双眼有效数据，请调整位置后再开始'
            return False
        self.guide.start(now);return True

    @property
    def control_enabled(self):
        return self.ready and self.guide.phase=='selection'

    def fail(self,controller,now,error):
        if self.error is not None:return
        self.error=error;self.ready=False;self.last_valid=None;self.last_region=None
        self.guide.phase='failed'
        self.guide.detail='采样中断，旧选择已撤销；PS_KEY0 重连，PS_KEY1 停止'
        controller.selection.clear_pending();controller.selection.selected=-1
        controller.last_selection=None
        controller._stop(now,'eye_input_lost');controller._clear_mi()

    def poll(self, controller, now):
        for event in self.worker.poll():
            if self.guide.phase=='failed':continue
            self.last_packet=now
            kind=event.get('kind')
            if kind=='ready':self.guide.phase='positioning'
            elif kind=='quality':self.tracking.update(event,now)
            elif kind=='point':self.guide.response(event.get('point'),event.get('accepted') is True)
            elif kind=='direction_ready':
                self.ready=event.get('trained') is True
                if self.ready:
                    from guardianloop_system.eye_entry import EyeEntryCheck
                    self.entry=EyeEntryCheck(controller.read_seconds)
                    self.guide.phase='verification'
                else:self.guide.phase='failed'
                self.sent=None
            elif kind=='horizontal_gaze' and self.ready:
                self.samples+=1
                source=event.get('monotonic_ns')
                fresh=type(source) is int and source>0 and 0<=now-source/1e9<=controller.selection.stale_seconds
                if event.get('valid') is True and fresh:
                    self.last_valid=source/1e9;self.valid_samples+=1
                    x=event.get('x')
                    self.last_region=min(2,int(x*3)) if type(x) in (int,float) and 0<=x<=1 else None
                elif not fresh:self.stale_samples+=1
                if self.guide.phase=='verification':
                    if self.entry.update(event,now):
                        controller.selection=self.entry.selection
                        controller._enter('home',now)
                        self.guide.phase='selection'
                    elif self.entry.failed:
                        row=self.entry.rows[-1]
                        self.fail(controller,now,'quick_check_wrong_region')
                        self.guide.detail='快速检查选区不符：目标%s，实际%s；请重新开始'%(
                            self.entry.names[row['target']],self.entry.names[row['selected']])
                elif self.control_enabled:controller.gaze(event,now)
            elif kind=='error':
                self.fail(controller,now,'native_exit_'+str(event.get('code')))
        if self.worker.done and self.guide.phase!='failed':
            self.fail(controller,now,'native_stopped')
        elif (self.guide.phase in ('positioning','verification','selection') and
              self.last_packet is not None and now-self.last_packet>3):
            self.fail(controller,now,'native_silent')
        view=self.entry.view(now) if self.guide.phase=='verification' else self.guide.tick(now)
        return replace(view,tracking=self.tracking.lines(now))

    def presented(self,view,now):
        if self.guide.phase=='verification':
            self.entry.presented(view,now);return
        token=(view.phase,view.point)
        if token==self.sent:return
        self.sent=token
        if view.phase=='collect':
            from guide import DIRECTION_POINTS
            self.guide.started=now
            self.worker.command('point %d %.9f %.9f'%((view.point,)+DIRECTION_POINTS[view.point]))
        elif view.phase=='compute' and not self.compute_sent:
            self.compute_sent=True;self.worker.command('compute')

    def snapshot(self,now):
        failed=self.guide.phase=='failed'
        return dict(connected=not failed and not self.worker.done,calibrated=self.ready,
                    valid=not failed and self.ready and self.last_valid is not None and 0<=now-self.last_valid<=.3,
                    state=self.guide.phase,samples=self.samples,error=self.error,
                    reconnect_required=failed,reconnect_action='eye_start' if failed else None,
                    recovery_detail=self.guide.detail if failed else None,
                    control_enabled=self.control_enabled,tracking=list(self.tracking.lines(now)),
                    quick_check=self.entry.snapshot() if self.entry else None,
                    valid_samples=self.valid_samples,stale_samples=self.stale_samples,
                    last_valid_monotonic=self.last_valid,last_region=self.last_region,
                    last_packet_monotonic=self.last_packet,
                    source='native_relative_eye',physical_output_enabled=False)

    def close(self):self.worker.close()
