"""Unified interaction policy; all effects are virtual, never device writes."""
from collections import deque
import math
from pathlib import Path
import sys

from wheelchair_ssvep.dry_run_bridge import DirectionPreview
# Existing eye modules are script-oriented and import their sibling guide.
sys.path.append(str(Path(__file__).resolve().parents[1]/'brain_eye_coexist/candidate/eye/src'))
from selection import Selection


TITLES = {'home':'GuardianLoop 综合系统','drive':'SSVEP 方向选择',
    'speed':'目标速度档位（未接硬件）','media':'多媒体', 'video':'视频观看',
    'video_nav':'选择上一条 / 下一条','video_rate':'评价当前视频',
    'speech':'想说的话','music':'歌曲选择','music_offer':'要选择舒缓歌曲吗？',
    'fatigue_alert':'疲劳警示已锁定，请先休息'}
LABELS = {'home':('速度与方向','交流表达','多媒体'),
    'drive':('','返回主页',''),
    'speed':('加速一档','返回方向界面','减速一档'),
    'media':('观看视频','返回主页','选择歌曲'),
    'video':('翻动视频','','评价'),
    'video_nav':('上一条','返回主页','下一条'),
    'video_rate':('好','返回观看','厌倦'),
    'speech':('我想喝水','返回主页','我需要帮助'),
    'music':('上一首','返回多媒体','下一首'),
    'music_offer':('选择歌曲','暂不需要','返回主页'),
    'fatigue_alert':('返回主页','恢复正常后确认','保持暂停')}


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


class SystemController:
    """Reuses audited dwell and SSVEP gates; no network/serial/audio methods."""
    read_seconds=1.2
    mi_pair_seconds=8.0
    direction_idle_seconds=15.0

    def __init__(self, now=0.0, *, direction_idle_enabled=True):
        if type(direction_idle_enabled) is not bool:
            raise ValueError('Direction idle policy must be explicit')
        self.direction_idle_enabled=direction_idle_enabled
        self.page='home';self.page_id=0;self.presented_page=-1;self.read_until=now+self.read_seconds
        self.selection=Selection();self.direction_gate=DirectionPreview()
        self.direction='stop';self.direction_until=0.;self.direction_armed=False
        self.speed_level=1;self.video_index=0;self.video_count=1;self.rating=None
        self.song_index=0;self.song_count=1;self.phrase=None
        self.events=deque(maxlen=128);self.alerts={};self.monitor_labels={}
        self.mi_first=None;self.mi_rearmed=False;self.mi_neutral_end=None
        self.mi_session=None;self.mi_seen=deque(maxlen=64)
        self.last_now=now;self.last_action='启动默认停止';self.exited=False
        self.last_selection=None
        self.mood_offer_at=-math.inf
        self.direction_idle_deadline=None;self.last_direction_window=None
        self.selected_frequency=None;self.force_stopped=False
        self.direction_requires_start=False

    def _event(self, action, now, **detail):
        self.last_action=action
        self.events.append(dict(action=action,monotonic=now,**detail))

    def _stop(self, now, reason):
        self.direction='stop';self.direction_until=0.;self.direction_armed=False
        self.selected_frequency=None
        self.direction_gate=DirectionPreview()
        self._event('撤销方向',now,reason=reason,physical_output_enabled=False)

    def _enter(self, page, now):
        if page not in LABELS:raise ValueError('Unknown page')
        self._stop(now,'page_transition')
        self.page=page;self.page_id+=1;self.read_until=now+self.read_seconds
        self.direction_idle_deadline=None;self.last_direction_window=None
        self._clear_mi()
        self.last_selection=None
        self.selection.clear_pending()  # Preserve held-region lock across pages.
        self._event('切换界面',now,page=page)

    def presented(self, page_id, now):
        if not self.tick(now):return
        if type(page_id) is int and page_id==self.page_id and self.presented_page!=page_id:
            self.presented_page=page_id;self.read_until=now+self.read_seconds
            if self.page=='drive' and not self.direction_requires_start and self.direction_idle_enabled:
                self.direction_idle_deadline=now+self.direction_idle_seconds
            self.selection.clear_pending()

    def direction_started(self, page_id, now):
        if (not self.tick(now) or self.page!='drive' or page_id!=self.page_id
                or not self.direction_armed or 'fatigue' in self.alerts):
            return False
        if self.direction_idle_enabled:
            self.direction_idle_deadline=now+self.direction_idle_seconds
        self._event('方向测试已呈现，开始15秒无选择计时' if self.direction_idle_enabled
                    else 'SSVEP测试：暂不自动退出方向页',now)
        return True

    def tick(self, now):
        if not finite(now) or now<self.last_now:
            self._stop(self.last_now,'clock_regression');self._clear_mi()
            self.selection.clear_pending();return False
        self.last_now=now
        self.selection.view(now)
        if self.direction!='stop' and now>self.direction_until:self._stop(now,'direction_expired')
        if (self.page=='drive' and self.direction_idle_deadline is not None
                and now>=self.direction_idle_deadline):
            self._enter('home',now)
            self._event('15秒无可信方向选择，停止并返回主页',now)
        if self.mi_first and now-self.mi_first['confirmed_at']>self.mi_pair_seconds:self._clear_mi()
        for kind,item in list(self.monitor_labels.items()):
            if now-item['received_at']>2:
                if kind=='emotion' and item['source']=='GAMEEMO_condition':
                    self.alerts.pop('mood',None)
                    if self.page=='music_offer':self._enter('home',now)
                del self.monitor_labels[kind]
        return True

    def gaze(self, event, now):
        if not self.tick(now):return False
        if not isinstance(event,dict):self.selection.clear_pending();return False
        stamp=event.get('monotonic_ns')
        if (self.presented_page!=self.page_id or now<self.read_until or
            type(stamp) is not int or stamp/1e9<self.read_until):
            self.selection.clear_pending();return False
        if self.page=='drive':
            # Corner gaze may re-arm the centre, but cannot execute side menus.
            selected=self.selection.update_horizontal(event,now)
            if selected and self.selection.selected==1:return self.choose(1,now)
            return False
        # On video pages, the centre is the viewing area, not a dwell button.
        if self.page=='video' and finite(event.get('x')) and 1/3<=event['x']<=2/3:
            # Stable viewing re-arms a side, but cannot select a centre command.
            self.selection.update_horizontal(event,now);return False
        if self.selection.update_horizontal(event,now):
            return self.choose(self.selection.selected,now)
        return False

    def choose(self, region, now):
        """Already-confirmed selection; public prototype labels it manual simulation."""
        if type(region) is not int or not 0<=region<=2:raise ValueError('Invalid region')
        if not self.tick(now):return False
        if self.presented_page!=self.page_id or now<self.read_until:return False
        if not self.labels()[region]:return False
        page=self.page
        page_id=self.page_id
        if page=='home':
            if region==1 and 'fatigue' in self.alerts:
                self._enter('fatigue_alert',now)
            else:
                if region==0:self.speed_level=1
                self._enter(('speed','speech','media')[region],now);self.exited=False
        elif page=='drive':self._enter(('speed','home','media')[region],now)
        elif page=='speed':
            if region==1:self._enter('drive',now)
            else:
                self.speed_level=max(1,min(3,self.speed_level+(1 if region==0 else -1)))
                self._event('虚拟目标档位',now,level=self.speed_level,hardware_speed_supported=False)
        elif page=='media':self._enter(('video','home','music')[region],now)
        elif page=='video':
            if region!=1:self._enter('video_nav' if region==0 else 'video_rate',now)
        elif page=='video_nav':
            if region==1:self._enter('home',now)
            else:
                self.video_index=(self.video_index+(-1 if region==0 else 1))%self.video_count
                self.rating=None
                self._event('虚拟切换视频',now,index=self.video_index)
                self._enter('video',now)
        elif page=='video_rate':
            if region!=1:
                self.rating='好' if region==0 else '厌倦'
                self._event('用户视频评价',now,index=self.video_index,rating=self.rating)
            self._enter('video',now)
        elif page=='speech':
            if region==1:self._enter('home',now)
            else:
                self.phrase=LABELS[page][region];self._event('选择表达（未发声）',now,text=self.phrase)
        elif page=='music':
            if region==1:self._enter('media',now)
            else:
                self.song_index=(self.song_index+(-1 if region==0 else 1))%self.song_count
                self._event('虚拟选歌（未发声）',now,index=self.song_index)
        elif page=='music_offer':
            self.alerts.pop('mood',None);self._enter(('music','media','home')[region],now)
        elif page=='fatigue_alert':
            if region==0:self._enter('home',now)
            elif region==1:
                if not self.acknowledge_alert('fatigue',now):return False
            else:self._event('保持暂停，警示未解除',now)
        self.last_selection=dict(page_id=page_id,region=region,monotonic=now,
                                 action=self.last_action)
        return True

    def arm_virtual_direction(self, now):
        if not self.tick(now):return False
        if (self.page!='drive' or self.presented_page!=self.page_id or
            now<self.read_until or 'fatigue' in self.alerts):return False
        self.direction_armed=True;self.force_stopped=False
        self._event('仅启用虚拟方向预览',now);return True

    def ssvep(self, snapshot, now, request_seconds=0):
        if not self.tick(now):return {'preview_direction':'stop','reason':'clock_regression'}
        result=self.direction_gate.observe(snapshot,now,request_seconds,origin='system_virtual_adapter')
        if self.page!='drive' or not self.direction_armed or 'fatigue' in self.alerts:
            self.direction='stop';self.direction_until=0.;self.selected_frequency=None
            return {**result,'preview_direction':'stop','reason':'system_gate_closed'}
        self.direction=result['preview_direction'];self.direction_until=now+.3 if self.direction!='stop' else 0.
        self.selected_frequency=snapshot['result'] if self.direction!='stop' else None
        if self.direction!='stop':
            window=(snapshot['id'],snapshot['decision']['window_end_index_exclusive'])
            if window!=self.last_direction_window:
                self.last_direction_window=window
                if self.direction_idle_enabled:
                    self.direction_idle_deadline=now+self.direction_idle_seconds
        return result

    def force_stop(self, now):
        if not self.tick(now):return False
        self.force_stopped=True;self._enter('home',now)
        self._event('人工强制停止已执行，需重新进入并启用方向',now,physical_command_sent=False)
        return True

    def labels(self):
        if self.page=='home' and 'fatigue' in self.alerts:
            return (LABELS['home'][0],'查看疲劳警示',LABELS['home'][2])
        return LABELS[self.page]

    def fatigue_ack_ready(self, now):
        item=self.monitor_labels.get('fatigue',{})
        label=item.get('label')
        normal=(type(label) is int and label==0) or (isinstance(label,str) and label in ('normal','正常'))
        return ('fatigue' in self.alerts and normal and item.get('qualified') is True
                and finite(item.get('received_at')) and 0<=now-item['received_at']<=2)

    def _clear_mi(self):
        self.mi_first=None;self.mi_rearmed=False;self.mi_neutral_end=None

    def mi(self, event, now):
        if not self.tick(now):return False
        required=('id','session','label','received_at','window_start','window_end','accepted','quality_ready')
        if not isinstance(event,dict) or any(k not in event for k in required):self._clear_mi();return False
        if (not finite(event['received_at']) or not 0<=now-event['received_at']<=.5 or
            event['accepted'] is not True or event['quality_ready'] is not True or
            not isinstance(event['id'],str) or not event['id'] or
            not isinstance(event['session'],str) or not event['session'] or
            type(event['window_start']) is not int or type(event['window_end']) is not int or
            not 0<=event['window_start']<event['window_end']):
            self._clear_mi();return False
        if event['session']!=self.mi_session:
            self._clear_mi();self.mi_seen.clear();self.mi_session=event['session']
        if event['id'] in self.mi_seen:return False
        self.mi_seen.append(event['id'])
        label=event['label']
        if label=='neutral':
            # A future trusted adapter must verify disengagement; binary logits alone cannot.
            if self.mi_first and event['window_start']>=self.mi_first['window_end']:
                self.mi_rearmed=True;self.mi_neutral_end=event['window_end']
            return False
        if label!='right':self._clear_mi();return False
        if self.mi_first is None:
            self.mi_first=dict(event,confirmed_at=now);self.mi_rearmed=False;return False
        if not self.mi_rearmed or event['window_start']<self.mi_neutral_end:return False
        self._clear_mi();self._enter('home',now);self.exited=True
        self._event('两次独立右手确认：退出当前功能',now,physical_command_sent=False)
        return True

    def monitoring_lost(self, now):
        if self.monitor_labels.get('emotion',{}).get('source')=='GAMEEMO_condition':
            self.alerts.pop('mood',None)
            if self.page=='music_offer':self._enter('home',now)
        self.monitor_labels.clear();self._event('信号失效，撤销旧结果',now)

    def signal_lost(self, now):
        self._stop(now,'input_lost');self._clear_mi();self.selection.clear_pending()
        self.monitoring_lost(now)

    def monitor(self, kind, label, now, *, source, qualified=False):
        if kind not in ('emotion','fatigue'):raise ValueError('Unknown monitor')
        if not self.tick(now):return
        self.monitor_labels[kind]=dict(label=label,source=source,received_at=now,qualified=qualified)
        # Optional comfort prompt; this policy does not change the model's label meaning.
        if kind=='fatigue' and label=='severe_candidate' and qualified:
            first='fatigue' not in self.alerts
            self.alerts['fatigue']='疲劳候选警示：请暂停操作并休息（非医疗结论）'
            self._stop(now,'fatigue_alert')
            if first:self._enter('fatigue_alert',now)
        elif kind=='emotion' and source=='user_report' and label=='poor':
            self.alerts['mood']='你确认当前情绪不佳，可以选择歌曲；不会自动播放。'
            self._enter('music_offer',now)
        elif (kind=='emotion' and source=='GAMEEMO_condition' and qualified
              and label=='horror' and now-self.mood_offer_at>=120):
            self.alerts['mood']='心情参考：模型估计负向情绪，是否选择舒缓歌曲？非本人心情实测，不自动播放。'
            self.mood_offer_at=now
            # A monitoring hint must not take over a direction or speed screen.
            if self.page not in ('drive','speed','fatigue_alert'):self._enter('music_offer',now)
        elif kind=='emotion' and source=='GAMEEMO_condition' and (not qualified or label!='horror'):
            self.alerts.pop('mood',None)
            if self.page=='music_offer':self._enter('home',now)

    def acknowledge_alert(self, kind, now):
        if kind not in ('mood','fatigue'):raise ValueError('Unknown alert')
        if not self.tick(now) or kind not in self.alerts:return False
        if kind=='fatigue' and not self.fatigue_ack_ready(now):
            self._event('警示仍锁定：需新鲜、质量合格的正常疲劳结果',now)
            return False
        self.alerts.pop(kind);self._stop(now,'alert_acknowledged_requires_rearm')
        if self.page=='fatigue_alert':self._enter('home',now)
        self._event('警示已确认，方向仍停止，请重新启用',now)
        return True

    def snapshot(self, now):
        self.tick(now)
        return dict(page=self.page,page_id=self.page_id,title=TITLES[self.page],labels=self.labels(),
            reading=now<self.read_until or self.presented_page!=self.page_id,
            direction=self.direction,direction_armed=self.direction_armed,speed_level=self.speed_level,
            selected_frequency=self.selected_frequency,force_stopped=self.force_stopped,
            fatigue_ack_ready=self.fatigue_ack_ready(now),
            fatigue_ack_reason='恢复正常后可确认；确认后必须重新启用方向' if self.fatigue_ack_ready(now) else '等待新鲜且质量合格的正常疲劳结果，方向保持锁定',
            direction_idle_remaining_s=max(0,self.direction_idle_deadline-now) if self.direction_idle_deadline is not None else None,
            direction_idle_enabled=self.direction_idle_enabled,
            speed_unit='virtual_level_not_kmh',video_index=self.video_index,rating=self.rating,
            song_index=self.song_index,phrase=self.phrase,alerts=dict(self.alerts),
            monitor_labels=dict(self.monitor_labels),mi_first_confirmed=self.mi_first is not None,
            mi_neutral_rearmed=self.mi_rearmed,mi_pair_timeout_s=self.mi_pair_seconds,
            last_action=self.last_action,last_selection=dict(self.last_selection) if self.last_selection else None,
            exited=self.exited,events=list(self.events),
            mode='manual_simulation_only',audio_output=False,physical_output_enabled=False,
            live_eeg_connected=False,live_gaze_connected=False,stimulus_enabled=False,
            hardware_speed_supported=False)
