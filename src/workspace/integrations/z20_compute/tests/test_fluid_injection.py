"""Exercise the production iframe message interface with a deterministic RNG."""
import json,shutil,subprocess,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class FluidInjectionTests(unittest.TestCase):
    def test_each_eye_action_varies_appearance_without_replaying_commands(self):
        html=(ROOT/'web/visual_demo/fluid.html').read_text(encoding='utf-8')
        inline=html.split('<script>')[-1].split('</script>')[0]
        harness=r'''
const calls=[];let listener;let seed=7;
Math.random=()=>((seed=(seed*16807)%2147483647)-1)/2147483646;
global.location={origin:'http://localhost'};global.parent={};
global.window={addEventListener:(_,fn)=>listener=fn};
global.config={SPLAT_RADIUS:.25};global.initFramebuffers=()=>{};
global.splat=(x,y,dx,dy,color)=>calls.push({x,y,dx,dy,color,radius:config.SPLAT_RADIUS});
'''
        after=r'''
const actions=Array.from({length:24},(_,i)=>({id:i+1,epoch:2,name:i%2?'inject_right':'inject_left'}));
const state={session:'one',epoch:2,mode:'fluid',menu:false,stopped:false,actions};
const send=(s,origin=location.origin)=>listener({origin,source:parent,data:{type:'z20-fluid',state:s}});
send(state);send(state);send({...state,actions:[{id:25,epoch:1,name:'inject_left'}]});
send({...state,menu:true,actions:[{id:26,epoch:2,name:'inject_left'}]});
send({...state,actions:[{id:27,epoch:2,name:'inject_left'}]},'http://other');
console.log(JSON.stringify(calls));
'''
        result=subprocess.run([shutil.which('node') or 'node','-e',harness+inline+after],capture_output=True,text=True,check=True)
        calls=json.loads(result.stdout)
        self.assertEqual(len(calls),24)
        self.assertGreater(len({round(c['radius'],4) for c in calls}),10)
        self.assertGreater(len({round(abs(c['dx'])) for c in calls}),10)
        self.assertGreater(len({tuple(c['color'].values()) for c in calls}),10)
        for i,c in enumerate(calls):
            self.assertEqual(c['dx']>0,i%2==0)
            self.assertTrue(.12<=c['radius']<=.65)
            self.assertTrue(450<=abs(c['dx'])<=1400)
            self.assertTrue(0<=c['x']<=1 and 0<=c['y']<=1)

