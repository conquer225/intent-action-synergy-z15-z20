"""Isolated candidate replay; writes only the supplied output directory."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from seed_shadow import SeedShadow
from seed_quality_runtime import CHANNELS


def main():
    p=argparse.ArgumentParser();p.add_argument('--weights',required=True);p.add_argument('--recorded',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    t=np.arange(140*250)/250
    clean=np.stack([20*np.sin(2*np.pi*(9+i*.2)*t+i*.3)+3*np.sin(2*np.pi*5*t) for i in range(8)],axis=1)
    recorded=np.loadtxt(args.recorded,delimiter=',',skiprows=5,usecols=range(9))
    reports={};arrays={}
    for name,values,sequence,gap in [('synthetic_gap',clean,np.arange(len(clean))%256,True),
                                   ('recorded',recorded[:,1:],recorded[:,0].astype(int),False)]:
        shadow=SeedShadow(args.weights,CHANNELS,source='replay',status_path=out/(name+'_status.json'))
        scores=[];events=[];started=time.perf_counter()
        for i,(x,s) in enumerate(zip(values,sequence)):
            if gap and 22500<=i<23500:
                if i==22750:shadow.idle(now=i/250)
                continue
            for event in shadow.packet(x,int(s),now=i/250,timing_verified=gap):
                events.append({'row':i,**{k:v for k,v in event.items() if k not in ('scores','quality','raw_mains_ratio')}})
                if event['valid']:scores.append(event['scores'])
        reports[name]={'events':events,'last_gap':shadow.last_gap,'compute_seconds':time.perf_counter()-started,
                       'source':'offline_replay_not_live','sequence_gaps':shadow.gaps}
        arrays[name]=np.asarray(scores).reshape(-1,3)
    np.savez(out/'scores.npz',**arrays)
    (out/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    assert reports['synthetic_gap']['last_gap']['baseline_retained']
    first=next(e for e in reports['synthetic_gap']['events'] if e['valid'] and e['row']>=23500)
    assert first['row']==26999
    print('ISOLATED_SHADOW_REPLAY_OK',flush=True)


if __name__=='__main__':main()
