#!/usr/bin/env python3
"""Serve board-local, real GuardianLoop status to a browser (no ESP32)."""

import argparse
import json
import math
import re
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cyton_trial_recorder import CONDITIONS, CONTROL_PATH, STATUS_PATH, atomic_json, read_json, recording_command_lock
from ssvep_cue_runtime import SSVEPCueBridge
from mi_web_bridge import MIWebBridge
LIVE_PATH = Path('/tmp/guardianloop-seed-shadow.json')
REPLAY_PATH = Path('/tmp/guardianloop-seed-replay.json')
SSVEP_LIVE_PATH = Path('/tmp/guardianloop-ssvep-shadow.json')
SSVEP_REPLAY_PATH = Path('/tmp/guardianloop-ssvep-replay.json')
STARTUP_PATH = Path('/run/guardianloop-startup/status.json')
BOOT_ID_PATH = Path('/proc/sys/kernel/random/boot_id')
MANIFEST_PATH = Path(__file__).with_name('release_manifest.json')


PAGE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Z15 GuardianLoop</title><style>
:root{--ink:#132d28;--muted:#647873;--green:#08755a;--red:#b63b36;--amber:#a66a00;--line:#d9e3df}
*{box-sizing:border-box}body{font:16px system-ui,sans-serif;background:#eef3f1;color:var(--ink);margin:0}
main{max-width:1180px;margin:24px auto;padding:16px}.card{background:#fff;border:1px solid #dce6e2;
border-radius:13px;padding:20px;box-shadow:0 5px 18px #18382f13;margin:14px 0}h1{font-size:1.7rem;margin:.3em 0}
h2{font-size:1.15rem;margin:0 0 12px}.value{font-size:1.8rem;font-weight:750}.bad{color:var(--red)}
.muted,small{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.grid .card{margin:0}.status-grid{display:grid;grid-template-columns:1.4fr 1fr;gap:14px}
.ok{color:var(--green)}.warn{color:var(--amber)}.dot{display:inline-block;width:.65em;height:.65em;
border-radius:50%;background:#9aa9a4;margin-right:.45em}.dot.ok{background:#19a974}.dot.warn{background:#dda52a}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}button,select{font:inherit;
padding:7px 11px;border:1px solid #afc0ba;border-radius:7px;background:white;color:var(--ink)}button{cursor:pointer}
button.active{background:#fff3cd;border-color:#d49a21;color:#714b00}.badge{padding:5px 9px;border-radius:99px;background:#e9efed;font-weight:650}
.badge.real{background:#d7f5e9;color:#086548}.badge.demo{background:#fff0c9;color:#805600}
.badge.replay{background:#dcecff;color:#145b8f}
.plot{width:100%;display:block;background:#101a1d;border-radius:8px}.plot-label{display:flex;justify-content:space-between;margin:12px 0 6px}
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:12px}.metric{padding:10px;border:1px solid var(--line);border-radius:8px}
.metric b{display:block;font-size:1.2rem;margin-top:3px}p{line-height:1.45}
.quality-channels{display:grid;grid-template-columns:repeat(8,1fr);gap:7px}.qch{padding:9px 6px;border:1px solid var(--line);border-radius:8px;text-align:center}
.qch.good{background:#e6f7ef}.qch.bad{background:#fde9e7}.qch b{display:block;font-size:1.05rem}.qch small{font-size:.72rem}
@media(max-width:760px){main{margin:4px auto;padding:8px}.grid,.metrics{grid-template-columns:repeat(2,1fr)}
.status-grid{grid-template-columns:1fr}.quality-channels{grid-template-columns:repeat(4,1fr)}.card{padding:14px}}
</style><main><h1>Z15 脑电质量、心情参考与疲劳监测</h1>
<div class="card"><h2>启动自检与计算分工</h2><div id="bootState" class="value">检查中</div>
<p id="plState" class="muted"></p><p id="computeAssignment" class="muted"></p>
<p class="muted">启动自检检查程序、模型及 PL 硬件标识。实时采集状态见下方“设备状态”。</p></div>
<div class="status-grid"><div class="card"><small>疲劳状态（只接受真实且质量合格的数据）</small>
<div class="value" id="fatigue">等待真实脑电数据</div><p id="detail"></p></div>
<div class="card"><small>设备状态</small><p><span class="dot" id="apdot"></span><span id="ap">检查中</span></p>
<p><span class="dot" id="rxdot"></span><span id="receiver">检查中</span></p>
<p><span class="dot" id="datadot"></span><span id="data">检查中</span></p></div></div>
<div class="status-grid"><div class="card"><small>心情参考：正向／中性／负向（模型估计；非真实情绪诊断）</small>
<div class="value" id="emotion">等待真实脑电数据</div><p id="emotionDetail" class="muted"></p></div>
<div class="card"><small>滤波后质量门控（不是原始数据质量）</small><div class="value" id="sqiState">--</div>
<p id="sqiDetail" class="muted">等待第一个完整窗口</p></div></div>
<div class="card"><h2>SEED 正／中／负影片条件 · 八通道候选</h2>
<p class="muted">影子模式，仅供研究观察；不替换主线心情参考或疲劳输出。固定 CH1–CH8：F3、F4、C3、C4、T7、T8、O1、O2。硬故障拒绝；软统计偏离会标记警告，不能当作信号已修复。</p>
<div id="seedShadow" class="value">未收到数据</div><p id="seedShadowDetail" class="muted"></p>
<p class="muted">公开 SEED 数据探索性 15 人逐人留出：平均平衡准确率约 67.4%，预测时间覆盖率约 93.4%。这是影片标签任务，不是当前佩戴者的准确率、预测概率或临床情绪诊断；旧 Cyton 记录经门控后没有候选预测。</p>
<p id="seedReplay" class="muted">历史回放：暂无记录</p></div>
<div class="card"><h2>SSVEP O1/O2 · 只读频率候选</h2>
<div id="ssvepShadow" class="value">未收到数据</div><p id="ssvepDetail" class="muted"></p>
<p class="muted">固定帽位不变，仅读取 O1/O2；ARM 连续滤波与 CCA，2 秒分析窗，每 200 ms 更新。此处是被动频率候选，不代表已识别你的注视或意图。下方提示实验仅做保守时序配对；无目标拒绝与误触发率仍未经真实佩戴验证。永不发送控制指令。无个人校准，质量检查仅为工程门控。</p>
<p><a href="/ssvep-cued">有提示 SSVEP 交互实验</a> · <a href="/ssvep-free">四角自由选择 SSVEP（实验候选）</a>（需手动启动闪烁）</p>
<p id="ssvepReplay" class="muted">历史回放：暂无记录</p></div>
<div class="card"><h2>运动想象与虚拟手 · 固定八通道基础 RMS</h2>
<p><a href="/mi-cued">打开左右手运动想象与虚拟手</a>（默认只观察，虚拟动作需主动勾选，永不驱动真实外设）</p>
<p class="muted">使用基础共享 RMS 模型，个人适配头关闭。与其他任务共用同一采集流，由 ARM 处理；启用受板端配置控制。有提示左右手二分类，休息按钮禁用推理，不是自由异步控制，也不表示准确率已全面验证。</p></div>
<div class="card"><h2>原始干扰与滤波后可用性</h2>
<p id="rawInterference" class="muted">等待原始脑电窗口；原始工频过强会持续告警，即使滤波后可用。</p>
<p id="filteredAvailability" class="muted">滤波后结果待测。没有通过校准与通道映射前，不输出识别结论。</p></div>
<div class="card"><h2>每通道信号质量</h2><div class="quality-channels" id="qualityChannels"></div>
<p class="muted" id="qualityReasons">SQI只用于工程质量判断，不是临床诊断。</p></div>
<div class="grid"><div class="card">校准进度<div class="value" id="calibration">--</div></div>
<div class="card">滤波后质量<div class="value" id="quality">--</div></div>
<div class="card">有效包数<div class="value" id="packets">--</div></div>
<div class="card">丢包 / 超范围行<div class="value" id="transport">--</div></div></div>
<div class="card"><h2>8 通道实时脑电</h2><div class="toolbar">
<span class="badge" id="sourceBadge">等待真实数据</span>
<button id="demoButton" onclick="toggleDemo()">开启界面演示</button>
<label>波形 <select id="signalView"><option value="filtered">滤波后</option><option value="raw">原始</option></select></label>
<label>纵轴 <select id="scale"><option value="100">±100 µV</option><option value="200" selected>±200 µV</option>
<option value="500">±500 µV</option><option value="1000">±1000 µV</option><option value="10000">±10000 µV</option></select></label>
<label>FFT 通道 <select id="fftChannel"></select></label></div>
<canvas class="plot" id="waves" data-css-height="480"></canvas>
<div class="plot-label"><b id="fftTitle">Ch1 频谱</b><span class="muted">0–50 Hz · 浏览器计算，仅用于观察</span></div>
<canvas class="plot" id="fft" data-css-height="240"></canvas>
<div class="metrics"><div class="metric">采样率<b id="sampleRate">--</b></div>
<div class="metric">接收包<b id="packetCount">--</b></div><div class="metric">可核实丢包率<b id="loss">--</b></div>
<div class="metric">异常字节<b id="malformed">--</b></div><div class="metric">超范围行（拦截）<b id="clipped">--</b></div></div>
<div class="metrics"><div class="metric">输入包年龄 / 快照年龄（板端）<b id="dataAge">--</b></div>
<div class="metric">接收队列等待 / 本次运行峰值<b id="queueDelay">--</b></div>
<div class="metric">最近主窗口计算<b id="windowCompute">--</b></div>
<div class="metric">显示快照跳过（非脑电丢包）<b id="displaySkipped">--</b></div></div>
<p class="muted" id="streamResets">主模型断流重置：--（与 SEED 候选的有条件保留策略分开）</p>
<p class="muted">输入包年龄包含排队和快照等待，从 ARM 读取 USB 字节起计，不含无线传输。超过 3 秒不显示当前预测。窗口计算不含独立 SEED 候选及浏览器绘图。</p>
<div class="metrics"><div class="metric">δ 1–4 Hz<b id="delta">--</b></div><div class="metric">θ 4–8 Hz<b id="theta">--</b></div>
<div class="metric">α 8–13 Hz<b id="alpha">--</b></div><div class="metric">β 13–30 Hz<b id="beta">--</b></div>
<div class="metric">主频<b id="peakFreq">--</b></div></div>
<p class="muted" id="monitorNote">没有真实数据时画面保持空白；演示信号只检查网页绘图，不进入 PL，也不生成疲劳结论。</p></div>
<div class="card"><h2>O1/O2 睁眼／闭眼验证</h2>
<p class="muted">请坐稳，依次记录睁眼和闭眼各 20 秒。仅比较滤波后枕区 8–13 Hz α 功率；这不是情绪或疲劳诊断。</p>
<div class="toolbar"><button id="eyesOpen" onclick="beginEyePhase('open')">记录睁眼 20 秒</button>
<button id="eyesClosed" onclick="beginEyePhase('closed')">记录闭眼 20 秒</button>
<button onclick="resetEyeTrial()">清除本次结果</button></div>
<p id="eyeProgress">等待真实 Cyton 数据</p><p id="eyeResult" class="muted">完成两段记录后显示比较结果；若丢样或设备断开，则该段无效。</p></div>
<div class="card"><h2>可选的原始脑电研究记录</h2>
<p class="muted">这不是当前演示的必做步骤，也无需刻意制造某种情绪。开始后 Z15 保存 250 Hz 八通道原始计数与包序号，最长 10 分钟。若自愿开展有标签研究，游戏/活动条件与实际感受须分开记录；条件名称不能当作真实情绪标签。</p>
<div class="toolbar"><label>匿名编号 <input id="participantId" value="P01" maxlength="24"></label>
<label>用途 <select id="trialPhase"><option value="calibration">个人校准</option><option value="evaluation">独立验证</option></select></label>
<label>研究条件 <select id="trialCondition"><option value="boring">无聊类游戏</option><option value="calm">平静类游戏</option><option value="horror">惊悚类游戏</option><option value="funny">趣味类游戏</option></select></label>
<label>素材/活动 <input id="stimulusNote" maxlength="120" placeholder="如：片段编号或活动"></label>
<button id="startTrial" onclick="startTrial()">开始保存</button></div>
<div class="toolbar"><label>实际感受 <select id="feltLabel"><option value="uncertain">不确定</option><option value="boring">无聊</option><option value="calm">平静</option><option value="horror">紧张</option><option value="funny">愉悦</option></select></label>
<label>愉悦程度 1–5 <select id="valenceRating"><option>1</option><option>2</option><option selected>3</option><option>4</option><option>5</option></select></label>
<label>激活程度 1–5 <select id="arousalRating"><option>1</option><option>2</option><option selected>3</option><option>4</option><option>5</option></select></label>
<button id="stopTrial" onclick="stopTrial()" disabled>结束并保存</button></div>
<p id="trialStatus">未开始记录。</p><p id="trialPath" class="muted"></p></div>
<p><a href="/mobile">打开安卓手机监控页</a></p>
<p class="muted" id="connection">连接中…</p><script>
const e=id=>document.getElementById(id), colors=['#62b5e5','#bd87dc','#62c8a1','#dfca58','#f39a58','#ef6f6c','#dc70a5','#b6c6cf'];
let telemetry=null,demo=false,demoPhase=0;
let trialState={},trialPending=false,pendingCommandId=null;
let eyeTrial={phase:null,started:0,end:0,lastIndex:0,lastDropped:0,lastUnresolved:0,samples:[],open:null,closed:null};
for(let i=1;i<=8;i++){let o=document.createElement('option');o.value=i-1;o.textContent='Ch'+i;e('fftChannel').appendChild(o)}
function fit(canvas){let d=devicePixelRatio||1,w=canvas.clientWidth,h=Number(canvas.dataset.cssHeight);canvas.style.height=h+'px';
if(canvas.width!==Math.floor(w*d)||canvas.height!==Math.floor(h*d)){canvas.width=Math.floor(w*d);canvas.height=Math.floor(h*d)}
let c=canvas.getContext('2d');c.setTransform(d,0,0,d,0,0);return [c,w,h]}
function demoData(){let fs=125,n=625,a=[];demoPhase+=.08;for(let j=0;j<n;j++){let row=[];
for(let ch=0;ch<8;ch++){let t=j/fs;row.push(28*Math.sin(2*Math.PI*(8+ch*.7)*t+ch+demoPhase)+
8*Math.sin(2*Math.PI*2*t)+3*Math.sin(j*1.731+ch));}a.push(row)}return {samples:a,sample_rate_hz:fs,source:'demo'}}
function activeData(){if(telemetry&&telemetry.samples&&telemetry.samples.length)return telemetry;return demo?demoData():null}
function plottedSamples(d){return e('signalView').value==='raw'&&d.raw_samples?d.raw_samples:d.samples}
function drawWaves(d){let [c,w,h]=fit(e('waves'));c.fillStyle='#101a1d';c.fillRect(0,0,w,h);let lane=h/8;
c.font='12px system-ui';for(let ch=0;ch<8;ch++){let y=(ch+.5)*lane;c.strokeStyle='#314247';c.beginPath();c.moveTo(46,y);c.lineTo(w,y);c.stroke();
c.fillStyle=colors[ch];c.fillText('Ch'+(ch+1),8,y+4)}if(!d){c.fillStyle='#9db0aa';c.font='17px system-ui';c.fillText('等待 Cyton 真实数据',w/2-82,h/2);return}
let a=plottedSamples(d),n=a.length,scale=Number(e('scale').value);for(let ch=0;ch<8;ch++){c.strokeStyle=colors[ch];c.lineWidth=1.2;c.beginPath();
for(let i=0;i<n;i++){let x=46+(w-52)*i/Math.max(1,n-1),v=Math.max(-scale,Math.min(scale,a[i][ch]||0));let y=(ch+.5)*lane-v/scale*lane*.42;
if(i)c.lineTo(x,y);else c.moveTo(x,y)}c.stroke()}}
function clearBands(){for(let id of ['delta','theta','alpha','beta','peakFreq'])e(id).textContent='--'}
function drawFFT(d){let [c,w,h]=fit(e('fft'));c.fillStyle='#101a1d';c.fillRect(0,0,w,h);c.strokeStyle='#314247';c.fillStyle='#9db0aa';c.font='11px system-ui';
for(let f=0;f<=50;f+=10){let x=38+(w-50)*f/50;c.beginPath();c.moveTo(x,8);c.lineTo(x,h-24);c.stroke();c.fillText(f+'',x-5,h-7)}
if(!d){clearBands();return}let ch=Number(e('fftChannel').value),a=plottedSamples(d).map(r=>r[ch]||0),n=a.length,fs=d.sample_rate_hz||125,mean=a.reduce((x,y)=>x+y,0)/n,bins=[];
for(let f=1;f<=Math.min(50,Math.floor(fs/2));f++){let re=0,im=0;for(let i=0;i<n;i++){let v=(a[i]-mean)*(0.5-0.5*Math.cos(2*Math.PI*i/(n-1))),q=2*Math.PI*f*i/fs;re+=v*Math.cos(q);im-=v*Math.sin(q)}bins.push(Math.sqrt(re*re+im*im)*2/n)}
let max=Math.max(1,...bins);c.strokeStyle=colors[ch];c.lineWidth=2;c.beginPath();bins.forEach((v,i)=>{let x=38+(w-50)*(i+1)/50,y=8+(h-35)*(1-v/max);if(i)c.lineTo(x,y);else c.moveTo(x,y)});c.stroke();e('fftTitle').textContent='Ch'+(ch+1)+' 频谱';
let power=bins.map(v=>v*v),total=power.reduce((x,y)=>x+y,0)||1,band=(lo,hi)=>100*power.slice(Math.max(0,lo-1),Math.min(power.length,hi-1)).reduce((x,y)=>x+y,0)/total;
e('delta').textContent=band(1,4).toFixed(1)+'%';e('theta').textContent=band(4,8).toFixed(1)+'%';e('alpha').textContent=band(8,13).toFixed(1)+'%';e('beta').textContent=band(13,30).toFixed(1)+'%';
let peak=power.indexOf(Math.max(...power))+1;e('peakFreq').textContent=peak+' Hz'}
function render(){let d=activeData();drawWaves(d);drawFFT(d);requestAnimationFrame(render)}
function toggleDemo(){demo=!demo;e('demoButton').className=demo?'active':'';e('demoButton').textContent=demo?'关闭界面演示':'开启界面演示';updateBadge()}
function resetEyeTrial(){eyeTrial={phase:null,started:0,end:0,lastIndex:0,lastDropped:0,lastUnresolved:0,samples:[],open:null,closed:null};
e('eyeProgress').textContent='等待真实 Cyton 数据';e('eyeResult').textContent='完成睁眼和闭眼两段记录后显示结果。'}
function beginEyePhase(phase){if(eyeTrial.phase)return;
if(!telemetry||telemetry.offline||!Number.isFinite(telemetry.sample_index)){
e('eyeProgress').textContent='需要正在接收的真实 Cyton 数据；演示和离线回放不可用于本验证。';return}
eyeTrial.phase=phase;eyeTrial.started=Date.now();eyeTrial.end=eyeTrial.started+20000;
eyeTrial.lastIndex=telemetry.sample_index;eyeTrial.lastDropped=telemetry.dropped_packets||0;
eyeTrial.lastUnresolved=telemetry.unresolved_gaps||0;eyeTrial.samples=[];
e('eyeProgress').textContent=(phase==='open'?'睁眼':'闭眼')+'采集中：20 秒';}
function alphaRelative(samples){if(samples.length<1800)return null;
let fs=125,n=samples.length,results=[];
for(let ch=0;ch<2;ch++){let mean=samples.reduce((sum,row)=>sum+row[ch],0)/n,alpha=0,total=0;
for(let f=4;f<30;f+=.5){let re=0,im=0;for(let i=0;i<n;i++){
let v=(samples[i][ch]-mean)*(0.5-0.5*Math.cos(2*Math.PI*i/(n-1))),angle=2*Math.PI*f*i/fs;
re+=v*Math.cos(angle);im-=v*Math.sin(angle)}let power=re*re+im*im;
total+=power;if(f>=8&&f<13)alpha+=power}results.push(total>0?alpha/total:0)}
return (results[0]+results[1])/2}
function feedEyeTrial(t,stale){if(!eyeTrial.phase)return;
if(stale||!t.samples||t.offline||!Number.isFinite(t.sample_index)){
eyeTrial.phase=null;e('eyeProgress').textContent='采集被设备断开或旧数据中断，请重新记录该段。';return}
if((t.dropped_packets||0)>eyeTrial.lastDropped||(t.unresolved_gaps||0)>eyeTrial.lastUnresolved){
eyeTrial.phase=null;e('eyeProgress').textContent='采集期间出现丢包或序号异常，请重新记录该段。';return}
let first=t.sample_index-t.samples.length+1;
if(first>eyeTrial.lastIndex+1){eyeTrial.phase=null;e('eyeProgress').textContent='浏览器漏收采样，请重新记录该段。';return}
for(let i=0;i<t.samples.length;i++){let id=first+i;if(id<=eyeTrial.lastIndex)continue;
if(Date.now()-eyeTrial.started>=2000)eyeTrial.samples.push([t.samples[i][6],t.samples[i][7]])}
eyeTrial.lastIndex=t.sample_index;
let remaining=Math.max(0,Math.ceil((eyeTrial.end-Date.now())/1000));
e('eyeProgress').textContent=(eyeTrial.phase==='open'?'睁眼':'闭眼')+'采集中：还剩 '+remaining+' 秒 · 有效采样 '+eyeTrial.samples.length;
if(remaining)return;
let value=alphaRelative(eyeTrial.samples),phase=eyeTrial.phase;eyeTrial.phase=null;
if(value===null){e('eyeProgress').textContent='该段有效采样不足，请重新记录。';return}
eyeTrial[phase]=value;e('eyeProgress').textContent=(phase==='open'?'睁眼':'闭眼')+'记录完成。';
if(eyeTrial.open!==null&&eyeTrial.closed!==null){let ratio=eyeTrial.open>0?eyeTrial.closed/eyeTrial.open:0;
e('eyeResult').textContent='O1/O2 α相对功率：睁眼 '+(100*eyeTrial.open).toFixed(1)+'%，闭眼 '+(100*eyeTrial.closed).toFixed(1)+'%；闭/睁比 '+ratio.toFixed(2)+'。这只是滤波后生理反应检查，不能单独证明信号或模型准确。'}
else e('eyeResult').textContent='还需记录'+(phase==='open'?'闭眼':'睁眼')+' 20 秒。'}
function updateBadge(){let available=telemetry&&telemetry.samples&&telemetry.samples.length,replay=available&&telemetry.offline,real=available&&!replay;
e('sourceBadge').className='badge '+(replay?'replay':real?'real':demo?'demo':'');
e('sourceBadge').textContent=replay?'SEED-VIG 离线回放':real?'真实 Cyton 数据':demo?'演示信号（非脑电）':'等待真实数据'}
async function sendTrial(payload){trialPending=true;try{let r=await fetch('/api/recording',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,browser_time_ms:Date.now()})});let x=await r.json();if(!r.ok)throw Error(x.error||'请求失败');pendingCommandId=x.command_id;e('trialStatus').textContent='已发送命令，等待 Z15 确认…';await refreshTrial()}catch(err){e('trialStatus').textContent='记录操作失败：'+err.message}finally{trialPending=false}}
function startTrial(){if(trialPending)return;sendTrial({action:'start',participant_id:e('participantId').value.trim(),phase:e('trialPhase').value,condition:e('trialCondition').value,stimulus_note:e('stimulusNote').value.trim()})}
function stopTrial(){if(trialPending||!trialState.trial_id)return;sendTrial({action:'stop',trial_id:trialState.trial_id,self_report:{felt_label:e('feltLabel').value,valence:Number(e('valenceRating').value),arousal:Number(e('arousalRating').value)}})}
async function refreshTrial(){try{let r=await fetch('/api/recording',{cache:'no-store'}),x=await r.json();trialState=x.recording||{};
if(pendingCommandId&&trialState.last_command===pendingCommandId)pendingCommandId=null;
let active=!x.stale&&trialState.state==='recording';e('startTrial').disabled=active||trialPending||!!pendingCommandId||!x.system.acquisition_active;
e('stopTrial').disabled=!active||trialPending||!!pendingCommandId;
if(pendingCommandId){e('trialStatus').textContent='已发送命令，等待 Z15 确认…';return}
e('trialStatus').textContent=active?('正在记录 '+trialState.condition+' · '+trialState.samples+' 个原始采样 · '+trialState.elapsed_seconds+' 秒'):(trialState.state==='complete'?'已保存 '+(trialState.detail?.samples??0)+' 个原始采样。':trialState.state==='error'?'记录错误：'+trialState.detail:trialState.state==='duration_limit'?'达到10分钟上限，已自动保存。':trialState.state==='service_stopped'?'采集服务停止，已保存可恢复记录。':'未开始记录。');
e('trialPath').textContent=active?'Z15 保存目录：'+trialState.path:trialState.detail?.path?'Z15 保存目录：'+trialState.detail.path:'';
}catch(err){e('trialStatus').textContent='记录状态暂不可用'}}
async function refreshStatus(){try{let r=await fetch('/api/status',{cache:'no-store'}),x=await r.json(),f=x.fatigue||{},s=x.system||{},stale=x.stale,review=f.offline&&f.seq;
let boot=s.startup||{},ready=boot.state==='ready';
e('bootState').textContent=boot.arm_update_pending_boot?'ARM版本已更新；新版本完整开机自检待下次启动':ready?'本次启动自检通过':boot.state==='failed'?'启动自检失败，采集未获准启动':boot.state==='checking'?'启动自检中':'本次启动尚无自检结果';
e('bootState').className='value '+(ready?'ok':boot.state==='failed'?'bad':'warn');
e('plState').textContent=ready&&boot.pl?.loaded?'正式 PL 已加载，启动时硬件标识已校验；当前固定帽位任务使用 ARM。':boot.error||'等待正式 PL 加载与硬件校验。';
e('computeAssignment').textContent=ready?'ARM：连续滤波／SQI、六通道 GAMEEMO、四通道疲劳、八通道 SEED 候选、O1/O2 SSVEP；PL：保留历史 DE/HGB 核，当前固定帽位任务未调用。':'模型与计算分工尚待自检确认。';
e('connection').textContent=review?(stale?'SEED-VIG 回放已结束 · 最后窗口 '+f.seq:'SEED-VIG 离线回放 · 窗口 '+f.seq):(stale?'数据尚未到达或已超时':'Z15 实时数据 · 窗口 '+f.seq);let label={normal:'正常',mild:'轻度疲劳',severe:'重度疲劳'};
e('fatigue').textContent=((!stale||review)&&f.valid)?(label[f.level]||f.level):(f.state==='calibrating'&&!stale?'校准中':'--（无有效预测）');
e('fatigue').className='value'+(f.valid&&f.level==='severe'&&(!stale||review)?' bad':'');e('detail').textContent=review?(stale?'离线回放已结束；最后结果不代表当前佩戴者。':(f.valid?'SEED-VIG 离线记录的板端推理；不是当前佩戴者结论。':'离线回放正在校准或未通过质量门。')):(stale?'请开启 Cyton 或启动离线回放。':f.reason==='CHANNEL_MAP_MISMATCH'?'当前佩戴通道与已训练疲劳模型不一致；疲劳结论已禁用。':(!f.valid?'信号未通过校验或仍在校准，不生成疲劳结论。':f.algorithm_version==='seedvig-cyton-overlap4-arm-v1'?'T7/T8/O1/O2 四通道的 Z15 ARM 疲劳估计；公开数据训练，尚非本人准确率验证。':'真实 PL 结果，且已通过质量校验。'));
if(!review&&!f.valid&&['STREAM_IDLE','STREAM_TIMING_GAP','MALFORMED_STREAM','SERVICE_STOPPED_OR_STREAM_TIMEOUT'].includes(f.reason))e('detail').textContent='采集已中断，旧结果已清除；恢复后主模型重新收集连续窗口并校准。';
if(!review&&['PROCESSING_BACKLOG','STALE_EEG'].includes(f.reason))e('detail').textContent='输入数据已过旧或发生处理积压，当前预测已屏蔽，等待新的及时窗口。';
e('calibration').textContent=(f.calibration_current??0)+' / '+(f.calibration_total??15);e('quality').textContent=f.signal_quality??(f.valid?'通过':'未通过');
let q=f.sqi||{},em=f.emotion||{},emotionNames={boring:'中性情绪',calm:'中性情绪',horror:'负向情绪',funny:'正向情绪'};
e('emotion').textContent=trialState.state==='recording'&&trialState.phase==='evaluation'?'独立验证记录中，预测暂时隐藏':(!stale&&em.valid)?(emotionNames[em.label]||'无可信结果'):'--（信号不足或模型未就绪）';
let modelChannels=em.model_channels||em.channel_map||[],minimum=em.minimum_usable_channels??6;
let modelNote=modelChannels.length?' · 使用 '+modelChannels.join('/')+' · 门控至少 '+minimum+'/'+modelChannels.length+' 通道':'';
e('emotionDetail').textContent=(em.valid?((em.confidence!=null?'模型分数 '+(em.confidence*100).toFixed(1)+'%（非实测准确率）': 'SVM投票 '+(em.votes||[]).join('/')+'（不是概率）')+' · 可用 '+(em.usable_channels??'--')+'/'+modelChannels.length+' · 心情参考为原始四类结果的展示归并，个人真实情绪准确率未验证'):(em.state==='sqi_calibrating'?'正在逐通道建立15窗SQI参考，模型通道校准不足。':em.state==='collecting_12s'?'正在收集12秒连续脑电。':em.state==='packet_gap_12s'?'最近12秒有接收丢包，已拒绝预测。':em.state==='insufficient_signal'?'模型所需六通道质量不足，已拒绝输出。':em.state==='channel_map_mismatch'?'当前电极 '+(em.actual_channel_map||[]).join('/')+' 缺少模型要求的 '+(em.expected_channel_map||[]).join('/')+'，已禁止输出。':'GAMEEMO跨设备模型暂不可用。'))+modelNote;
if(trialState.state==='recording'&&trialState.phase==='evaluation')e('emotionDetail').textContent='本段结束后再查看模型输出，避免影响自评。';
let stateText={good:'良好',degraded:'降级运行',invalid:'不可用'};e('sqiState').textContent=stateText[q.state]||'--';
e('sqiState').className='value '+(q.state==='good'?'ok':q.state==='degraded'?'warn':q.state==='invalid'?'bad':'');
e('sqiDetail').textContent=q.state?('总体 '+((q.overall_quality??0)*100).toFixed(1)+'% · 可用 '+(q.usable_channels??0)+'/8 · 已校准 '+(q.calibrated_channels??0)+'/8，六通道进度 '+(q.calibration_current??0)+'/'+(q.calibration_total??15)):'等待第一个完整窗口';
let raw=f.raw_interference||{},ratios=raw.mains_ratio||[],rawDominant=ratios.filter(v=>v>0.5).length;
e('rawInterference').textContent=ratios.length?('原始 50 Hz 占主导：'+rawDominant+'/8 通道；最大占比 '+(100*Math.max(...ratios)).toFixed(1)+'%。原始数据保留，滤波不会清除这项告警。'):'等待原始干扰数据。';
e('filteredAvailability').textContent=q.state?('滤波后可用 '+(q.usable_channels??0)+'/8，状态 '+(stateText[q.state]||q.state)+'；'+(q.calibrated?'全局SQI参考已就绪。':'全局SQI参考尚未就绪。')+'心情参考另按模型所用通道的校准和质量门控。'):'等待滤波后质量数据。';
let channelRows=q.channels||[],channelMap=f.channel_map||[];e('qualityChannels').innerHTML=Array.from({length:8},(_,i)=>{let present=Boolean(channelRows[i]),c=channelRows[i]||{},good=present&&c.usable!==false,reason=present?((c.reasons||[]).join(', ')||'正常'):'等待数据',raw50=ratios[i];return '<div class="qch '+(present?(good?'good':'bad'):'')+'"><b>CH'+(i+1)+' '+(channelMap[i]||'')+'</b><span>'+(present?((c.quality??0)*100).toFixed(0)+'%':'--')+'</span><small>'+(present?(c.downweighted?'已降权':'滤波后可用')+' · 校准 '+(c.calibration_current??0)+'/'+(q.calibration_total??15):reason)+'</small><small>原始50 Hz '+(raw50!=null?(100*raw50).toFixed(0)+'%':'--')+'</small></div>'}).join('');
let bad=channelRows.filter(c=>c.usable===false).map(c=>'CH'+c.index+': '+(c.reasons||[]).join('/'));e('qualityReasons').textContent=!q.state?'等待真实Cyton窗口；SQI只用于工程质量判断，不是临床诊断。':bad.length?('已降权：'+bad.join('；')):'没有检测到需降权通道。';
e('packets').textContent=f.packets_seen??'--';e('transport').textContent=(f.dropped_packets??f.sequence_gaps??'--')+' / '+(f.clipped_rows??'--');
e('ap').textContent=s.ap_active?'板卡热点正常：'+s.ap_ssid+'（'+s.ap_ip+'）':'板卡热点异常';e('receiver').textContent=s.receiver_present?'Cyton USB 接收器已连接':'Cyton USB 接收器未连接';
e('data').textContent=review?(stale?'离线回放已结束，可查看最后一窗':'正在处理 SEED-VIG 离线记录'):(!stale?'正在接收真实脑电数据':'当前没有脑电数据（不会生成结果）');e('apdot').className='dot '+(s.ap_active?'ok':'warn');
e('rxdot').className='dot '+(s.receiver_present?'ok':'warn');e('datadot').className='dot '+(!stale?'ok':'warn');
if(!review&&['STREAM_STARTING','STREAM_IDLE','STREAM_TIMING_GAP','MALFORMED_STREAM','SERVICE_STOPPED_OR_STREAM_TIMEOUT'].includes(f.reason)){e('connection').textContent='启动／中断保护：等待新的完整窗口';e('data').textContent='主模型等待恢复；当前收包情况请看波形快照年龄及接收包计数';e('datadot').className='dot warn'}
}catch(err){e('connection').textContent='网页与板卡服务连接断开'}}
async function refreshTelemetry(){try{let r=await fetch('/api/telemetry',{cache:'no-store'}),x=await r.json(),t=x.telemetry||{};telemetry=(x.stale&&!t.offline)?null:t;
let d=t.runtime||{},ms=v=>Number.isFinite(v)?v.toFixed(1)+' ms':'--';
e('dataAge').textContent=Number.isFinite(x.data_age_seconds)?x.data_age_seconds.toFixed(2)+' / '+x.snapshot_age_seconds.toFixed(2)+' s'+(x.stale?'（过期）':''):'--';
e('queueDelay').textContent=x.stale?'--':ms(d.reader_queue_delay_ms)+' / '+ms(d.reader_queue_delay_max_ms);
e('windowCompute').textContent=x.stale?'--':ms(d.last_window_compute_ms);
e('displaySkipped').textContent=x.stale?'--':(d.display_snapshots_skipped??'--');
e('streamResets').textContent='主模型断流重置：'+(x.stale?'--':(d.primary_stream_resets??'--'))+'；恢复后重新收集连续窗口并校准。';
e('sampleRate').textContent=t.sample_rate_hz?t.sample_rate_hz+' Hz':'--';e('packetCount').textContent=t.packets_seen??'--';
e('loss').textContent=t.packet_loss_percent!=null?t.packet_loss_percent.toFixed(3)+'%':'无法核实（序号异常 '+(t.unresolved_gaps??0)+'）';e('malformed').textContent=t.malformed_bytes??'--';e('clipped').textContent=t.clipped_rows??'--';
feedEyeTrial(t,x.stale);updateBadge()}catch(err){telemetry=null;for(let id of ['dataAge','queueDelay','windowCompute','displaySkipped','streamResets'])e(id).textContent='--（连接中断）';feedEyeTrial({},true);updateBadge()}}
e('fftChannel').onchange=()=>{e('fftTitle').textContent='Ch'+(Number(e('fftChannel').value)+1)+' 频谱'};
async function refreshShadow(){try{let r=await fetch('/api/seed-shadow',{cache:'no-store'});if(!r.ok)throw Error('HTTP');let x=await r.json(),v=x.live||{},names={no_data:'未收到数据',reset:'断流后已重置',rejected:'信号不合格',warming:'滤波热身',collecting:'收集完整窗口',calibrating:'校准中',prediction:'可输出候选',error:'候选不可用'},labels={[-1]:'负性',0:'中性',1:'正性'};
let ready=!x.stale&&v.source==='live'&&v.valid&&v.state==='prediction'&&Object.prototype.hasOwnProperty.call(labels,v.class_id);
e('seedShadow').textContent=x.stale?'输入过旧，候选已隐藏':ready?'SEED 影片条件候选：'+labels[v.class_id]:(names[v.state]||'等待');
e('seedShadowDetail').textContent=x.stale?'未取得及时数据；不沿用历史类别。':'实时影子模式 · '+(names[v.state]||'等待')+' · 基线 '+Math.min(v.accepted_windows||0,5)+'/5 个完整窗口 · '+(ready?'研究候选，非当前真实情绪诊断':(v.reason||'尚未达到输出条件'));
if(!x.stale){e('seedShadowDetail').textContent+=' · '+(v.policy_version||'策略未知');if(v.warning)e('seedShadowDetail').textContent+=' · 软质量警告，未证明信号已修复';if(v.last_gap)e('seedShadowDetail').textContent+=' · 上次中断基线'+(v.last_gap.baseline_retained?'已保留':'已清空');}
let q=x.replay||{};e('seedReplay').textContent='历史离线回放（非当前佩戴者）：'+(q.updated_at?((q.finished?'已结束':'进行中')+' · '+(names[q.state]||q.state)+' · '+(q.summary?JSON.stringify(q.summary):'无准确率结论')):'暂无记录');
}catch(err){e('seedShadow').textContent='候选状态暂不可用';e('seedShadowDetail').textContent='网页与板卡服务连接失败，不显示历史类别。';e('seedReplay').textContent='历史回放状态暂不可用';}}
refreshShadow();setInterval(refreshShadow,2000);
async function refreshSSVEP(){try{let r=await fetch('/api/ssvep-shadow',{cache:'no-store'});if(!r.ok)throw Error('HTTP');let x=await r.json(),v=x.live||{},q=v.quality||{},names={no_data:'未收到及时数据',warmup:'滤波热身／收集完整窗口',signal_invalid:'信号不合格',candidate_only:'仅供观察的候选',error:'候选不可用'};
let ready=!x.stale&&v.source==='live'&&v.valid&&v.state==='candidate_only'&&Number.isFinite(v.frequency_hz);
e('ssvepShadow').textContent=ready?v.frequency_hz+' Hz · 非控制指令':(names[v.state]||'等待数据');
e('ssvepDetail').textContent='实时只读旁路 · '+(names[v.state]||'等待')+' · 热身 '+(v.warmup_samples||0)+'/660 样本 · 序号/时序异常 '+(v.sequence_gaps||0)+(q.warning?' · 原始或残余干扰警告':'')+(v.reason?' · '+v.reason:'');
if(q.channels)e('ssvepDetail').textContent+=' · '+q.channels.map(c=>c.channel+': '+(c.hard_reasons.length?c.hard_reasons.join(', '):'硬检查通过')+(c.warnings.length?' / '+c.warnings.join(', '):'')).join('；');
let p=x.replay||{};e('ssvepReplay').textContent='历史离线回放（非实时、非当前佩戴者）：'+(p.finished?JSON.stringify(p.summary):'暂无已完成记录');
}catch(err){e('ssvepShadow').textContent='连接中断，候选已隐藏';e('ssvepDetail').textContent='不沿用旧频率';e('ssvepReplay').textContent='回放状态暂不可用';}}
refreshSSVEP();setInterval(refreshSSVEP,500);
refreshStatus();refreshTelemetry();refreshTrial();setInterval(refreshStatus,2000);setInterval(refreshTelemetry,500);setInterval(refreshTrial,1000);requestAnimationFrame(render);
</script></main></html>"""

SSVEP_CUED_PAGE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SSVEP 提示实验 · Z15</title>
<style>body{font:17px system-ui,sans-serif;background:#eef3f1;color:#132d28;margin:0}
main{max-width:850px;margin:auto;padding:20px}.card{background:white;padding:20px;border-radius:12px;margin:14px 0}
button,select{font:inherit;padding:9px;margin:5px}#stimulus{height:300px;display:grid;place-items:center;
background:#393939;border-radius:12px;color:white;font-size:3rem}#stimulus.on{background:#b9b9b9;color:#101010}
.bad{color:#a42b2b}.good{color:#08755a}p{line-height:1.5}</style>
<main><p><a href="/">← 返回总览</a></p><h1>有提示 SSVEP 交互实验</h1>
<div class="card"><p>固定 O1/O2，单目标逐次呈现，ARM 的 8/10/12/14 Hz CCA 候选只用于屏幕反馈。目标为“休息”时不闪烁，也不会接受任何候选。匹配只是工程反馈，不是经过无目标误触发验证的脑控命令。</p>
<p class="bad">闪烁可能引起不适；有光敏性风险者请勿启动。感到不适立即点“停止”或离开页面。请勿在驾驶或操作设备时使用。</p>
<label><input id="consent" type="checkbox">我了解风险，自愿在此屏幕启动短时闪烁</label><p>
<label>提示目标 <select id="target"><option value="10">10 Hz</option><option value="12">12 Hz</option>
<option value="8">8 Hz</option><option value="14">14 Hz</option><option value="0">休息／无目标</option></select></label>
<button id="start">开始一次 8 秒以内的提示</button><button id="stop">停止</button></p>
<p><label><input id="requireRaw" type="checkbox" autocomplete="off">本轮同步保存原始脑电＋提示事件（点击开始后自动准备录制，再开始闪烁）</label></p>
<p id="rawStatus">读取同步录制状态中……</p>
<button id="demoOnly" type="button">普通演示：不要求原始录制</button>
<p id="inputStatus">读取 O1/O2 输入状态中……</p>
<p><a href="/">查看系统启动自检与 ARM／PL 计算分工</a></p>
<button id="timingCheck">测浏览器帧时序（不闪烁，约 3 秒）</button>
<p id="timingResult">尚未检查当前显示端。此检查不产生闪烁，也不是光学实测。</p>
<p id="cue">尚未开始</p><div id="stimulus">停止</div>
<p id="feedback">无识别结论</p><p id="frame">显示帧时序待测</p>
<p>严格条件：屏幕报告开始呈现后，等待至少 2.5 秒完整数据窗；实时数据新鲜、O1/O2 质量合格、显示帧时序正常，并连续三个 200 ms 窗口匹配提示，才显示“匹配”。断流、坏质量、页面隐藏、停顿均撤销反馈。帧时序只是浏览器自报，不能证明实际光学频率准确；无佩戴时仅可验证软件流程。</p>
<p>试次提示、呈现回执、帧统计及采集进程逐窗候选会写入板端研究日志。原始同步录制另存八路未滤波、未量化裁剪的ADC计数、包序号和USB接收单调时间；它不是屏幕发光同步测量。</p></div>
<p>在约 240 Hz 且预检合格的屏幕上，10/12 Hz 分别按每半周期 12/10 帧切换。开始前请在实际刺激屏幕上重新运行上方预检；预检或运行中帧间隔异常时不会确认匹配。仍需光学实测。</p>
<script>
const $=id=>document.getElementById(id);let trial=null,active=false,activeHz=0,started=0,lastFrame=0,frameCount=0,poor=0,maxGap=0,transitions=0,previousOn=false,raf=0,timer=0,pollTimer=0,lastState=null;
let timingBusy=false,timingReady=null,locked240=false,arming=false,startEpoch=0;
function readiness(x){const i=x.input||{},names={ready:'可测试',warmup:'热身',signal_invalid:'信号不合格',no_data:'无及时数据'};
const reasons={input_backlog:'输入积压',input_expired:'数据过期',packet_timeout:'断流，等待恢复；恢复后重新热身',waiting_for_cyton:'等待 Cyton 开机并拨到 PC；当前无数据，不是休息判定',ssvep_reader_queue_gap:'读包旁路丢包，重新热身',nonfinite_or_adc_rail:'ADC 饱和或非有限数据',startup:'刚启动'};
$('inputStatus').textContent='O1/O2 输入：'+(names[i.state]||'不可用')+(i.age_seconds==null?'':' · 延迟 '+Math.round(i.age_seconds*1000)+' ms')+(i.ready?'':' · '+(reasons[i.reason]||i.reason||'等待数据'));
if(i.state==='warmup')$('inputStatus').textContent+=' · '+i.warmup_samples+'/'+i.required_samples+' 样本';
const raw=x.raw_recording,control=x.recording_control||{};
$('rawStatus').textContent=control.state==='starting'?'正在等待采集端确认录制与首批原始样本（尚不闪烁）':control.state==='stopping'?'正在关闭本轮录制':
raw?'同步原始录制已就绪 · '+raw.samples+' 样本':control.error||'勾选后点击开始，将自动准备录制；不勾选则仅演示，不保存原始数据。';}
async function refreshReadiness(){if(active)return;try{const r=await fetch('/api/ssvep-cue',{cache:'no-store'});readiness(await r.json());}catch(_){$('inputStatus').textContent='输入状态不可用；不沿用旧结果。';}}
$('demoOnly').onclick=()=>{if(active||arming)return;$('requireRaw').checked=false;$('feedback').textContent='已选择普通演示；预检通过后点击“开始”即可，不需要同步录制。';};
setInterval(refreshReadiness,1000);refreshReadiness();
function percentile(values,p){let sorted=[...values].sort((a,b)=>a-b);return sorted[Math.min(sorted.length-1,Math.floor(p*(sorted.length-1)))]}
function frameLockedOn(hz,index){return Math.floor(index/(120/hz))%2===0}
function timingReport(times){let gaps=times.slice(1).map((ts,i)=>ts-times[i]).filter(x=>x>0),median=percentile(gaps,.5),
span=times.at(-1)-times[0],refresh=gaps.length*1000/span,p95=percentile(gaps,.95),late=gaps.filter(x=>x>1.5*median).length;
timingReady={refresh,p95,late,count:gaps.length,measuredAt:performance.now()};
let rows=[`软件测得回调 ${refresh.toFixed(2)} Hz（${gaps.length} 帧间隔/总时长；中位间隔 ${median.toFixed(2)} ms，p95 ${p95.toFixed(2)} ms，超 1.5 倍间隔 ${late}/${gaps.length}）；以下不是屏幕发光实测。`];
let lockEligible=refresh>=235&&refresh<=245&&p95<=6&&late<=Math.max(1,gaps.length*.005);
for(let hz of [8,10,12,14]){let previous=true,changes=[],frameLock=lockEligible&&(hz===10||hz===12);
for(let index=1;index<times.length;index++){let ts=times[index],on=frameLock?frameLockedOn(hz,index):Math.sin(2*Math.PI*hz*(ts-times[0])/1000)>=0;if(on!==previous)changes.push(ts);previous=on}
let half=1000/(2*hz),errors=changes.slice(1).map((ts,i)=>Math.abs((ts-changes[i])-half)),visible=changes.length*500/span,
frames=refresh/(2*hz),integerHalf=Math.abs(frames-Math.round(frames))<.12;
rows.push(`${hz} Hz：半周期约 ${frames.toFixed(2)} 帧（${integerHalf?'接近整数':'非整数，存在帧量化'}）；${frameLock?'固定帧':'按时间'}模拟切换 ${(visible).toFixed(2)} Hz，半周期误差 p95 ${errors.length?percentile(errors,.95).toFixed(1):'--'} ms。`)}
return rows.join('\n')}
$('timingCheck').onclick=()=>{if(active||timingBusy){$('timingResult').textContent='请先停止当前试次或等待检查完成。';return}
if(document.hidden){$('timingResult').textContent='页面不可见，无法测量；请让页面保持前台。';return}
timingReady=null;timingBusy=true;$('timingCheck').disabled=true;$('timingResult').textContent='测量中：画面保持静止，不闪烁……';let times=[];
function sample(ts){if(document.hidden){timingReady=null;timingBusy=false;$('timingCheck').disabled=false;$('timingResult').textContent='页面转入后台，测量作废。';return}
times.push(ts);if(times.length<2||ts-times[0]<3000){requestAnimationFrame(sample);return}
$('timingResult').style.whiteSpace='pre-line';$('timingResult').textContent=timingReport(times);
timingBusy=false;$('timingCheck').disabled=false}requestAnimationFrame(sample)};
async function cmd(action,more={}){const r=await fetch('/api/ssvep-cue',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({action,id:trial&&trial.id,...more}),cache:'no-store'});const x=await r.json();if(!r.ok)throw Error(x.error||'请求失败');return x;}
function clearView(){cancelAnimationFrame(raf);clearInterval(timer);clearInterval(pollTimer);$('target').disabled=false;$('stimulus').classList.remove('on');$('stimulus').textContent='停止';}
async function stop(reason='user_stopped'){const wasArming=arming;startEpoch++;arming=false;active=false;clearView();$('start').disabled=false;$('requireRaw').disabled=false;if(trial){try{await cmd('stop',{stop_reason:reason})}catch(e){/* expired session */}trial=null;}if(wasArming){try{await cmd('record_cancel')}catch(e){$('rawStatus').textContent='取消录制确认失败；板端最长 45 秒自动关闭';}}$('cue').textContent='已停止';
$('feedback').className='';$('feedback').textContent=lastState?
`本次已结束；${lastState.ever_matched?'曾达到提示匹配条件':'未确认'}（历史显示，当前无识别）`:'本次已结束；无识别结论';}
function tick(ts){if(!active)return;if(!started){started=ts;lastFrame=ts;cmd('presented',{browser_onset_ms:ts,browser_send_ms:performance.now(),browser_wall_ms:Date.now()}).catch(e=>{stop('display_timing_unreliable');$('feedback').textContent=e.message});}
let gap=ts-lastFrame;if(frameCount&&gap>0){maxGap=Math.max(maxGap,gap);if(gap>25)poor++}frameCount++;lastFrame=ts;
if(locked240&&frameCount>1&&gap>8){stop('display_timing_unreliable');$('feedback').textContent='240 Hz 帧间隔中断，试次已拒绝；请重新预检。';timingReady=null;return}
let hz=activeHz,on=hz>0&&(locked240?frameLockedOn(hz,frameCount-1):Math.sin(2*Math.PI*hz*(ts-started)/1000)>=0);
if(frameCount>1&&on!==previousOn)transitions++;previousOn=on;
$('stimulus').classList.toggle('on',on);$('stimulus').textContent=hz===0?'休息':hz+' Hz';
if(ts-started>=7500){stop('display_complete');return}raf=requestAnimationFrame(tick);}
async function heartbeat(){if(!active||!trial)return;try{let x=await cmd('heartbeat',{frame_count:frameCount,
duration_ms:performance.now()-started,max_gap_ms:maxGap,poor_frames:poor,
display_hz:started?transitions*500/(performance.now()-started):0});if(x.state!=='active')stop();
$('frame').textContent=`帧 ${frameCount}，最大间隔 ${maxGap.toFixed(1)} ms，延迟帧 ${poor}，可见转换约 ${(started?transitions*500/(performance.now()-started):0).toFixed(2)} Hz；${x.frame_ok?'工程时序检查通过':'时序未达门限'}`;
}catch(e){stop();$('feedback').textContent='会话断开：'+e.message}}
async function poll(){if(!active)return;try{let r=await fetch('/api/ssvep-cue',{cache:'no-store'}),x=await r.json();
readiness(x);
if(x.state!=='active'&&x.state!=='awaiting_presentation'){stop();return}
lastState=x;
$('feedback').textContent=x.accepted?`提示匹配：${x.observed_hz} Hz（仅屏幕反馈）`:
`未确认／拒绝：${x.reason}；候选 ${x.observed_hz===null?'无':x.observed_hz+' Hz'}；连续 ${x.streak}/3`;
$('feedback').className=x.accepted?'good':'';
}catch(e){stop();$('feedback').textContent='状态读取失败：'+e.message}}
$('start').onclick=async()=>{if(active||arming)return;if(!$('consent').checked){alert('请先确认闪烁风险');return}
activeHz=Number($('target').value);locked240=(activeHz===10||activeHz===12);
if(locked240&&(!timingReady||performance.now()-timingReady.measuredAt>300000||timingReady.refresh<235||timingReady.refresh>245||timingReady.p95>6||timingReady.late>Math.max(1,timingReady.count*.005))){$('feedback').textContent='请在当前刺激屏幕前台重做无闪烁 240 Hz 预检；10/12 Hz 试次尚未启动。';return}
const token=++startEpoch,requireRaw=$('requireRaw').checked;arming=true;$('start').disabled=true;$('requireRaw').disabled=true;$('target').disabled=true;
try{if(requireRaw){$('feedback').textContent='正在准备同步原始录制；此时不闪烁。';let status=await cmd('record_start',{target_hz:activeHz,consent:true});
for(let attempt=0;attempt<32;attempt++){if(token!==startEpoch){await cmd('record_cancel');return;}readiness(status);
const control=status.recording_control||{};if(control.error)throw Error(control.error);
if(status.raw_recording&&(control.state==='ready'||control.state==='external'))break;
if(attempt===31)throw Error('原始录制启动超时；没有启动闪烁');
await new Promise(resolve=>setTimeout(resolve,250));status=await cmd('record_status');}}
if(token!==startEpoch||document.hidden||!$('consent').checked){if(requireRaw)await cmd('record_cancel');return;}
const begun=await cmd('start',{target_hz:activeHz,require_raw_recording:requireRaw});
if(token!==startEpoch){await cmd('stop',{id:begun.id,stop_reason:'user_stopped'});return;}
trial=begun;arming=false;active=true;started=0;lastFrame=0;frameCount=0;poor=0;maxGap=0;transitions=0;previousOn=false;lastState=null;
$('target').disabled=true;$('cue').textContent='请注视提示：'+(activeHz===0?'休息':activeHz+' Hz');
raf=requestAnimationFrame(tick);timer=setInterval(heartbeat,400);pollTimer=setInterval(poll,250);
}catch(e){if(requireRaw){try{await cmd('record_cancel')}catch(_){}}if(token===startEpoch)$('feedback').textContent=e.message}
finally{if(token===startEpoch&&!active){arming=false;clearView();$('start').disabled=false;$('requireRaw').disabled=false;}}};
$('stop').onclick=()=>stop();document.addEventListener('visibilitychange',()=>{if(document.hidden){timingReady=null;if(active||arming)stop('page_hidden')}});
window.addEventListener('pagehide',()=>{if(active||arming)stop('page_hidden')});
</script></main></html>"""


def command_ok(*args):
    try:
        return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=1, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def cyton_receiver_present():
    """Match the OpenBCI FTDI receiver, not just any USB serial adapter."""
    for tty in Path("/sys/class/tty").glob("ttyUSB*"):
        device = tty.resolve()
        for parent in (device, *device.parents):
            try:
                vendor = (parent / "idVendor").read_text().strip().lower()
                product = (parent / "idProduct").read_text().strip().lower()
            except OSError:
                continue
            if (vendor, product) == ("0403", "6015"):
                return True
    return False


def startup_status():
    status = read_json(STARTUP_PATH)
    try:
        current_boot = BOOT_ID_PATH.read_text().strip()
    except OSError:
        return {'state': 'not_checked'}
    if not isinstance(status, dict) or status.get('boot_id') != current_boot:
        return {'state': 'not_checked'}
    installed = read_json(MANIFEST_PATH)
    if isinstance(installed, dict) and installed.get('release_id') and installed['release_id'] != status.get('release_id'):
        return dict(status, installed_release_id=installed.get('release_id'), arm_update_pending_boot=True)
    return status


def system_status():
    return {
        "board_online": True,
        "ap_active": command_ok("systemctl", "is-active", "--quiet", "guardianloop-ap.service"),
        "ap_ssid": "GuardianLoop-Z15",
        "ap_ip": "192.168.50.1",
        "receiver_present": cyton_receiver_present(),
        "acquisition_active": command_ok("systemctl", "is-active", "--quiet",
                                         "guardianloop-cyton.service"),
        "startup": startup_status(),
    }


def read_payload(path, stale_seconds):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        updated = float(payload.get("updated_at", 0))
        stale = updated == 0 or time.time() - updated > stale_seconds
        return payload, stale
    except (OSError, ValueError, TypeError):
        return {}, True


def ssvep_payload(live_path=SSVEP_LIVE_PATH, replay_path=SSVEP_REPLAY_PATH):
    live, stale = read_payload(live_path, 2)
    age = time.monotonic() - float(live.get('updated_monotonic', 0))
    lag = float(live.get('input_age_seconds', 0))
    stale = bool(stale or not math.isfinite(age+lag) or age < 0 or lag < 0
                 or age+lag > .75 or live.get('source') != 'live')
    if stale:
        live = {'state':'no_data', 'valid':False, 'source':'live',
                'frequency_hz':None, 'control_enabled':False, 'reason':'stale_or_no_input'}
    else:
        live = dict(live, control_enabled=False)
        if live.get('state') != 'candidate_only' or not live.get('valid'):
            live.update(valid=False, frequency_hz=None, scores=None, target_index=None, margin=None)
    replay, _ = read_payload(replay_path, 2)
    return {'live':live, 'stale':stale, 'replay':replay if replay.get('source') == 'replay' else {}}


class TelemetryResponseCache:
    """Reuse producer JSON bytes; never re-encode thousands of waveform floats."""
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.key = None
        self.raw = b'{}'
        self.updated = 0.
        self.input_lag_seconds = 0.

    def _freshness(self):
        age = max(0., time.time() - self.updated) if self.updated else None
        data_age = None if age is None else age + self.input_lag_seconds
        return {'stale':data_age is None or data_age > 3,
                'snapshot_age_seconds':age, 'data_age_seconds':data_age}

    def freshness(self):
        self.body()
        with self.lock:
            return self._freshness()

    def body(self):
        with self.lock:
            try:
                stat = self.path.stat()
                key = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
                if key != self.key:
                    raw = self.path.read_bytes()
                    payload = json.loads(raw)
                    updated = float(payload.get('updated_at', 0))
                    if not math.isfinite(updated):
                        raise ValueError('Nonfinite telemetry time')
                    runtime = payload.get('runtime') or {}
                    lag = float(runtime.get('input_age_at_snapshot_ms', runtime.get('reader_queue_delay_ms', 0.))) / 1000.
                    if not math.isfinite(lag) or lag < 0:
                        raise ValueError('Invalid input age')
                    self.input_lag_seconds = lag
                    self.raw, self.updated, self.key = raw, updated, key
                suffix = json.dumps(self._freshness(), separators=(',', ':')).encode('utf-8')
                return b'{"telemetry":' + self.raw + b',' + suffix[1:]
            except (OSError, ValueError, TypeError, AttributeError):
                self.key, self.raw, self.updated = None, b'{}', 0.
                self.input_lag_seconds = 0.
                return b'{"telemetry":{},"stale":true}'


def make_handler(path, telemetry_path, stale_seconds,
                 record_command_path=CONTROL_PATH, record_status_path=STATUS_PATH,
                 ssvep_live_path=SSVEP_LIVE_PATH, ssvep_replay_path=SSVEP_REPLAY_PATH,
                 cued_session=None, mi_bridge=None):
    recording_lock = threading.Lock()
    telemetry_cache = TelemetryResponseCache(telemetry_path)
    cue = cued_session if cued_session is not None else SSVEPCueBridge()
    mi = mi_bridge if mi_bridge is not None else MIWebBridge()

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path not in ("/api/recording", "/api/ssvep-cue", "/api/ssvep-free", "/api/mi-cue"):
                self.send_json(404, {"error": "unknown endpoint"})
                return
            origin = self.headers.get("Origin")
            if ((self.path in ("/api/ssvep-cue", "/api/ssvep-free", "/api/mi-cue") and origin != "http://" + self.headers.get("Host", ""))
                    or (origin and origin != "http://" + self.headers.get("Host", ""))):
                self.send_json(403, {"error": "origin mismatch"})
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.send_json(415, {"error": "JSON body required"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("request body must be 1–4096 bytes")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError("JSON object required")
                if self.path == '/api/mi-cue':
                    status, payload = mi.request(request)
                    self.send_json(status, payload)
                    return
                if self.path == "/api/ssvep-cue":
                    self.send_json(200, cue.command(request))
                    return
                if self.path == "/api/ssvep-free":
                    self.send_json(200, cue.free_command(request))
                    return
                with recording_lock, recording_command_lock(record_command_path):
                    state, stale = read_payload(record_status_path, 3)
                    pending_command = read_json(record_command_path)
                    if (pending_command.get("id")
                            and pending_command["id"] != state.get("last_command")):
                        self.send_json(409, {"error": "上一个记录命令仍在等待确认"})
                        return
                    action = request.get("action")
                    if action == "start":
                        telemetry, telemetry_stale = read_payload(telemetry_path, 3)
                        if not command_ok("systemctl", "is-active", "--quiet", "guardianloop-cyton.service") or telemetry_stale or not telemetry.get("real"):
                            self.send_json(409, {"error": "真实 Cyton 数据未在持续接收"})
                            return
                        if state.get("state") == "recording":
                            self.send_json(409, {"error": "已有实验正在记录"})
                            return
                        participant = request.get("participant_id", "")
                        phase = request.get("phase")
                        condition = request.get("condition")
                        note = request.get("stimulus_note", "")
                        if not isinstance(participant, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", participant):
                            raise ValueError("匿名编号仅能使用 1–24 个字母、数字、_ 或 -")
                        if phase not in ("calibration", "evaluation") or condition not in CONDITIONS:
                            raise ValueError("用途或测试条件无效")
                        if not isinstance(note, str) or len(note) > 120:
                            raise ValueError("素材说明过长")
                        command = {"id": secrets.token_hex(8), "trial_id": secrets.token_hex(8),
                                   "action": "start", "participant_id": participant,
                                   "phase": phase, "condition": condition,
                                   "stimulus_note": note, "browser_time_ms": request.get("browser_time_ms")}
                    elif action == "stop":
                        if stale or state.get("state") != "recording" or state.get("trial_id") != request.get("trial_id"):
                            self.send_json(409, {"error": "没有匹配的活动记录"})
                            return
                        rating = request.get("self_report")
                        if not isinstance(rating, dict) or rating.get("felt_label") not in (*CONDITIONS, "uncertain"):
                            raise ValueError("请选择实际感受")
                        if any(type(rating.get(key)) is not int or not 1 <= rating[key] <= 5
                               for key in ("valence", "arousal")):
                            raise ValueError("愉悦和激活程度均须为 1–5")
                        command = {"id": secrets.token_hex(8), "action": "stop",
                                   "trial_id": state["trial_id"],
                                   "self_report": {"felt_label": rating["felt_label"],
                                                   "valence": rating["valence"],
                                                   "arousal": rating["arousal"]},
                                   "browser_time_ms": request.get("browser_time_ms")}
                    else:
                        raise ValueError("未知记录操作")
                    atomic_json(record_command_path, command)
                self.send_json(202, {"accepted": True, "command_id": command["id"]})
            except (ValueError, TypeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except OSError as exc:
                self.send_json(500, {"error": "写入板卡记录命令失败: " + str(exc)})

        def do_GET(self):
            if self.path == "/" or self.path == "/index.html":
                body = PAGE.encode("utf-8")
                content_type = "text/html; charset=utf-8"
            elif self.path in ("/mobile", "/mobile/", "/mobile.js"):
                name = 'mobile.js' if self.path == '/mobile.js' else 'mobile.html'
                body = Path(__file__).with_name(name).read_bytes()
                content_type = ('text/javascript; charset=utf-8' if name.endswith('.js')
                                else 'text/html; charset=utf-8')
            elif self.path == "/ssvep-cued":
                body = SSVEP_CUED_PAGE.encode("utf-8")
                content_type = "text/html; charset=utf-8"
            elif self.path == "/ssvep-free":
                body = Path(__file__).with_name('ssvep_free.html').read_bytes()
                content_type = "text/html; charset=utf-8"
            elif self.path == '/mi-cued':
                body = mi.page()
                content_type = 'text/html; charset=utf-8'
            elif self.path == '/api/mi-cue':
                status, payload = mi.request()
                self.send_json(status, payload)
                return
            elif self.path == "/api/status":
                fatigue, stale = read_payload(path, stale_seconds)
                if not fatigue.get('offline'):
                    telemetry_stale = telemetry_cache.freshness()['stale']
                    if stale or telemetry_stale:
                        reason = 'STALE_EEG' if telemetry_stale else 'STALE_STATUS'
                        stale = True
                        fatigue = dict(fatigue, valid=False, score=None, raw_ratio=None,
                                       level='unknown', state='invalid', reason=reason,
                                       emotion={'valid':False, 'state':reason.lower()})
                body = json.dumps({"fatigue": fatigue, "stale": stale,
                                   "system": system_status(), "server_time": int(time.time())},
                                  ensure_ascii=False, allow_nan=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif self.path == "/api/seed-shadow":
                live, stale = read_payload(LIVE_PATH, 6)
                stale = stale or telemetry_cache.freshness()['stale']
                replay, _ = read_payload(REPLAY_PATH, 6)
                if stale:
                    live = {"state":"no_data", "valid":False, "source":"live"}
                body = json.dumps({"live":live,"stale":stale,"replay":replay}, ensure_ascii=False, allow_nan=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif self.path == "/api/ssvep-shadow":
                body = json.dumps(ssvep_payload(ssvep_live_path, ssvep_replay_path), ensure_ascii=False, allow_nan=False).encode('utf-8')
                content_type = 'application/json; charset=utf-8'
            elif self.path == "/api/ssvep-cue":
                body = json.dumps(cue.snapshot(), ensure_ascii=False, allow_nan=False).encode('utf-8')
                content_type = 'application/json; charset=utf-8'
            elif self.path == "/api/ssvep-free":
                body = json.dumps(cue.free_snapshot(), ensure_ascii=False, allow_nan=False).encode('utf-8')
                content_type = 'application/json; charset=utf-8'
            elif self.path == "/api/telemetry":
                body = telemetry_cache.body()
                content_type = "application/json; charset=utf-8"
            elif self.path == "/api/recording":
                recording, stale = read_payload(record_status_path, 3)
                body = json.dumps({"recording": recording, "stale": stale,
                                   "system": {"acquisition_active": command_ok(
                                       "systemctl", "is-active", "--quiet",
                                       "guardianloop-cyton.service")}},
                                  ensure_ascii=False, allow_nan=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif self.path == "/healthz":
                body = json.dumps({"ok": True, "system": system_status()},
                                  ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9102)
    parser.add_argument("--status-file", default="/run/guardianloop/status.json")
    parser.add_argument("--telemetry-file", default="/run/guardianloop/telemetry.json")
    parser.add_argument("--stale-seconds", type=int, default=20)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port),
                                 make_handler(Path(args.status_file), Path(args.telemetry_file),
                                              args.stale_seconds))
    print(f"GUARDIANLOOP_WEB_READY: http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
