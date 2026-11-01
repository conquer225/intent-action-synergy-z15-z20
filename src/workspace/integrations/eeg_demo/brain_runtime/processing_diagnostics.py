"""JSON-only observation of computed features; no filtering or model execution."""


def processing_snapshot(collected, sample_end, sequence, emotion, fatigue,
                        emotion_valid, fatigue_valid, fatigue_feature_end=None):
    def branch(seconds, model, valid, feature_end=None):
        count=min(collected,seconds*250)
        end=sample_end if feature_end is None else feature_end
        return dict(window_seconds=seconds,collected_samples=count,required_samples=seconds*250,
                    window=[max(0,sample_end-count),sample_end],
                    feature_window=[max(0,end-seconds*250),end] if valid else None,
                    features=getattr(model,'diagnostics',None) if valid else None)
    return dict(version=1,sequence=sequence,sample_rate_hz=250,
                filter=dict(backend='arm',notch_hz=50,notch_q=5,bandpass_hz=[1,45],order=4),
                emotion=branch(12,emotion,emotion_valid),fatigue=branch(8,fatigue,fatigue_valid,fatigue_feature_end))
