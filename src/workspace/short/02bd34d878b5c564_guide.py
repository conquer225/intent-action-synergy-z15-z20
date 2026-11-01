"""Display contract for timed calibration guidance; no invented device results."""
from dataclasses import dataclass
import math

POINTS = ((.5,.5), (.15,.25), (.5,.25), (.85,.25),
          (.85,.5), (.85,.75), (.5,.75), (.15,.75), (.15,.5))
# Three x positions, with a small vertical spread for the OEM's 2D fit.
# Whether this firmware accepts three points must still be measured.
HORIZONTAL_POINTS = ((.5,.4), (.15,.6), (.85,.6))
FIVE_POINTS = ((.5,.5), (.15,.25), (.85,.25), (.85,.75), (.15,.75))
DIRECTION_POINTS = ((.5,.5),(.15,.5),(.85,.5))
PREPARE_SECONDS = 5
SETTLE_SECONDS = 1
COLLECT_SECONDS = 3
POINT_TIMEOUT_SECONDS = 10

@dataclass(frozen=True)
class View:
    phase: str = "ready"
    point: int = 0
    remaining: int = 0
    progress: float = 0
    detail: str = ""
    preview: bool = False
    tracking: tuple = ()
    hover: int = -1
    selected: int = -1
    confirmations: int = 0
    paused: bool = False

class Guide:
    """Backend-neutral view state. All times are host monotonic seconds.

    prepare -> settle -> collect -> waiting -> compute -> complete/failed.
    A collect ACK permits advancing; completion additionally requires a
    calibrated result and real positive gaze samples. Preview never calibrates.
    """
    def __init__(self, relaxed=False, points=POINTS, diagnostic_seconds=15,collect_seconds=COLLECT_SECONDS):
        self.points = points
        self.diagnostic_seconds = diagnostic_seconds
        self.collect_seconds = collect_seconds
        self.settle_seconds = 2 if relaxed else SETTLE_SECONDS
        self.point_timeout = 35 if relaxed else POINT_TIMEOUT_SECONDS
        self.phase = "ready"
        self.started = 0.0
        self.point_started = 0.0
        self.point = 0
        self.detail = ""
        self.preview = False
        self.ack = None

    def start(self, now, preview=False):
        if self.phase not in ("ready", "complete", "failed", "cancelled", "positioning"):
            raise ValueError("A guide is already running")
        self.phase, self.started = "prepare", now
        self.point, self.detail, self.preview, self.ack = 0, "", preview, None

    def response(self, point, accepted):
        if self.phase in ("collect", "waiting") and point == self.point:
            self.ack = bool(accepted)

    def result(self, calibrated, valid_samples):
        if self.phase != "compute":
            return
        if calibrated and type(valid_samples) is int and valid_samples > 0:
            self.phase = "complete"
            self.detail = "校准已应用，已收到有效注视；识别精度仍需验证"
        else:
            self.phase = "failed"
            self.detail = "未取得可验证的校准结果，请检查位置后重试"

    def cancel(self):
        self.phase, self.detail = "cancelled", "本次已停止，可以移开视线"

    def tick(self, now):
        if self.phase == "prepare" and now-self.started >= PREPARE_SECONDS:
            self.phase, self.started, self.point_started = "settle", now, now
        elif self.phase == "settle" and now-self.started >= self.settle_seconds:
            self.phase, self.started, self.ack = "collect", now, None
        elif self.phase in ("collect", "waiting"):
            elapsed = now-self.point_started
            if self.preview and now-self.started >= self.collect_seconds:
                self.ack = True
            if self.ack is False:
                self.phase, self.detail = "failed", "模组未接受本点，请检查位置后重试"
            elif elapsed >= self.point_timeout:
                self.phase, self.detail = "failed", "单点等待超过 %d 秒，本次已停止" % self.point_timeout
            elif now-self.started >= self.collect_seconds:
                if self.ack is True:
                    self.point += 1
                    if self.point == len(self.points):
                        self.phase, self.started = "compute", now
                    else:
                        self.phase, self.started, self.point_started = "settle", now, now
                        self.detail = ""
                else:
                    self.phase = "waiting"
        elif self.phase == "compute":
            if self.preview and now-self.started >= 2:
                self.phase, self.detail = "complete", "演练结束；没有采样，也没有改写校准"
            elif now-self.started >= 45:
                self.phase, self.detail = "failed", "校准处理超过 45 秒，本次已停止"
        duration = {"prepare": PREPARE_SECONDS, "settle": self.settle_seconds,
                    "collect": self.collect_seconds}.get(self.phase, 0)
        elapsed = now-self.started
        remaining = max(0, math.ceil(duration-elapsed)) if duration else 0
        if self.phase == "waiting":
            remaining = max(0, math.ceil(self.point_timeout-(now-self.point_started)))
        if self.phase == "diagnostic":
            remaining = max(0, math.ceil(self.diagnostic_seconds-elapsed))
        return View(self.phase, self.point, remaining,
                    min(1, max(0, elapsed/duration)) if duration else 0,
                    self.detail, self.preview)
