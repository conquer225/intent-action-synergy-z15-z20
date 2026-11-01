import hashlib,json,tempfile,unittest,sys,importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))


class VisualReleaseTests(unittest.TestCase):
    def test_reviewed_changes_do_not_rebase_or_accept_an_unlisted_edit(self):
        from z20_compute.reviewed_baseline import verify_reviewed
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a.py').write_bytes(b'new')
            sha=lambda data:hashlib.sha256(data).hexdigest()
            baseline=dict(files=[dict(path='a.py',sha256=sha(b'old'))])
            review={'a.py':dict(before=sha(b'old'),after=sha(b'new'),reason='approved change')}
            report=verify_reviewed(root,baseline,review)
            self.assertTrue(report['passed']);self.assertFalse(report['unchanged'])
            self.assertEqual(report['reviewed_changes'],['a.py'])
            (root/'a.py').write_bytes(b'unreviewed')
            self.assertFalse(verify_reviewed(root,baseline,review)['passed'])
            review['a.py']['before']=sha(b'wrong baseline')
            self.assertFalse(verify_reviewed(root,baseline,review)['passed'])

    def test_installer_keeps_paired_integrity_and_exact_rollback(self):
        import install_visual_z15 as installer
        spec=importlib.util.spec_from_file_location('visual_install_fixtures',HERE.parent/'eeg_demo/tests/test_install_demo.py')
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,_,_=fixture.InstallDemoTests().fixture(root)
            media=roots['media'];source=(HERE.parent/'eeg_demo/runtime/system_hdmi.py').read_bytes()
            (media/'system_hdmi.py').write_bytes(source)
            (media/'media_player.py').write_text('audible=vision.signal and vision.signal.session.snapshot()\nworker=vision.signal and vision.signal.analysis.thread.is_alive()\n')
            (media/'media_state.json').write_text(json.dumps(dict(vision_demo=dict(signal_pages=True),hardware_hashes={'preserve':'pin'})))
            (media/'z20_visual_config.json').write_text(json.dumps(dict(enabled=True,host='192.168.50.10',token='o'*32)))
            bundle=root/'bundle';bundle.mkdir();(bundle/'payload.py').write_bytes(b'x=1\n')
            digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            manifest=dict(files={'vision_demo/session.py':dict(source='payload.py',sha256=digest(bundle/'payload.py'),before=[None])},
                system_hdmi_before=[digest(media/'system_hdmi.py')],signal_player_guards=True)
            (bundle/'z15-overlay.json').write_text(json.dumps(manifest))
            before={p:p.read_bytes() for r in roots.values() for p in r.rglob('*') if p.is_file()}
            plan=installer.plan_update(roots,bundle,host='192.168.50.20',token='t'*32)
            backup=installer.transaction.apply_transaction(roots,plan)
            state=json.loads((media/'media_state.json').read_text())
            self.assertEqual(state['vision_demo']['enabled_image_modes'],['neon','trails','motion'])
            self.assertEqual(state['vision_demo']['enabled_signal_pages'],['fatigue','emotion','music','audio'])
            self.assertEqual(state['hardware_hashes'],{'preserve':'pin'})
            self.assertIn('and vision.signal.session and',(media/'media_player.py').read_text())
            pins=json.loads((media/'boot-pins.json').read_text())
            for name,sha in pins['files'].items():self.assertEqual(digest(Path(name)),sha)
            self.assertIn('Z20_VISUAL_MENU_V1',(media/'system_hdmi.py').read_text(encoding='utf-8'))
            installer.transaction.rollback(roots,backup)
            for path,data in before.items():self.assertEqual(path.read_bytes(),data)
            self.assertEqual(json.loads((media/'z20_visual_config.json').read_text())['host'],'192.168.50.10')

    def test_capture_profile_falls_back_on_sustained_slow_delivery(self):
        from z20_compute.visual_profile import CaptureProfile
        p=CaptureProfile();self.assertEqual(p.size,(960,540))
        self.assertFalse(p.observe(now=0,sent=0))
        self.assertFalse(p.observe(now=4,sent=10))
        self.assertTrue(p.observe(now=6,sent=20))
        self.assertEqual((p.size,p.quality,p.fps),((640,360),65,10))
        self.assertFalse(p.observe(now=12,sent=100))

    def test_release_contains_offline_assets_licenses_and_no_firmware_or_secret(self):
        from build_visual_release import create_release
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            path=create_release(Path(directory)/'visual.zip')
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip());names=archive.namelist()
                for name in ('third_party/visual/fluid/LICENSE','third_party/visual/spectrum/LICENSE',
                             'build/reconstruction/models/yolo26m-depth.pt','assets/display/libz20_visual.so',
                             'z15/z15-overlay.json','install_visual_z15.py','install_demo.py','START_BOARD.sh',
                             'START_OFFLINE.ps1','z20_compute/visual_offline.py','assets/replay/scene-bgr.npy'):
                    self.assertIn(name,names)
                for name in ('z15_preview/vision_demo/signal_render.py','z15_preview/presentation_theme.py',
                             'z15_preview/presentation.css','z15_preview/build/signal_assets/music/calm.wav',
                             'z15_preview/build/signal_assets/replay/eeg_replay.npz'):
                    self.assertIn(name,names)
                self.assertNotIn(b'\r',archive.read('START_BOARD.sh'))
                self.assertTrue(json.loads(archive.read('z15/z15-overlay.json'))['signal_player_guards'])
                prior=json.loads((HERE/'report/z15_visual_prior_release_20261027.json').read_text())
                overlay=json.loads(archive.read('z15/z15-overlay.json'))
                for name,sha in prior['files'].items():self.assertIn(sha,overlay['files'][name]['before'])
                self.assertFalse(any(name.endswith(('.bit','BOOT.BIN','token.txt')) for name in names))
                manifest=json.loads(archive.read('SHA256.json'))
                for name,sha in manifest.items():self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),sha)

    def test_release_includes_matching_built_wifi_module_without_autoload(self):
        from build_visual_release import create_release
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            with zipfile.ZipFile(create_release(Path(directory)/'visual.zip')) as archive:
                driver=archive.read('drivers/8733bu-navigator-20261027.ko')
                provenance=json.loads(archive.read('drivers/build-result.json'))
                self.assertEqual(hashlib.sha256(driver).hexdigest(),provenance['sha256'])
                self.assertTrue(provenance['passed'])
                self.assertIn(b'5.4.0-xilinx-v2020.2 SMP preempt mod_unload modversions ARMv7 p2v8',driver)
                release=json.loads(archive.read('release.json'))
                self.assertFalse(release['driver_autoload'])
                self.assertNotIn('real_usb_wifi_driver',release['pending'])
                self.assertNotIn('real_z15_install',release['pending'])
                self.assertTrue(release['actual_z15_installed'])
                self.assertTrue(json.loads(archive.read('verification/board-20261027/z15-final-state.json'))['passed'])
