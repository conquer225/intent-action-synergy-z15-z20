"""Compile the actual HLS C++ and compare its public memory interface."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/workspace/integrations'))
from pl_accel.eeg import EEGModel, EEGReference, BANDS
from pl_accel.mapping import MapScene, render_reference
from pl_accel.backend import MapHardware, EEGHardware
from pl_accel.view import MapView
from test_pl_eeg import identity_model

HLS = Path(__file__).resolve().parents[1] / 'src/workspace/integrations/pl_accel/hls'


class HLSMemoryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='intent_hls_')
        cls.library = Path(cls.directory.name) / ('kernels.dll' if sys.platform == 'win32' else 'kernels.so')
        subprocess.run([shutil.which('g++') or 'g++', '-std=c++14', '-shared', '-O2',
                        '-Wno-unknown-pragmas', str(HLS/'eeg.cpp'), str(HLS/'map.cpp'), '-o', str(cls.library)], check=True,
                       capture_output=True)
        cls.dll = ctypes.CDLL(str(cls.library))
        pointer = np.ctypeslib.ndpointer(dtype=np.int32, flags='C_CONTIGUOUS')
        cls.dll.z15_fbcsp.argtypes = [pointer, pointer, pointer, ctypes.c_uint, ctypes.c_uint]
        cls.dll.z15_fbcsp.restype = None
        cls.dll.z20_map.argtypes = [pointer]*5
        cls.dll.z20_map.restype = None

    @classmethod
    def tearDownClass(cls):
        # A loaded Windows DLL stays owned until the interpreter exits.
        if sys.platform != 'win32':
            cls.directory.cleanup()
        else:
            cls.directory._finalizer.detach()

    def compare(self, model, samples):
        parameters, output = model.parameter_words(), np.zeros(16, np.int32)
        reference = EEGReference(model)
        self.dll.z15_fbcsp(np.zeros(8, np.int32), parameters, output, 0, 1)
        for offset in range(0, len(samples), min(50, model.hop)):
            chunk = np.ascontiguousarray(samples[offset:offset+min(50, model.hop)], np.int32)
            expected = reference.feed(chunk)
            self.dll.z15_fbcsp(chunk.ravel(), parameters, output, len(chunk), 0)
            self.assertEqual(bool(output[1] & 1), bool(expected))
            if expected:
                result = expected[-1]
                np.testing.assert_array_equal(output[8:14], result['features'])
                score = (int(output[6]) << 32) | (int(output[5]) & 0xffffffff)
                self.assertEqual(score, result['score_q24'])
                self.assertEqual(bool(output[1] & 2), result['valid'])
                self.assertEqual(int(output[2]), result['sample_count'])
                self.assertEqual(int(output[3]), result['window_count'])

    def test_worked_csp_case(self):
        x = np.zeros((6, 8), np.int32)
        x[:, 2] = [256, -256]*3;x[:, 3] = [512, -512]*3
        self.compare(identity_model(), x)

    def test_three_band_stream_and_window_hops(self):
        sos = np.asarray([signal.butter(2, band, btype='bandpass', fs=250, output='sos')
                          for band in BANDS])
        coefficients = np.rint(sos[:, :, [0, 1, 2, 4, 5]]*2**28).astype(np.int32)
        csp = np.rint(np.random.default_rng(17).uniform(-.1, .1, (3, 2, 8))*2**14).astype(np.int32)
        model = EEGModel(coefficients, csp, [11, -7, 17, -9, 5, -3], -123456, window=64, hop=16)
        x = np.random.default_rng(23).integers(-10000, 10001, (320, 8), dtype=np.int32)
        self.compare(model, x)

    def test_point_cloud_depth_clipping_and_trajectory_pixels(self):
        rng = np.random.default_rng(71)
        xyz = rng.uniform([-3, -3, -.5], [3, 3, 6], (200, 3))
        colors = rng.integers(0, 256, (200, 3), dtype=np.uint8)
        scene = MapScene(xyz, colors=colors, trajectory=[[-5, -1, 2], [0, 1, 2], [5, -1, 2]],
                         width=63, height=47, focal=24, center=(31, 23), radius=1)
        expected, stats = render_reference(scene)
        frame, depth, actual = np.zeros(63*47, np.int32), np.zeros(63*47, np.int32), np.zeros(16, np.int32)
        self.dll.z20_map(scene.vertex_words(), scene.parameter_words(), frame, depth, actual)
        rgb = np.stack(((frame >> 16) & 255, (frame >> 8) & 255, frame & 255), axis=-1).astype(np.uint8).reshape(47, 63, 3)
        np.testing.assert_array_equal(rgb, expected)
        self.assertEqual(actual[1], 0)
        self.assertEqual(actual[2], stats['visible_points'])
        self.assertEqual(actual[3], stats['clipped_points'])
        self.assertEqual(actual[4], stats['trajectory_segments'])

    def hardware_bridge(self, kernel, layout):
        from test_pl_driver import Buffer
        buffers, registers, events = {}, {}, []
        next_address = [0x06000000]
        def allocate(*, shape, dtype):
            value = Buffer(shape[0], next_address[0], events)
            buffers[value.physical_address] = value
            next_address[0] += (shape[0]*4+63)//64*64
            return value
        def write(offset, value):
            registers[offset] = value
            if offset == 0 and value == 1:
                pointers = [buffers[registers[x]] for x in layout]
                if kernel == 'map':self.dll.z20_map(*pointers)
                else:self.dll.z15_fbcsp(*pointers, registers[0x40], registers[0x48])
        return SimpleNamespace(read=lambda _: 6, write=write), allocate

    def test_map_driver_and_observation_camera_reach_the_kernel(self):
        registers, allocate = self.hardware_bridge('map', [0x10, 0x20, 0x30, 0x40, 0x50])
        backend = MapHardware(registers, allocate, width=9, height=9)
        view = MapView(backend, width=9, height=9)
        geometry = SimpleNamespace(points=np.array([[0., 0., 1.]]), colors=np.array([[17, 34, 51]], np.uint8),
            trajectory=np.empty((0, 3)), units='m', frame_id='known:1', metric_verified=True)
        frame, stats = view.render_geometry(geometry)
        np.testing.assert_array_equal(frame[5, 5], [17, 34, 51])
        self.assertEqual(stats['visible_points'], 1)
        self.assertEqual(stats['backend'], 'PL_pointcloud_map_renderer')
        view.close()

    def test_eeg_driver_reaches_kernel_without_losing_windows(self):
        registers, allocate = self.hardware_bridge('eeg', [0x10, 0x20, 0x30])
        driver = EEGHardware(identity_model(), registers, allocate)
        x = np.zeros((6, 8), np.int32);x[:, 2] = [256, -256]*3;x[:, 3] = [512, -512]*3
        result = driver.feed(x)
        self.assertEqual([r['sample_count'] for r in result], [4, 6])
        self.assertEqual([r['score_q24'] for r in result], [33554432, 33554432])
        self.assertTrue(all(r['valid'] and not r['control_enabled'] for r in result))
        driver.close()


if __name__ == '__main__':
    unittest.main()
