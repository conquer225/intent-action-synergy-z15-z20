"""Per-enabled classifier availability, independent of deferred hardware tasks."""
from pathlib import Path
from .training import ModelBundle


def load_enabled_models(root,*,tasks=('emotion','fatigue','sound'),loader=ModelBundle.load):
    models,states={},{}
    if any(task not in ('emotion','fatigue','sound') for task in tasks):
        raise ValueError('unsupported enabled classifier')
    for task in tasks:
        try:
            model=loader(Path(root)/task)
            if model.task!=task:raise ValueError('model task mismatch')
            teacher=task=='fatigue' and model.source_kind=='synthetic'
            operational=model.deployable or teacher
            states[task]=dict(operational=operational,state='teacher_candidate' if teacher else
                'recorded_model_candidate' if operational else 'provenance_not_accepted',version=model.version,
                source_kind=model.source_kind,recognition_quality='separate_evaluation_required')
            if operational:models[task]=model
        except (OSError,ValueError,KeyError) as exc:
            states[task]=dict(operational=False,state='model_unavailable',reason=type(exc).__name__)
    return models,states
