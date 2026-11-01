import struct
import unittest
import zlib
import json
import tempfile
import hashlib
from pathlib import Path
from types import SimpleNamespace
from build_stereo_package import script_image, build, HERE


class StereoPackageTests(unittest.TestCase):
    def test_runtime_manifest_does_not_claim_stale_files_from_prior_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);hardware=root/'hardware';hardware.mkdir();boot=root/'boot';boot.mkdir()
            digest=hashlib.sha256(b'candidate').hexdigest()
            (hardware/'system_wrapper.bit').write_bytes(b'candidate')
            (hardware/'manifest.json').write_text(json.dumps(dict(observer_netlist_present=True,
                files={'system_wrapper.bit':digest,'z20_stereo.xsa':'matched'},sources={
                    'hardware/rtl/'+name:hashlib.sha256((HERE/'hardware/rtl'/name).read_bytes()).hexdigest()
                    for name in ('z20_video_epoch.sv','z20_video_observer.sv')})))
            (boot/'manifest.json').write_text(json.dumps(dict(linux_handoff=True,
                matched_xsa_sha256='matched',files={'system.bit':digest})))
            (boot/'BOOT.BIN').write_bytes(b'boot')
            for name in ('system.dtb','zImage'):(root/name).write_bytes(name.encode())
            output=root/'output';(output/'boot').mkdir(parents=True)
            (output/'boot/rootfs.gz').write_bytes(b'prior root filesystem')
            build(SimpleNamespace(output=output,hardware=hardware,boot=boot,
                                  dtb=root/'system.dtb',kernel=root/'zImage'))
            manifest=json.loads((output/'manifest.json').read_text())
            self.assertNotIn('rootfs.gz',manifest['files'])
            self.assertEqual(manifest['files']['BOOT.BIN'],hashlib.sha256(b'boot').hexdigest())

    def test_package_refuses_hardware_without_matching_validation_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);hardware=root/'hardware';hardware.mkdir();boot=root/'boot';boot.mkdir()
            (hardware/'system_wrapper.bit').write_bytes(b'candidate')
            (boot/'manifest.json').write_text(json.dumps(dict(linux_handoff=True,
                files={'system.bit':hashlib.sha256(b'candidate').hexdigest()})))
            args=SimpleNamespace(output=root/'output',hardware=hardware,boot=boot,
                                 dtb=root/'system.dtb',kernel=root/'zImage')
            with self.assertRaisesRegex(ValueError,'validated stereo hardware'):
                build(args)

    def test_uboot_legacy_script_has_header_and_payload_crc(self):
        image = script_image(b'echo stereo\n', timestamp=0)
        header = bytearray(image[:64])
        magic, hcrc, stamp, size, load, entry, dcrc = struct.unpack_from('>7I', header)
        self.assertEqual(magic, 0x27051956)
        self.assertEqual((stamp, load, entry), (0,0,0))
        self.assertEqual(image[28:32], b'\x05\x02\x06\x00')
        struct.pack_into('>I', header, 4, 0)
        self.assertEqual(zlib.crc32(header), hcrc)
        self.assertEqual(zlib.crc32(image[64:]), dcrc)
        self.assertEqual(size, len(image)-64)
        self.assertEqual(struct.unpack_from('>II',image,64), (12,0))
        self.assertEqual(image[72:], b'echo stereo\n')


if __name__ == '__main__': unittest.main()
