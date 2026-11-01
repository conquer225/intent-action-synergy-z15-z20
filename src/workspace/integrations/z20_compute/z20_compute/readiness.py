"""Read-only preparation checks; configuration assertions are not physical tests."""
import hashlib
from pathlib import Path
from .training import DIMENSIONS, ModelBundle
from .stereo import Calibration

REVIEW_FIELDS = ("official_sources_reviewed", "dma_generation_counter_verified", "fmc_electrical_reviewed",
                 "npu_dma_adapter_verified", "independent_video_verified", "classification_data_reviewed")


def verify_baseline(project_root, record):
    project_root = Path(project_root)
    missing, changed = [], []
    for entry in record["files"]:
        path = project_root/entry["path"]
        if not path.is_file():
            missing.append(entry["path"])
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            changed.append(entry["path"])
    return dict(passed=not missing and not changed, files=len(record["files"]), missing=missing, changed=changed)


def inspect_readiness(model_root, calibration_path, board_review):
    models = {}
    for task in DIMENSIONS:
        try:
            model = ModelBundle.load(Path(model_root)/task)
            ready = model.task == task and model.deployable
            models[task] = dict(ready=ready, version=model.version, source_kind=model.source_kind,
                                state="real_data_model_present" if ready else "synthetic_or_wrong_task")
        except (OSError, ValueError, KeyError) as exc:
            models[task] = dict(ready=False, state=type(exc).__name__)
    try:
        calibration = Calibration.load(calibration_path)
        calibration_info = dict(ready=True, capture_mode=calibration.capture_mode, image_size=calibration.image_size)
    except (OSError, ValueError, KeyError) as exc:
        calibration_info = dict(ready=False, state=type(exc).__name__)
    review = {key: board_review.get(key) is True for key in REVIEW_FIELDS}
    ready = all(model["ready"] for model in models.values()) and calibration_info["ready"] and all(review.values())
    return dict(ready=ready, scope="local files and explicit review flags; no hardware probe",
                models=models, calibration=calibration_info, review=review, board_executed=False)
