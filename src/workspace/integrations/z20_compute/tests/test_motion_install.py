import hashlib,importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]


class MotionInstallationTests(unittest.TestCase):
    def fixture(self,root):
        spec=importlib.util.spec_from_file_location('motion_install_fixture',HERE.parent/'eeg_demo/tests/test_install_demo.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        roots,_,_=module.InstallDemoTests().fixture(root)
        media=roots['media'];overlay=media/'vision_demo/overlay';overlay.mkdir(parents=True)
        (overlay/'display_vision.bit').write_bytes(b'old-bit')
        (overlay/'display_vision.hwh').write_bytes(b'old-hwh')
        digest=lambda b:hashlib.sha256(b).hexdigest()
        hashes={str(p):digest(p.read_bytes()) for p in overlay.iterdir()}
        (media/'media_state.json').write_text(json.dumps(dict(display_overlay=str(overlay/'display_vision.bit'),hardware_hashes=hashes)))
        (media/'page_audio.py').write_text("EXPECTED_BIT='%s'\nEXPECTED_HWH='%s'\n"%(hashes[str(overlay/'display_vision.bit')],hashes[str(overlay/'display_vision.hwh')]))
        addresses={'axi_vdma_0':0x43000000,'axi_vdma_1':0x43010000,'live_osd_0':0x43c00000,'v_tc_0':0x43c10000,'pcm_buffer_0':0x43c20000,'vision_core_0':0x43c30000,'vision_keys_0':0x43c40000,'audio_fft_0':0x43c50000}
        hwh=('<ROOT>'+''.join('<MEMRANGE INSTANCE="%s" BASEVALUE="%s"/>'%(n,hex(a)) for n,a in addresses.items())+'</ROOT>').encode()
        files={'candidate/guardianloop_display_audio.bit':b'new-bit','candidate/guardianloop_display_audio.hwh':hwh}
        files.update({n:b'checked report' for n in ('timing.rpt','cdc.rpt','methodology.rpt','drc.rpt','io.rpt','utilization.rpt')})
        quality=dict(passed=True,part='xc7z015clg485-2',files={n:digest(b) for n,b in files.items()})
        def archive(path,corrupt=False):
            with zipfile.ZipFile(path,'w') as z:
                for n,b in files.items():z.writestr(n,b'corrupted' if corrupt and n.endswith('.bit') else b)
                z.writestr('quality.json',json.dumps(quality))
        return roots,archive

    def test_installs_firmware_audio_pins_and_manifest_as_one_rollback_transaction(self):
        from install_motion_firmware import plan_update,transaction
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,archive=self.fixture(root);candidate=root/'candidate.zip';archive(candidate)
            before={p:p.read_bytes() for r in roots.values() for p in r.rglob('*') if p.is_file()}
            plan=plan_update(roots,candidate);backup=transaction.apply_transaction(roots,plan)
            media=roots['media'];bit=media/'vision_demo/overlay/display_vision.bit'
            self.assertEqual(bit.read_bytes(),b'new-bit')
            digest=hashlib.sha256(b'new-bit').hexdigest()
            self.assertIn(digest,(media/'page_audio.py').read_text())
            self.assertEqual(json.loads((media/'media_state.json').read_text())['hardware_hashes'][str(bit)],digest)
            for name,sha in json.loads((media/'boot-pins.json').read_text())['files'].items():
                self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(),sha)
            transaction.rollback(roots,backup)
            for p,data in before.items():self.assertEqual(p.read_bytes(),data)

    def test_corrupt_firmware_is_rejected_without_any_write(self):
        from install_motion_firmware import plan_update
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,archive=self.fixture(root);candidate=root/'bad.zip';archive(candidate,True)
            before={p:p.read_bytes() for r in roots.values() for p in r.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError,'checksum'):plan_update(roots,candidate)
            for p,data in before.items():self.assertEqual(p.read_bytes(),data)

    def test_unknown_audio_pin_rejects_update_instead_of_removing_the_gate(self):
        from install_motion_firmware import plan_update
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);roots,archive=self.fixture(root);candidate=root/'candidate.zip';archive(candidate)
            path=roots['media']/'page_audio.py';path.write_text("EXPECTED_BIT='unknown'\n")
            before={p:p.read_bytes() for r in roots.values() for p in r.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError,'Audio firmware pin'):plan_update(roots,candidate)
            for p,data in before.items():self.assertEqual(p.read_bytes(),data)
