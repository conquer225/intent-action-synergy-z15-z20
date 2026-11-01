"""Linux publication parity, including current timestamps and invalidation fields."""
import json
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from telemetry_json import WaveformJSONCache


@unittest.skipUnless(os.name == 'posix', 'Publication imports Linux acquisition code')
class TelemetryPublicationTests(unittest.TestCase):
    def test_cached_publication_matches_full_payload(self):
        from cyton_guardianloop import publish_telemetry
        values = np.random.default_rng(53).normal(0, 50, (2000, 8))
        cache = WaveformJSONCache()
        with tempfile.TemporaryDirectory() as directory:
            reference, candidate = (Path(directory)/name for name in ('reference.json', 'candidate.json'))
            for index, start in enumerate((0, 63, 188, 188, 800, 0)):
                sample = values[start:start+625]
                args = (sample, sample*1000, start+625)
                metadata = (start*2+1250, 3, 1, 1, 0, 0,
                            {'calibrated': True}, {'valid': index < 2}, 100.+index,
                            {'reader_queue_delay_ms': 600 if index==2 else 0})
                publish_telemetry(*args, reference, *metadata)
                publish_telemetry(*args, candidate, *metadata, waveform_cache=cache)
                self.assertEqual(json.loads(reference.read_text()), json.loads(candidate.read_text()))
                self.assertEqual(json.loads(candidate.read_text())['updated_at'], 100.+index)
            before = candidate.read_bytes()
            bad = sample.copy(); bad[-1, 0] = np.nan
            for destination, waveform_cache in ((reference, None), (candidate, cache)):
                with self.assertRaises(ValueError):
                    publish_telemetry(bad, sample*1000, 625, destination, *metadata,
                                      waveform_cache=waveform_cache)
            self.assertEqual(candidate.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
