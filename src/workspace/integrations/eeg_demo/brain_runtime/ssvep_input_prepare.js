'use strict';

function ssvepInputPreparation(endpoint) {
  const button = document.getElementById('inputPrepare');
  const status = document.getElementById('inputPreparationStatus');
  let token = null, timer = null, pending = false, epoch = 0;

  async function send(payload) {
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 1200);
    try {
      const response = await fetch(endpoint, {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload), signal: controller.signal});
      const value = await response.json();
      if (!response.ok) throw Error(value.error || '输入准备接口不可用');
      return value.input.preparation;
    } finally { clearTimeout(deadline); }
  }

  function stop() {
    const old = token;
    token = null; epoch++;
    clearInterval(timer); timer = null;
    button.disabled = false;
    status.textContent = '脑电输入准备已停止；不会闪烁。';
    if (old) fetch(endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'input_release', token: old}), keepalive: true})
      .catch(error => { status.textContent = '停止回执未收到；输入准备将在 3 秒内自动过期。'; });
  }

  async function heartbeat() {
    if (!token || pending) return;
    if (document.hidden) { stop(); return; }
    const current = epoch;
    pending = true;
    try { await send({action: 'input_heartbeat', token}); }
    catch (error) {
      if (current === epoch) { stop(); status.textContent = '输入准备中断：' + error.message; }
    } finally { pending = false; }
  }

  async function start() {
    if (token || pending || document.hidden) return;
    const current = ++epoch;
    pending = true; button.disabled = true;
    try {
      const preparation = await send({action: 'input_prepare', consent: true});
      if (current !== epoch || document.hidden) {
        if (preparation.token) fetch(endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action: 'input_release', token: preparation.token}), keepalive: true})
          .catch(() => { status.textContent = '页面已离开；输入准备将在 3 秒内自动过期。'; });
        return;
      }
      token = preparation.token;
      status.textContent = preparation.supported
        ? '脑电输入已启用，等待完整窗口；未录制、未闪烁。'
        : '独立采集模式；无需页面调度申请。';
      if (token) timer = setInterval(heartbeat, 1000);
    } catch (error) { status.textContent = '输入未准备：' + error.message; }
    finally { pending = false; button.disabled = !!token; }
  }

  button.onclick = start;
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  window.addEventListener('pagehide', stop);
  return {start, stop, get active() { return token !== null; }};
}
