"""Four fixed-size HDMI views; every plotted point comes from admitted data."""
import math
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from .presentation import Presenter
from .signal_core import CAP,PAGES
from .signal_charts import wave_scale,covariance_maps,spectrogram,pcm_wave_scale,spectrum_columns
from presentation_theme import BG,FG,DIM,GRID,ACCENT as CYAN,AMBER,SECONDARY as VIOLET,GREEN
TITLES={'fatigue':'疲劳分析','emotion':'情绪分析','music':'脑电与音乐联动','audio':'音乐音频分析'}
GENRES={'calm':'舒缓','steady':'平稳','bright':'明快'}
class SignalPresenter(Presenter):
 def __init__(self,font_path=None,enabled_pages=PAGES):
  super().__init__(font_path);self.shells={};self.history=[];self.last_key=None;self.history_source=None
  self.enabled_pages=tuple(enabled_pages)
  self.hero=ImageFont.truetype(self.title.path,46);self.latin[46]=ImageFont.truetype(self.latin[32].path,46)
 def label(self,d,xy,text,color=DIM,large=False):self.text(d,xy,str(text),self.title if large else self.body,color)
 def line_plot(self,d,values,box,lo,hi,color):
  a=np.asarray(values,dtype=float)
  if a.ndim!=1 or len(a)<2:return
  finite=np.isfinite(a);l,t,r,b=box
  xs=np.linspace(l,r,len(a));ys=b-(b-t)*np.clip((a-lo)/max(1e-9,hi-lo),0,1)
  boundaries=np.flatnonzero(np.diff(np.r_[False,finite,False].astype(np.int8)))
  for start,end in boundaries.reshape(-1,2):
   if end-start>1:d.line(list(zip(xs[start:end].tolist(),ys[start:end].tolist())),fill=color,width=2)
 def shell(self,page):
  if page not in self.enabled_pages:raise ValueError('signal page disabled')
  if page not in self.shells:
   im=Image.new('RGB',(1280,720),BG);d=ImageDraw.Draw(im)
   if page in ('fatigue','emotion'):
    self.label(d,(28,15),'我们意念合一  /  '+TITLES[page],FG,True)
    for i,name in enumerate(self.enabled_pages):
     x=28+i*305;self.label(d,(x,73),TITLES[name],FG if page==name else DIM)
     if page==name:d.line((x,105,x+265,105),fill=CYAN,width=3)
    d.line((982,130,982,646),fill=GRID)
    self.label(d,(28,118),'八通道脑电',FG)
    self.label(d,(668,118),'原始',DIM);d.line((642,135,660,135),fill=(174,162,143),width=2)
    self.label(d,(789,118),'滤波后',CYAN);d.line((763,135,781,135),fill=CYAN,width=2)
    for c in range(8):
     y=165+c*37;self.label(d,(28,y-13),CAP[c],DIM);d.line((83,y,950,y),fill=(230,222,205))
    self.label(d,(28,477),'时频能量' if page=='fatigue' else '五频段 · 对数协方差',FG)
    d.line((28,667,1250,667),fill=GRID)
    self.label(d,(28,681),'PL_KEY1 切页   ·   PL_KEY0 图像   ·   PS 按键退出',DIM)
   else:
    self.label(d,(30,17),'我们意念合一  /  '+TITLES[page],FG,True)
    for i,name in enumerate(self.enabled_pages):
     x=30+i*305;self.label(d,(x,76),TITLES[name],FG if page==name else DIM)
     if page==name:d.line((x,109,x+265,109),fill=CYAN,width=3)
    d.line((30,655,1250,655),fill=GRID)
    self.label(d,(30,675),'PL_KEY1 下一页   ·   PL_KEY0 图像处理   ·   PS 按键退出',DIM)
   if page=='music':
    self.label(d,(30,130),'状态分析、选曲与播放',DIM)
    for x in (30,445,860):d.line((x,185,x+370,185),fill=GRID)
    for x,t in ((30,'分析结果'),(445,'联动决策'),(860,'音乐播放')):self.label(d,(x,204),t,FG,True)
    self.label(d,(30,503),'脑电变化与选曲事件',DIM)
   elif page=='audio':
    self.label(d,(30,128),'频谱 · 64 段峰值 · dBFS',FG)
    for y,value in ((174,0),(230,-30),(286,-60),(342,-90)):
     d.line((82,y,1248,y),fill=GRID);self.label(d,(28,y-12),str(value),DIM)
    for x in (470.67,859.33,1248):d.line((x,174,x,342),fill=GRID)
    for ratio,text in ((0,'20'),(1/3,'200'),(2/3,'2k'),(1,'20k Hz')):
     self.label(d,(82+1166*ratio-(70 if ratio==1 else 0),352),text,DIM)
    self.label(d,(30,390),'频谱瀑布 · 同频轴',FG)
    for left,ch in ((82,'L'),(704,'R')):
     self.label(d,(left-50,542),ch,DIM)
     d.line((left,557,left+544,557),fill=GRID)
    for left,ch in ((30,'低频'),(445,'中频'),(860,'高频')):
     self.label(d,(left,587),ch,DIM)
     d.rectangle((left+65,596,left+280,606),fill=GRID)
   self.shells[page]=im
  return self.shells[page].copy()
 def render(self,page,frame,music,audio,now):
  im=self.shell(page);d=ImageDraw.Draw(im)
  origin={'live':'脑电分析','replay':'脑电记录','fixture':'合成测试'}.get(frame.get('origin'),'来源未知')
  self.label(d,(30,50),'LEMON · 八通道脑电记录' if frame.get('origin')=='replay' else frame.get('source_label','脑电分析')[:48],DIM)
  pos=max(0,int(frame.get('position_seconds',0)));self.label(d,(890,23),'%s  %02d:%02d'%(origin,pos//60,pos%60),AMBER if origin!='脑电分析' else CYAN)
  if not frame.get('ok') and page not in ('fatigue','emotion'):self.label(d,(30,618),str(frame.get('reason','等待数据'))[:48],AMBER)
  key=(frame.get('origin'),frame.get('source_id'),frame.get('seq'),pos)
  source=(frame.get('origin'),frame.get('source_id'))
  if source!=self.history_source:self.history=[];self.history_source=source
  if key!=self.last_key:
   score=(frame.get('fatigue') or {}).get('score',float('nan'))
   emotion={'funny':1.,'calm':.5,'boring':.5,'horror':0.}.get((frame.get('emotion') or {}).get('raw'),float('nan'))
   self.history.append((pos,score,emotion));self.history=self.history[-180:];self.last_key=key
  if page in ('fatigue','emotion'):self.brain(im,d,page,frame)
  elif page=='music':self.music(d,frame,music)
  else:self.audio(im,d,audio,music)
  return np.asarray(im)
 def heatmap(self,im,values,box,lo,hi,diverging=False):
  a=np.asarray(values,dtype=float);l,t,r,b=map(int,box)
  if a.ndim!=2 or not a.size or not np.isfinite(a).all():return
  z=np.clip((a-lo)/max(1e-9,hi-lo),0,1)
  # Warm ivory/gold, with aubergine for low spectral power or negative covariance.
  stops=np.array([(54,38,58),(114,69,83),(191,123,67),(231,186,94),(255,240,193)])
  if diverging:stops=np.array([(77,57,99),(155,128,163),(248,241,224),(210,170,96),(134,85,29)])
  ramp=np.linspace(0,1,len(stops));rgb=np.stack([np.interp(z,ramp,stops[:,c]) for c in range(3)],axis=-1).astype('uint8')
  im.paste(Image.fromarray(rgb).resize((r-l,b-t),getattr(Image,'Resampling',Image).NEAREST),(l,t))
 def brain(self,im,d,page,f):
  valid=f.get('ok');a=np.asarray(f.get('samples',[]));scale=wave_scale(a)
  if valid:
   for key,color in (('raw',(182,170,149)),('samples',CYAN)):
    values=np.asarray(f.get(key,[]))
    if values.ndim==2 and values.shape[1]==8:
     for c in range(8):self.line_plot(d,values[:,c],(83,148+c*37,950,182+c*37),-scale,scale,color)
  self.label(d,(844,445),'±%g μV'%scale,DIM)
  self.label(d,(83,445),'−4 s',DIM);self.label(d,(458,445),'−2 s',DIM)
  p=(f.get('processing') or {}).get(page) or {};features=(p.get('features') or {}).get('values') if valid else None
  required=p.get('required_samples',2000 if page=='fatigue' else 3000);collected=p.get('collected_samples',0)
  ratio=float(np.clip(collected/max(1,required),0,1)) if valid else 0
  result=f.get(page) if valid else None
  self.label(d,(1010,119),'疲劳状态' if page=='fatigue' else '情绪状态',DIM)
  title=({'normal':'正常','mild':'轻度疲劳','severe':'严重疲劳'}.get(result.get('level')) if page=='fatigue' else {'funny':'正向','calm':'中性','boring':'中性','horror':'负向'}.get(result.get('raw'))) if result else '分析中'
  if not valid:title='数据间断'
  elif not result and str(f.get('reason','')).lower()=='invalid':title='质量不足'
  self.text(d,(1007,158),title,self.hero,CYAN if page=='fatigue' else VIOLET)
  if result:
   if page=='fatigue':
    self.text(d,(1010,224),'%.3f'%result['score'],self.hero,FG)
    self.label(d,(1010,283),'模型分数',DIM)
   else:self.label(d,(1010,224),result['raw'],DIM)
  d.rectangle((1010,331,1245,338),fill=GRID)
  if ratio:d.rectangle((1010,331,1010+235*ratio,338),fill=CYAN)
  self.label(d,(1010,352),'%d s 窗口  %.1f s'%(8 if page=='fatigue' else 12,collected/250.),DIM)
  pos=float(f.get('position_seconds',0))
  if page=='fatigue':
   self.label(d,(1010,407),'频段特征 · 20 维',FG)
   v=np.asarray(features if features is not None else [])
   if v.shape==(20,) and np.isfinite(v).all():
    matrix=v.reshape(4,5);lo=float(v.min());hi=float(v.max())
    self.heatmap(im,matrix,(1045,474,1245,594),lo,hi)
    for i,c in enumerate(('T7','T8','O1','O2')):self.label(d,(998,475+i*30),c,DIM)
    for i,b in enumerate(('δ','θ','α','β','γ')):self.label(d,(1052+i*40,442),b,DIM)
    for r in range(1,4):d.line((1045,474+r*30,1245,474+r*30),fill=BG,width=2)
    for c in range(1,5):d.line((1045+c*40,474,1045+c*40,594),fill=BG,width=2)
    self.label(d,(1010,608),'%.1f … %.1f nats'%(lo,hi),DIM)
   else:self.label(d,(1010,483),'等待有效特征',DIM)
   spectrum=spectrogram(a,50) if valid else None
   if spectrum is not None:
    freqs=spectrum['frequency_hz'];keep=(freqs>=1)&(freqs<=25)
    self.heatmap(im,spectrum['power_db'][keep][::-1],(83,519,950,643),-8,10)
    for value in (25,13,1):self.label(d,(28,510+(25-value)/24*113),str(value),DIM)
    # Actual 50 Hz display branch: no energy above 25 Hz is represented.
    self.label(d,(195,477),'1–25 Hz · 八通道均值',DIM)
    gradient=np.linspace(-8,10,100).reshape(1,-1)
    self.heatmap(im,gradient,(677,485,802,497),-8,10)
    self.label(d,(816,477),'−8 … 10 dB',DIM)
   else:self.label(d,(350,562),'等待信号',DIM)
  else:
   maps=covariance_maps(features)
   if maps is not None:
    bound=max(.1,float(np.max(np.abs(maps))));names=('δ 1–4','θ 4–8','α 8–13','β 13–30','γ 30–43')
    for k,matrix in enumerate(maps):
     x=83+k*174;self.label(d,(x,504),names[k],DIM)
     self.heatmap(im,matrix,(x,540,x+142,646),-bound,bound,True)
     for c in range(1,6):d.line((x+c*142/6,540,x+c*142/6,646),fill=BG)
     for r in range(1,6):d.line((x,540+r*106/6,x+142,540+r*106/6),fill=BG)
    self.label(d,(482,477),'F3  F4  T7  T8  O1  O2',DIM)
    self.label(d,(1010,409),'协方差尺度',DIM)
    self.heatmap(im,np.linspace(-bound,bound,120).reshape(1,-1),(1010,453,1245,470),-bound,bound,True)
    self.label(d,(1010,479),'−%.1f          +%.1f'%(bound,bound),DIM)
   else:self.label(d,(330,562),'等待有效特征',DIM)
   self.label(d,(1010,536),'近期情绪',DIM)
   self.line_plot(d,[x[2] for x in self.history],(1010,577,1245,628),0,1,VIOLET)
  # A short aligned state ribbon contains gaps rather than carrying stale labels.
  if page=='fatigue':
   for k,entry in enumerate(self.history[-180:]):
    value=entry[1]
    if math.isfinite(value):
     color=GREEN if value<.35 else AMBER if value<.70 else (157,68,55)
     x=810+440*k/max(1,len(self.history[-180:])-1);d.line((x,687,x,703),fill=color,width=3)
 def music(self,d,f,m):
  fat=f.get('fatigue');em=f.get('emotion')
  self.label(d,(30,270),'疲劳：'+({'normal':'正常','mild':'轻度','severe':'严重'}.get((fat or {}).get('level'),'未知')),AMBER)
  self.label(d,(30,314),'情绪：'+str((em or {}).get('raw','未知')),VIOLET)
  self.label(d,(30,370),'根据有效分析结果选曲',DIM)
  reason=str(m.get('reason','等待两次有效分析结果'))
  # Fixed width split avoids clipping Chinese decisions at720p.
  self.label(d,(445,270),reason[:16],CYAN)
  if len(reason)>16:self.label(d,(445,310),reason[16:32],CYAN)
  self.label(d,(445,368),'确认 %s / 2'%min(2,m.get('confirmations',0)),DIM)
  self.label(d,(445,412),'曲目至少保持 20 秒',DIM)
  self.label(d,(860,270),str(m.get('title','尚未选曲'))[:18],FG)
  self.label(d,(860,314),'组别：'+GENRES.get(m.get('genre'),'等待'),DIM)
  player=m.get('player') or {};phase=player.get('phase','idle')
  self.label(d,(860,365),{'feeding':'播放器正在输出','starting':'已请求播放','stopped':'已停止','completed':'播放完成','error':'播放器错误'}.get(phase,'等待播放'),CYAN if phase=='feeding' else AMBER)
  self.label(d,(860,410),'播放进度 %.1f 秒'%(player.get('position_frames_estimate',0)/48000.),DIM)
  self.label(d,(860,452),'',DIM)
  for k,event in enumerate((m.get('events') or [])[-3:]):
   self.label(d,(32,548+32*k),'%6.1fs  %s  %s'%(event.get('source_position_seconds',event['time']),GENRES.get(event['action'],'停止'),event.get('reason','')[:36]),DIM)
 def audio(self,im,d,a,m):
  self.label(d,(450,128),str(m.get('title','等待选曲'))[:14],DIM)
  self.heatmap(im,np.linspace(-90,-15,80).reshape(1,-1),(898,404,1024,414),-90,-15)
  self.label(d,(1040,390),'−90 … −15 dBFS',DIM)
  if not a:
   self.label(d,(550,244),'等待音乐样本',DIM)
   self.label(d,(550,443),'等待频谱历史',DIM)
   self.label(d,(32,624),str(m.get('analysis_error') or '进入音乐联动页后启动播放')[:52],AMBER)
   return
  columns=spectrum_columns(a['frequencies'],a['spectrum_dbfs'])
  values=columns['peak_dbfs'];edges=82+1166*np.log10(columns['edges_hz']/20)/3
  for k,value in enumerate(values):
   if not np.isfinite(value):continue
   top=342-168*float(np.clip((value+90)/90,0,1))
   if top>=342:continue
   left,right=edges[k]+2,edges[k+1]-2
   d.rectangle((left,top,right,342),fill=(226,202,154))
   d.line((left,top,right,top),fill=CYAN,width=3)
  water=np.asarray(a.get('waterfall',[]))
  if water.ndim==2 and len(water):
   # Color the measured bins before upscaling, avoiding a full-canvas float map.
   frequencies=20*1000**(np.arange(389)/388)
   indices=np.clip(np.rint(frequencies/(48000/1024)).astype(int),1,512)
   self.heatmap(im,water[:,indices],(82,424,1248,486),-90,-15)
  waves=np.asarray(a['waveform']);limit=pcm_wave_scale(waves)
  if waves.ndim==2 and waves.shape[1]==2:
   for k,color in enumerate((CYAN,VIOLET)):
    left=82+k*622
    self.line_plot(d,waves[:,k],(left,535,left+544,579),-limit,limit,color)
  self.label(d,(960,500),'量程 ±%g FS'%limit,DIM)
  for k,value in enumerate(a['rms_dbfs']):
   self.label(d,(82+k*622,500),'电平 %.1f dBFS'%value,DIM)
  for k,value in enumerate(a['bands']):
   left=30+415*k;value=max(0,min(1,float(value)))
   if value:d.rectangle((left+65,596,left+65+215*value,606),fill=(CYAN,VIOLET,AMBER)[k])
   self.label(d,(left+295,587),'%d%%'%round(value*100),DIM)
  peak='静音' if a['peak_hz'] is None else '峰值 %.0f Hz'%a['peak_hz']
  backend='PL FFT1024' if a.get('backend','').startswith('PL ') else 'PS FFT参考'
  self.label(d,(30,624),peak,DIM)
  self.label(d,(350,624),'48 kHz · Hann → '+backend,DIM)
  self.label(d,(1040,624),'%.2f s'%a['position_seconds'],DIM)
