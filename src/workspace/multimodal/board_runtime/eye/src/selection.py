"""Three horizontal regions driven only by fresh native gaze samples."""
from dataclasses import replace
import math
from guide import View


class Selection:
    dwell_seconds = 1.2
    settle_seconds = .2
    stale_seconds = .25
    # Full-height columns: this test does not assess vertical pointing accuracy.
    margin = .025

    def __init__(self):
        self.hover = self.selected = self.locked = -1
        self.candidate = -1
        self.candidate_since = self.dwell_since = None
        self.last_source = None
        self.last_received = None
        self.paused = False
        self.confirmations = 0
        self.progress = 0.0

    def clear_pending(self):
        self.hover = self.candidate = -1
        self.candidate_since = self.dwell_since = None
        self.progress = 0.0

    def toggle_pause(self):
        self.paused = not self.paused
        self.clear_pending()

    def update(self, event, now):
        return self._update(event, now, horizontal=False)

    def update_horizontal(self, event, now):
        """Derived horizontal coordinate from explicit board direction training."""
        return self._update(event, now, horizontal=True)

    def _update(self, event, now, horizontal):
        source = event.get("monotonic_ns")
        if type(source) is not int or source <= 0:
            self.clear_pending()
            return False
        source /= 1e9
        # Native and UI run on the same Linux CLOCK_MONOTONIC domain.
        if source > now + .01 or now-source > self.stale_seconds:
            self.clear_pending()
            return False
        if self.last_source is not None and source <= self.last_source:
            return False
        if self.last_source is not None and source-self.last_source > self.stale_seconds:
            self.clear_pending()
        self.last_source, self.last_received = source, now
        x, y = event.get("x"), event.get("y")
        vertical_bad = not horizontal and (type(y) not in (int,float) or
            not math.isfinite(y) or not 0 <= y <= 1)
        if (self.paused or event.get("valid") is not True or
            type(x) not in (int, float) or not math.isfinite(x) or
            not 0 <= x <= 1 or vertical_bad):
            self.clear_pending()
            return False
        column = min(2, int(x*3))
        # A small neutral strip prevents boundary flicker from becoming clicks.
        if abs(x-1/3) < self.margin or abs(x-2/3) < self.margin:
            self.clear_pending()
            return False
        if column != self.candidate:
            self.candidate, self.candidate_since = column, source
            self.hover, self.dwell_since, self.progress = -1, None, 0.0
        if source-self.candidate_since < self.settle_seconds:
            return False
        self.hover = column
        # A different region must be stably acquired before the old one rearms.
        if column != self.locked:
            self.locked = -1
        if self.locked == column:
            self.progress = 1.0
            return False
        if self.dwell_since is None:
            self.dwell_since = source
        self.progress = min(1.0, (source-self.dwell_since)/self.dwell_seconds)
        if self.progress >= 1:
            self.selected = self.locked = column
            self.confirmations += 1
            return True
        return False

    def view(self, now):
        fresh = self.last_source is not None and 0 <= now-self.last_source <= self.stale_seconds
        if not fresh:
            self.clear_pending()
        detail = "已暂停，按 PS_KEY1 继续" if self.paused else "看另一选区可再次选择" if self.locked == self.hover and self.hover >= 0 else "稳定看一个选区约 1.4 秒，进度满后确认" if self.hover >= 0 else "等待有效注视，请看左、中、右任一区"
        return replace(View(phase="selection", progress=round(self.progress, 2), detail=detail),
                       hover=self.hover, selected=self.selected,
                       confirmations=self.confirmations, paused=self.paused)
