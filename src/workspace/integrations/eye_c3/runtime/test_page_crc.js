const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function main() {
  const html = fs.readFileSync(path.join(__dirname, 'upload.html'), 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const elements = new Map();
  const sandbox = {
    location: { hash: '#test-key' },
    document: { getElementById(id) {
      if (!elements.has(id)) elements.set(id, { value: 0, textContent: '', files: [] });
      return elements.get(id);
    } },
    fetch: async () => ({ ok: true, json: async () => ({ files: [] }) }),
    setInterval() {},
    Uint32Array, Uint8Array, Blob,
  };
  vm.createContext(sandbox);
  vm.runInContext(script, sandbox);
  for (const [data, expected] of [['123456789', 'cbf43926'], ['a'.repeat(1048576), 'd7cd5672']]) {
    sandbox.testFile = new Blob([data]);
    assert.equal(await vm.runInContext('crcFile(testFile)', sandbox), expected);
  }
  console.log('PAGE_CRC_TESTS_PASSED vectors=2 including multi-chunk');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
