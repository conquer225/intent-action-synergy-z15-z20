"""Navigator PS_KEY1/PS_KEY2 polling from the factory GPIO mapping."""
from pathlib import Path
import time


class KeyDebouncer:
    def __init__(self, stable_seconds=.05):
        self.stable_seconds = stable_seconds
        self.candidate = 0
        self.candidate_since = 0.0
        self.stable = 0

    def update(self, previous_pressed, next_pressed, now):
        candidate = 0 if previous_pressed == next_pressed else (-1 if previous_pressed else 1)
        if candidate != self.candidate:
            self.candidate, self.candidate_since = candidate, now
            return 0
        if candidate != self.stable and now - self.candidate_since >= self.stable_seconds:
            self.stable = candidate
            return candidate
        return 0


class NavigatorKeys:
    """PS GPIO12 is previous; PS GPIO11 is next. Both are active low."""
    def __init__(self, gpio_root='/sys/class/gpio'):
        self.root = Path(gpio_root)
        chips = []
        for chip in self.root.glob('gpiochip*'):
            label = (chip / 'label').read_text().strip().lower()
            width = int((chip / 'ngpio').read_text())
            if 'zynq' in label and width >= 54:
                chips.append(chip)
        if len(chips) != 1:
            raise ValueError('expected one Zynq PS GPIO controller')
        base = int((chips[0] / 'base').read_text())
        self.lines = []
        self.owned = []
        try:
            for offset in (12, 11):
                number = base + offset
                line = self.root / ('gpio{}'.format(number))
                owned = not line.exists()
                if owned:
                    (self.root / 'export').write_text(str(number))
                    end = time.monotonic() + 1
                    while not line.exists():
                        if time.monotonic() > end:
                            raise TimeoutError('GPIO export timed out')
                        time.sleep(.01)
                    (line / 'direction').write_text('in')
                self.lines.append(line)
                if owned:
                    self.owned.append(number)
        except BaseException:
            self.close()
            raise
        self.debouncer = KeyDebouncer()

    def poll(self):
        states = self.read_pressed()
        return self.debouncer.update(states[0], states[1], time.monotonic())

    def read_pressed(self):
        return tuple(line.joinpath('value').read_text().strip() == '0' for line in self.lines)

    def close(self):
        for number in getattr(self, 'owned', []):
            (self.root / 'unexport').write_text(str(number))
        self.owned = []
