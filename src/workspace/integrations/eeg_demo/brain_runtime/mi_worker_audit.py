"""Optional replay-only numerical capture inside the independent MI process."""
import json
from pathlib import Path

import numpy as np

from cyton_sqi import CausalEEGFilter
from mi_eegnet_rms import OfflineEEGNet


class MIWorkerAudit:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.arrays={}
        self.calls=[]
        self.filters=[]
        original_filter=CausalEEGFilter.process
        original_logits=OfflineEEGNet.logits

        def record(task, **values):
            entry=dict(task=task)
            for key,value in values.items():
                name=f'miw_{len(self.calls):05d}_{key}'
                self.arrays[name]=np.asarray(value).copy()
                entry[key]=name
            self.calls.append(entry)

        def filtered(instance, values):
            if not any(instance is obj for obj in self.filters):
                self.filters.append(instance)
            identifier=-1-next(i for i,obj in enumerate(self.filters) if obj is instance)
            result=original_filter(instance,values)
            record('filter',instance=identifier,input=values,output=result)
            return result

        def logits(instance, values):
            result=original_logits(instance,values)
            record('mi',input=values,output=result)
            return result

        CausalEEGFilter.process=filtered
        OfflineEEGNet.logits=logits

    def save(self):
        (self.directory/'mi-worker-calls.json').write_text(json.dumps(self.calls),encoding='utf-8')
        np.savez(self.directory/'mi-worker-calls.npz',**self.arrays)
