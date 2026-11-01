"""Independent target verification; no calibration commands or fitted thresholds."""
import math
from guide import View

TARGETS=((.5,.5),(.2,.5),(.8,.5),(.5,.5),(.8,.5),(.2,.5),(.2,.5),(.5,.5),(.8,.5))

def assess(event, baseline=False):
    """All nine holds must meet the same coverage, validity and direction criteria."""
    points=event.get('points')
    if event.get('validation') is not True or event.get('unchanged') is not True or not isinstance(points,list) or len(points)!=9:
        return False,'验证结果不完整'
    counts=[]
    for p in points:
        n,v,c=(p.get(k) for k in ('samples','valid','correct'))
        if not all(type(x) is int for x in (n,v,c)) or not 0<=c<=v<=n:
            return False,'验证统计无效'
        counts.append((n,v,c))
    n=sum(x[0] for x in counts);v=sum(x[1] for x in counts);c=sum(x[2] for x in counts)
    gap=event.get('max_gap_ms')
    gap_ok=type(gap) in (int,float) and math.isfinite(gap) and 0<=gap<=250
    covered=all(n>=300 and v>=30 and c/v>=.9 for n,v,c in counts)
    strict=covered and gap_ok and all(v/n>=.9 for n,v,c in counts)
    usable=covered and gap_ok and v>=.9*n
    passed=usable if baseline else strict
    return passed,'有效 %.1f%%，方向符合 %.1f%%；%s'%(100*v/n if n else 0,100*c/v if v else 0,'九段均通过' if strict else '左侧偶发无效，基线可用' if usable else '未达到验证要求')

class Validation:
    def __init__(self):
        self.phase='ready';self.started=0.;self.point=0;self.detail='';self.preview=False
        self.gaze=None;self.gaze_at=0.

    def start(self,now,preview=False):
        self.phase='prepare';self.started=now;self.point=0;self.detail='';self.gaze=None

    def cancel(self):
        self.phase='cancelled';self.detail='验证已停止，校准未改写'

    def update_gaze(self,event,now):
        x,y=event.get('x'),event.get('y')
        valid=event.get('valid') is True and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in (x,y))
        self.gaze=(x,y) if valid else None;self.gaze_at=now

    def finish(self,event):
        if self.phase!='vprocessing':return
        passed,self.detail=assess(event)
        usable,_=assess(event,baseline=True)
        self.phase='validated' if passed else 'usable' if usable else 'validation_failed'

    def tick(self,now):
        duration={'prepare':5,'vsettle':2,'vcollect':8,'vprocessing':12}.get(self.phase)
        if duration and now-self.started>=duration:
            if self.phase=='prepare':self.phase='vsettle'
            elif self.phase=='vsettle':self.phase='vcollect'
            elif self.phase=='vcollect':
                self.point+=1;self.phase='vsettle' if self.point<len(TARGETS) else 'vprocessing'
            else:self.phase='failed';self.detail='验证结果等待超时'
            self.started=now
        duration={'prepare':5,'vsettle':2,'vcollect':8}.get(self.phase,0)
        remaining=max(0,math.ceil(duration-(now-self.started))) if duration else 0
        gaze=self.gaze if now-self.gaze_at<=.3 else None
        # Show text feedback, avoiding a moving cursor that biases the subject.
        detail=self.detail
        if self.phase in ('vsettle','vcollect'):
            detail='当前注视：%s'%('左 中 右'.split()[min(2,int(gaze[0]*3))] if gaze else '无有效数据')
        return View(self.phase,self.point,remaining,0,detail,False)
