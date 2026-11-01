"""Pillow HDMI pages shared by preview and the board framebuffer."""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont

class Renderer:
    def __init__(self,font=None):
        candidates=[font,'/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc','/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc','C:/Windows/Fonts/msyh.ttc']
        path=next((str(p) for p in candidates if p and Path(p).is_file()),None)
        if not path: raise RuntimeError('Chinese font missing; supply --font')
        self.fonts={n:ImageFont.truetype(path,n) for n in (20,24,32,38)}
        self.last_key=None;self.last_image=None
    def render(self,state,video_image=None):
        cached_page=state.get('page','operate') in ('operate','technical')
        key=None
        if cached_page:
            stable={k:v for k,v in state.items() if k not in ('hover','progress','raw','timeline','pl_signal','brain_display','mi_trial','epoch')}
            if stable.get('media'):stable['media']={k:v for k,v in stable['media'].items() if k!='frame'}
            key=json.dumps(stable,sort_keys=True,ensure_ascii=False)
        if key is not None and key==self.last_key:
            im=self.last_image.copy();self._dynamic(im,state,video_image);return im
        im=Image.new('RGB',(1280,720),(247,246,243));d=ImageDraw.Draw(im)
        def text(x,y,value,size=24,color='#242421'):
            d.text((x,y),str(value),font=self.fonts[size],fill=color)
        text(42,28,'我们意念合一',32)
        origin={'simulation':'模拟演示 · 无实物输出','replay':'记录回放 · 无实物输出','live':'实时设备'}.get(state.get('origin'),'等待输入')
        text(420,34,origin,24)
        d.line((42,84,1238,84),fill='#b6b5b1')
        mode={'eye':'眼控','emg':'肌电','eeg':'脑电'}.get(state.get('interaction_mode'),{'eye':'眼控','brain':'脑电','contact':'肌电','mpu':'MPU辅助'}.get(state.get('mode'),'未选择'))
        device={'hand':'灵巧手','pendulum':'倒立摆'}.get(state.get('device'),'未选择')
        text(42,107,'控制方式：'+mode+'    设备：'+device)
        text(930,107,'已启用' if state.get('enabled') else '已停止',color='#9d261e' if state.get('enabled') else '#242421')
        page=state.get('page','operate');labels=state.get('labels',['灵巧手','倒立摆','查看过程'])
        if page=='operate':
            titles={'home':'选择要控制的设备','devices':'选择要控制的设备','actions':'灵巧手控制' if state.get('device')=='hand' else '倒立摆控制',
                    'turns':'倒立摆短动作','pend_start':'倒立摆启停','more':'表达与媒体','speech':'想说的话',
                    'media':'多媒体','video':'观看视频','video_nav':'选择视频','video_rate':'评价当前视频','music':'音乐播放','auxiliary':'辅助功能'}
            menu=state.get('menu_page','home');text(42,158,titles.get(menu,'选择功能'),32)
            eye=state.get('eye_status') or {};tracking=eye.get('tracking') or []
            if tracking:text(42,202,tracking[0][:70],20)
            for n,label in enumerate(labels):
                x=42+n*410
                if menu=='video' and n==1:continue
                d.rectangle((x,238,x+380,490),outline='#b6b5b1',width=2)
                text(x+28,330,label,38)
            media=state.get('media') or {}
            if menu in ('more','speech','media','music','video','video_nav','video_rate'):
                text(42,535,str(media.get('video_name') or '等待视频')[:18] if menu.startswith('video') else media.get('song') if menu=='music' else media.get('detail') or '原素材与评分保留',20)
                text(42,577,'评价：'+str(media.get('rating') or '未评价') if menu.startswith('video') else '播放状态：'+{'idle':'停止','playing':'播放中','complete':'结束','error':'失败'}.get(media.get('audio_status'),'停止'),20)
            else:text(42,527,'目标角度：'+str(state.get('angles') or '等待执行端回传'))
            raw=state.get('pendulum_raw')
            if menu not in ('more','speech','media','music','video','video_nav','video_rate'):
                text(42,568,'倒立摆 ADC / 编码器 / PWM：'+(str(raw['adc'])+' / '+str(raw['location'])+' / '+str(raw['pwm']) if raw else '等待回传'))
        elif page in ('process','emg','mpu'):
            text(42,162,'肌电与电极信号 / ADC计数' if page=='emg' else 'MPU倒立摆与信号过程' if page=='mpu' else 'S3 原始电极信号 / ADC计数',32)
            values=state.get('raw',[])[-500:]
            d.rectangle((42,219,780,431),outline='#b6b5b1',width=1)
            if len(values)>1:
                points=[(45+i*732/(len(values)-1),426-max(0,min(4095,v))*200/4095) for i,v in enumerate(values)]
                d.line(points,fill='#242421',width=2)
            else:text(64,290,'等待连续原始采样')
            text(820,230,'去均值RMS：'+str(state.get('rms') if state.get('rms') is not None else '等待完整窗口'))
            text(820,276,'按压：'+('按下' if state.get('pressed') is True else '松开' if state.get('pressed') is False else '未知'))
            text(820,322,'流状态：'+{'live':'实时','stale':'数据过期','waiting':'等待数据','disconnected':'已断开'}.get(state.get('signal_state'),'等待数据'))
            pl=state.get('pl_signal')
            text(820,368,'PL RMS：'+(str(round(pl['pl_rms'],2)) if pl else '等待完整窗口'))
            if page=='emg':text(820,412,'当前控制：原电极按压开合',20)
            monitor=state.get('monitor') or {};fatigue=monitor.get('fatigue') or {};emotion=fatigue.get('emotion') or {}
            trend=fatigue.get('level','等待合格信号') if fatigue.get('valid') is True and fatigue.get('offline') is not True else '等待合格信号'
            mood=emotion.get('label','等待合格信号') if emotion.get('valid') is True and fatigue.get('offline') is not True else '等待合格信号'
            text(42,462,'模型趋势参考：疲劳 '+str(trend)+'；情绪 '+str(mood),20)
            text(42,503,'事件 / 指令 / 回传',24)
            for n,row in enumerate(state.get('timeline',[])[-3:]):text(42,544+n*31,row,20)
        elif page=='brain':
            text(42,160,'独立SSVEP选区；闪烁由PL逐帧产生')
            for n,label in enumerate(labels[:4]):text(35+n*320,194,label,24)
            if state.get('origin')=='simulation':
                for n,frequency in enumerate((8,10,12,14)):
                    x=n*320+40;d.rectangle((x,240,x+240,539),fill='#d4d3cf')
                    text(x+25,370,str(frequency)+' Hz预览')
            reasons={'display_timing_unconfirmed':'等待合格的实际显示帧统计','no_fresh_quality_passed_window':'等待新鲜、质量通过的完整脑电窗口',
                     'collecting_nonoverlapping_window':'第一窗口通过，等待独立的第二窗口','window_discontinuity':'样本不连续，重新收集',
                     'ambiguous_or_low_score':'候选分数不足或过于接近','selected':'选区已触发','invalid_window':'窗口不合格','waiting_for_complete_window':'等待完整窗口'}
            text(42,558,reasons.get(state.get('brain_reason'),'等待合格脑电与显示帧统计'))
            text(42,600,'候选分数：'+str(state.get('scores') or '等待完整窗口'))
        elif page in ('eeg','mi'):
            text(42,162,'脑电模式 · '+('运动想象识别展示' if page=='mi' else '情绪与疲劳参考'),32)
            brain=state.get('brain_display') or {}
            text(42,232,'情绪参考：'+{'boring':'中性／无聊类','calm':'平静类','horror':'紧张类','funny':'正向类'}.get(brain.get('emotion'),'等待合格信号'),32)
            text(42,296,'疲劳参考：'+{0:'正常（等级0）',1:'轻度（等级1）',2:'高（等级2）','low':'低','normal':'正常','moderate':'中等','high':'高','severe':'高','critical':'高'}.get(brain.get('fatigue'),'等待合格信号'),32)
            text(42,370,'运动想象：'+{'left':'左手候选','right':'右手候选'}.get(brain.get('mi_label'),'等待完整试次'),32)
            trial=state.get('mi_trial') or {};target=trial.get('target') or brain.get('mi_target')
            if page=='mi':
                text(42,431,'当前提示：'+{'left':'想象左手运动','right':'想象右手运动','rest':'放松休息'}.get(target,'未开始'),32)
                text(42,485,trial.get('error') or ('实验模型仅展示结果' if brain.get('mi_enabled') else '板端MI实验配置尚未开启'),20)
            text(42,553,'PS_KEY0短按切任务；在运动想象页长按启动左手／右手／休息提示',20)
            text(42,590,'模型参考不切页，不改变执行动作。',20)
        else:
            text(42,163,'PS / PS＋PL 同输入对照',32)
            rows=state.get('benchmark')
            if rows:
                for n,(name,value) in enumerate(list(rows.items())[:7]):text(42,239+n*38,str(name)+'：'+str(value))
            else:text(42,239,'尚无本板实测结果；载入对照报告后显示。')
            text(42,540,'现有脑电模型运行于ARM；信号核和显示链路分别记录。')
        d.line((42,652,1238,652),fill='#b6b5b1')
        text(42,672,state.get('message','操作 / 过程 / 技术切页；停止可随时执行'),20)
        text(995,672,'PL_KEY1停止 / ESC',20,color='#9d261e')
        if key is not None:self.last_key=key;self.last_image=im.copy()
        self._dynamic(im,state,video_image)
        return im
    def _dynamic(self,im,state,video_image):
        d=ImageDraw.Draw(im)
        if state.get('page','operate')=='operate' and type(state.get('hover')) is int and 0<=state['hover']<3:
            x=42+state['hover']*410
            d.rectangle((x+2,479,x+2+int(376*max(0,min(1,state.get('progress',0)))),488),fill='#242421')
        if state.get('menu_page')=='video' and video_image is not None:
            # Keep the current frame inside the original middle viewing column.
            w,h=video_image.size;scale=min(376/w,420/h)
            picture=video_image.resize((int(w*scale),int(h*scale)),Image.NEAREST)
            im.paste(picture,(640-picture.width//2,420-picture.height//2))
