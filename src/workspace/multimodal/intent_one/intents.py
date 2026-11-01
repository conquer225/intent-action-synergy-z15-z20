"""Same SSVEP numerical gates as imported candidate, with a 60Hz HDMI witness."""
import math

def finite(value): return type(value) in (int,float) and math.isfinite(value)

class BrainSelection:
    def __init__(self): self.start(None,0)
    def start(self,epoch,now):
        self.epoch=epoch; self.started=now;self.last_end=None;self.candidate=None;self.first_end=None
        self.locked=None;self.reason='waiting_for_complete_window'
    def clear(self,reason):
        self.candidate=self.first_end=None;self.reason=reason
    def observe(self,row,now,display):
        if (display.get('epoch')!=self.epoch or display.get('active') is not True
            or not finite(display.get('refresh_hz')) or not 59<=display['refresh_hz']<=61
            or not finite(display.get('seconds')) or display['seconds']<2
            or not finite(display.get('max_gap_ms')) or display['max_gap_ms']>34
            or not isinstance(display.get('rates'),list) or len(display['rates'])!=4
            or any(not finite(v) or abs(v-f)>.75 for v,f in zip(display['rates'],(8,10,12,14)))):
            self.clear('display_timing_unconfirmed');return None
        stamp,age=row.get('updated_monotonic'),row.get('input_age_seconds')
        if (row.get('source')!='live' or row.get('valid') is not True or row.get('state')!='candidate_only'
            or not isinstance(row.get('quality'),dict) or row['quality'].get('hard_bad') is not False
            or not finite(stamp) or not finite(age) or not 0<=age<=.5 or not 0<=now-stamp+age<=.5
            or stamp-age<self.started+2.5):
            self.clear('no_fresh_quality_passed_window');return None
        start,end,scores=row.get('window_start_index'),row.get('window_end_index_exclusive'),row.get('scores')
        if (type(start) is not int or type(end) is not int or start<0 or end-start!=500
            or not isinstance(scores,list) or len(scores)!=4 or any(not finite(x) or not 0<=x<=1.000001 for x in scores)):
            self.clear('invalid_window');return None
        if self.last_end==end:return None
        if self.last_end is not None and end-self.last_end!=50:self.clear('window_discontinuity')
        self.last_end=end
        ranked=sorted(range(4),key=lambda n:scores[n],reverse=True);n=ranked[0]
        if row.get('frequency_hz')!=(8,10,12,14)[n] or scores[n]<.55 or scores[n]-scores[ranked[1]]<.10:
            self.clear('ambiguous_or_low_score');return None
        if self.locked==n:return None
        if self.candidate!=n:self.candidate=n;self.first_end=end;self.reason='collecting_nonoverlapping_window';return None
        if end-self.first_end<500:return None
        self.locked=n;self.clear('selected');return n

