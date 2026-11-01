"""One-way bandwidth fallback; the delivered rate remains separately measured."""


class CaptureProfile:
    def __init__(self):
        self.size,self.quality,self.fps=(960,540),70,12
        self.started=None;self.start_sent=0;self.fallback=False

    def observe(self,*,now,sent):
        if self.started is None:self.started,self.start_sent=now,sent;return False
        elapsed=now-self.started
        if self.fallback or elapsed<5:return False
        rate=(sent-self.start_sent)/elapsed
        self.started,self.start_sent=now,sent
        if rate<10:
            self.size,self.quality,self.fps=(640,360),65,10;self.fallback=True
            return True
        return False
