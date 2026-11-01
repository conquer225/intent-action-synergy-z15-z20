"""Small environment-result contracts. Pixels, waveforms and files stay separate."""
import copy
import math
import re

ENV_TTL=dict(person_dog=2.,depth=2.,cloud=5.,audio=3.,adda=5.)


def finite(value):
    return type(value) in (float,int) and math.isfinite(value)


def _matches(pattern,value):
    return isinstance(value,str) and re.fullmatch(pattern,value) is not None


def _bounded(value,depth=0):
    if depth>6:raise ValueError('environment payload nesting exceeds limit')
    if value is None or type(value) is bool:return
    if type(value) in (float,int):
        if not finite(value):raise ValueError('nonfinite environment value')
    elif isinstance(value,str):
        if len(value)>512:raise ValueError('environment string exceeds limit')
    elif isinstance(value,list):
        if len(value)>32:raise ValueError('send large arrays separately')
        for item in value:_bounded(item,depth+1)
    elif isinstance(value,dict):
        if len(value)>32 or any(not isinstance(k,str) or len(k)>64 for k in value):
            raise ValueError('environment object exceeds limit')
        for item in value.values():_bounded(item,depth+1)
    else:raise ValueError('unsupported environment value')


def validate_environment(body):
    if (body.get('task') not in ENV_TTL or type(body.get('valid')) is not bool
            or any(not isinstance(body.get(key),str) or not 1<=len(body[key])<=limit
                   for key,limit in (('source',256),('model_version',128),('frame_id',128),
                                     ('state',128),('reason',128)))):
        raise ValueError('invalid environment metadata')
    value=body.get('payload')
    if not body['valid']:
        if value is not None:raise ValueError('invalid environment result must clear payload')
        return
    if not isinstance(value,dict):raise ValueError('valid environment result requires payload')
    _bounded(value)
    task=body['task']
    if task=='depth':
        if (not finite(value.get('distance_m')) or value['distance_m']<=0 or value.get('units')!='m'
                or not _matches(r'[0-9a-f]{64}',value.get('calibration_id'))
                or not isinstance(value.get('capture_mode'),str) or not value['capture_mode']
                or type(value.get('valid_points')) is not int or value['valid_points']<10):
            raise ValueError('metric depth requires calibration and sufficient valid points')
    elif task=='cloud':
        if (not _matches(r'[A-Za-z0-9_-]{1,64}',value.get('artifact_id'))
                or type(value.get('points')) is not int or not 1<=value['points']<=500000
                or type(value.get('metric')) is not bool
                or value.get('units')!=('m' if value['metric'] else 'baseline_length')
                or (value['metric'] and not _matches(r'[0-9a-f]{64}',value.get('calibration_id')))
                or (not value['metric'] and value.get('case_only') is not True)):
            raise ValueError('point cloud units/provenance invalid')
    elif task=='person_dog':
        if (value.get('interaction') not in ('holding','petting','leashing','walking_with_dog')
                or value.get('method') not in ('registered_photo','reviewed_video_annotations')
                or (value.get('geometry') is not None and value.get('geometry_kind')!='reference_size_estimate')):
            raise ValueError('person/dog method or distance provenance missing')
    elif task=='audio':
        if (not finite(value.get('rms')) or not 0<=value['rms']<=1
                or not finite(value.get('dbfs')) or not -160<=value['dbfs']<=1
                or (value.get('peak_frequency_hz') is not None and
                    (not finite(value['peak_frequency_hz']) or not 0<=value['peak_frequency_hz']<=8000))
                or value.get('playback_started') is not False):
            raise ValueError('invalid silent audio analysis')


class EnvironmentStore:
    def __init__(self,now):
        self.now,self.entries=now,{}

    def put(self,body):
        validate_environment(body)
        self.entries[body['task']]=(copy.deepcopy(body),self.now())

    def expire(self):
        expired=[]
        for task,(body,received) in self.entries.items():
            if body['valid'] and self.now()-received>ENV_TTL[task]:
                body.update(valid=False,payload=None,state='expired',reason='expired')
                expired.append(copy.deepcopy(body))
        return expired

    def snapshot(self):
        return {task:dict(copy.deepcopy(body),age_seconds=max(0.,self.now()-received))
                for task,(body,received) in self.entries.items()}
