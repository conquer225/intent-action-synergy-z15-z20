const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function main() {
  const html = fs.readFileSync(path.join(__dirname, 'player.html'), 'utf8');
  const elements = new Map();
  const element = () => ({ textContent: '', value: 0, files: [], children: [],
    append(...items) { this.children.push(...items); },
    replaceChildren() { this.children = []; } });
  const buttons = ['pause','resume','stop'].map(action => ({ ...element(), dataset: { action } }));
  const calls = [];
  const sandbox = {
    location: { hash: '#test-private-key' },
    document: {
      querySelector(selector) { if (!elements.has(selector)) elements.set(selector, element()); return elements.get(selector); },
      querySelectorAll() { return buttons; }, createElement: element,
    },
    fetch: async (url, options) => {
      calls.push({url, options});
      return { ok: true, json: async () => ({files:[{id:'a'.repeat(32),name:'<img onerror=bad>',bytes:1024,prepared:true}],
        player:{state:'playing',frame:40,seconds:2},preparation:{},fixture_ready:true}) };
    },
    setInterval() {}, Uint32Array, Uint8Array, Blob,
  };
  vm.createContext(sandbox);
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], sandbox);
  await vm.runInContext('refresh()', sandbox);
  assert.match(elements.get('#player').textContent, /40/);
  assert.equal(elements.get('#files').children[0].children[0].textContent.includes('<img'), true);
  assert.equal(elements.get('#fixture').disabled, false);
  for (const button of buttons) await button.onclick();
  const actions = calls.filter(c => c.options.method === 'POST').map(c => JSON.parse(c.options.body).action);
  assert.deepEqual(actions, ['pause','resume','stop']);
  assert.ok(calls.every(c => c.options.headers['X-Media-Key'] === 'test-private-key'));
  for (const [data, expected] of [['123456789','cbf43926'],['a'.repeat(1048576),'d7cd5672']]) {
    sandbox.testFile = new Blob([data]);
    assert.equal(await vm.runInContext('crcFile(testFile)',sandbox), expected);
  }
  console.log('PLAYER_PAGE_TESTS_PASSED status, text-only filenames, commands, private key, bounded CRC');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
