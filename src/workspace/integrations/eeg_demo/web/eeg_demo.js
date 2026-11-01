/* Presentation reads one local observation endpoint; recording stays in this browser. */
(function(){'use strict';
const C=window.EegDemoCore,$=id=>document.getElementById(id),session=new C.Session(),recorder=new C.Recording();
const key=decodeURIComponent(location.hash.slice(1));let generation=0,pending=null,timer=null,history=[],historyKey='',lastTime=performance.now(),lastRender='',waveRows=[],endIndex=null,incomingAt=0,rate=125,paintAt=0,replayDuration=0,recording=null;
const colors=['#835d22','#655e3b','#9b702f','#6b7045','#805b3b','#536746','#a47734','#796141'];
const words={FEATURE_WARMUP:'等待完整特征窗口',REQUIRED_CHANNEL_QUALITY:'所需通道质量不足',REQUIRED_CHANNEL_SQI_CALIBRATING:'所需通道仍在校准',TRANSPORT:'传输窗口不完整',calibrating:'正在采集个人基线',invalid:'当前窗口不可用',prediction:'当前窗口已完成',collecting_12s:'正在收集 12 秒窗口',sqi_calibrating:'信号质量校准中',packet_gap_12s:'12 秒窗口存在丢包',insufficient_signal:'所需通道质量不足'};
const positions=[[94,37],[156,37],[94,65],[156,65],[52,79],[198,79],[94,105],[156,105]];
const bandLabels=document.querySelector('.fatigue-feature .feature-meta span');bandLabels.className='bands';bandLabels.replaceChildren(...['δ','θ','α','β','γ'].map(word=>{const e=document.createElement('span');e.textContent=word;return e;}));
C.CAP.forEach((name,i)=>{const ns='http://www.w3.org/2000/svg',g=document.createElementNS(ns,'g'),circle=document.createElementNS(ns,'circle'),text=document.createElementNS(ns,'text');circle.setAttribute('cx',positions[i][0]);circle.setAttribute('cy',positions[i][1]);circle.setAttribute('r','7');circle.setAttribute('class','electrode');text.setAttribute('x',positions[i][0]+11);text.setAttribute('y',positions[i][1]+3);text.textContent=name;g.append(circle,text);$('electrodes').append(g);const q=document.createElement('span');q.textContent=name;$('qualityChannels').append(q);});
function notice(message){$('message').textContent=message;$('message').hidden=!message;}
function timecode(ms){const s=Math.floor(ms/1000);return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
function resetVisual(){history=[];historyKey='';waveRows=[];endIndex=null;lastRender='';$('history').replaceChildren();}
function ingest(f,now,reset=false){
 if(reset){waveRows=[];endIndex=null;}
 if(!f.ok){waveRows=[];endIndex=null;return;}
 if(endIndex===f.sample_index)return;
 if(endIndex!==null&&f.sample_index<endIndex)waveRows=[];
 const start=f.sample_index-f.samples.length;
 const oldEnd=endIndex;
 for(let i=0;i<f.samples.length;i++){const index=start+i;if(oldEnd===null||index>=oldEnd)waveRows.push({index,raw:f.raw[i],filtered:f.samples[i]});}
 waveRows=waveRows.slice(-1500);rate=f.rate;endIndex=f.sample_index;incomingAt=now;
}
function canvas(id){const el=$(id),box=el.getBoundingClientRect(),dpi=Math.min(2,devicePixelRatio||1),w=Math.max(1,box.width),h=Math.max(1,box.height);if(el.width!==Math.round(w*dpi)||el.height!==Math.round(h*dpi)){el.width=Math.round(w*dpi);el.height=Math.round(h*dpi);}const ctx=el.getContext('2d');ctx.setTransform(dpi,0,0,dpi,0,0);ctx.clearRect(0,0,w,h);return {ctx,w,h};}
function drawWave(f,now){
 const {ctx,w,h}=canvas('waveform'),pad=43,right=12,plot=w-pad-right,row=h/8,span=4*rate,amplitude=Math.max(5,5*Math.ceil(waveRows.length?waveRows.slice(-Math.round(4*rate)).reduce((m,p)=>Math.max(m,...p.filtered.map(Math.abs)),0)/5:1));
 $('waveScale').textContent='±'+amplitude+' μV';ctx.font='14px system-ui';ctx.lineWidth=.7;
 for(let i=0;i<8;i++){const y=(i+.5)*row;ctx.fillStyle=colors[i];ctx.fillText(C.CAP[i],3,y+3);ctx.strokeStyle='#e5dac5';ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(w-right,y);ctx.stroke();}
 for(let i=0;i<=4;i++){const x=pad+plot*i/4;ctx.strokeStyle='#e5dac5';ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}
 if(!f.ok||endIndex===null)return;
 // Reveal only samples actually delivered. Never extrapolate a waveform.
 const end=endIndex-Math.max(0,1-Math.min(1,(now-incomingAt)/1000))*Math.min(rate,f.samples.length),start=end-span;
 for(let channel=0;channel<8;channel++){
  for(const lane of ['raw','filtered']){
   ctx.save();ctx.beginPath();ctx.rect(pad,channel*row,plot,row);ctx.clip();ctx.beginPath();let previous=null;
   ctx.strokeStyle=lane==='raw'?'#ab9f89':colors[channel];ctx.globalAlpha=lane==='raw'?.55:1;ctx.lineWidth=lane==='raw'?1:1.6;
   for(const p of waveRows){if(p.index<start||p.index>end)continue;const x=pad+(p.index-start)/span*plot,y=(channel+.5)*row-Math.max(-1,Math.min(1,p[lane][channel]/amplitude))*row*.42;
    if(previous===null||p.index-previous>1)ctx.moveTo(x,y);else ctx.lineTo(x,y);previous=p.index;
   }ctx.stroke();ctx.restore();
  }
 }
}
function heatColor(value,lo,hi){
 const stops=[[54,38,58],[114,69,83],[191,123,67],[231,186,94],[255,240,193]],q=Math.max(0,Math.min(1,(value-lo)/Math.max(1e-9,hi-lo)))*4,i=Math.min(3,Math.floor(q)),u=q-i;
 return 'rgb('+stops[i].map((x,c)=>Math.round(x+(stops[i+1][c]-x)*u)).join(',')+')';
}
function drawFeatures(f){
 const de=f.ok?f.processing?.fatigue?.features:null,co=f.ok?f.processing?.emotion?.features:null;
 {const {ctx,w,h}=canvas('deFeatures'),v=de?.values,lo=v?Math.min(...v):0,hi=v?Math.max(...v):1,pad=32,cw=(w-pad)/5,ch=(h-23)/4;
  ctx.font='12px system-ui';ctx.textAlign='left';
  for(let r=0;r<4;r++){ctx.fillStyle='#74644d';ctx.fillText(['T7','T8','O1','O2'][r],0,23+(r+.5)*ch+4);for(let c=0;c<5;c++){ctx.fillStyle=v?heatColor(v[r*5+c],lo,hi):'#f2e8d3';ctx.fillRect(pad+c*cw+1,23+r*ch+1,cw-2,ch-2);}}
  for(let c=0;c<5;c++){ctx.fillStyle='#74644d';ctx.fillText(['δ','θ','α','β','γ'][c],pad+(c+.45)*cw,15);}
  $('deRange').textContent=v?lo.toFixed(1)+' … '+hi.toFixed(1)+' nats':'等待特征';}
 {const {ctx,w,h}=canvas('covFeatures'),v=co?.values,lo=v?Math.min(...v):0,hi=v?Math.max(...v):1,pad=24,ch=h/5,cw=(w-pad)/21;
  ctx.font='12px system-ui';for(let r=0;r<5;r++){ctx.fillStyle='#74644d';ctx.fillText(['δ','θ','α','β','γ'][r],0,(r+.5)*ch+4);for(let c=0;c<21;c++){ctx.fillStyle=v?heatColor(v[r*21+c],lo,hi):'#f2e8d3';ctx.fillRect(pad+c*cw+1,r*ch+1,Math.max(1,cw-2),ch-2);}}
  $('covRange').textContent=v?lo.toFixed(1)+' … '+hi.toFixed(1):'等待特征';}

}
function updateHistory(f){
 const k=session.mode+':'+(f.ok?String(f.seq)+':'+(f.fatigue?.level||f.reason)+':'+(f.emotion?.raw||''):f.reason);if(k===historyKey)return;historyKey=k;
 if(!f.ok&&!history.length)return;
 const stamp=session.mode==='replay'?timecode(session.position):new Date().toLocaleTimeString('zh-CN',{hour12:false});
 history.unshift({stamp,fatigue:f.ok?(f.fatigue?.label||words[f.reason]||'收集窗口'):'数据间断',emotion:f.ok?(f.emotion?.label||'情绪等待'):'旧结果撤销'});history=history.slice(0,8);
 $('history').replaceChildren();for(const v of history){const el=document.createElement('div');el.className='history-entry';for(const [tag,value] of [['time',v.stamp],['span',v.fatigue],['small',v.emotion]]){const child=document.createElement(tag);child.textContent=value;el.append(child);}$('history').append(el);}
}
function render(f){
 $('liveDot').className='dot '+(session.mode==='replay'?'replay':f.ok?'live':'');
 $('source').textContent=session.mode==='replay'?'LEMON 脑电记录':f.ok?'脑电分析':'脑电记录分析';
 $('waveEmpty').hidden=f.ok;$('waveEmpty').querySelector('strong').textContent=session.mode==='replay'?'记录中的数据间断':'正在载入脑电记录';
 $('waveEmpty').querySelector('span:last-child').textContent=f.reason||'八通道信号正在载入';
 $('displayRate').textContent=f.ok?f.rate:'--';$('dataAge').textContent=f.ok?f.seq:'--';
 $('sampleInfo').textContent=f.ok?'样本 '+f.sample_index.toLocaleString()+' · 最近 4 秒 · μV':'固定帽位 · F3 / F4 / C3 / C4 / T7 / T8 / O1 / O2';
 const usable=f.quality?.filter(q=>q.usable).length;$('usable').textContent=f.ok&&f.quality.length?usable:'--';
 for(let i=0;i<8;i++){const q=f.ok?f.quality[i]:null,cls=q?(q.usable?'good':'bad'):'';$('qualityChannels').children[i].className=cls;$('electrodes').children[i].querySelector('circle').setAttribute('class','electrode '+(q?(q.usable?'usable':'bad'):''));$('qualityChannels').children[i].title=q?.reasons?.join(' / ')||'等待评估';}
 $('calibration').textContent=f.ok?f.calibration.join(' / '):'-- / 15';$('qualityNote').textContent=f.ok?(f.calibration[0]>=f.calibration[1]?'基线已建立':'正在建立分析基线'):'分析基线';
 $('filterStatus').textContent=f.ok?'连续滤波 · 1–45 Hz':'等待输入';
 for(const name of ['fatigue','emotion']){const branch=f.ok?f.processing?.[name]:null,full=name==='fatigue'?2000:3000;$(`${name}Progress`).value=branch?.collected_samples||0;$(`${name}Window`).textContent=branch?`${(branch.collected_samples/250).toFixed(1)} / ${full/250} s`:'等待数据';}
 $('fatigueState').textContent=f.fatigue?.label||(f.ok?(f.reason==='calibrating'?'基线校准中':'等待结果'):'等待数据');$('fatigueScore').replaceChildren(document.createTextNode(f.fatigue?.score!==null&&f.fatigue?f.fatigue.score.toFixed(2):'--'));const suffix=document.createElement('small');suffix.textContent=' / 1';$('fatigueScore').append(suffix);
 $('scoreFill').style.transform='scaleX('+(f.fatigue?.score!==null&&f.fatigue?Math.max(0,Math.min(1,f.fatigue.score)):0)+')';
 $('fatigueDetail').textContent=f.fatigue?'模型分数':f.ok?(words[f.reason]||'等待完整窗口与质量检查'):'等待完整窗口与质量检查';
 $('emotionState').textContent=f.emotion?.label||(f.ok?'窗口收集中':'等待数据');$('emotionDetail').textContent=f.emotion?'原始类别 '+f.emotion.raw+'':f.ok?'等待 12 秒连续窗口与六通道质量检查':'等待完整窗口与质量检查';
 const mood=f.emotion?(f.emotion.raw==='funny'?'positive':f.emotion.raw==='horror'?'negative':'neutral'):null;
 document.querySelectorAll('[data-emotion]').forEach(el=>el.className=el.dataset.emotion===mood?'active':'');
 $('emotionGlyph').querySelector('path').setAttribute('d','M21 25h1m20 0h1'+(mood==='positive'?'M21 38q11 14 22 0':mood==='negative'?'M21 45q11-14 22 0':'M21 42h22'));
 $('resultFresh').textContent=f.ok?'窗口 '+(f.seq??'--'):'旧结果已撤销';
 const p=f.processing;$('processingState').textContent=p?'特征窗口 #'+p.sequence:'特征将在模型实际计算后呈现';
 $('windowBounds').textContent=p?'特征样本范围：疲劳 '+(p.fatigue?.feature_window?.join('–')||'--')+'；情绪 '+(p.emotion?.feature_window?.join('–')||'--'):'窗口范围：等待数据';
 drawFeatures(f);updateHistory(f);
}
function transport(){
 const replay=session.mode==='replay';$('liveMode').classList.toggle('selected',!replay);$('replayMode').classList.toggle('selected',replay);$('liveMode').setAttribute('aria-pressed',String(!replay));$('replayMode').setAttribute('aria-pressed',String(replay));$('play').hidden=!replay;$('record').disabled=replay;$('record').textContent=recorder.active?'结束记录':'开始记录';$('record').classList.toggle('recording',recorder.active);$('export').disabled=!recorder.frames.length;$('scrubberWrap').hidden=!replay;$('scrubber').max=replayDuration||1;$('scrubber').value=session.position;$('replayTime').textContent=timecode(session.position)+' / '+timecode(replayDuration);$('play').textContent=session.playing?'暂停':'播放';$('recordStatus').textContent=recorder.active?'正在记录 · '+recorder.frames.length+' 次观测':recorder.reason||'本机记录 · 最长 10 分钟';
}
function cancel(){generation++;clearTimeout(timer);if(pending)pending.abort();pending=null;}
async function poll(){
 if(session.mode!=='live'||document.hidden)return;const token=generation;const abort=new AbortController();pending=abort;const deadline=setTimeout(()=>abort.abort(),1800);
 try{const r=await fetch('/api/eeg-demo',{headers:{'X-Media-Key':key},cache:'no-store',signal:abort.signal});if(!r.ok)throw Error(r.status===403?'访问码无效，请从原控制台链接进入':'脑电接口暂不可用');const body=await r.json();if(token!==generation||document.hidden)return;const frame=C.normalize(body),now=performance.now();session.live(frame,now);ingest(frame,now);if(recorder.active)recorder.append(frame,now);notice(body.reason&&body.stale?body.reason:'');}
 catch(error){if(token!==generation||document.hidden)return;const f=C.empty(error.name==='AbortError'?'脑电接口响应超时':error.message);session.live(f,performance.now());ingest(f,performance.now());if(recorder.active)recorder.append(f,performance.now());notice(f.reason);}
 finally{clearTimeout(deadline);if(pending===abort)pending=null;if(token===generation&&session.mode==='live'&&!document.hidden)timer=setTimeout(poll,1000);transport();}
}
$('record').onclick=()=>{if(recorder.active)recorder.stop();else{if(!session.view(performance.now()).ok){notice('连接真实脑电后才能开始记录');return;}recorder.start(performance.now());recorder.append(session.view(performance.now()),performance.now());}transport();};
$('export').onclick=()=>{const blob=new Blob([recorder.serialize()],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='intent-one-eeg-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);};
$('import').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>64*1024*1024)throw Error('记录文件超过 64 MB');const contents=await file.text();recording=JSON.parse(contents).format==='guardianloop-eeg-public-v1'?C.importPublicRecording(contents):C.importRecording(contents);enterReplay();notice('记录已载入');}catch(error){notice(error.message);}event.target.value='';};
function enterReplay(){if(!recording&&recorder.frames.length){recorder.stop();recording=C.importRecording(recorder.serialize());}if(!recording){notice('暂无真实记录，请先记录本次数据或导入文件');return;}cancel();recorder.stop();session.replay(recording);replayDuration=recording.duration_ms;resetVisual();ingest(session.view(0),performance.now(),true);notice('');transport();}
$('replayMode').onclick=enterReplay;
$('liveMode').onclick=()=>{cancel();session.toLive();resetVisual();notice('');transport();poll();};
$('play').onclick=()=>{if(session.position>=replayDuration)session.position=0;session.playing=!session.playing;lastTime=performance.now();transport();};
$('scrubber').oninput=()=>{session.position=Number($('scrubber').value);resetVisual();ingest(session.view(performance.now()),performance.now(),true);transport();};
$('presentation').onclick=()=>setPresentation(!document.body.classList.contains('presentation'));
$('exitPresentation').onclick=()=>setPresentation(false);
function setPresentation(on){document.body.classList.toggle('presentation',on);$('presentation').setAttribute('aria-pressed',String(on));$('exitPresentation').hidden=!on;}
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch(_){notice('可按 F11 进入全屏');}};
$('consoleLink').href='/'+location.hash;
document.addEventListener('visibilitychange',()=>{if(document.hidden){cancel();if(recorder.active)recorder.append(C.empty('页面后台暂停'),performance.now());session.live(C.empty('页面后台暂停'),performance.now());session.playing=false;waveRows=[];endIndex=null;}else{lastTime=performance.now();if(session.mode==='live')poll();}});
window.addEventListener('pagehide',()=>cancel());window.addEventListener('offline',()=>{cancel();const f=C.empty('网络断开');session.live(f,performance.now());waveRows=[];endIndex=null;if(recorder.active)recorder.append(f,performance.now());});window.addEventListener('online',()=>{cancel();poll();});
function animate(now){
 if(!document.hidden){if(session.mode==='replay'&&session.playing){session.position=Math.min(replayDuration,session.position+now-lastTime);if(session.position>=replayDuration)session.playing=false;ingest(session.view(now),now);transport();}
  const f=session.view(now),signature=JSON.stringify([session.mode,f.ok,f.seq,f.sample_index,f.reason,f.quality,f.fatigue,f.emotion]);if(signature!==lastRender){lastRender=signature;render(f);}
  const interval=matchMedia('(prefers-reduced-motion: reduce)').matches?500:33;if(now-paintAt>=interval){drawWave(f,now);paintAt=now;}
  $('clock').textContent=session.mode==='replay'?timecode(session.position):new Date().toLocaleTimeString('zh-CN',{hour12:false});
  if(recorder.active&&now-recorder.started>600000){recorder.stop('已到 10 分钟，请导出记录');transport();}
 }lastTime=now;requestAnimationFrame(animate);
}
window.addEventListener('beforeunload',event=>{if(recorder.active){event.preventDefault();event.returnValue='';}});
async function loadBundledRecording(){
 session.mode='replay';notice('');
 try{const response=await fetch('/eeg_recording.json',{cache:'no-store'});if(!response.ok)throw Error('脑电记录读取失败');recording=C.importPublicRecording(await response.text());session.replay(recording);replayDuration=recording.duration_ms;session.playing=true;resetVisual();ingest(session.view(performance.now()),performance.now(),true);lastTime=performance.now();transport();}
 catch(error){notice(error.message);}
}
transport();render(C.empty('正在载入脑电记录'));loadBundledRecording();requestAnimationFrame(animate);
})();
