const button=document.querySelector('#record-sound'),file=document.querySelector('#sound-file'),feedback=document.querySelector('#sound-feedback');
async function submit(bytes,microphone){
 feedback.textContent='提取 40 项特征，正在送往 Z20…';
 const response=await fetch('/api/sound',{method:'POST',headers:{'Content-Type':'audio/wav','X-Sound-Source':microphone?'microphone':'file'},body:bytes});
 if(!response.ok)throw Error('声音未提交：请进入 NPU 页，并使用十秒以内的 16 位 PCM WAV');
 const result=await response.json();feedback.textContent=result.valid?'已提交真实声音，请看 Z20 分类结果':'声音太小或信号不足，请重新采集';
}
function wav(samples,rate){
 const buffer=new ArrayBuffer(44+samples.length*2),v=new DataView(buffer);
 const text=(offset,s)=>{for(let i=0;i<s.length;i++)v.setUint8(offset+i,s.charCodeAt(i));};
 text(0,'RIFF');v.setUint32(4,36+samples.length*2,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);text(36,'data');v.setUint32(40,samples.length*2,true);
 for(let i=0;i<samples.length;i++)v.setInt16(44+2*i,Math.max(-32768,Math.min(32767,Math.round(samples[i]*32768))),true);
 return buffer;
}
button.onclick=async()=>{
 let stream,context,processor;button.disabled=true;
 try{
  if(!navigator.mediaDevices?.getUserMedia)throw Error('麦克风不可用，请使用导入 WAV');
  stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
  context=new AudioContext({sampleRate:16000});await context.resume();
  const source=context.createMediaStreamSource(stream),mute=context.createGain();mute.gain.value=0;
  const chunks=[];processor=context.createScriptProcessor(1024,1,1);
  feedback.textContent='正在录音：请拍手、吹口哨，或敲击';
  await new Promise((resolve,reject)=>{
   let count=0;const timeout=setTimeout(()=>reject(Error('麦克风没有送来足够数据，请检查输入设备')),8000);
   processor.onaudioprocess=e=>{
    const chunk=e.inputBuffer.getChannelData(0).slice();chunks.push(chunk);count+=chunk.length;
    if(count>=context.sampleRate){clearTimeout(timeout);processor.onaudioprocess=null;resolve();}
   };
   source.connect(processor);processor.connect(mute);mute.connect(context.destination);
  });processor.disconnect();
  const all=new Float32Array(chunks.reduce((n,a)=>n+a.length,0));let offset=0;for(const chunk of chunks){all.set(chunk,offset);offset+=chunk.length;}
  if(all.length<context.sampleRate)throw Error('录音不足一秒，请重试');
  await submit(wav(all.slice(0,context.sampleRate),context.sampleRate),true);
 }catch(error){feedback.textContent=error.message||'录音失败，可改用导入 WAV';}
 finally{stream?.getTracks().forEach(track=>track.stop());processor?.disconnect();if(context)await context.close();button.disabled=false;}
};
document.querySelector('#import-sound').onclick=()=>file.click();
file.onchange=async()=>{try{if(file.files[0])await submit(await file.files[0].arrayBuffer(),false);}catch(error){feedback.textContent=error.message;}finally{file.value='';}};
document.querySelector('#sound-example').onchange=async e=>{if(e.target.value==='')return;try{const r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'recorded_sound_'+e.target.value})});if(!r.ok)throw Error('请先进入 NPU 页面');feedback.textContent='已选择登记录音样例';}catch(error){feedback.textContent=error.message;}finally{e.target.value='';}};
