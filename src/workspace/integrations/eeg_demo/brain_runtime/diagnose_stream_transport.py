"""Bounded framing-only check. Reports counters, never stores EEG samples."""

import argparse
import json
import os
import sys
import termios
import time

from cyton_guardianloop import configure_serial, packets, write_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True)
    parser.add_argument('--seconds', type=float, default=40.)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        raise ValueError('Check duration must be between 1 and 60 seconds')
    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    reader = None
    result = dict(frames=0, malformed_bytes=0, sequence_gaps=0,
                  receive_gaps_over_250ms=0, max_receive_gap_s=0.,
                  first_fault_after_s=None, source='physical_cyton_framing_only',
                  completed=False, max_delivery_age_ms=0., reader_batch_samples=10)
    started = None
    try:
        configure_serial(fd)
        write_command(fd, b's')
        time.sleep(.25)
        termios.tcflush(fd, termios.TCIFLUSH)
        write_command(fd, b'b')
        reader = packets(fd, 3., with_timing=True, reader_batch_samples=10)
        started = time.monotonic()
        previous_sequence = previous_at = None
        for packet, malformed, received_at in reader:
            now = time.monotonic()
            elapsed = now - started
            result['max_delivery_age_ms'] = max(result['max_delivery_age_ms'],
                                               max(0., now-received_at)*1000)
            gap = previous_sequence is not None and (packet[1] - previous_sequence) % 256 != 1
            result['frames'] += 1
            result['malformed_bytes'] += malformed
            result['sequence_gaps'] += int(gap)
            if previous_at is not None:
                interval = received_at - previous_at
                result['max_receive_gap_s'] = max(result['max_receive_gap_s'], interval)
                result['receive_gaps_over_250ms'] += int(interval > .25)
            if (gap or malformed) and result['first_fault_after_s'] is None:
                result['first_fault_after_s'] = elapsed
            previous_sequence, previous_at = packet[1], received_at
            if elapsed >= args.seconds:
                result['duration_s'] = elapsed
                result['frames_per_second'] = result['frames'] / elapsed
                result['completed'] = True
                break
    finally:
        # A timeout must retain its partial counters without becoming a pass.
        if started is not None and not result['completed']:
            result['duration_s'] = time.monotonic() - started
            result['frames_per_second'] = result['frames'] / max(result['duration_s'], 1e-9)
        error_type = sys.exc_info()[0]
        result['error_type'] = None if error_type is None else error_type.__name__
        print(json.dumps(result, sort_keys=True), flush=True)
        if reader is not None:
            reader.close()
        write_command(fd, b's')
        os.close(fd)


if __name__ == '__main__':
    main()
