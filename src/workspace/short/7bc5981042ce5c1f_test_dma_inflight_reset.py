"""Adversarial MMIO model: partial S2MM writes while a frame is in flight.

This is not the vendor AXI DMA RTL or an FPGA test. It checks the ARM adapter's
fail-closed ownership/recovery contract under delayed completion and reset.
"""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'pl_filter_candidate'))
from primary_filter_dma import PrimaryFilterDMA, SIGNATURE, IOC, _quarantined
from test_primary_filter_dma import GPIO, PARAMETERS, RegisterModel


class InFlightDMA(RegisterModel):
    def __init__(self):
        super().__init__()
        self.inject = False
        self.external_reset = False
        self.in_flight = False
        self.reset_ticks = 0
        self.poll_ticks = 0
        self.partial_writes = 0
        self.halt_observed_before_reset_done = False

    def write(self, address, value):
        if address == 0x28 and self.inject:
            self.writes.append((address, value))
            self.reg[address] = value
            self.reg[4] = self.reg[0x34] = 0
            self.in_flight = True
            self.buffers[1][:16] = 777777  # Partial result is never publishable.
            self.partial_writes = 16
            return
        if address == 0 and value == 4 and self.in_flight:
            self.writes.append((address, value))
            self.reg[0] = self.reg[0x30] = 4
            self.reset_ticks = 1_000_000 if self.reset_stuck else 5
            return
        super().write(address, value)

    def sleep(self, duration):
        self.now += duration
        if self.reset_ticks:
            self.reset_ticks -= 1
            if self.reset_ticks:
                # An old transfer may still alter RX while DMA reset is pending.
                if self.partial_writes < len(self.buffers[1]):
                    self.buffers[1][self.partial_writes] = 888888
                    self.partial_writes += 1
                self.reg[4] = self.reg[0x34] = IOC
            else:
                self.reg.update({0:0, 0x30:0, 4:1, 0x34:1})
                self.in_flight = False
                self.inject = False
                self.status = SIGNATURE | 1
            return
        if self.in_flight and self.external_reset:
            self.poll_ticks += 1
            if self.poll_ticks == 3:
                # Shared PL reset was asserted during the transfer.
                self.status = SIGNATURE | 1
                self.reg[4] = self.reg[0x34] = 1


class InFlightResetTests(unittest.TestCase):
    def setUp(self):
        self.model = InFlightDMA()
        self.driver = PrimaryFilterDMA(self.model, GPIO(self.model),
                                       self.model.allocate, PARAMETERS, timeout=.001,
                                       clock=self.model.clock, sleep=self.model.sleep,
                                       test_only=True)
        self.driver.reset()
        self.samples = np.random.default_rng(410).normal(size=(10,8))*35

    def tearDown(self):
        self.model.external_reset = False
        self.model.reset_stuck = False
        if self.driver.bus_ownership_uncertain:
            with self.assertRaises(RuntimeError):
                self.driver.close()
            self.assertIn(id(self.driver), _quarantined)
            self.assertFalse(self.driver.rx.closed)
            _quarantined.pop(id(self.driver))  # Test-model cleanup, not a recovery API.
        else:
            self.driver.close()
            self.assertNotIn(id(self.driver), _quarantined)

    def assert_fail_closed(self):
        self.assertFalse(self.driver.ready)
        self.assertIsNone(self.driver.origin)
        self.assertTrue(self.driver.bus_ownership_uncertain)
        self.assertIn(id(self.driver), _quarantined)
        self.assertEqual(self.driver.rx.events.count('invalidate'), 0)
        with self.assertRaises(RuntimeError):
            self.driver.process(self.samples)
        writes_before = list(self.model.writes)
        with self.assertRaises(RuntimeError):
            self.driver.reset()
        self.assertEqual(self.model.writes,writes_before)
        self.assertFalse(self.driver.rx.closed)

    def test_timeout_after_partial_s2mm_and_delayed_soft_reset(self):
        self.model.inject = True
        with self.assertRaises(TimeoutError):
            self.driver.process(self.samples)
        self.assertGreaterEqual(self.model.partial_writes, 16)
        self.assert_fail_closed()

    def test_external_pl_reset_during_inflight_transfer(self):
        self.model.inject = self.model.external_reset = True
        with self.assertRaises(RuntimeError):
            self.driver.process(self.samples)
        self.assertEqual(self.model.poll_ticks, 3)
        self.model.external_reset = False
        self.assert_fail_closed()

    def test_stuck_dma_reset_never_releases_partial_buffer(self):
        self.model.inject = True
        with self.assertRaises(TimeoutError):
            self.driver.process(self.samples)
        self.model.reset_stuck = True
        self.assert_fail_closed()


if __name__ == '__main__':
    unittest.main()
