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
    def __init__(self, context, capacity=128):
        self.pending = context.Queue(maxsize=capacity)
        self.offered = 0

    def offer(self, packet, malformed, received_at):
        self.offered += 1
        try:
            self.pending.put_nowait((self.offered, packet, malformed, received_at))
        except queue.Full:
            return False
        return True

    def close(self):
        self.pending.cancel_join_thread()
        self.pending.close()
