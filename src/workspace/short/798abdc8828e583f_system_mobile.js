'use strict';
const key=location.hash.slice(1),$=id=>document.getElementById(id);
$('brainDetails').href='http://'+location.hostname+':9102/mobile';
let filter='all',busy=false,lastSignature='',current=null,connectionFailed=false;
let phoneVideoUrl=null,lastCommandId=null,lastManualId=null;
let manualCommand=null,manualGeneration=0,heartbeatBusy=false,manualEpoch=null;
function closeWatch(){const v=$('phoneVideo');v.pause();v.removeAttribute('src');v.load();$('phoneWatch').hidden=true;$('phoneStatus').textContent='';if(phoneVideoUrl)URL.revokeObjectURL(phoneVideoUrl);phoneVideoUrl=null;}
async function watch(v){try{if(v.bytes>134217728)throw Error('手机页观看限128MB；大视频可用HDMI播放或下载。');$('error').textContent='正在读取手机播放副本…';const r=await fetch('/download/'+encodeURIComponent(v.id),{headers:{'X-Media-Key':key}});if(!r.ok)throw Error('读取视频失败');const length=Number(r.headers.get('Content-Length'));if(!length||length>134217728)throw Error('视频大小不满足手机页观看限制，请使用HDMI播放或下载。');const blob=await r.blob();closeWatch();phoneVideoUrl=URL.createObjectURL(blob);$('phoneVideo').src=phoneVideoUrl;$('phoneVideo').muted=true;$('phoneTitle').textContent=v.name;$('phoneWatch').hidden=false;$('phoneStatus').textContent='正在读取视频信息；默认静音。';$('error').textContent='';}catch(e){$('error').textContent=e.message;}}
$('phoneVideo').onloadedmetadata=()=>{$('phoneStatus').textContent='视频已就绪，点击播放器播放；默认静音。';};
$('phoneVideo').onerror=()=>{if(phoneVideoUrl)$('phoneStatus').textContent='当前浏览器无法播放此视频；可保存到手机后用系统播放器打开，或选择HDMI播放。';};
$('closeWatch').onclick=closeWatch;
async function api(method,body,options={}){const r=await fetch('/api/player',{method,headers:{'X-Media-Key':key,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,cache:'no-store',...options});const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d;}
function haltManual(){manualCommand=null;manualGeneration++;return api('POST',{action:'wheelchair_manual',value:'stop'},{keepalive:true}).catch(()=>{});}
async function manualApi(body){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),600);try{return await api('POST',body,{signal:controller.signal});}finally{clearTimeout(timer);}}
async function action(action,more={}){if(action==='force_stop')haltManual();try{$('error').textContent='';const result=await api('POST',{action,...more});if(result.not_yet_confirmed){lastCommandId=result.command_id;$('commandReceipt').textContent='指令已排队，尚未确认执行';}await refresh();}catch(e){$('error').textContent=e.message;}}
async function manualDirection(value){const generation=++manualGeneration;manualCommand=null;try{const remote=current?.wheelchair?.motor_gpio_enabled===true;if(document.hidden&&!['stop','ssvep'].includes(value))throw Error('请保持控制页面在前台');const result=await manualApi({action:'wheelchair_manual',value:remote&&!['stop','ssvep'].includes(value)?{direction:value,epoch:manualEpoch}:value});if(generation!==manualGeneration)return;lastManualId=result.command_id;if(result.control_epoch)manualEpoch=result.control_epoch;if(remote&&!['stop','ssvep'].includes(value))manualCommand=result.command_id;$('manualReceipt').textContent='手机指令已提交，等待 ESP32 回执；尚未确认动作。';await refresh();}catch(e){if(generation===manualGeneration){haltManual();$('manualReceipt').textContent='指令未确认，已撤销持续控制：'+e.message;}}}
async function manualHeartbeat(){if(!manualCommand||heartbeatBusy)return;if(document.hidden){haltManual();return;}const id=manualCommand,generation=manualGeneration;heartbeatBusy=true;try{await manualApi({action:'wheelchair_heartbeat',value:id});}catch(e){if(generation===manualGeneration){haltManual();$('manualReceipt').textContent='心跳中断，已撤销持续控制；恢复连接后需重新点方向。';}}finally{heartbeatBusy=false;}}
function button(label,fn,disabled=false){const b=document.createElement('button');b.textContent=label;b.disabled=disabled;b.onclick=fn;return b;}
async function download(v){try{$('error').textContent='下载中，请保持页面前台…';const r=await fetch('/download/'+encodeURIComponent(v.id),{headers:{'X-Media-Key':key}});if(!r.ok)throw Error('下载失败');const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=v.name.replace(/\.mp4$/i,'')+'.mp4';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);$('error').textContent='已交给手机浏览器保存；请查看下载列表，是否写入手机由浏览器确认。';}catch(e){$('error').textContent=e.message;}}
function render(s){current=s;const brain=s.brain||{},f=brain.fatigue||{},e=brain.emotion||{};
 if(s.wheelchair_control_epoch)manualEpoch=s.wheelchair_control_epoch;
 $('sessionMode').textContent=s.user_controlled?'持续运行：无自动到期，关闭由你决定；单轮闪烁仍限30秒，断流与异常仍撤销方向。':'限时会话：到期自动恢复正式PL。';
 const fatigueNames={0:'正常',1:'轻度',2:'严重',normal:'正常',mild:'轻度',severe:'严重'};
 const emotionNames={boring:'中性情绪',calm:'中性情绪',horror:'负向情绪',funny:'正向情绪'};
 $('brain').textContent=(brain.state==='live'?'实时接口在线':'未收到可信脑电／等待Cyton')+'；心情参考（模型估计）：'+(e.valid===true?(emotionNames[e.class_name||e.label]||'无可信结果'):'无可信结果')+'；疲劳：'+(f.valid===true?(fatigueNames[f.level]||'未知'):'无可信结果')+'；校准 '+(f.calibration_current||0)+'/'+(f.calibration_total||15)+(f.calibration_retained&&f.valid!==true?'（基线已保留，等待新鲜连续数据，不需重新校准）':'');
 const p=s.player||{},system=p.system||{},eye=system.eye||{};$('hdmi').textContent='HDMI：'+(p.state||'未启动')+' · 已呈现新帧 '+(p.frame||0)+(p.error?'；'+p.error:'');
 const audio=p.audio,volume=$('audioVolume');volume.disabled=!audio||!p.audio_output;
 if(audio){
  if(document.activeElement!==volume)volume.value=audio.volume_percent;
  $('audioVolumeValue').textContent=volume.value+'%';
  const phases={idle:'待播放',starting:'正在启动',feeding:'正在送出音频',stopped:'已停止',completed:'已播完',error:'播放出错'};
  $('audioStatus').textContent='HDMI 音频已启用；'+(phases[audio.player?.phase]||'等待状态')+'；数字音量 '+audio.volume_percent+'%'+(audio.player?.error?'；'+audio.player.error:'');
 }else $('audioStatus').textContent='此会话尚未启用 HDMI 音频；不会把静音旧版显示为有声。';
 const wear=s.wear||{};
 $('wearStatus').textContent='佩戴会话：'+(wear.reason||'等待采集服务')+'；不会根据断流自动清除基线。';
 $('wearNew').disabled=!wear.id;$('wearContinue').disabled=!wear.id;
 $('fatigueWarning').hidden=!system.alerts?.fatigue;
 $('fatigueReason').textContent=system.alerts?.fatigue?system.fatigue_ack_reason:'';
 $('ackFatigue').disabled=system.fatigue_ack_ready!==true;
 $('armDirection').disabled=system.page!=='drive'||system.reading||!!system.alerts?.fatigue;
 $('hdmiCandidate').hidden=s.hdmi_candidate_available!==true;
 const preflight=s.hdmi_preflight||{};
 $('preflight').textContent='启动预检：'+(preflight.reason||'等待板端预检');
 $('startHdmi').disabled=s.hdmi_candidate_available!==true||preflight.ready!==true||!$('hdmiConsent').checked||($('hdmiRecord').checked&&preflight.raw_recording_supported!==true);
 const receipt=p.command_receipt;
 if(receipt&&(!lastCommandId||receipt.id===lastCommandId))$('commandReceipt').textContent=(receipt.state==='rejected'?'未执行：':receipt.state==='preparing'?'准备中：':'执行回执：')+receipt.reason;
 const timing=system.hdmi_stimulus||{};
 $('hdmiTiming').textContent=timing.error?'四角已停止：'+timing.error:timing.preparing?'等待同步录制首批样本；尚未闪烁':timing.active?'四角运行中；'+(timing.timing?.ready?'扫描证据合格（非光学实测）':'正在检查扫描证据')+'；'+(timing.decision_reason||'等待识别窗口')+(timing.raw_recording?'；原始录制 '+timing.raw_recording.trial_id:'；未录制原始脑电'):s.auto_hdmi_on_drive?'进入方向页自动闪烁；无有效脑电时不产生方向；注视中央框返回主页':'四角未启动；不会自动闪烁';
 $('stopReceipt').textContent=system.force_stopped?'已收到停止回执：方向停止，已返回主页；需重新进入并启用。':'当前方向：'+(system.direction||'无活动会话')+'；'+(system.last_action||'等待显示会话');
 const votes=timing.votes;
 const selection=votes?.mode==='window_plurality_test_only'?(votes.selected_hz?'投票选中 '+votes.selected_hz+' Hz（本段 '+Math.round(votes.plurality_share*100)+'%，仅测试）':'等待有效窗口投票'):(system.selected_frequency?system.selected_frequency+' Hz 可信候选（未验证驾驶）':'未选中／等待可信证据');
 $('directionStatus').textContent=system.page==='drive'?'SSVEP：'+selection+'；'+(system.direction_idle_enabled===false?'测试期：15秒自动退出已关闭':system.direction_idle_remaining_s==null?'准备阶段，15秒计时尚未开始':Math.ceil(system.direction_idle_remaining_s)+'秒无新选择后返回主页'):'';
 const eyeDevice=s.eye_device||{},eyeUnavailable=['maintenance','missing','unsupported'].includes(eyeDevice.state);
 $('eye').textContent='眼控：'+(eyeDevice.state==='maintenance'?'设备维护模式 0102，暂不能采样':eyeDevice.state==='missing'?'USB 未识别':eye.state||'未启动')+(eye.valid?' · 有效眼位':' · 尚无可信选择');
 const displayActive=['playing','menu','buffering','paused','waiting_runtime'].includes(p.state);
 $('startDisplay').textContent=displayActive?'显示已运行／返回主页':'启动／恢复 HDMI 主页';
 $('homeButton').disabled=!displayActive;
 $('startEye').disabled=!displayActive||eyeUnavailable||['connecting','prepare','collect','compute','verification'].includes(eye.state);
 $('startEye').textContent=eye.state==='positioning'?'位置已就绪，开始三点标定':eye.state==='failed'?'重新连接眼控并定位':eye.state==='selection'?'重新标定（当前已完成）':'开始眼控定位与三点标定';
 $('eyeTracking').textContent=(eye.tracking||[]).join('；')+(eye.recovery_detail?'；'+eye.recovery_detail:'');
 const wc=s.wheelchair||{},motorTest=wc.motor_gpio_enabled===true,wcNames={offline:'离线／尚未接入 Z15 热点',unavailable:'发送服务未运行或状态过期',preparing:'先停止并等待方向切换间隔',permit_required:motorTest?'控制许可失效，请重新点方向':'已接入，等待 ESP32 本机台架许可',sent:motorTest?'ESP32 已受理电机方向指令':'ESP32 已接收虚拟方向',stopped:'停止请求已提交（不是车轮反馈）'},directions={stop:'停止',forward:'前进',backward:'后退',left:'左转',right:'右转'};
 const outputNote=['offline','unavailable'].includes(wc.state)?'接收端不可达，当前 GPIO 状态未核实':motorTest?'电机 GPIO 已启用：仅限无人架空测试，尚未验收载人行驶':'电机 GPIO 禁用';
 $('wheelchair').textContent='轮椅 ESP32：'+(wcNames[wc.state]||'等待发送接口')+'；请求方向：'+(directions[wc.direction]||'停止')+'；'+outputNote+'，速度仍为虚拟档位。';
 $('motorProfile').textContent=motorTest?'持续遥控：点方向后持续执行，点停止才停，无固定行驶时长。请保持此页面在前台；断网、退出或程序异常时撤销驱动，重连不自动恢复。首次更新后须无人架空验证，独立断电开关保持可用。':'当前是禁用电机 GPIO 的台架版，按钮不驱动车轮。';
 if(manualCommand&&wc.command_id===manualCommand&&['offline','unavailable','stopped','permit_required'].includes(wc.state))haltManual();
 document.querySelectorAll('[data-wheelchair]').forEach(b=>{b.disabled=connectionFailed||(['offline','unavailable'].includes(wc.state)&&!['stop','ssvep'].includes(b.dataset.wheelchair));});
 if(wc.command_id&&(!lastManualId||wc.command_id===lastManualId))$('manualReceipt').textContent='手机遥控回执：'+(wcNames[wc.state]||wc.state)+'；'+(directions[wc.direction]||'停止')+'；'+(wc.reason==='local_permit_required'?'ESP32 本机尚未许可，未执行方向':wc.reason||'')+'；'+(motorTest?'当前为实际输出测试版，受理不是车轮反馈':'当前电机禁用')+'。';
 $('page').textContent=(system.title||'点击视频的“HDMI播放”启动')+'；虚拟档位 '+(system.speed_level||1)+'/3；方向 '+(system.direction||'stop');
 const choices=$('choices');choices.replaceChildren();(system.labels||[]).forEach((label,i)=>{if(label)choices.append(button(label,()=>action('choose',{value:i}),system.reading||(system.page==='fatigue_alert'&&i===1&&!system.fatigue_ack_ready)));});
 const videos=s.videos||[],signature=JSON.stringify([videos,filter,p.state]);if(signature===lastSignature)return;lastSignature=signature;
 const list=$('videos');list.replaceChildren();for(const v of videos.filter(v=>filter==='all'||v.rating===filter)){
  const card=document.createElement('div');card.className='video';const title=document.createElement('p');title.textContent=v.name+' · '+(v.rating||'未评价');card.append(title);
  const row=document.createElement('div');row.className='row';row.append(button('HDMI播放',()=>action(['playing','menu','buffering','paused'].includes(p.state)?'video':'play',{id:v.id}),!v.prepared),button('手机观看',()=>watch(v),!v.downloadable),button('点赞收藏',()=>action('rate',{id:v.id,value:'好'})),button('厌倦',()=>action('rate',{id:v.id,value:'厌倦'})),button('保存到手机',()=>download(v),!v.downloadable));
  if(!v.prepared)row.append(button('准备显示缓存',()=>action('prepare',{id:v.id})));card.append(row);list.append(card);
 }if(!list.children.length)list.textContent='当前列表暂无视频。';
}
async function refresh(){if(busy)return;busy=true;try{render(await api('GET'));if(connectionFailed)$('error').textContent='';connectionFailed=false;}catch(e){if(manualCommand)haltManual();connectionFailed=true;$('error').textContent=e.message;$('brain').textContent='连接中断；不沿用旧脑电结果';$('eye').textContent='眼控状态不可用';$('eyeTracking').textContent='';$('startEye').disabled=true;$('homeButton').disabled=true;$('hdmi').textContent='HDMI状态不可用';$('audioVolume').disabled=true;$('audioStatus').textContent='连接中断，无法确认屏幕音频状态。';$('wheelchair').textContent='轮椅状态不可用；不能确认指令送达或停车。';document.querySelectorAll('[data-wheelchair]').forEach(b=>{b.disabled=!['stop','ssvep'].includes(b.dataset.wheelchair);});$('manualReceipt').textContent='连接中断，不能确认 ESP32 已执行或车轮已停。';$('page').textContent='连接失效；旧方向和档位不作为当前状态';$('stopReceipt').textContent='连接中断，不能确认停止已执行；不要继续方向操作。';$('directionStatus').textContent='';$('ackFatigue').disabled=true;$('armDirection').disabled=true;$('startHdmi').disabled=true;$('choices').replaceChildren();}finally{busy=false;}}
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>action(b.dataset.action));document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;lastSignature='';if(current)render(current);});
$('audioVolume').oninput=()=>{$('audioVolumeValue').textContent=$('audioVolume').value+'%';};
$('audioVolume').onchange=()=>action('volume',{value:Number($('audioVolume').value)});
document.querySelectorAll('[data-wheelchair]').forEach(b=>b.onclick=()=>manualDirection(b.dataset.wheelchair));
document.addEventListener('visibilitychange',()=>{if(document.hidden&&(manualCommand||current?.wheelchair?.control_mode==='manual'))haltManual();});
window.addEventListener('pagehide',()=>{if(manualCommand||current?.wheelchair?.control_mode==='manual')haltManual();});
$('ackFatigue').onclick=()=>action('ack',{value:'fatigue'});
 $('wearContinue').onclick=()=>action('wear_continue');
 $('wearNew').onclick=()=>{if(current?.wear?.id&&confirm('只有换人、重新佩戴或改变电极位置时才开始新佩戴。这会清除当前校准基线，确认吗？'))action('wear_new',{value:{confirm:true,expected_id:current.wear.id}});};
 $('startHdmi').onclick=()=>{if($('hdmiConsent').checked)action('hdmi_start',{value:{consent:true,record:$('hdmiRecord').checked===true}});};
 $('hdmiConsent').onchange=()=>{if(current&&!connectionFailed)render(current);};
 $('hdmiRecord').onchange=()=>{if(current&&!connectionFailed)render(current);};
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!event.repeat){event.preventDefault();action('force_stop');}});
async function crcFile(file){const table=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let i=0;i<8;i++)c=c&1?0xedb88320^(c>>>1):c>>>1;table[n]=c>>>0;}let crc=0xffffffff;for(let o=0;o<file.size;o+=524288){const bytes=new Uint8Array(await file.slice(o,o+524288).arrayBuffer());for(const b of bytes)crc=table[(crc^b)&255]^(crc>>>8);}return ((crc^0xffffffff)>>>0).toString(16).padStart(8,'0');}
$('upload').onclick=async()=>{const file=$('file').files[0];if(!file||!file.name.toLowerCase().endsWith('.mp4')||file.size>536870912){$('error').textContent='请选择不超过512MB的MP4';return;}$('upload').disabled=true;try{$('uploadStatus').textContent='计算校验码…';const crc=await crcFile(file);await new Promise((resolve,reject)=>{const x=new XMLHttpRequest();x.open('POST','/upload');x.timeout=600000;x.setRequestHeader('X-Media-Key',key);x.setRequestHeader('X-File-Name',encodeURIComponent(file.name));x.setRequestHeader('X-File-CRC32',crc);x.setRequestHeader('Content-Type','video/mp4');x.upload.onprogress=e=>{if(e.lengthComputable)$('progress').value=100*e.loaded/e.total;};x.onload=()=>{if(x.status===201)resolve();else reject(Error('上传未通过：'+x.status));};x.onerror=()=>reject(Error('上传连接中断'));x.ontimeout=()=>reject(Error('上传超时'));x.send(file);});$('uploadStatus').textContent='原文件上传校验完成，可在视频库准备显示缓存。';lastSignature='';await refresh();}catch(e){$('error').textContent=e.message;}finally{$('upload').disabled=false;}};
refresh();setInterval(refresh,1000);setInterval(manualHeartbeat,200);
