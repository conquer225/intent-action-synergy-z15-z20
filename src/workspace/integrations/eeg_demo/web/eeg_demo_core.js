(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.EegDemoCore=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const CAP=['F3','F4','C3','C4','T7','T8','O1','O2'];
 const finite=x=>typeof x==='number'&&Number.isFinite(x);
 const clone=x=>JSON.parse(JSON.stringify(x));
 const sameCap=x=>Array.isArray(x)&&x.join(',')===CAP.join(',');
 function wave(x){return Array.isArray(x)&&x.length<=1500&&x.every(r=>Array.isArray(r)&&r.length===8&&r.every(finite));}
 function empty(reason='等待真实脑电'){return {ok:false,reason,samples:[],raw:[],fatigue:null,emotion:null,processing:null,quality:[],sample_index:null,rate:125,seq:null};}
 function features(x,count){return x&&Array.isArray(x.values)&&x.values.length===count&&x.values.every(finite)?clone(x):null;}
 function processing(x){
  if(!x||x.version!==1)return null;
  const out={sequence:x.sequence,filter:x.filter||{},emotion:null,fatigue:null};
  for(const [name,size] of [['emotion',105],['fatigue',20]]){
   const v=x[name];if(!v||!finite(v.collected_samples)||!finite(v.required_samples)||v.required_samples<=0)continue;
   out[name]={collected_samples:Math.max(0,Math.min(v.required_samples,v.collected_samples)),required_samples:v.required_samples,
    window:Array.isArray(v.window)?v.window.slice(0,2):null,feature_window:Array.isArray(v.feature_window)?v.feature_window.slice(0,2):null,features:features(v.features,size)};
  }return out;
 }
 function normalize(packet){
  if(!packet||packet.format!=='guardianloop-eeg-live-v1'||packet.origin!=='live'||packet.stale!==false||packet.control_enabled!==false)return empty(packet?.reason||'脑电数据已失效');
  const f=packet.status?.fatigue||{},t=packet.telemetry||{};
  if(f.offline||!['bci','cyton_usb'].includes(f.source)||!sameCap(f.channel_map)||t.real!==true||t.offline||!sameCap(t.channels)||!sameCap(t.channel_map||t.channels)
   ||!wave(t.samples)||!wave(t.raw_samples)||!t.samples.length||t.samples.length!==t.raw_samples.length
   ||!finite(t.sample_rate_hz)||t.sample_rate_hz<=0||t.sample_rate_hz>250||!Number.isSafeInteger(t.sample_index)||t.sample_index<0)return empty('等待新鲜的固定八通道脑电');
  const names={normal:'正常',mild:'轻度疲劳',severe:'严重疲劳'},emNames={funny:'正向情绪',calm:'中性情绪',boring:'中性情绪',horror:'负向情绪'};
  const level=typeof f.level==='number'?['normal','mild','severe'][f.level]:f.level;
  const e=f.emotion||{};
  const quality=(f.sqi?.channels||[]).slice(0,8).map(v=>({usable:v.usable===true,quality:finite(v.quality)?v.quality:null,reasons:Array.isArray(v.reasons)?v.reasons.map(String).slice(0,8):[]}));
  return {ok:true,reason:f.valid===true?'':String(f.reason||f.state||'收集窗口中'),seq:Number.isSafeInteger(f.seq)?f.seq:null,
   samples:t.samples,raw:t.raw_samples,sample_index:t.sample_index,rate:t.sample_rate_hz,quality,
   fatigue:f.valid===true&&names[level]?{level,label:names[level],score:finite(f.score)?f.score:null}:null,
   emotion:e.valid===true&&emNames[e.label]?{label:emNames[e.label],raw:e.label,votes:Array.isArray(e.votes)?e.votes.slice(0,4):null}:null,
   processing:processing(f.processing),calibration:[Number(f.calibration_current)||0,Number(f.calibration_total)||15],
   updated_at:finite(f.updated_at)?f.updated_at:null,data_age:finite(packet.data_age_seconds)?packet.data_age_seconds:null,
   runtime:t.runtime||{},packets:Number(t.packets_seen)||0,gaps:Number(t.dropped_packets)||0};
 }
 function validFrame(f){
  if(!f||typeof f!=='object'||typeof f.ok!=='boolean'||typeof f.reason!=='string'||f.reason.length>500)return false;
  if(!wave(f.samples)||!wave(f.raw)||f.samples.length!==f.raw.length)return false;
  if(!f.ok)return f.samples.length===0&&f.fatigue===null&&f.emotion===null;
  if(!f.samples.length||!finite(f.rate)||f.rate<=0||f.rate>250||!Number.isSafeInteger(f.sample_index)||f.sample_index<0)return false;
  if(f.fatigue!==null&&(!f.fatigue||!['normal','mild','severe'].includes(f.fatigue.level)||typeof f.fatigue.label!=='string'||(f.fatigue.score!==null&&(!finite(f.fatigue.score)||f.fatigue.score<0||f.fatigue.score>1))))return false;
  if(f.emotion!==null&&(!f.emotion||!['funny','calm','boring','horror'].includes(f.emotion.raw)||typeof f.emotion.label!=='string'))return false;
  if(!Array.isArray(f.quality)||f.quality.length>8)return false;
  if(f.processing){for(const [name,size] of [['emotion',105],['fatigue',20]]){const b=f.processing[name];if(b&&(!finite(b.collected_samples)||!finite(b.required_samples)||b.required_samples<=0||b.collected_samples<0||b.collected_samples>b.required_samples||(b.features&&!features(b.features,size))))return false;}}
  return true;
 }
 class Recording{
  constructor(){this.active=false;this.frames=[];this.bytes=0;this.reason='';this.started=0;this.created='';}
  start(now){this.active=true;this.frames=[];this.bytes=0;this.reason='';this.started=now;this.created=new Date().toISOString();}
  append(frame,now){
   if(!this.active)return false;const t=Math.max(0,Math.round(now-this.started));
   if(t>600000||this.frames.length>=620){this.stop('已到 10 分钟，请导出记录');return false;}
   if(this.frames.length&&t<this.frames[this.frames.length-1].t)return false;
   const entry=clone({t,frame});const n=JSON.stringify(entry).length*2;
   if(this.bytes+n>64*1024*1024){this.stop('记录达到内存上限，请导出');return false;}
   this.frames.push(entry);this.bytes+=n;return true;
  }
  stop(reason='记录已结束，可导出'){this.active=false;this.reason=reason;}
  serialize(){return JSON.stringify({format:'guardianloop-eeg-recording-v1',source:'recorded_live',channels:CAP,
   acquisition_rate_hz:250,created_at:this.created,duration_ms:this.frames.at(-1)?.t||0,frames:this.frames});}
 }
 function importRecording(text){
  if(typeof text!=='string'||text.length>64*1024*1024)throw Error('记录文件超过 64 MB');
  const d=JSON.parse(text);
  if(d?.format!=='guardianloop-eeg-recording-v1'||d.source!=='recorded_live'||!sameCap(d.channels)||d.acquisition_rate_hz!==250
   ||!Array.isArray(d.frames)||!d.frames.length||d.frames.length>620||!finite(d.duration_ms)||d.duration_ms<0||d.duration_ms>600000)throw Error('记录格式或来源不符');
  let previous=-1;
  for(const e of d.frames){if(!Number.isSafeInteger(e.t)||e.t<previous||e.t<0||e.t>600000||!validFrame(e.frame))throw Error('记录时间或数据无效');previous=e.t;}
  if(d.duration_ms!==previous)throw Error('记录时长不一致');return d;
 }
 function importPublicRecording(text){
  if(typeof text!=='string'||text.length>16*1024*1024)throw Error('脑电记录大小无效');
  const d=JSON.parse(text);
  if(d?.format!=='guardianloop-eeg-public-v1'||d.origin!=='replay'||d.source!=='LEMON-sub010002'||!sameCap(d.channels)||d.metadata?.license!=='CC-BY-4.0'||typeof d.metadata?.source_url!=='string'||!d.metadata.source_url.startsWith('https://ftp.gwdg.de/')||!Array.isArray(d.frames)||!d.frames.length||d.frames.length>620||!finite(d.duration_ms)||d.duration_ms<0||d.duration_ms>600000)throw Error('公开脑电记录来源无效');
  let previous=-1;for(const e of d.frames){if(!Number.isSafeInteger(e.t)||e.t<previous||e.t<0||!validFrame(e.frame))throw Error('脑电记录数据无效');previous=e.t;}
  if(previous!==d.duration_ms)throw Error('脑电记录时长不一致');return d;
 }
 function frameAt(recording,t){
  if(!recording?.frames?.length)return {t:0,frame:empty('暂无真实记录')};
  let low=0,high=recording.frames.length-1,index=-1;
  while(low<=high){const middle=(low+high)>>1;if(recording.frames[middle].t<=t){index=middle;low=middle+1;}else high=middle-1;}
  if(index<0)return {t:0,frame:empty('等待记录开始')};
  const e=recording.frames[index];return t-e.t>3000?{t,frame:empty('记录中的数据间断')}:e;
 }
 class Session{
  constructor(){this.mode='live';this.frame=empty();this.received=-Infinity;this.recording=null;this.position=0;this.playing=false;}
  live(frame,now){if(this.mode==='live'){this.frame=frame;this.received=now;}}
  view(now){if(this.mode==='replay')return frameAt(this.recording,this.position).frame;return now-this.received<=3000?this.frame:empty('连接中断，旧结果已撤销');}
  replay(recording){this.mode='replay';this.recording=recording;this.position=0;this.playing=false;this.frame=empty();}
  toLive(){this.mode='live';this.frame=empty();this.received=-Infinity;this.playing=false;this.position=0;}
 }
 return {CAP,normalize,empty,Recording,importRecording,importPublicRecording,frameAt,Session,validFrame};
});
