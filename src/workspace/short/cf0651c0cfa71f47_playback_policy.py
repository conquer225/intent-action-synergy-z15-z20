"""Explicit session lifetime and bounded diagnostics for user-controlled display."""
class RecentSamples(list):
    def __init__(self, limit=4096):
        super().__init__()
        self.limit = limit
        self.discarded = 0

    def append(self, value):
        if len(self) >= self.limit:
            remove = max(1, self.limit // 4)
            del self[:remove]
            self.discarded += remove
        super().append(value)


def session_deadline(state, live, started):
    if state.get('user_controlled') is True:
        if not live or state.get('unified_system') is not True:
            raise ValueError('User-controlled lifetime requires the live unified display')
        return None
    return started + min(900 if live else 180, int(state.get('seconds', 180)))


def recovery_reason(active, row, now, started):
    if not active:
        return 'display_process_exited'
    if row.get('state') == 'error':
        return 'display_reported_error'
    stamp = row.get('updated_monotonic')
    if isinstance(stamp, (int, float)) and 0 <= now - stamp <= 20:
        return None
    if row.get('state') == 'starting' and now - started <= 240:
        return None
    return 'display_heartbeat_expired'
