"""Fetch a bounded prefix of the licensed LEMON recording and select true cap channels."""
import argparse,hashlib,json,re,urllib.request
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
BASE='https://ftp.gwdg.de/pub/misc/MPI-Leipzig_Mind-Brain-Body-LEMON/EEG_MPILMBB_LEMON/EEG_Raw_BIDS_ID/sub-010002/RSEEG/'
CAP=['F3','F4','C3','C4','T7','T8','O1','O2']
def parse_header(text):
 if 'DataOrientation=MULTIPLEXED' not in text or 'BinaryFormat=INT_16' not in text:raise ValueError('Unsupported raw format')
 rate=1e6/float(re.search(r'^SamplingInterval=(.+)$',text,re.M)[1]);count=int(re.search(r'^NumberOfChannels=(.+)$',text,re.M)[1])
 channels={}
 for index,name,scale,unit in re.findall(r'^Ch(\d+)=([^,]+),[^,]*,([^,]+),([^\r\n]+)',text,re.M):channels[name]=(int(index)-1,float(scale),unit)
 if rate!=2500 or any(c not in channels for c in CAP):raise ValueError('Recording rate/montage mismatch')
 if any(channels[c][2] not in ('µV','μV','uV') for c in CAP):raise ValueError('Unknown source units')
 return count,channels
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 header=urllib.request.urlopen(BASE+'sub-010002.vhdr',timeout=30).read();text=header.decode('utf-8-sig');count,channels=parse_header(text)
 needed=310*2500*count*2;request=urllib.request.Request(BASE+'sub-010002.eeg',headers={'Range':'bytes=0-%d'%(needed-1)})
 with urllib.request.urlopen(request,timeout=60) as response:raw=response.read(needed)
 if len(raw)!=needed:raise ValueError('Incomplete raw prefix')
 values=np.frombuffer(raw,dtype='<i2').reshape(-1,count)
 selected=np.stack([values[:,channels[c][0]].astype(float)*channels[c][1] for c in CAP],axis=1)
 uv=resample_poly(selected,1,10,axis=0)[:75000].astype(np.float32)
 np.save(a.output/'lemon_250hz_uv.npy',uv,allow_pickle=False)
 metadata=dict(dataset='LEMON MPI Leipzig Mind-Brain-Body',subject='sub-010002',source_url=BASE+'sub-010002.eeg',source_prefix_bytes=needed,
  source_prefix_sha256=hashlib.sha256(raw).hexdigest(),header_sha256=hashlib.sha256(header).hexdigest(),license='CC BY4.0',
  citation='Babayan et al.(2019),Scientific Data6,180308',doi='10.1038/sdata.2018.308',channels=CAP,channel_indices_zero_based=[channels[c][0] for c in CAP],
  input_rate_hz=2500,output_rate_hz=250,input_unit='uV',reference='Original recording reference retained; no rereferencing',
  conversion='INT16 times header0.1uV; scipy resample_poly1/10; no synthesized or imputed channels',calibration_seconds=120,demonstration_seconds=180,
  data_sha256=hashlib.sha256((a.output/'lemon_250hz_uv.npy').read_bytes()).hexdigest(),ground_truth='resting EO/EC; fatigue and emotion truth unavailable')
 (a.output/'source.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8');(a.output/'source.vhdr').write_bytes(header)
 print(json.dumps(metadata,indent=2),flush=True)
if __name__=='__main__':main()
