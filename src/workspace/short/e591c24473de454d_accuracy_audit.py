"""Observe independent cued selections without changing calibration or dwell gates."""
from dataclasses import replace
import json
import math


TARGETS = (0, 1, 2, 0, 2, 1) * 5
NAMES = ("左区", "中区", "右区")


class AccuracyAudit:
    trial_seconds = 5.0

    def __init__(self, path):
        self.path = path
        self.phase = "idle"
        self.rows = []
        self.current = None
        self.detail = ""
        self.outside_confirmations = 0
        self.stop_reason = None

    def start(self):
        if self.phase != "idle":
            return False
        self.phase = "running"
        self._next()
        self.save()
        return True

    def _next(self):
        index = len(self.rows)
        self.current = dict(trial=index + 1, target=TARGETS[index],
                            presented_s=None, confirmations=[])

    def tick(self, now):
        if self.phase != "running" or self.current["presented_s"] is None:
            return
        if now - self.current["presented_s"] < self.trial_seconds:
            return
        row = self.current
        events = row["confirmations"]
        row.update(first_correct=bool(events and events[0]["region"] == row["target"]),
                   missed=not events, wrong_confirmations=sum(e["region"] != row["target"] for e in events),
                   extra_confirmations=max(0, len(events) - 1), closed_s=now)
        self.rows.append(row)
        if len(self.rows) == len(TARGETS):
            self.phase, self.current = "complete", None
        else:
            self._next()
        self.save()

    def observe(self, region, event, now):
        """Called only after the unchanged Selection reports a confirmation."""
        self.tick(now)
        source = event.get("monotonic_ns")
        if (self.phase != "running" or self.current["presented_s"] is None or
                type(source) is not int or source / 1e9 < self.current["presented_s"]):
            self.outside_confirmations += 1
            self.save()
            return
        if type(region) is not int or region not in (0, 1, 2):
            raise ValueError("Invalid confirmed region")
        row = self.current
        row["confirmations"].append(dict(region=region, source_s=source / 1e9,
            received_s=now, response_ms=1000 * (now - row["presented_s"])))
        self.save()

    def view(self, view, now):
        self.tick(now)
        if self.phase == "idle":
            detail = "标定完成；按 PS_KEY0 开始左、中、右各 10 次计分"
        elif self.phase == "running":
            row = self.current
            left = self.trial_seconds if row["presented_s"] is None else max(0, self.trial_seconds - now + row["presented_s"])
            detail = "第 %d / 30 次：请看%s，保持到提示改变（%d 秒）" % (row["trial"], NAMES[row["target"]], math.ceil(left))
        elif self.phase == "complete":
            correct = sum(r["first_correct"] for r in self.rows)
            detail = "计分结束：首选正确 %d / 30；可以移开视线，等待汇总" % correct
        else:
            detail = "计分已中止；未完成试次不会冒充通过"
        self.detail = detail
        return replace(view, detail=detail)

    def presented(self, view, now):
        if (self.phase == "running" and self.current["presented_s"] is None and
                view.phase == "selection" and view.detail == self.detail):
            self.current["presented_s"] = now
            self.save()

    def cancel(self, reason):
        if self.phase == "running":
            self.phase, self.stop_reason = "cancelled", reason
            self.save()

    def snapshot(self):
        per_region = []
        for region in (0, 1, 2):
            rows = [r for r in self.rows if r["target"] == region]
            per_region.append(dict(region=region, completed=len(rows), planned=10,
                                   first_correct=sum(r["first_correct"] for r in rows)))
        correct = sum(r["first_correct"] for r in self.rows)
        return dict(phase=self.phase, completed=len(self.rows), planned=30, first_correct=correct,
            accuracy_all=correct / 30 if self.phase == "complete" else None,
            missed=sum(r["missed"] for r in self.rows),
            wrong_confirmations=sum(r["wrong_confirmations"] for r in self.rows),
            extra_confirmations=sum(r["extra_confirmations"] for r in self.rows),
            outside_confirmations=self.outside_confirmations, per_region=per_region,
            stop_reason=self.stop_reason, current=self.current, trials=self.rows,
            latency_origin="HDMI park call returned; software timing, not optical measurement",
            calibration_changed_during_test=False, physical_control=False,
            central_video_test="pending", page_transition_test="pending", look_away_test="pending")

    def save(self):
        part = self.path.with_suffix(".json.part")
        part.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        part.replace(self.path)
