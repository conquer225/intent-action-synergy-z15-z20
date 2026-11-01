"""Fresh calibrated horizontal gaze, center rearm, one event per deliberate dwell."""
import math


class EyeGate:
    StaleSeconds = 0.25
    DwellSeconds = 1.2
    CenterSeconds = 0.6

    def __init__(self):
        self.armed = False
        self.last_source = None
        self.region = "none"
        self.since = None
        self.center_ready = False
        self.wait_center = True
        self.progress = 0.0
        self.last_action = None

    def disarm(self):
        self.armed = False
        self.wait_center = True

    def clear(self):
        self.disarm()
        self.last_source = None
        self.region = "none"
        self.since = None
        self.center_ready = False
        self.progress = 0.0

    def fresh(self, now):
        return self.last_source is not None and 0 <= now - self.last_source <= self.StaleSeconds

    def arm(self, now):
        if not self.fresh(now) or not self.center_ready:
            raise ValueError("Look at the center until it is ready before enabling control")
        self.armed = True
        self.wait_center = False

    def update(self, event, now):
        stamp = event.get("monotonic_ns")
        x = event.get("x")
        if (event.get("kind") != "horizontal_gaze" or event.get("valid") is not True
                or type(stamp) is not int or stamp <= 0 or type(x) not in (int, float)
                or not math.isfinite(x) or not 0 <= x <= 1):
            self.clear()
            return None
        source = stamp / 1e9
        if source > now + 0.01 or now - source > self.StaleSeconds:
            self.clear()
            return None
        if self.last_source is not None and source <= self.last_source:
            return None
        if self.last_source is not None and source - self.last_source > self.StaleSeconds:
            self.clear()
        self.last_source = source
        region = "center" if 0.4 <= x <= 0.6 else "left" if x <= 0.25 else "right" if x >= 0.75 else "neutral"
        if region != self.region:
            self.region, self.since = region, source
            self.progress = 0.0
        duration = source - self.since
        self.center_ready = region == "center" and duration >= self.CenterSeconds
        if self.center_ready:
            self.wait_center = False
        if region not in {"left", "right"} or self.wait_center or not self.armed:
            self.progress = 0.0
            return None
        self.progress = min(1.0, duration / self.DwellSeconds)
        if duration < self.DwellSeconds:
            return None
        if self.last_action is not None and source - self.last_action < 2.3:
            return None
        self.last_action = source
        self.wait_center = True
        self.progress = 0.0
        return "PREV" if region == "left" else "NEXT"
