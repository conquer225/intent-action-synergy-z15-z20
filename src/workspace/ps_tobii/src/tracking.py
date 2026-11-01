"""Advisory sensor telemetry; never grants calibration success."""
import math

class Tracking:
    def __init__(self, reference_cm=None):
        self.updated = None
        self.event = None
        self.reference_cm = reference_cm

    def update(self, event, now):
        n = event.get("samples")
        if type(n) is not int or n <= 0:
            return False
        for key in ("left", "right", "pupil_left", "pupil_right"):
            v = event.get(key)
            if type(v) is not int or not 0 <= v <= n:
                return False
        distance = event.get("distance_mm")
        if distance is not None and (type(distance) not in (int,float) or
            not math.isfinite(distance) or distance <= 0):
            return False
        self.event = dict(event)
        self.updated = now
        return True

    def lines(self, now):
        reference = ("上次可用参考 %g～%g cm · " % self.reference_cm
                     if self.reference_cm is not None else "")
        if self.updated is None or now-self.updated > 1.5:
            return ("距离 未知 · 眼部状态：等待新数据", reference+"先调整位置，再开始标定")
        e = self.event
        distance = "未知" if e["distance_mm"] is None else "约 %.1f cm" % (e["distance_mm"]/10)
        def percent(key): return round(100*e[key]/e["samples"])
        return ("距离 %s · 左眼检测 %d%% / 右眼检测 %d%%" % (distance,percent("left"),percent("right")),
                reference+"瞳孔可用：左 %d%% / 右 %d%%" % (percent("pupil_left"),percent("pupil_right")))
