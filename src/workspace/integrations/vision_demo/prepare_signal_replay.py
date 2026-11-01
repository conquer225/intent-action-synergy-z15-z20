"""Run public EEG through unmodified primary processing; persist source-labeled replay."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'eeg_demo/brain_runtime'))
from cyton_sqi import CausalEEGFilter,CytonSQIMonitor,primary_windows,segmented_sqi
from cyton_fatigue import FourChannelFatigue
from cyton_covariance import CovarianceSVM,CovarianceFeatureStream
from primary_window import PrimaryWindowProcessor
from vision_demo.signal_core import CAP

def prepare(source,out,brain):
 metadata=json.loads((source/'source.json').read_text(encoding='utf-8'));path=source/'lemon_250hz_uv.npy'
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 if sha(path)!=metadata['data_sha256'] or metadata['channels']!=CAP or metadata['output_rate_hz']!=250:raise ValueError('Public source contract mismatch')
 raw=np.load(path,allow_pickle=False).astype(float)
 if raw.shape!=(75000,8) or not np.isfinite(raw).all():raise ValueError('Expected120s calibration+180s demonstration')
 filt=CausalEEGFilter();filtered=filt.process(raw)
 fatigue=FourChannelFatigue(brain/'cyton_fatigue_overlap4.json');emotion=CovarianceSVM(brain/'gameemo_covariance_svm.npz')
 scale=4_500_000./24./(2**23-1)
 engine=PrimaryWindowProcessor(CytonSQIMonitor(calibration_windows=15),fatigue,emotion,CovarianceFeatureStream(CAP,storage='array'),None,None,None,CAP,scale,'ARM original replay',primary_windows,segmented_sqi)
 results=[];counters=dict(packets_seen=0,dropped_packets=0,sequence_gaps=0,unresolved_gaps=0,malformed_bytes=0)
 for index,(r,f) in enumerate(zip(raw,filtered)):
  counters['packets_seen']=index+1
  row=engine.append(r/scale,f.copy(),False,counters)
  if row is not None:
   row=dict(row,seq=row['window'],valid=row.get('valid') is True and row.get('state') in ('NORMAL','MILD','SEVERE'))
   row['level']=str(row['state']).lower();row['score']=row.get('smoothed_perclos');row['source']='public_lemon_replay';row['offline']=True
   results.append(dict(sample_end=index+1,fatigue=row))
 out.mkdir(parents=True,exist_ok=True)
 #250Hz inference above;50Hz is display decimation only, not inference input.
 np.savez_compressed(out/'eeg_replay.npz',raw=raw[::5].astype(np.float32),filtered=filtered[::5].astype(np.float32))
 model_files=['cyton_fatigue_overlap4.json','gameemo_covariance_svm.npz']
 code_files=['primary_window.py','cyton_sqi.py','cyton_fatigue.py','cyton_covariance.py','processing_diagnostics.py']
 report=dict(format='guardianloop-public-replay-v1',origin='replay',source_id='LEMON-sub010002',source_label='LEMON sub-010002 / 原算法离线处理',channels=CAP,
  display_rate_hz=50,sample_rate_hz=250,calibration_seconds=120,duration_seconds=180,metadata=metadata,model_hashes={n:sha(brain/n) for n in model_files},runtime_hashes={n:sha(brain/n) for n in code_files},results=results,
  data_sha256=sha(out/'eeg_replay.npz'),accuracy_claim=False,control_enabled=False)
 (out/'replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
 summary=dict(windows=len(results),fatigue_valid=sum(x['fatigue']['valid'] for x in results),emotion_valid=sum((x['fatigue'].get('emotion') or {}).get('valid') is True for x in results),model_hashes=report['model_hashes'],runtime_hashes=report['runtime_hashes'],physical_devices=False)
 (out/'processing_report.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(a.source,a.output,HERE.parent/'eeg_demo/brain_runtime')
