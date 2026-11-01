"""Mode selection and admission of fresh, generation-bound camera frames."""
from dataclasses import dataclass
import math
import numpy as np

MODES = (
    ('original', '原图'), ('neon', '霓虹轮廓'), ('trails', '彩色拖影'),
    ('motion', '运动分析'), ('gray', '灰度处理'), ('binary', '二值化'),
    ('median', '中值滤波'), ('sobel', 'Sobel 边缘检测'),
    ('equalize', '直方图均衡化'), ('pupil', '瞳孔定位'),
)
DEMO_MODES = ('neon', 'trails', 'motion')


@dataclass(frozen=True)
class Frame:
    source: str
    generation: int
    sequence: int
    captured: float
    rgb: np.ndarray


class VisionSession:
    def __init__(self, max_age=1.5, enabled_modes=None):
        names = [name for name, _ in MODES]
        enabled = tuple(names if enabled_modes is None else enabled_modes)
        if not enabled or len(set(enabled)) != len(enabled) or any(name not in names for name in enabled):
            raise ValueError('invalid enabled image modes')
        self.enabled_indices = tuple(names.index(name) for name in enabled)
        self.index = self.enabled_indices[0]
        self.generation = 0
        self.max_age = max_age
        self.last_sequence = -1
        self.latest = None
        self.reason = 'waiting'

    @property
    def source(self):
        return 'tobii' if self.index == 9 else 'ov5640'

    def next_mode(self):
        self.index = self.enabled_indices[(self.enabled_indices.index(self.index) + 1) % len(self.enabled_indices)]
        self.reset('source_switch')
        return self.snapshot()

    def reset(self, reason='reset'):
        self.generation += 1
        self.last_sequence = -1
        self.latest = None
        self.reason = reason

    def accept(self, frame, now):
        if (frame.source != self.source or frame.generation != self.generation
                or type(frame.sequence) is not int or frame.sequence <= self.last_sequence
                or not math.isfinite(now) or not math.isfinite(frame.captured)
                or not 0 <= now - frame.captured <= self.max_age
                or (self.latest is not None and frame.captured <= self.latest.captured)):
            return False
        rgb = np.asarray(frame.rgb)
        if (rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3
                or not 4 <= rgb.shape[0] <= 1080 or not 4 <= rgb.shape[1] <= 1920):
            return False
        image = np.array(rgb, copy=True, order='C')
        image.flags.writeable = False
        self.latest = Frame(frame.source, frame.generation, frame.sequence, frame.captured, image)
        self.last_sequence = frame.sequence
        self.reason = 'live'
        return True

    def current(self, now):
        if self.latest is not None and not 0 <= now-self.latest.captured <= self.max_age:
            self.latest = None
            self.reason = 'stale'
        return self.latest

    def snapshot(self):
        return dict(index=self.index, mode=MODES[self.index][0], label=MODES[self.index][1],
                    source=self.source, generation=self.generation, reason=self.reason,
                    physical_control=False, calibration_modified=False)
