"""Register-model tests, not a substitute for vendor DMA simulation or hardware."""
from pathlib import Path
import unittest
import numpy as np
from fixed_sos import FixedSOS, quantize
from primary_filter_dma import PrimaryFilterDMA, SIGNATURE, IOC, _quarantined

SOS = Path(__file__).resolve().parents[1]/'output/pl_primary_filter_q31_20260927/sos_float.npy'
PARAMETERS = dict(C_INCLUDE_MM2S='1', C_INCLUDE_S2MM='1', C_INCLUDE_SG='0',
                  C_M_AXIS_MM2S_TDATA_WIDTH='64', C_S_AXIS_S2MM_TDATA_WIDTH='64', C_ADDR_WIDTH='32')


class Buffer(np.ndarray):
    def __new__(cls, shape, dtype, address):
        obj = np.zeros(shape, dtype=dtype).view(cls)
        obj.physical_address = address
        obj.closed = False
        obj.events = []
        return obj

    def flush(self):
        self.events.append('flush')

    def invalidate(self):
        self.events.append('invalidate')

    def freebuffer(self):
        self.closed = True

    def close(self):
        raise AssertionError('PYNQ close() is a no-op; use freebuffer()')


class RegisterModel:
    def __init__(self):
        self.reg = {0:0, 0x30:0, 4:1, 0x34:1}
        self.status = SIGNATURE | 1
        self.buffers = []
        self.writes = []
        self.mode = 'normal'
        self.reset_stuck = False
        self.now = 0.
        self.kernel = FixedSOS(np.load(SOS))

    def allocate(self, shape, dtype):
        buf = Buffer(shape, dtype, 0x10000+len(self.buffers)*0x1000)
        self.buffers.append(buf)
        return buf

    def clock(self):
        return self.now

    def sleep(self, duration):
        self.now += duration

    def read(self, address):
        return self.reg.get(address, 0)

    def write(self, address, value):
        self.writes.append((address, value))
        if address in (4, 0x34):
            self.reg[address] &= ~(value & 0x7000)
            return
        self.reg[address] = value
        if address == 0 and value == 4:
            if not self.reset_stuck:
                self.reg.update({0:0, 0x30:0, 4:1, 0x34:1})
        elif address in (0, 0x30) and value == 1:
            self.reg[address+4] = 2
        elif address == 0x58:
            self.reg[0x34] = 0
        elif address == 0x28:
            assert self.reg[0x58] == 640 and self.reg[0x34] == 0, 'RX must start first'
            assert self.buffers[0].events[-1] == 'flush'
            assert self.buffers[1].events[-1] == 'flush'
            self.reg[4] = 0
            if self.mode == 'timeout':
                return
            if self.mode == 'dma_error':
                self.reg[0x34] = 0x20
                return
            if self.mode == 'filter_fault':
                self.status |= 2
                return
            if self.mode == 'halted':
                self.reg[4] = 1
                return
            self.buffers[1][:] = self.kernel.process_quantized(self.buffers[0].reshape(10,8)).reshape(-1)
            self.reg[4] = self.reg[0x34] = IOC | 2
            if self.mode == 'short_frame':
                self.reg[0x58] = 632
            if self.mode == 'bad_sign':
                self.buffers[1][0] = 1 << 40
            if self.mode == 'not_idle':
                self.reg[0x34] = IOC


class GPIO:
    def __init__(self, model):
        self.model = model

    def read(self, address):
        assert address == 8
        return self.model.status

    def write(self, address, value):
        if address == 0:
            if value & 1:
                self.model.kernel.reset()
            self.model.status = SIGNATURE | (value & 1)


class DMATests(unittest.TestCase):
    def setUp(self):
        self.model = RegisterModel()
        self.driver = PrimaryFilterDMA(self.model, GPIO(self.model), self.model.allocate,
                                      PARAMETERS, timeout=.001, clock=self.model.clock, sleep=self.model.sleep,
                                      test_only=True)
        self.driver.reset()
        self.samples = np.random.default_rng(91).normal(size=(30,8))*100

    def tearDown(self):
        self.model.reset_stuck = False
        if self.driver.bus_ownership_uncertain:
            with self.assertRaises(RuntimeError):
                self.driver.close()
            self.assertIn(id(self.driver), _quarantined)
            self.assertFalse(self.driver.tx.closed)
            self.assertFalse(self.driver.rx.closed)
            _quarantined.pop(id(self.driver))  # Test-model teardown, not a recovery API.
        else:
            self.driver.close()
            self.assertNotIn(id(self.driver), _quarantined)

    def test_continuous_bit_exact_and_receive_first(self):
        expected = FixedSOS(np.load(SOS)).process_quantized(quantize(self.samples-self.samples[0],16,40))/65536
        actual = np.concatenate([self.driver.process(row) for row in np.split(self.samples,3)])
        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(self.driver.rx.events.count('invalidate'), 3)
        starts = [a for a,v in self.model.writes if a in (0x58,0x28)]
        self.assertEqual(starts, [0x58,0x28]*3)

    def test_reset_restarts_origin_and_state(self):
        first = self.driver.process(self.samples[:10])
        self.driver.reset()
        np.testing.assert_array_equal(first, self.driver.process(self.samples[:10]))

    def test_faults_reject_and_forbid_pl_only_rearm(self):
        for mode in ('timeout','dma_error','filter_fault','halted','short_frame','bad_sign','not_idle'):
            with self.subTest(mode=mode):
                model = RegisterModel()
                driver = PrimaryFilterDMA(model,GPIO(model),model.allocate,PARAMETERS,
                                          timeout=.001,clock=model.clock,sleep=model.sleep,test_only=True)
                driver.reset()
                model.mode = mode
                with self.assertRaises((RuntimeError,TimeoutError)):
                    driver.process(self.samples[:10])
                self.assertFalse(driver.ready)
                self.assertTrue(driver.bus_ownership_uncertain)
                self.assertIn(id(driver), _quarantined)
                self.assertFalse(driver.rx.closed)
                with self.assertRaises(RuntimeError):
                    driver.process(self.samples[:10])
                with self.assertRaises(RuntimeError):
                    driver.reset()
                with self.assertRaises(RuntimeError):
                    driver.close()
                self.assertFalse(driver.rx.closed)
                _quarantined.pop(id(driver))  # Discard fake session only.

    def test_stuck_reset_does_not_free_buffers(self):
        self.model.mode = 'timeout'
        with self.assertRaises(TimeoutError):
            self.driver.process(self.samples[:10])
        self.model.reset_stuck = True
        with self.assertRaises(RuntimeError):
            self.driver.close()
        self.assertFalse(self.driver.tx.closed)
        self.assertFalse(self.driver.rx.closed)
        self.assertIn(id(self.driver), _quarantined)

    def test_stuck_quiesce_latches_fault_before_new_transfer(self):
        self.model.reset_stuck = True
        with self.assertRaises(TimeoutError):
            self.driver.reset()
        self.assertTrue(self.driver.bus_ownership_uncertain)
        self.assertFalse(self.driver.ready)
        self.assertIn(id(self.driver), _quarantined)
        with self.assertRaises(RuntimeError):
            self.driver.reset()
        with self.assertRaises(RuntimeError):
            self.driver.close()
        self.assertFalse(self.driver.tx.closed)
        self.assertFalse(self.driver.rx.closed)

    def test_stuck_quiesce_on_close_retains_buffers(self):
        self.model.reset_stuck = True
        with self.assertRaises(TimeoutError):
            self.driver.close()
        self.assertTrue(self.driver.bus_ownership_uncertain)
        self.assertIn(id(self.driver), _quarantined)
        self.assertFalse(self.driver.tx.closed)
        self.assertFalse(self.driver.rx.closed)

    def test_reject_invalid_input_before_dma(self):
        for value in (np.zeros((8,10)), np.full((10,8),np.nan), np.full((10,8),np.inf)):
            with self.assertRaises(ValueError):
                self.driver.process(value)
        huge = np.zeros((10,8)); huge[1] = 1e8
        with self.assertRaises(OverflowError):
            self.driver.process(huge)
        self.assertIsNone(self.driver.origin)
        self.assertNotIn(0x28,[a for a,v in self.model.writes])

    def test_wrong_signature_disables_backend(self):
        self.model.status = 0
        with self.assertRaises(RuntimeError):
            self.driver.process(self.samples[:10])
        self.assertFalse(self.driver.ready)

    def test_old_overlay_rejected_before_allocation(self):
        for key, value in [('C_INCLUDE_S2MM','0'), ('C_M_AXIS_MM2S_TDATA_WIDTH','128'), ('C_INCLUDE_SG','1')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                PrimaryFilterDMA(self.model,GPIO(self.model),self.model.allocate,{**PARAMETERS,key:value},test_only=True)
        self.assertEqual(len(self.model.buffers),2)

    def test_physical_mode_rejected_before_mmio_or_allocation(self):
        model = RegisterModel()
        with self.assertRaisesRegex(RuntimeError, 'Physical DMA disabled'):
            PrimaryFilterDMA(model, GPIO(model), model.allocate, PARAMETERS)
        self.assertEqual(model.buffers, [])
        self.assertEqual(model.writes, [])

    def test_stale_interrupt_cannot_complete_timeout(self):
        self.model.reg[4] = self.model.reg[0x34] = IOC | 2
        self.model.mode = 'timeout'
        with self.assertRaises(TimeoutError):
            self.driver.process(self.samples[:10])
        self.assertEqual(self.driver.rx.events.count('invalidate'),0)
        self.assertIn((4,0x7000),self.model.writes)

    def test_close_is_idempotent_and_disables_processing(self):
        self.driver.close()
        self.driver.close()
        self.assertTrue(self.driver.rx.closed)
        with self.assertRaises(RuntimeError):
            self.driver.process(self.samples[:10])
        with self.assertRaises(RuntimeError):
            self.driver.reset()

    def test_allocation_failure_releases_first_buffer(self):
        allocated = []
        def allocate(shape,dtype):
            if allocated:
                raise MemoryError('test allocation failure')
            allocated.append(Buffer(shape,dtype,0x10000))
            return allocated[0]
        with self.assertRaises(MemoryError):
            PrimaryFilterDMA(self.model,GPIO(self.model),allocate,PARAMETERS,test_only=True)
        self.assertTrue(allocated[0].closed)

    def test_invalid_buffer_contract_closes_both(self):
        for address in (3, 2**32-8):
            allocated = []
            def allocate(shape,dtype):
                allocated.append(Buffer(shape,dtype,address))
                return allocated[-1]
            with self.assertRaises(ValueError):
                PrimaryFilterDMA(self.model,GPIO(self.model),allocate,PARAMETERS,test_only=True)
            self.assertTrue(all(b.closed for b in allocated))


if __name__ == '__main__':
    unittest.main()
