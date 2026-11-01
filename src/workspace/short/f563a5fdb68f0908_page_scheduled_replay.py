"""Replay-only lane suspension. Never changes release files or model labels."""
from page_policy import ScheduledLane, ScheduledSink


def ssvep_factory(path, *args, **kwargs):
    from ssvep_shadow import SSVEPShadow
    return ScheduledLane(SSVEPShadow(*args,**kwargs),path,'ssvep_candidate')
