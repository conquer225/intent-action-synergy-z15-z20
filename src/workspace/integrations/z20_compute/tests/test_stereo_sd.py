from pathlib import Path
import struct
import tempfile
import unittest
from build_stereo_sd import fat16_image


class StereoSDTests(unittest.TestCase):
    def test_disk_contains_partition_fat_chain_and_original_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = bytes(range(256))*80
            source = root/'kernel';source.write_bytes(data)
            disk = root/'test.img'
            fat16_image(disk, {'ZIMAGE': source})
            with disk.open('rb') as stream:
                mbr = stream.read(512)
                self.assertEqual(mbr[510:], b'\x55\xaa')
                partition = struct.unpack_from('<B3sB3sII', mbr, 446)
                self.assertEqual((partition[0], partition[2], partition[4]), (0x80,0x0e,2048))
                stream.seek(2048*512);bpb=stream.read(512)
                self.assertEqual(bpb[510:], b'\x55\xaa')
                self.assertEqual(bpb[54:62], b'FAT16   ')
                sector = struct.unpack_from('<H',bpb,11)[0]
                spc,reserved,fats,entries = bpb[13],struct.unpack_from('<H',bpb,14)[0],bpb[16],struct.unpack_from('<H',bpb,17)[0]
                fat_sectors = struct.unpack_from('<H',bpb,22)[0]
                stream.seek((2048+reserved)*sector);fat=stream.read(fat_sectors*sector)
                root_sector = 2048+reserved+fats*fat_sectors
                stream.seek(root_sector*sector);entry=stream.read(32)
                self.assertEqual(entry[:11], b'ZIMAGE     ')
                self.assertEqual(struct.unpack_from('<I',entry,28)[0],len(data))
                cluster=struct.unpack_from('<H',entry,26)[0]
                start=root_sector+(entries*32+sector-1)//sector
                result=b''
                while cluster<0xfff8:
                    stream.seek((start+(cluster-2)*spc)*sector)
                    result+=stream.read(spc*sector)
                    cluster=struct.unpack_from('<H',fat,cluster*2)[0]
                self.assertEqual(result[:len(data)],data)


if __name__ == '__main__': unittest.main()
