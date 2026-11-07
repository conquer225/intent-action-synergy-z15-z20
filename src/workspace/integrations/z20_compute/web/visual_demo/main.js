// Local adapter; spectrum shader source retains the upstream GPL-3.0 license.
import * as THREE from 'three';
import {vertexShader,solidFragmentShader} from '/vendor/spectrum/shaders.js';

const $=s=>document.querySelector(s),names={fluid:'眼控流体',spectrum:'三维声谱',npu:'NPU 分类计算',spatial:'空间感知'};
const stage=$('#stage'),renderer=new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(1);$('#three').appendChild(renderer.domElement);
const scene=new THREE.Scene();scene.background=new THREE.Color('#100e0c');
const camera=new THREE.PerspectiveCamera(48,1,.01,1000);camera.position.set(0,50,90);
let state=null,binding=null,modeKey=null,object=null,texture=null,cloudKey=null,viewIndex=0,lastAction=0,lastTrace=null,lastTraceAt=0;
window.demoBinding=null;window.demoReady=false;
function clear(){if(object){scene.remove(object);object.geometry.dispose();object.material.dispose();object=null;}if(texture){texture.dispose();texture=null;}}
function spectrum(data){
 if(!object){const pixels=new Uint8Array(64*40*4);texture=new THREE.DataTexture(pixels,64,40,THREE.RGBAFormat);texture.magFilter=THREE.LinearFilter;texture.minFilter=THREE.LinearFilter;
 const geometry=new THREE.PlaneGeometry(100,65,63,39);geometry.rotateX(-Math.PI/2);
 object=new THREE.Mesh(geometry,new THREE.ShaderMaterial({vertexShader,fragmentShader:solidFragmentShader,side:THREE.DoubleSide,
 uniforms:{u_audioTexture:{value:texture},u_colorBase:{value:new THREE.Color('#241a28')},u_colorLow:{value:new THREE.Color('#80533a')},u_colorMid:{value:new THREE.Color('#dba449')},u_colorHigh:{value:new THREE.Color('#fff0bd')}}}));scene.add(object);}
 const rows=data.history||[{band_values:data.band_values}];const pixels=texture.image.data;pixels.fill(0);
 for(let y=0;y<Math.min(40,rows.length);y++){const row=rows[rows.length-1-y].band_values;for(let x=0;x<64;x++){const i=(y*64+x)*4;pixels[i]=pixels[i+1]=pixels[i+2]=row[x]||0;pixels[i+3]=255;}}texture.needsUpdate=true;
}
function npu(data){const canvas=$('#npu'),ctx=canvas.getContext('2d');canvas.width=stage.clientWidth;canvas.height=stage.clientHeight;ctx.fillStyle='#fbf7ee';ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.scale(canvas.width/960,canvas.height/412);
 const w=960,h=412,task=data.task||['fatigue','emotion','sound'][state.sample_index];
 const labels={fatigue:['清醒','轻度疲劳','重度疲劳'],emotion:['负向','中性','正向'],sound:['拍手','口哨','敲击']}[task];
 const write=(s,x,y,size=16,color='#332c22')=>{ctx.fillStyle=color;ctx.font=`${size}px "Microsoft YaHei",sans-serif`;ctx.fillText(s,x,y);};
 write({fatigue:'脑电疲劳分类',emotion:'脑电情绪分类',sound:'声音三分类'}[task],20,38,26);
 const source=data.source||'',origin=source==='live:pc_microphone'?'现场麦克风 · 一秒声音':source==='recorded:pc_wav'?'导入音频文件':source.includes('LEMON')?'脑电特征记录回放':source.startsWith('recorded:')?'登记录音回放':'等待输入';
 write(origin+' · 窗口 '+(data.window_id||'等待采集').slice(-26),20,65,14,'#74644d');write('输入特征',20,105,19);write('Z20 计算过程',w*.39,105,19);write('本次分类',w*.73,105,19);
 const features=data.quantized_features||[];write(`${features.length} 项实际特征 → INT8`,20,132,14);
 for(let i=0;i<features.length;i++){const level=(features[i]+128)/255;ctx.fillStyle=`rgb(${80+150*level},${65+115*level},${60+55*level})`;ctx.fillRect(20+(i%15)*w*.019,151+Math.floor(i/15)*Math.min(12,h*.024),w*.016,Math.min(9,h*.018));}
 for(const [i,name] of ['输入量化','全连接 → ReLU → 三输出','读取结果 · 软件整数核对'].entries())write(name,w*.39,145+i*h*.12,14,data.event==='completed'?'#855f22':'#74644d');
 write(data.event==='completed'?'计算完成':data.event==='submitted'?'正在计算':'等待输入',w*.39,h*.73,19,'#855f22');
 write(data.valid?labels[data.class_id]:'等待有效结果',w*.73,145,Math.max(21,w*.03),'#855f22');
 const scores=data.scores||[],low=Math.min(...scores),span=Math.max(1e-6,Math.max(...scores)-low);
 for(let i=0;i<3;i++){const y=185+i*h*.12;write(labels[i],w*.73,y,14);if(scores[i]!=null){write(scores[i].toFixed(3),w*.91,y,13);ctx.fillStyle='#d9ccb6';ctx.fillRect(w*.73,y+10,w*.24,6);ctx.fillStyle='#855f22';ctx.fillRect(w*.73,y+10,(scores[i]-low)/span*w*.24,6);}}
 const timing=data.timing;write(timing?`软件 ${(timing.software_seconds*1000).toFixed(3)} ms   NPU ${(timing.npu_predict_seconds*1000).toFixed(3)} ms   速度比 ${timing.speedup.toFixed(2)} 倍`:'耗时对照：等待实板计算',20,h-44,16);
 write(`${data.backend==='PL_z20_mlp'?'Z20 PL 硬件计算':'软件参考'} · 整数核对：${data.integer_reference_equal===true?'一致':data.integer_reference_equal===false?'不一致':'待核对'} · 三类得分不是概率${task==='fatigue'?' · 疲劳教师候选模型':''}${data.frozen?' · 保留本次样本结果':''}`,20,h-16,12,'#74644d');
}
async function command(name){await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name==='enter'&&state&&!state.menu?'back':name})});}
for(const b of document.querySelectorAll('[data-command]'))b.onclick=()=>command(b.dataset.command).catch(showError);
window.addEventListener('keydown',e=>{const name={ArrowLeft:'left',ArrowRight:'right',Enter:'enter',Escape:'back'}[e.key];if(name){e.preventDefault();command(name).catch(showError);}});
function showError(e){$('#message').hidden=false;$('#message').textContent=String(e.message||e);window.demoBinding=null;binding=null;}
async function cloud(){const response=await fetch('/api/cloud');if(!response.ok)return;const data=await response.json();if(!data.valid||data.id===cloudKey)return;cloudKey=data.id;clear();
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(data.points,3));geometry.setAttribute('color',new THREE.Float32BufferAttribute(data.colors,3));geometry.computeBoundingSphere();
 const center=geometry.boundingSphere.center.clone();geometry.translate(-center.x,-center.y,-center.z);const scale=45/Math.max(geometry.boundingSphere.radius,1e-6);geometry.scale(scale,-scale,-scale);
 object=new THREE.Points(geometry,new THREE.PointsMaterial({size:.22,vertexColors:true}));scene.add(object);
}
async function poll(){try{const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw Error('连接中断');state=await r.json();if(!state.renderer_online)throw Error('等待无线连接恢复');
 const key=state.session+':'+state.epoch;const changed=key!==modeKey;if(changed){clear();cloudKey=null;viewIndex=0;modeKey=key;window.demoBinding=null;}
 binding={session:state.session,epoch:state.epoch};$('#title').textContent=names[state.mode];$('#status').textContent=state.transport_label+' · '+(state.mode==='npu'?(state.data?.npu?.backend==='PL_z20_mlp'?'Z20 PL 推理':'软件整数参考'):'电脑辅助渲染');
 $('#middle').textContent=state.menu?'进入':'返回';$('#fluid').style.visibility=state.menu||state.mode!=='fluid'?'hidden':'visible';$('#three').hidden=state.menu||!['spectrum','spatial'].includes(state.mode);$('#npu').hidden=state.menu||state.mode!=='npu';$('#image').hidden=true;$('#menu').hidden=!state.menu;$('#message').hidden=true;
 $('#sound-controls').hidden=state.menu||state.mode!=='npu'||state.sample_index!==2;
 $('#map-controls').hidden=state.menu||state.mode!=='spatial';$('#map-pl').disabled=!state.map_available;
 const actionLabels=state.menu?['上个模式','下个模式']:({fluid:['左侧随机注入','右侧随机注入'],spectrum:['上一段录音','下一段录音'],npu:['上一分类任务','下一分类任务'],spatial:['拍摄并生成','切换视图']}[state.mode]);
 document.querySelector('[data-command="left"]').textContent=actionLabels[0];document.querySelector('[data-command="right"]').textContent=actionLabels[1];
 $('#menu').replaceChildren(...Object.entries(names).map(([mode,title])=>{const p=document.createElement('p');p.textContent=title;p.className=mode===state.mode?'selected':'';return p;}));
 $('#fluid').contentWindow.postMessage({type:'z20-fluid',state},location.origin);
 const audio=state.data?.spectrum;$('#source').hidden=state.mode==='npu';$('#source').textContent=state.mode==='spatial'?'单目预测可见表面 · 相对深度':audio?`登记录音循环 · ${audio.source} · ${audio.position_seconds.toFixed(2)} s`:'眼控确认后执行';
 if(!state.menu&&state.mode==='spectrum'){if(audio)spectrum(audio);else{$('#message').hidden=false;$('#message').textContent='等待板端顺序 FFT';}}
 if(!state.menu&&state.mode==='npu')npu(state.data?.npu||{});
 if(!state.menu&&state.mode==='spatial'){
  for(const action of state.actions||[])if(action.id>lastAction){lastAction=action.id;if(action.name==='view_next')viewIndex=(viewIndex+1)%3;}
  if(state.map_backend==='pl'){
   $('#three').hidden=true;$('#image').hidden=false;$('#image').src='/api/pl-map.png?epoch='+state.epoch+'&t='+Math.floor(Date.now()/750);
   $('#status').textContent=state.transport_label+' · Z20 PL 地图绘制';
   $('#source').textContent='点云投影 · 深度遮挡 · 轨迹绘制 · 三视角';
  }else if(viewIndex<2){$('#image').hidden=false;$('#image').src=viewIndex===0?'/api/original.png?epoch='+state.epoch:'/api/depth.png?epoch='+state.epoch;}else await cloud();
  if(!state.spatial_ready){$('#message').hidden=false;$('#message').textContent=state.spatial_message||'等待新鲜相机帧与深度结果';}
 }
 window.demoReady=true;
 }catch(e){showError(e);}setTimeout(poll,100);}poll();
function animate(now){requestAnimationFrame(animate);const w=stage.clientWidth,h=stage.clientHeight;if(renderer.domElement.width!==w||renderer.domElement.height!==h){renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}
 const angle=Math.sin(now*.0002)*.3;camera.position.set(Math.sin(angle)*85,48,Math.cos(angle)*85);camera.lookAt(0,5,0);renderer.render(scene,camera);
 if(binding&&state?.renderer_online)window.demoBinding=binding;
}requestAnimationFrame(animate);
