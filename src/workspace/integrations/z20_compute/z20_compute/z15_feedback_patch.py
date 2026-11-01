"""Minimal, version-checked KEY1 guards for already installed display owners."""


def patch_signal_audio_guards(source):
    source=source.replace('\r\n','\n')
    for old,new in (
        ('vision.signal and vision.signal.session.snapshot()',
         'vision.signal and vision.signal.session and vision.signal.session.snapshot()'),
        ('vision.signal and vision.signal.analysis.thread.is_alive()',
         'vision.signal and vision.signal.analysis and vision.signal.analysis.thread.is_alive()')):
        if source.count(new)==1 and source.count(old)==0:continue
        if source.count(old)!=1 or new in source:raise ValueError('unknown player baseline; inspect before applying KEY1 guard')
        source=source.replace(old,new,1)
    compile(source,'media_player-feedback.py','exec')
    return source
