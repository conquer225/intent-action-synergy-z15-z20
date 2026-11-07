"""Optional filter-bank CSP/SVM observer attached to the existing Cyton reader."""
import json
import multiprocessing
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pl_accel.eeg import CHANNELS, EEGModel
from pl_accel.live import EEGComparison, LiveEEGTap, open_pynq_eeg
from cyton_reader_sink import ReaderPacketSink
from cyton_trial_recorder import atomic_json


def create_pl_mi(model_path, channel_map, *, status_path, ip_name='z15_fbcsp_0', microvolts_per_count=1.,
                 packet_decoder, audit_path=None, hwh_path=None, engine_factory=open_pynq_eeg):
    status_path = Path(status_path)
    engine = sink = None
    def publish(state):
        state = dict(state, source='live:Cyton', backend=engine.name, model_sha256=model.identity)
        atomic_json(status_path, state)
        if audit_path:
            Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
            with Path(audit_path).open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(state, ensure_ascii=False, allow_nan=False)+'\n')
    try:
        if tuple(channel_map) != CHANNELS:
            raise ValueError('PL MI model requires the fixed eight-channel cap order')
        model = EEGModel.load(model_path)
        engine = engine_factory(model, ip_name, **({'hwh': hwh_path} if hwh_path is not None else {}))
        method = 'fork' if 'fork' in multiprocessing.get_all_start_methods() else 'spawn'
        sink = ReaderPacketSink(multiprocessing.get_context(method), capacity=250, batch_samples=10)
        observer = EEGComparison(engine, microvolts_per_count=microvolts_per_count, publish=publish)
        publish(dict(observer.snapshot(), updated_at=time.time()))
        return LiveEEGTap(observer, sink, packet_decoder)
    except Exception as exc:
        if sink is not None:sink.close()
        if engine is not None:engine.close()
        state = dict(valid=False, label=None, class_id=None, reason='backend_unavailable',
            error=type(exc).__name__+': '+str(exc), source='live:Cyton',
            backend='PL_filterbank_CSP_SVM', control_enabled=False, updated_at=time.time())
        try:atomic_json(status_path, state)
        except OSError as status_error:state['status_error'] = str(status_error)
        print('PL_MI_STATUS: '+json.dumps(state, ensure_ascii=False), flush=True)
        return None
