"""Nonblocking, bounded taps of the single Cyton serial reader."""
import queue

import numpy as np


def decode_eeg_counts(packet):
    values = np.empty(8, dtype=np.int32)
    for channel in range(8):
        offset = 2+channel*3
        value = (packet[offset]<<16) | (packet[offset+1]<<8) | packet[offset+2]
        if value & 0x800000:
            value -= 1<<24
        values[channel] = value
    return values


class ReaderPacketSink:
    def __init__(self, context, capacity=128, batch_samples=1):
        if batch_samples not in (1, 10) or capacity < batch_samples:
            raise ValueError('Tap batch must be 1 or 10 and fit the packet capacity')
        self.pending = context.Queue(maxsize=capacity // batch_samples)
        self.offered = 0
        self.batch_samples = batch_samples
        self.batch = []

    def offer(self, packet, malformed, received_at):
        self.offered += 1
        self.batch.append((self.offered, packet, malformed, received_at))
        return self.flush() if len(self.batch) == self.batch_samples else True

    def flush(self):
        if not self.batch:
            return True
        message = self.batch[0] if self.batch_samples == 1 else tuple(self.batch)
        self.batch.clear()
        try:
            self.pending.put_nowait(message)
        except queue.Full:
            return False
        return True

    def close(self):
        self.pending.cancel_join_thread()
        self.pending.close()
