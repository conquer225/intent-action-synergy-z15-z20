"""Minimal five-target SSVEP stimulus with presentation timestamp logging.

This is a bring-up tool, not a medically validated stimulus generator.  Stop
with Escape.  Do not use if flickering light may pose a health risk.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import QApplication, QWidget

from ssvep_core import DEFAULT_FREQUENCIES


class StimulusWindow(QWidget):
    def __init__(self, output: Path, duration_s: float, windowed: bool) -> None:
        super().__init__()
        self.output = output
        self.duration_s = duration_s
        self.started = time.perf_counter()
        self.frame_rows: list[tuple[int, float]] = []
        self.frame_index = 0
        self.setWindowTitle("Z15 SSVEP stimulus - Esc to stop")
        self.setCursor(Qt.BlankCursor)
        self.setStyleSheet("background: black")
        if windowed:
            self.resize(1280, 720)
        else:
            self.showFullScreen()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.update)
        self.timer.start(8)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.timer.stop()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(("frame_index", "elapsed_seconds"))
            writer.writerows(self.frame_rows)
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        elapsed = time.perf_counter() - self.started
        self.frame_rows.append((self.frame_index, elapsed))
        self.frame_index += 1
        if elapsed >= self.duration_s:
            QTimer.singleShot(0, self.close)
            return

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        painter.setFont(QFont("Arial", max(12, self.height() // 42)))
        width = self.width()
        height = self.height()
        size = max(80, min(width // 5, height // 3))
        positions = (
            (width // 5 - size // 2, height // 4 - size // 2),
            (width // 2 - size // 2, height // 4 - size // 2),
            (4 * width // 5 - size // 2, height // 4 - size // 2),
            (width // 3 - size // 2, 3 * height // 4 - size // 2),
            (2 * width // 3 - size // 2, 3 * height // 4 - size // 2),
        )
        for target, (frequency, (x, y)) in enumerate(zip(DEFAULT_FREQUENCIES, positions), 1):
            luminance = 0.5 * (1.0 + math.sin(2.0 * math.pi * frequency * elapsed))
            level = int(round(255.0 * luminance))
            painter.fillRect(x, y, size, size, QColor(level, level, level))
            painter.setPen(QColor(0, 200, 255))
            painter.drawText(x, y + size + 30, f"{target}: {frequency:.1f} Hz")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument(
        "--frame-log", type=Path, default=Path("output/ssvep_stimulus_frames.csv")
    )
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be positive")
    app = QApplication(sys.argv)
    window = StimulusWindow(args.frame_log, args.duration, args.windowed)
    window.show()
    return int(app.exec_())


if __name__ == "__main__":
    raise SystemExit(main())
