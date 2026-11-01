// Run with the inline page script on stdin; no display or EEG is generated.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      value: '10', checked: true, disabled: false, textContent: '', style: {},
      classList: {toggle() {}, remove() {}}, onclick: null,
    });
  }
  return elements.get(id);
}
const context = vm.createContext({
  document: {getElementById: element, hidden: false, addEventListener() {}},
  window: {addEventListener() {}},
  performance: {now: () => 100},
  requestAnimationFrame: () => 1,
  cancelAnimationFrame() {},
  setInterval: () => 1,
  clearInterval() {},
  fetch() {throw Error('A pure timing test must not access the board')},
  alert() {throw Error('Unexpected alert')},
  Math,
});
vm.runInContext(fs.readFileSync(0, 'utf8'), context);

assert.equal(typeof element('timingCheck').onclick, 'function');
for (let index = 0; index < 36; index++) {
  assert.equal(vm.runInContext(`frameLockedOn(10, ${index})`, context),
    Math.floor(index / 12) % 2 === 0);
  assert.equal(vm.runInContext(`frameLockedOn(12, ${index})`, context),
    Math.floor(index / 10) % 2 === 0);
}
const sample240 = Array.from({length: 722}, (_, index) =>
  Math.round((index * 1000 / 240 + 0.04 * Math.sin(index)) * 10) / 10);
context.samples = sample240;
const report240 = vm.runInContext('timingReport(samples)', context);
assert.match(report240, /240\.0\d Hz/);
assert.match(report240, /12\.00/);
assert.match(report240, /10\.00/);
assert.match(report240, /10 Hz.*固定帧/);
assert.match(report240, /12 Hz.*固定帧/);
assert.ok(Math.abs(vm.runInContext('timingReady.refresh', context) - 240) < 0.1);
assert.equal(vm.runInContext('timingReady.late', context), 0);
const sample60 = Array.from({length: 182}, (_, index) => index * 1000 / 60);
context.samples = sample60;
const report60 = vm.runInContext('timingReport(samples)', context);
assert.match(report60, /2\.50/);
assert.match(report60, /10 Hz.*按时间/);
assert.ok(Math.abs(vm.runInContext('timingReady.refresh', context) - 60) < 0.1);
element('start').onclick();
assert.match(element('feedback').textContent, /240 Hz/);
console.log('240 Hz frame lock and 60 Hz fallback: OK');
