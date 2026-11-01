const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function main() {
  const html = fs.readFileSync(__dirname + '/preview.html', 'utf8');
  const elements = new Map(), frames = [], calls = [];
  const element = tag => ({tag, textContent:'', children:[], style:{},
    append(...nodes){this.children.push(...nodes);}, replaceChildren(){this.children=[];}});
  const initial = {page:'home',page_id:0,title:'主页',labels:['轮椅方向','交流','多媒体'],
    direction:'stop',speed_level:1,reading:false,mi_first_confirmed:false,alerts:{},events:[],last_action:'无'};
  const sandbox = {location:{hash:'#local-test-key'},requestAnimationFrame:f=>frames.push(f),setInterval(){},
    document:{querySelector(s){if(!elements.has(s))elements.set(s,element('div'));return elements.get(s);},
      querySelectorAll(){return [];},createElement:element},
    fetch:async (url,options)=>{calls.push({url,options});return {ok:true,json:async()=>initial};}};
  vm.createContext(sandbox);vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],sandbox);
  await vm.runInContext('refresh()',sandbox);
  sandbox.next={...initial,page:'video',page_id:1,title:'视频',labels:['翻动视频','','评价'],video_index:2,rating:'好'};
  vm.runInContext('render(next)',sandbox);
  let zones=elements.get('#zones').children;
  assert.equal(zones[1].tag,'div');assert.equal(zones[1].onclick,undefined);
  assert.match(zones[1].children[0].textContent,/视频 3/);
  await zones[0].onclick();
  const command=calls.find(c=>c.options.method==='POST');
  assert.deepEqual(JSON.parse(command.options.body),{action:'choose',value:0});
  sandbox.next={...initial,page:'drive',page_id:2,labels:['速度','返回','媒体'],direction_armed:false};
  vm.runInContext('render(next)',sandbox);
  const corners=elements.get('#corners').children;
  assert.equal(corners.length,4);assert.ok(corners.every(c=>c.disabled));
  assert.match(corners[0].textContent,/8 Hz.*前进/);assert.match(corners[3].textContent,/14 Hz.*右转/);
  assert.ok(calls.every(c=>c.options.headers['X-Preview-Key']==='local-test-key'));
  assert.doesNotMatch(html,/<audio|autoplay|\.play\(/i);
  console.log('SYSTEM_PAGE_TESTS_PASSED neutral centre, routes, unarmed directions, explicit simulations, no audio');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
