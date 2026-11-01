'use strict';
const mobileEl = id => document.getElementById(id);
const CAP = ['F3','F4','C3','C4','T7','T8','O1','O2'];
const own = (map, key) => Object.prototype.hasOwnProperty.call(map,key);
const emotionLabels = {boring:'中性情绪',calm:'中性情绪',horror:'负向情绪',funny:'正向情绪'};
const fatigueLabels = {normal:'正常区间',mild:'轻度疲劳候选',severe:'较高疲劳候选'};
const qualityReasons = {clipping:'削顶',flatline:'平线／疑似断线',amplitude:'幅度偏大',mains:'工频偏高',
  high_frequency:'高频干扰',step:'突变',transport:'传输不完整',not_calibrated:'通道未校准',adaptive_outlier:'偏离本次基线'};
const interruptions = {STREAM_IDLE:'接收断流',STREAM_TIMING_GAP:'收包间隔异常',MALFORMED_STREAM:'收包格式异常',
  SEQUENCE_GAP:'收包序号缺口',WAITING_FOR_CYTON:'等待 Cyton 开机',STREAM_STARTING:'采集启动',
  PROCESSING_BACKLOG:'处理积压',PRIMARY_WORKER_BACKLOG:'主计算处理积压',PRIMARY_WORKER_RESULT_STALE:'计算结果过期',
  PRIMARY_WORKER_QUEUE_FULL:'主计算队列已满',STALE_EEG:'脑电已过期',STALE_STATUS:'监测状态已过期',
  SERVICE_STOPPED_OR_STREAM_TIMEOUT:'采集停止或超时'};
const states = {sqi_calibrating:'信号校准中',collecting_12s:'收集连续 12 秒窗口',
  insufficient_signal:'信号质量不足',channel_map_mismatch:'通道不一致',packet_gap_12s:'窗口存在丢包',
  CALIBRATING:'校准中',calibrating:'校准中',warming:'热身中',warmup:'热身中',
  INVALID:'信号不可用',invalid:'信号不可用',no_data:'无及时数据',signal_invalid:'质量不合格',
  candidate_only:'仅供观察',idle:'等待手动提示',disabled:'板端未启用',rejected:'当前候选已拒绝',
  active:'提示试次进行中',ready:'输入已热身'};
let generation=0, polling=false, timer=null;
const pending = new Set(), received = {primary:null,ssvep:null,mi:null};
function show(id, value, detail) {mobileEl(id).textContent=value;mobileEl(id+'Detail').textContent=detail;}
function clearTask(task, reason='未收到及时状态，已隐藏旧结果') {
  received[task]=null;
  if(task==='primary') {
    show('emotion','暂无有效结果',reason);show('fatigue','暂无有效结果',reason);
    mobileEl('quality').textContent=reason;mobileEl('channels').replaceChildren();
  } else show(task,'暂无有效结果',reason);
}
function clearAll(reason) {for(const task of Object.keys(received))clearTask(task,reason);}
function sameCap(value) {return Array.isArray(value)&&value.join(',')===CAP.join(',');}
function renderPrimary(data) {
  const f=data.fatigue||{}, sys=data.system||{};
  mobileEl('device').textContent='采集服务：'+(sys.acquisition_active?'运行':'未运行')+' · 接收器：'+(sys.receiver_present?'已连接':'未确认')+' · HDMI：'+(sys.hdmi?.ready?'正在更新':'未就绪，四频测试前请检查');
  const startup=sys.startup||{};
  mobileEl('release').textContent='板端自检：'+(startup.state==='ready'?'通过':'尚未通过')+' · '+(startup.release_id||'版本未知')+(startup.arm_update_pending_boot?' · 网页已更新，新清单将在下次开机核对':'');
  const real=!data.stale&&!f.offline&&['bci','cyton_usb'].includes(f.source)&&sameCap(f.channel_map);
  if(!real) {clearTask('primary',f.offline?'离线回放不作为当前佩戴者结果':f.calibration_retained?
    (interruptions[f.reason]||'输入中断')+'；校准 '+(f.calibration_current??0)+'/'+(f.calibration_total??15)+' 已保留，不是重新校准；旧结果已撤销':'无新鲜固定八通道输入，旧结果已隐藏');return;}
  const q=f.sqi||{}, current=f.calibration_current??0, total=f.calibration_total??15;
  mobileEl('quality').textContent='滤波后质量：'+({good:'良好',degraded:'降级',invalid:'不可用'}[q.state]||'待检查')+' · 校准 '+current+'/'+total;
  mobileEl('channels').replaceChildren();
  for(let index=0;index<CAP.length;index++) {
    const item=(q.channels||[])[index]||{}, box=document.createElement('div'), label=document.createElement('b'), hint=document.createElement('small');
    box.className='channel'+(item.usable===true?' good':item.usable===false?' bad':'');
    label.textContent=CAP[index];hint.textContent=item.usable===true?'可用':item.usable===false?'降权':'待测';
    if(item.usable===false)hint.textContent+=' · '+(item.reasons||[]).map(reason=>qualityReasons[reason]||reason).join('／');
    box.append(label,hint);mobileEl('channels').append(box);
  }
  const em=f.emotion||{};
  if(em.valid===true&&own(emotionLabels,em.label))
    show('emotion',emotionLabels[em.label],'模型估计；由原始四类结果归并，个人真实情绪准确率尚未验证。');
  else show('emotion',states[em.state]||'暂无有效结果','未通过校准或质量门控时不显示分类。');
  if(f.valid===true&&own(fatigueLabels,f.level))
    show('fatigue',fatigueLabels[f.level],'T7/T8/O1/O2 的 ARM 估计；非临床诊断。');
  else show('fatigue',f.calibration_retained&&f.state==='invalid'?'数据恢复中':states[f.state]||'暂无有效结果',
    (f.calibration_retained?(interruptions[f.reason]||'连续窗口恢复中')+'；校准 '+current+'/'+total+' 已保留，不是重新校准；等待新鲜完整窗口与质量检查。':'校准 '+current+'/'+total+'；需连续且质量合格的输入。'));
}
function renderSSVEP(data) {
  const v=data.live||{};
  if(data.stale||v.source!=='live'||v.valid!==true||v.state!=='candidate_only'||![8,10,12,14].includes(v.frequency_hz)) {
    show('ssvep',states[v.state]||'无可信频率候选','无选择结论；不能把无数据当作休息。');return;
  }
  show('ssvep',v.frequency_hz+' Hz 候选','被动频率观察，不代表已识别你的注视或控制意图。');
}
function renderMI(data) {
  if(data.source!=='live'||!sameCap(data.channels)||data.control_enabled!==false) {
    clearTask('mi','输入来源或安全标识不符，已隐藏结果');return;
  }
  const result=data.result, active=data.state==='active';
  if(active&&data.id&&data.input_state==='ready'&&data.quality?.ready===true&&result?.source==='live'&&result.control_enabled===false&&['left','right'].includes(result.label))
    show('mi',(result.label==='left'?'左手':'右手')+'候选','当前提示试次结果，不是自由异步脑控。');
  else show('mi',states[data.state]||'暂无有效结果','输入：'+(states[data.input_state]||'待检查')+' · '+(data.quality?.ready===false?'质量未通过':'在交互页主动开始提示'));
}
const renderers={primary:renderPrimary,ssvep:renderSSVEP,mi:renderMI};
const endpoints={primary:'/api/status',ssvep:'/api/ssvep-shadow',mi:'/api/mi-cue'};
function updateConnection() {
  const live=received.primary!==null&&performance.now()-received.primary<=3000;
  mobileEl('connection').textContent=document.hidden?'后台暂停':live?'Z15 已连接':'连接中断或等待状态';
  if(!live)mobileEl('device').textContent='未收到及时采集状态，不能确认接收器或采集服务。';
}
async function fetchTask(task, token) {
  const controller=new AbortController();pending.add(controller);
  const deadline=setTimeout(()=>controller.abort(),1800);
  try {
    const response=await fetch(endpoints[task],{cache:'no-store',signal:controller.signal});
    if(!response.ok)throw Error('HTTP '+response.status);
    const data=await response.json();
    if(token!==generation||document.hidden)return;
    if(!data||typeof data!=='object'||Array.isArray(data))throw Error('状态格式不符');
    renderers[task](data);received[task]=performance.now();
    if(task==='primary')mobileEl('lastUpdate').textContent='状态接收于 '+new Date().toLocaleTimeString()+' · 非脑电采样时间';
  } catch(error) {
    if(token===generation&&!document.hidden)clearTask(task,'网络或接口不可用，已隐藏旧结果');
  } finally {clearTimeout(deadline);pending.delete(controller);}
}
async function pollMobile() {
  if(polling||document.hidden)return;
  clearTimeout(timer);polling=true;const token=generation;
  try {await Promise.all(Object.keys(endpoints).map(task=>fetchTask(task,token)));}
  finally {polling=false;updateConnection();if(!document.hidden)timer=setTimeout(pollMobile,1000);}
}
function suspendMobile(reason) {
  generation++;clearTimeout(timer);for(const controller of pending)controller.abort();
  clearAll(reason);mobileEl('lastUpdate').textContent='实时显示已暂停';updateConnection();
}
document.addEventListener('visibilitychange',()=>{
  if(document.hidden)suspendMobile('后台或锁屏：暂停监控，旧结果已隐藏');else pollMobile();
});
window.addEventListener('pagehide',()=>suspendMobile('页面离开，旧结果已隐藏'));
window.addEventListener('pageshow',()=>{if(!document.hidden)pollMobile();});
window.addEventListener('offline',()=>suspendMobile('手机网络断开，旧结果已隐藏'));
window.addEventListener('online',pollMobile);
mobileEl('refresh').onclick=pollMobile;
setInterval(()=>{
  for(const task of Object.keys(received))if(received[task]!==null&&performance.now()-received[task]>3000)clearTask(task);
  updateConnection();
},500);
pollMobile();
