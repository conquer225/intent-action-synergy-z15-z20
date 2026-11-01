"""Publish real prepared EEG for the browser; no model, acquisition or actuator writes."""
import json
from pathlib import Path
import numpy as np
from vision_demo.signal_source import PublicReplay
from vision_demo.signal_core import normalize_eeg,CAP

def prepare(assets,output):
 replay=PublicReplay(assets/'replay');frames=[]
 fatigue_names={'normal':'正常','mild':'轻度疲劳','severe':'严重疲劳'}
 emotion_names={'funny':'正向情绪','calm':'中性情绪','boring':'中性情绪','horror':'负向情绪'}
 for second in range(181):
  value=normalize_eeg(replay.snapshot(second));fatigue=value.get('fatigue');emotion=value.get('emotion')
  if fatigue:fatigue=dict(fatigue,label=fatigue_names[fatigue['level']])
  if emotion:emotion=dict(emotion,label=emotion_names[emotion['raw']])
  frame=dict(ok=value['ok'],reason=value.get('reason',''),seq=value.get('seq'),
    raw=np.round(value.get('raw',[]),4).tolist(),samples=np.round(value.get('samples',[]),4).tolist(),
    sample_index=(120+second)*50,rate=50,quality=value.get('quality',[]),fatigue=fatigue,emotion=emotion,
    processing=value.get('processing'),calibration=value.get('calibration',[0,15]),data_age=0.)
  frames.append(dict(t=second*1000,frame=frame))
 metadata=dict(license='CC-BY-4.0',source_url=replay.metadata['metadata']['source_url'],
   label='LEMON sub-010002',doi='10.1038/sdata.2018.308',calibration_seconds=120,
   processing='原有疲劳与情绪模型；八通道，250 Hz 分析，50 Hz 波形显示',
   model_hashes=replay.metadata['model_hashes'])
 data=dict(format='guardianloop-eeg-public-v1',origin='replay',source='LEMON-sub010002',
   channels=CAP,duration_ms=180000,metadata=metadata,control_enabled=False,frames=frames)
 output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
 print('PUBLIC_RECORDING_READY',output,output.stat().st_size)

if __name__=='__main__':
 here=Path(__file__).resolve().parent
 prepare(here/'build/signal_assets',here.parent/'eeg_demo/runtime/eeg_recording.json')
