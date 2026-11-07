"""Public display commands and bounded geometry transport preserve old modes."""
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import threading
from types import SimpleNamespace
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]/'src/workspace/integrations'
sys.path[:0] = [str(ROOT), str(ROOT/'z20_compute')]
from z20_compute.visual_demo import DemoState
from z20_compute.visual_wire import GeometryFrame, decode_geometry, read_frame, write_geometry


class GeometryModeContract(unittest.TestCase):
    def spatial(self):
        state = DemoState(now=lambda: 10.)
        state.map_available = True
        state.attach_renderer()
        for i, name in enumerate(('right', 'right', 'right', 'enter')):state.command('user', i, name)
        return state

    def test_unavailable_hardware_preserves_original_backend(self):
        state = self.spatial()
        state.map_available = False
        before = state.snapshot()
        result = state.command('user', 4, 'map_pl')
        self.assertFalse(result['accepted'])
        self.assertEqual(result['map_backend'], 'original')
        self.assertEqual(result['epoch'], before['epoch'])

    def test_explicit_switch_rejects_old_frames_and_restores_original(self):
        state = self.spatial()
        original = state.snapshot()
        self.assertEqual(original['map_backend'], 'original')
        changed = state.command('user', 4, 'map_pl')
        self.assertEqual(changed['map_backend'], 'pl')
        self.assertFalse(state.accept_frame(original['session'], original['epoch'], 1, b'old'))
        scene = GeometryFrame([[0, 0, 1]], [[1, 2, 3]], units='m', frame_id='frame:1')
        self.assertTrue(state.accept_geometry(changed['session'], changed['epoch'], 1, scene))
        self.assertIsNotNone(state.latest_geometry())
        restored = state.command('user', 5, 'map_original')
        self.assertEqual(restored['map_backend'], 'original')
        self.assertIsNone(state.latest_geometry())
        self.assertTrue(state.accept_frame(restored['session'], restored['epoch'], 2, b'new'))

    def test_geometry_envelope_round_trip_and_invalid_payload(self):
        scene = GeometryFrame([[.5, -.25, 2]], [[17, 34, 51]], trajectory=[[0, 0, 1]],
                              units='relative_depth_median', frame_id='camera:9')
        stream = io.BytesIO()
        write_geometry(stream, 'a'*32, 7, 11, scene)
        stream.seek(0)
        meta, raw = read_frame(stream)
        restored = decode_geometry(meta, raw)
        np.testing.assert_array_equal(restored.points, scene.points)
        np.testing.assert_array_equal(restored.colors, scene.colors)
        self.assertEqual(restored.units, 'relative_depth_median')
        with self.assertRaises(ValueError):decode_geometry(meta, raw[:-1])
        with self.assertRaises(ValueError):GeometryFrame([[float('nan'), 0, 1]], [[0, 0, 0]])

    def test_existing_fusion_manifest_supplies_world_points_and_pose_trajectory(self):
        from z20_compute.map_source import load_fusion_geometry
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.savez(root/'depth.npz', xyz=np.array([[[0., 0., 1.], [1., 0., 1.]]]),
                     valid_mask=np.array([[True, False]]))
            first = np.eye(4);second = np.eye(4);second[0, 3] = 1
            manifest = dict(views=[dict(depth_npz='depth.npz', camera_to_world=p.tolist())
                                   for p in (first, second)])
            (root/'views.json').write_text(json.dumps(manifest), encoding='utf-8')
            geometry = load_fusion_geometry(root/'views.json')
            np.testing.assert_allclose(geometry.points, [[0, 0, 1], [1, 0, 1]])
            np.testing.assert_allclose(geometry.trajectory, [[0, 0, 0], [1, 0, 0]])
            self.assertEqual(geometry.units, 'm')
            self.assertFalse(geometry.metric_verified)

    def test_live_host_reuses_cloud_when_switching_renderers_over_sockets(self):
        from z20_compute.visual_host import VisualHost
        from z20_compute.visual_server import DemoServer
        state = self.spatial()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            depth = root/'depth.npz'
            np.savez(depth, xyz=np.array([[[0., 0., 1.]]]), valid_mask=np.array([[True]]))
            manifest = root/'views.json'
            manifest.write_text(json.dumps(dict(views=[dict(depth_npz='depth.npz',
                camera_to_world=np.eye(4).tolist())])), encoding='utf-8')
            with DemoServer(state, '127.0.0.1', 0, 0, token='test-map') as server:
                host = VisualHost('127.0.0.1', 'test-map', control_port=server.control_port,
                    frame_port=server.frame_port, map_manifest=manifest).start()
                def wait_for(predicate):
                    deadline = time.monotonic()+4
                    while time.monotonic() < deadline:
                        if predicate():return
                        time.sleep(.01)
                    self.fail('live geometry condition timed out: '+str(host.snapshot()))
                try:
                    wait_for(lambda: host.snapshot().get('spatial_ready'))
                    source_id = host.cloud['id']
                    depth.write_bytes(b'cloud must be reused across a renderer switch')
                    result = host.command('map_pl')
                    self.assertTrue(result['accepted'])
                    wait_for(lambda: state.latest_geometry() is not None)
                    self.assertEqual(state.latest_geometry()[3].frame_id, source_id)
                    host.command('map_original')
                    wait_for(lambda: host.snapshot().get('map_backend') == 'original')
                    self.assertEqual(host.cloud['id'], source_id)
                    self.assertIsNone(state.latest_geometry())
                finally:host.close()

    def test_stereo_cloud_is_bounded_and_returns_to_original_display(self):
        from z20_compute.headless_pipeline import HeadlessPipeline
        calls, shown = [], []
        original = np.zeros((720, 1280, 3), np.uint8)
        accelerated = np.full_like(original, 23)
        class Renderer:
            font = SimpleNamespace(text=lambda *a, **k: None)
            def render(self, *a, **k):return original
        class Display:
            def show(self, raw):self.raw = raw;shown.append(raw[0])
            def readback(self):return self.raw
            def close(self):pass
        class Map:
            def render_geometry(self, geometry, **kwargs):
                calls.append(len(geometry.points));return accelerated, dict(backend='test')
        runtime = SimpleNamespace(lock=threading.RLock(), navigation=SimpleNamespace(version=0))
        state = dict(page='cloud', detail=0, environment=dict(cloud=dict(valid=True)))
        with tempfile.TemporaryDirectory() as directory:
            pipeline = HeadlessPipeline(runtime, lambda: state, assets=directory,
                preview=Path(directory)/'preview.png', renderer=Renderer(), display=Display(),
                map_renderer=Map(), map_mode='pl')
            pipeline.cloud_points = np.tile([0., 0., 1.], (70000, 1))
            pipeline.cloud_payload = dict(units='m', artifact_id='stereo:1')
            pipeline.start()
            def wait_for(predicate):
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    if predicate():return
                    time.sleep(.01)
                self.fail(str(pipeline.status()))
            try:
                wait_for(lambda: 23 in shown)
                self.assertLessEqual(calls[0], 65536)
                self.assertEqual(pipeline.status()['map_mode'], 'pl')
                pipeline.set_map_mode('original')
                wait_for(lambda: 0 in shown)
                self.assertEqual(pipeline.status()['map_mode'], 'original')
            finally:pipeline.close()

    def test_four_mode_pipeline_displays_map_pixels_then_original_jpeg(self):
        import cv2
        from pl_accel.mapping import render_reference
        from pl_accel.view import MapView
        from z20_compute.visual_pipeline import VisualPipeline
        state = self.spatial()
        changed = state.command('user', 4, 'map_pl')
        scene = GeometryFrame([[0, 0, 1]], [[17, 34, 51]], units='m', frame_id='known:1')
        state.accept_geometry(changed['session'], changed['epoch'], 1, scene)
        rendered, original = threading.Event(), threading.Event()
        class Backend:
            def render(self, scene):return render_reference(scene)
        class Display:
            def show(self, raw):
                self.raw = raw
                center = raw[(360*1280+640)*3:(360*1280+640)*3+3]
                if center == bytes([17, 34, 51]):rendered.set()
                if center == bytes([77]*3):original.set()
            def readback(self):return self.raw
        with tempfile.TemporaryDirectory() as directory:
            owner = SimpleNamespace(renderer=SimpleNamespace(font=SimpleNamespace(text=lambda *a, **k: None)),
                stopped=threading.Event(), lock=threading.Lock(), errors={}, display=Display(), frames=0,
                display_matches=0, preview=Path(directory)/'frame.png', map_renderer=MapView(Backend()))
            pipeline = VisualPipeline(owner, state)
            thread = threading.Thread(target=pipeline.render_loop)
            thread.start()
            try:
                self.assertTrue(rendered.wait(2))
                self.assertEqual(state.snapshot()['data']['map']['visible_points'], 1)
                restored = state.command('user', 5, 'map_original')
                jpeg = cv2.imencode('.jpg', np.full((720, 1280, 3), 77, np.uint8))[1].tobytes()
                state.accept_frame(restored['session'], restored['epoch'], 2, jpeg)
                self.assertTrue(original.wait(2))
                self.assertFalse(owner.errors)
            finally:owner.stopped.set();thread.join(3)
            self.assertFalse(thread.is_alive())


if __name__ == '__main__':unittest.main()
