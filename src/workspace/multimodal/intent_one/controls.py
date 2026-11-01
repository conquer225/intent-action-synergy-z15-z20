"""Board PL keys share the original one-press/debounce behavior of PS keys."""
from . import vendor
from buttons import Edges

class PlButtons:
    def __init__(self,mmio):
        self.mmio=mmio;self.mmio.write(4,3) # GPIO channel 1, both bits input.
        self.edges=Edges((0,1),held=[i for i in (0,1) if not (self.mmio.read(0)&(1<<i))])
    def poll(self,now):
        value=self.mmio.read(0);pressed=[]
        for index in (0,1):pressed.extend(self.edges.feed(index,0 if value&(1<<index) else 1,now))
        pressed.extend(self.edges.advance(now))
        if 1 in pressed:return ['stop']
        return ['mode_next'] if 0 in pressed else []

class PsControls:
    """Keep the original eye actions; add cue starts without extra hardware."""
    def __init__(self,reader):self.reader=reader;self.pressed_at=None;self.long_sent=False;self.context=None;self.target=0
    def poll(self,now,mode,page):
        events=self.reader.poll(now)
        down=any(self.reader.edges.down[code] for code,action in self.reader.mapping.items() if action=='start')
        if 'pause' in events:self.pressed_at=None;self.long_sent=True;return ['pause']
        if mode!='eeg':
            self.pressed_at=None
            if page=='mpu' and 'start' in events:return ['confirm']
            if mode=='eye' and page in ('connecting','diagnostic','countdown','settle','collect','compute','verification','restarting'):return []
            return ['p' if page=='positioning' else 'c'] if mode=='eye' and 'start' in events else ['confirm'] if 'start' in events else []
        if self.context is not None and self.context!=mode:self.pressed_at=None
        self.context=mode
        if 'start' in events:self.pressed_at=now;self.long_sent=False
        if self.pressed_at is not None and down and not self.long_sent and now-self.pressed_at>=.8:
            self.long_sent=True
            if page=='mi':
                command=('mi-left','mi-right','mi-rest')[self.target];self.target=(self.target+1)%3;return [command]
        if self.pressed_at is not None and not down:
            self.pressed_at=None
            return [] if self.long_sent else ['confirm']
        return []
