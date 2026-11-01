// Virtual DOM only: never presents flicker on a real screen.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const htmlPath=process.argv[2]||'ssvep_free.html',html=fs.readFileSync(htmlPath,'utf8');
const script=html.split('<script>')[1].split('</script>')[0];
function environment(scriptSource=script){
  const elements=new Map(),raf=[],events={},calls=[],intervals=[];let time=0;
  const listen=(name,callback)=>{const previous=events[name];events[name]=()=>{if(previous)previous();callback();};};
  const element=id=>{if(!elements.has(id))elements.set(id,{checked:false,disabled:false,value:'four',textContent:'',
    style:{},classList:{values:new Set(),add(...values){values.forEach(v=>this.values.add(v));},remove(...values){values.forEach(v=>this.values.delete(v));},
      toggle(value,on){if(on)this.values.add(value);else this.values.delete(value);}}});return elements.get(id);};
  const context=vm.createContext({document:{hidden:false,body:element('body'),getElementById:element,addEventListener:listen},
    window:{addEventListener:listen,scrollTo:()=>{}},performance:{now:()=>time},AbortController,
    requestAnimationFrame:f=>{raf.push(f);return raf.length;},cancelAnimationFrame:()=>{},
    setInterval:f=>{intervals.push(f);return intervals.length;},clearInterval:()=>{},setTimeout:()=>1,clearTimeout:()=>{},
    fetch:async(url,options)=>{const request=options?.body?JSON.parse(options.body):{};calls.push(request);
      return {ok:true,json:async()=>({input:{preparation:{supported:false,active:false,token:null}},id:'one',state:request.action==='start'?'awaiting_presentation':'active',accepted:false,
        recording_control:{state:'ready'},raw_recording:{trial_id:'raw-one',samples:250}})};}});
  vm.runInContext(fs.readFileSync(path.join(path.dirname(htmlPath),'ssvep_input_prepare.js'),'utf8'),context);
  vm.runInContext(scriptSource,context);
  return {context,element,raf,events,calls,intervals,tick:step=>{time+=step;const f=raf.shift();if(f)f(time);},
    run:code=>vm.runInContext(code,context)};
}
(async()=>{
  const prepared=environment();
  prepared.context.fetch=async(_url,options)=>{const payload=JSON.parse(options.body);prepared.calls.push(payload);
    return {ok:true,json:async()=>({input:{preparation:{supported:true,active:true,token:'0123456789abcdef'}}})};};
  assert.equal(prepared.calls.length,0);
  await prepared.element('inputPrepare').onclick();
  assert.equal(prepared.calls.length,1);assert.equal(prepared.calls[0].action,'input_prepare');
  assert.equal(prepared.raf.length,0);assert.equal(prepared.run('inputPreparation.active'),true);
  await prepared.intervals.at(-1)();assert.equal(prepared.calls.at(-1).action,'input_heartbeat');
  prepared.context.document.hidden=true;prepared.events.visibilitychange();
  assert.equal(prepared.run('inputPreparation.active'),false);
  assert.equal(prepared.calls.at(-1).action,'input_release');
  assert.ok(prepared.calls.every(r=>!['start','record_start','presented'].includes(r.action)));
  const e=environment();assert.equal(e.raf.length,0);assert.equal(e.element('start').disabled,true);
  e.run('precheck()');for(let i=0;i<721;i++)e.tick(1000/240);
  assert.equal(e.raf.length,0);assert.equal(e.element('start').disabled,true);
  e.element('consent').checked=true;e.run('refreshControls()');assert.equal(e.element('start').disabled,false);
  await e.run('start()');e.tick(1000/240);await Promise.resolve();
  for(let i=0;i<720;i++)e.tick(1000/240);
  const transitions=JSON.parse(e.run('JSON.stringify(run.transitions)'));
  assert.deepEqual(transitions,{'8':48,'10':60,'12':72,'14':84});
  assert.ok(e.calls.every(r=>!('target_hz'in r)));assert.equal(e.element('tl').classList.values.has('selected'),false);
  e.context.document.hidden=true;e.events.visibilitychange();assert.equal(e.run('run'),null);
  for(const id of ['tl','tr','bl','br'])assert.equal(e.element(id).classList.values.size,0);
  const slow=environment();slow.run('precheck()');for(let i=0;i<721;i++)slow.tick(1000/60);
  slow.element('consent').checked=true;slow.run('refreshControls()');assert.equal(slow.element('start').disabled,true);
  const gap=environment();gap.element('consent').checked=true;gap.run('timing={at:0,hz:240};refreshControls()');
  await gap.run('start()');gap.tick(4.2);gap.tick(20);assert.equal(gap.run('run'),null);
  const diagnose=environment();diagnose.run("run={id:'one'};render({id:'one',state:'active',accepted:false,frame_ok:true,reason:'no_selection_insufficient_or_ambiguous_evidence',min_score:.55,min_margin:.1,input:{ready:true,state:'ready',age_seconds:.01,top_score:.35,margin:.05}})");
  assert.ok(diagnose.element('details').textContent.includes('0.350'));
  assert.ok(diagnose.element('details').textContent.includes('0.050'));
  const cued=fs.readFileSync(path.join(path.dirname(htmlPath),'guardianloop_web.py'),'utf8').split('SSVEP_CUED_PAGE = r"""')[1].split('"""')[0];
  const c=environment(cued.split('<script>')[1].split('</script>')[0]);
  assert.equal(c.raf.length,0);c.element('requireRaw').checked=true;
  c.run("readiness({input:{state:'no_data',ready:false,reason:'waiting_for_cyton'}})");
  assert.ok(c.element('inputStatus').textContent.includes('等待 Cyton'));
  assert.equal(c.raf.length,0);
  e.run("inputView({input:{state:'no_data',ready:false,reason:'waiting_for_cyton'}})");
  assert.ok(e.element('inputStatus').textContent.includes('无数据不代表休息'));
  c.element('demoOnly').onclick();assert.equal(c.element('requireRaw').checked,false);
  assert.ok(c.calls.every(request=>request.action!=='start'));
  c.element('consent').checked=true;c.element('target').value='10';
  c.element('timingCheck').onclick();for(let i=0;i<722;i++)c.tick(1000/240);
  await c.element('start').onclick();
  assert.equal(c.calls.find(request=>request.action==='start').require_raw_recording,false);
  await c.element('stop').onclick();
  const failure=environment(cued.split('<script>')[1].split('</script>')[0]);
  failure.element('consent').checked=true;failure.element('requireRaw').checked=true;failure.element('target').value='10';
  failure.run('timingReady={measuredAt:0,refresh:240,p95:4.2,late:0,count:720}');
  failure.context.fetch=async(_url,options)=>{const payload=JSON.parse(options.body);failure.calls.push(payload);
    return {ok:false,json:async()=>({error:'录制失败'})};};
  await failure.element('start').onclick();
  assert.ok(!failure.calls.some(request=>request.action==='start'));
  assert.equal(failure.raf.length,0);assert.equal(failure.run('arming'),false);
  assert.equal(failure.element('start').disabled,false);
  c.element('requireRaw').checked=true;
  await c.element('start').onclick();
  const rawStart=c.calls.findIndex(request=>request.action==='record_start');
  const cueStart=c.calls.findIndex((request,index)=>index>rawStart&&request.action==='start');
  assert.ok(rawStart>=0&&cueStart>rawStart);assert.equal(c.calls[cueStart].require_raw_recording,true);
  await c.element('stop').onclick();
  diagnose.run("render({id:'one',state:'active',accepted:false,frame_ok:true,min_score:.55,min_margin:.1,decision:{failures:['score_below_minimum']},input:{ready:true,state:'ready',frequency_hz:10,top_score:.35,margin:.12}})");
  assert.ok(diagnose.element('details').textContent.includes('CCA 未达门限'));
  e.element('size').value='large';e.element('size').onchange();assert.ok(e.element('body').classList.values.has('large-targets'));
  const rawFree=environment();rawFree.element('consent').checked=true;rawFree.element('requireRaw').checked=true;
  rawFree.run('timing={at:0,hz:240};refreshControls()');await rawFree.run('start()');
  assert.equal(rawFree.calls[0].action,'record_start');
  assert.equal(rawFree.calls[1].action,'start');assert.equal(rawFree.calls[1].require_raw_recording,true);
  const freeFailure=environment();freeFailure.element('consent').checked=true;freeFailure.element('requireRaw').checked=true;
  freeFailure.run('timing={at:0,hz:240};refreshControls()');
  freeFailure.context.fetch=async(_url,options)=>{freeFailure.calls.push(JSON.parse(options.body));return {ok:false,json:async()=>({error:'录制没有就绪'})};};
  await freeFailure.run('start()');assert.equal(freeFailure.raf.length,0);
  assert.ok(!freeFailure.calls.some(r=>r.action==='start'));
  const study=environment();study.element('consent').checked=true;study.element('studyMode').checked=true;study.element('studyMode').onchange();
  const plan={id:'study-one',state:'ready',completed_attempts:0,total_attempts:20,current:{phase:'calibration',requested_hz:0}};
  study.context.fetch=async(_url,options)=>{const request=JSON.parse(options.body);study.calls.push(request);
    return {ok:true,json:async()=>({study:plan,id:'one',state:request.action==='start'?'awaiting_presentation':'idle',
      recording_control:{state:'ready'},raw_recording:{trial_id:'raw-one',samples:250}})};};
  await study.element('studyCreate').onclick();assert.equal(study.raf.length,0);
  study.run('timing={at:0,hz:240};refreshControls()');await study.run('start()');
  assert.ok(study.calls.every(r=>!('target_hz' in r)&&!('selected_hz' in r)&&!('result' in r)));
  assert.equal(study.calls.find(r=>r.action==='record_start').study_id,'study-one');
  assert.ok(study.element('gazeGuide').textContent.includes('中心静止区'));
  assert.equal(study.element('mode').value,'four');
  console.log('PASS: no auto flash; frame safety; four rates; withdrawal; gate diagnostics; checked flow arms raw before stimulus');
})().catch(error=>{console.error(error);process.exitCode=1;});
