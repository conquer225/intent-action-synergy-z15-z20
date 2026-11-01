"""Event audit for isolated SEED replay; never imported by the live service."""

import json
import time
from pathlib import Path

from seed_shadow import SeedShadow


class AuditedSeedShadow(SeedShadow):
    def __init__(self, model_path, channel_map, *, status_path, audit_path):
        self.audit_path = Path(audit_path)
        super().__init__(model_path, channel_map, source='replay', status_path=status_path)

    def publish(self, event):
        super().publish(event)
        with self.audit_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({
                'event': event, 'sequence_gaps': self.gaps,
                'last_gap': self.last_gap,
                'published_monotonic': time.monotonic(),
                'input_age_ms': None if self.last_packet is None else
                    1000 * (time.monotonic() - self.last_packet),
            }, allow_nan=False) + '\n')
