import hashlib,json,sys,tempfile,unittest,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('vision_install_fixtures',ROOT.parent/'eeg_demo/tests/test_install_demo.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
from install_vision import plan_update,retire_display_status
install=fixtures.install

class VisionInstallTests(unittest.TestCase):
    def bundle(self,root):
        bundle=root/'bundle';bundle.mkdir()
        hwh=('<SYSTEM>'+''.join('<MEMRANGE INSTANCE="%s" BASEVALUE="%s"/>'%item for item in [('axi_vdma_0','0x43000000'),('axi_vdma_1','0x43010000'),('live_osd_0','0x43c00000'),('v_tc_0','0x43c10000'),('pcm_buffer_0','0x43c20000'),('vision_core_0','0x43c30000'),('vision_keys_0','0x43c40000')])+'</SYSTEM>').encode()
        data={'media_player.py':b'new','vision_demo/overlay/display_vision.bit':b'bit fixture',
              'vision_demo/overlay/display_vision.hwh':hwh,'vision_demo/addon.py':b'addon',
              'vision_demo/libvision_capture.so':b'library','vision_demo/bin/tobii-images':b'worker'}
        for name,value in data.items():
            p=bundle/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
        manifest=dict(version=1,gates_passed=True,baseline_player=hashlib.sha256(b'old').hexdigest(),
            files={n:hashlib.sha256(v).hexdigest() for n,v in data.items()})
        (bundle/'bundle_manifest.json').write_text(json.dumps(manifest))
        return bundle
    def test_install_preserves_models_control_config_pins_and_exact_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,_,_=fixtures.InstallDemoTests().fixture(root)
            media=roots['media'];original=dict(display_overlay='old.bit',hardware_hashes={'old.bit':'preserved'},hdmi_audio=True)
            (media/'media_state.json').write_text(json.dumps(original))
            (media/'eye_devices.json').write_text('{"debug_hold":true,"s3_host":"192.168.50.45"}')
            before={p:p.read_bytes() for r in roots.values() for p in r.rglob('*') if p.is_file()}
            plan=plan_update(roots,self.bundle(root));backup=install.apply_transaction(roots,plan)
            state=json.loads((media/'media_state.json').read_text())
            self.assertEqual(state['hardware_hashes']['old.bit'],'preserved')
            self.assertTrue(state['hdmi_audio']);self.assertIn('vision_demo',state)
            bit=media/'vision_demo/overlay/display_vision.bit'
            self.assertEqual(state['display_overlay'],str(bit))
            pins=json.loads((media/'boot-pins.json').read_text())
            self.assertEqual(pins['files'][str(bit)],install.digest(bit))
            self.assertEqual((media/'eye_devices.json').read_bytes(),before[media/'eye_devices.json'])
            self.assertEqual((roots['brain']/'model.bin').read_bytes(),b'frozen model')
            install.rollback(roots,backup)
            for p,data in before.items():self.assertEqual(p.read_bytes(),data)
            self.assertFalse(bit.exists())
    def test_corrupt_unrelated_boot_pin_blocks_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,_,_=fixtures.InstallDemoTests().fixture(root);bundle=self.bundle(root)
            (roots['media']/'media_state.json').write_text('{"hardware_hashes":{}}')
            p=roots['media']/'control.py';p.write_bytes(b'changed')
            pin=roots['media']/'boot-pins.json';data=json.loads(pin.read_text())
            data['files'][str(p)]=hashlib.sha256(b'original').hexdigest();pin.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Existing boot pin differs'):plan_update(roots,bundle)

    def test_retiring_completed_display_keeps_history_and_releases_adoption(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,_,_=fixtures.InstallDemoTests().fixture(root)
            status=roots['media']/'player_status.json';status.write_text('{"session_id":"play-deadbeef"}')
            report=roots['media']/'play-deadbeef-report.json'
            report.write_text('{"display_halted":true,"buffers_released":true,"original_restored":true}')
            archive=retire_display_status(roots,ram_root=root)
            self.assertFalse(status.exists());self.assertTrue(archive.is_file());self.assertTrue(report.is_file())

    def test_signal_bundle_without_fft_registers_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,_,_=fixtures.InstallDemoTests().fixture(root);bundle=self.bundle(root)
            (roots['media']/'media_state.json').write_text('{"hardware_hashes":{}}')
            path=bundle/'bundle_manifest.json';row=json.loads(path.read_text());row['signal_pages']=True;path.write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError,'FFT'):plan_update(roots,bundle)

    def test_tampered_bundle_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,_,_=fixtures.InstallDemoTests().fixture(root);bundle=self.bundle(root)
            (bundle/'vision_demo/overlay/display_vision.bit').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Bundle checksum'):plan_update(roots,bundle)
            self.assertEqual((roots['media']/'media_player.py').read_bytes(),b'old')

    def test_current_eeg_device_control_is_an_accepted_install_baseline(self):
        name='system_runtime/guardianloop_system/device_link.py'
        current=(ROOT.parent/'eeg_demo/runtime'/name).read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,_,_=fixtures.InstallDemoTests().fixture(root)
            (roots['media']/'media_state.json').write_text('{"hardware_hashes":{}}')
            installed=roots['media']/name;installed.parent.mkdir(parents=True,exist_ok=True)
            installed.write_bytes(current)
            bundle=self.bundle(root);(bundle/name).parent.mkdir(parents=True,exist_ok=True)
            (bundle/name).write_bytes(current)
            path=bundle/'bundle_manifest.json';row=json.loads(path.read_text())
            row['files'][name]=hashlib.sha256(current).hexdigest()
            row['baseline_files']=json.loads((ROOT/'device_control_baseline.json').read_text())
            path.write_text(json.dumps(row))
            self.assertEqual(plan_update(roots,bundle)[('media',name)],current)
            installed.write_bytes(current+b'\n# unreviewed change\n')
            with self.assertRaisesRegex(ValueError,'Installed baseline differs'):
                plan_update(roots,bundle)

    def test_formal_presentation_requires_theme_recording_and_all_primary_surfaces(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,_,_=fixtures.InstallDemoTests().fixture(root);bundle=self.bundle(root)
            (roots['media']/'media_state.json').write_text('{"hardware_hashes":{}}')
            path=bundle/'bundle_manifest.json';row=json.loads(path.read_text());row['presentation_release']=True;path.write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError,'Presentation bundle incomplete'):plan_update(roots,bundle)

if __name__=='__main__':unittest.main()
