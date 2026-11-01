"""Independent debounced gestures and view navigation; no compute ownership."""


class _Key:
    def __init__(self):
        self.candidate = self.stable = None
        self.since = self.pressed_at = 0.
        self.armed = self.fired = False

    def update(self, pressed, now, *, long_enabled):
        event = None
        if pressed != self.candidate:
            self.candidate, self.since = pressed, now
        if self.stable != self.candidate and now-self.since >= .05:
            self.stable = self.candidate
            if not pressed:
                if self.armed and self.pressed_at and not self.fired:
                    event = 'short'
                self.armed, self.pressed_at, self.fired = True, 0., False
            elif self.armed:
                self.pressed_at, self.fired = now, False
        if (long_enabled and self.armed and self.stable and self.candidate
                and self.pressed_at and not self.fired and now-self.pressed_at >= .8):
            self.fired, event = True, 'long'
        return event


class KeyGestures:
    def __init__(self):
        self.keys = (_Key(), _Key())

    def update(self, key1_pressed, key2_pressed, now):
        events = []
        for index, (key, pressed) in enumerate(zip(self.keys, (key1_pressed, key2_pressed))):
            event = key.update(bool(pressed), now, long_enabled=index == 0)
            if event:
                events.append('key%d_%s' % (index+1, event))
        return events


class Navigation:
    PAGES = ('overview', 'emotion', 'fatigue', 'depth', 'cloud', 'person_dog', 'sound', 'audio', 'adda')

    def __init__(self):
        self.page, self.detail = 'overview', 0
        self.version=0

    def apply(self, event):
        if event == 'key1_short':
            self.page = self.PAGES[(self.PAGES.index(self.page)+1) % len(self.PAGES)]
            self.detail = 0
        elif event == 'key1_long':
            self.page, self.detail = 'overview', 0
        elif event == 'key2_short':
            self.detail = (self.detail+1) % (3 if self.page in ('sound', 'cloud') else 2)
        else:
            raise ValueError('unknown key gesture')
        self.version+=1
