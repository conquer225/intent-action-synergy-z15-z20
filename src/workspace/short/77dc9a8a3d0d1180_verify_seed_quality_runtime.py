"""Recorded and synthetic replay; tests engineering state, never emotion accuracy."""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from .emotion_baseline import sha256
from .seed_causal_normalization import past_center
from .seed_covariance_diagnosis import model_for
from .seed_export_candidate import linear_parameters

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pynq_guardianloop"))
from seed_quality_runtime import SeedQualityRuntime

OUT = Path(__file__).parent / "output/seed_quality_runtime_20260926"


def run(values, weights, sequences=None, disconnect_at=None):
    runtime = SeedQualityRuntime(weights)
    events = []
    split = set([0, len(values)] + list(range(500, len(values), 500)))
    if sequences is not None:
        gaps = set((np.flatnonzero(np.diff(sequences) % 256 != 1)+1).tolist())
        split.update(gaps)
    else:
        gaps = set()
    if disconnect_at is not None:
        split.add(disconnect_at)
        gaps.add(disconnect_at)
    bounds = sorted(split)
    for a,b in zip(bounds[:-1], bounds[1:]):
        if a in gaps:
            events.append({"source_row_end": a, **runtime.disconnect("recorded_or_injected_gap")})
        before = runtime.mean.copy()
        accepted = runtime.accepted_windows
        sqi_before = [np.asarray(v).copy() for v in runtime.sqi.reference]
        batch_events = runtime.append(values[a:b])
        # At most one 2s segment emitted per supplied block.
        if batch_events and batch_events[-1]["state"] == "rejected":
            np.testing.assert_array_equal(runtime.mean, before)
            assert runtime.accepted_windows == accepted
            for old,new in zip(sqi_before,runtime.sqi.reference):
                np.testing.assert_array_equal(old,np.asarray(new))
            assert runtime.last_prediction is None
        events.extend({"source_row_end": b, **event} for event in batch_events)
    counts = dict(Counter(e["state"] for e in events))
    predictions = counts.get("prediction",0)
    return {"events": events, "counts": counts, "input_seconds": len(values)/250,
        "prediction_window_seconds_fraction": predictions*12/(len(values)/250),
        "note": "coverage includes startup/calibration/rejection cost; no accepted-only accuracy is computed"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "results.json").exists():
        raise FileExistsError("Preserve prior results")
    source = OUT.parent / "seed_matched_preprocessing_20260926/features.npz"
    record = json.loads((source.parent / "results.json").read_text())
    assert sha256(source) == record["hashes"][str(source)]
    data = dict(np.load(source, allow_pickle=False))
    x,y,keys = data["matched"],data["targets"],data["keys"]
    features = np.empty_like(x)
    eligible = np.ones(len(x),dtype=bool)
    for subject,session in np.unique(keys[:,:2],axis=0):
        idx = np.flatnonzero((keys[:,0]==subject)&(keys[:,1]==session))
        idx = idx[np.lexsort((keys[idx,3],keys[idx,2]))]
        features[idx] = past_center(x[idx],"expanding")
        eligible[idx[:5]]=False
    with threadpool_limits(limits=2):
        model = model_for("lda").fit(features[eligible],y[eligible])
    w,b=linear_parameters(model)
    weights={"weight":w.astype(np.float32),"bias":b.astype(np.float32),"classes":model[-1].classes_}
    np.savez(OUT / "matched_linear_weights.npz",**weights)
    protocol = {"scope":"local candidate only; no service replacement",
        "channels":"F3 F4 C3 C4 T7 T8 O1 O2, all8 required",
        "gate":"reuse CytonSQIMonitor defaults; atomic accept of 2s segments, 60 accepted segments for SQI calibration",
        "rejection":"freeze personal mean and SQI reference; discard incomplete feature window and reset filters; retain earlier valid calibration",
        "disconnect":"clear mean/SQI/filter/pending/prediction; 2s warmup then5 accepted12s calibration windows; first scored window ends earliest74s",
        "model":"full-fit matched-preprocessing SEED candidate, not new accuracy measurement",
        "limitations":"gated subset distribution not revalidated with emotion labels; synthetic stress is not real-artefact evidence"}
    (OUT / "protocol.json").write_text(json.dumps(protocol,indent=2),encoding="utf-8")
    t=np.arange(160*250)/250
    good=np.stack([20*np.sin(2*np.pi*(9+i*.2)*t+i*.3)+3*np.sin(2*np.pi*5*t) for i in range(8)],axis=1)
    scenarios={"synthetic_good":good}
    flat=good.copy(); flat[40*250:44*250,6:]=0; scenarios["synthetic_O1_O2_flat"]=flat
    burst=good.copy(); burst[40*250:44*250,0]+=1500*np.sin(2*np.pi*12*t[40*250:44*250]); scenarios["synthetic_burst"]=burst
    results={name:run(v,weights) for name,v in scenarios.items()}
    results["synthetic_disconnect"]=run(good,weights,disconnect_at=40*250)
    raw_manifest=json.loads((OUT.parent / "seed_recorded_replay_20260926/manifest.json").read_text())
    raw_path=Path(raw_manifest["source"])
    assert sha256(raw_path)==raw_manifest["source_hash"]
    raw=np.loadtxt(raw_path,delimiter=",",skiprows=5,usecols=range(9))
    results["recorded_cyton"]=run(raw[:,1:],weights,raw[:,0].astype(int))
    assert results["synthetic_good"]["counts"].get("prediction",0)>0
    for name in ("synthetic_O1_O2_flat","synthetic_burst"):
        assert results[name]["counts"].get("rejected",0)>0
    after=[e for e in results["synthetic_disconnect"]["events"] if e["valid"] and e["epoch"]==1]
    assert after and after[0]["source_row_end"]>=114*250
    report={"cases":results,"hashes":{str(p):sha256(p) for p in [Path(__file__),source,raw_path,OUT/"protocol.json",OUT/"matched_linear_weights.npz",
        ROOT/"pynq_guardianloop/seed_quality_runtime.py",ROOT/"pynq_guardianloop/cyton_sqi.py",ROOT/"pynq_guardianloop/seed_replay_check.py"]}}
    (OUT/"results.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    for name,result in results.items():
        print(name,result["counts"],"coverage",result["prediction_window_seconds_fraction"],flush=True)


if __name__=="__main__":
    main()
