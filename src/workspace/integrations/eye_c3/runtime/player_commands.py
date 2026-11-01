"""Volatile session commands; a STOP cannot be overwritten by navigation."""
import json
import math
from pathlib import Path


class PlayerCommands:
    def __init__(self, prefix, session_id, directory='/dev/shm'):
        self.base=Path(directory);self.prefix=prefix;self.session_id=session_id
        self.seen={};self.stop_at=-math.inf

    def poll(self):
        for lane in ('stop','command'):
            path=self.base/(self.prefix+'-player-'+lane+'.json')
            if not path.exists():continue
            if path.stat().st_size>2048:raise ValueError('Oversize player command')
            row=json.loads(path.read_text())
            if row.get('session_id')!=self.session_id:continue
            ident=row.get('id');stamp=row.get('queued_monotonic')
            if (not isinstance(ident,str) or not ident or type(stamp) not in (int,float)
                    or not math.isfinite(stamp)):raise ValueError('Invalid player command')
            if self.seen.get(lane)==ident:continue
            self.seen[lane]=ident
            if lane=='stop':
                if row.get('action')!='force_stop':raise ValueError('Invalid priority STOP')
                self.stop_at=max(self.stop_at,stamp)
                return row
            if stamp>self.stop_at:return row
        return {}
