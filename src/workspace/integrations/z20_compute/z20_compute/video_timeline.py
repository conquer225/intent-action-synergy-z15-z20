"""Reviewed-video annotation playback; model inference can replace this seam."""
import bisect
import copy
import math

from .fixed_scene import describe_scene


class VideoTimeline:
    def __init__(self,data):
        self.data=copy.deepcopy(data)
        self.rows=self.data.get('keyframes',[])
        self.times=[row.get('time_s') for row in self.rows]
        self.duration=self.data.get('duration_s')
        if (data.get('format')!='z20-video-annotations-v1' or data.get('image_size')!=[640,480]
                or not self.rows or not isinstance(self.duration,(int,float))
                or not math.isfinite(self.duration) or self.duration<=0
                or any(type(t) not in (int,float) or not math.isfinite(t) for t in self.times)
                or self.times[0]!=0 or self.times[-1]!=self.duration
                or any(a>=b for a,b in zip(self.times,self.times[1:]))):
            raise ValueError('invalid video annotation timeline')
        for row in self.rows:
            if row.get('visible',True):describe_scene(row,(640,480))

    def at(self,time_s):
        if not math.isfinite(time_s) or time_s<0 or time_s>self.duration:return None
        index=min(bisect.bisect_right(self.times,time_s)-1,len(self.rows)-1)
        first=self.rows[index]
        second=self.rows[min(index+1,len(self.rows)-1)]
        if not first.get('visible',True):return None
        if time_s!=self.times[index] and not second.get('visible',True):return None
        row=copy.deepcopy(first)
        if index<len(self.rows)-1 and second.get('visible',True):
            t=(time_s-self.times[index])/(self.times[index+1]-self.times[index])
            for label in ('person','dog'):
                row[label]=[round(a+(b-a)*t) for a,b in zip(first[label],second[label])]
                a,b=first['depth_reference'][label],second['depth_reference'][label]
                if a['length_m']!=b['length_m'] or a['part']!=b['part']:
                    raise ValueError('physical reference must stay fixed within an interval')
                row['depth_reference'][label]['segment_px']=[
                    [x+(y-x)*t for x,y in zip(p,q)]
                    for p,q in zip(a['segment_px'],b['segment_px'])]
        result=describe_scene(row,(640,480))
        result.update(time_s=float(time_s),annotation_source='reviewed_keyframes_interpolated')
        return result
