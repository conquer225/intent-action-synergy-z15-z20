"""Read only KEY0. Reuse the already-tested PS button edge/debounce policy."""
from buttons import Edges


class VisionKey:
    def __init__(self,initial=3):
        self.edges=Edges([0],held=[] if initial&1 else [0])

    def feed(self,value,now):
        # Board buttons are active low. KEY1 is intentionally ignored.
        return bool(self.edges.feed(0,0 if value&1 else 1,now))


class SignalKeys:
    """KEY0 image, KEY1 signals; a chord requires a full release before reuse."""
    def __init__(self,initial=3):
        self.edges=Edges([0,1],held=[k for k in (0,1) if not initial&(1<<k)])
        self.chord=False
    def feed(self,value,now):
        if value==0:self.chord=True
        events=[]
        for k in (0,1):events.extend(self.edges.feed(k,0 if value&(1<<k) else 1,now))
        if self.chord:
            if value==3 and not any(self.edges.down.values()) and not self.edges.pending:self.chord=False
            return None
        if len(set(events))!=1:return None
        return 'image' if events[0]==0 else 'signal'
