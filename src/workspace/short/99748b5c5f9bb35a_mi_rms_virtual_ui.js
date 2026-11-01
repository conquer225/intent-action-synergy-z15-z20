// Adds recorded-input controls to the existing, unchanged virtual-hand client.
const rmsBaseRender = render;
let replayPending = false;
render = function(data) {
  rmsBaseRender(data);
  const record = data.replay;
  const model = data.candidate_model;
  if (!record || !model || data.source !== 'replay') {
    el('replayStatus').textContent = '来源无效；不可操作';
    el('replayStart').disabled = true;
    stopTrial('network_error');
    return;
  }
  const names = {idle:'尚未开始',running:'回放中',stopped:'已停止',eof:'回放已结束',error:'回放失败'};
  el('replayStatus').textContent = (names[record.state] || '未知状态') + ' · ' +
    record.samples_sent + '/' + record.total_samples + ' 样本 · ' +
    (record.samples_sent / 250).toFixed(1) + '/' + record.duration_seconds.toFixed(1) +
    ' 秒 · 输入：' + data.input_state + ' · 第 ' + record.run + ' 次回放';
  el('modelHash').textContent = '候选 SHA256：' + model.sha256;
  el('replayStart').disabled = replayPending || record.state === 'running';
  el('replayStop').disabled = replayPending || record.state !== 'running';
  if (record.state !== 'running' || data.input_state !== 'ready') {
    for (const target of ['left','right','rest']) el(target).disabled = true;
    el('virtualEnabled').disabled = true;
  }
};
async function replayAction(action) {
  if (replayPending || document.hidden) return;
  replayPending = true;
  stopTrial();
  el('replayStart').disabled = el('replayStop').disabled = true;
  try {
    const data = await api({action});
    render(data);
  } catch (error) {
    el('replayStatus').textContent = '回放请求失败：' + error.message;
    stopTrial('network_error');
  } finally {replayPending = false; poll();}
}
el('replayStart').onclick = () => replayAction('replay_start');
el('replayStop').onclick = () => replayAction('replay_stop');
el('left').textContent = '左手提示（回放测试）';
el('right').textContent = '右手提示（回放测试）';
reasons.replay_eof = '回放结束，结果及控制已撤销';
reasons.replay_stopped = '回放停止，结果及控制已撤销';
reasons.replay_restarted = '新一轮回放，滤波重新热身';
reasons.replay_error = '回放失败，结果及控制已撤销';
poll();
