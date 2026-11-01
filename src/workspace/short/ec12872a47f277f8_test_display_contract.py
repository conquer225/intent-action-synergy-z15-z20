"""Negative controls for the HWH compatibility checker; never touches a board."""
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from verify_display_contract import verify

FIXTURE=Path(__file__).resolve().parent/'output/full_10/project/hdmi_audio.gen/sources_1/bd/system/hw_handoff/system.hwh'


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'candidate.hwh'
        self.tree=ET.parse(FIXTURE)

    def tearDown(self):self.temp.cleanup()

    def save(self):self.tree.write(self.path,encoding='utf-8')

    def param(self,instance,key):
        return self.tree.find(f'./MODULES/MODULE[@INSTANCE="{instance}"]/PARAMETERS/PARAMETER[@NAME="{key}"]')

    def test_current_candidate(self):
        self.save();self.assertTrue(verify(self.path)['passed'])

    def test_audio_address_collision(self):
        node=self.tree.find('./MODULES/MODULE[@INSTANCE="processing_system7_0"]/MEMORYMAP/MEMRANGE[@INSTANCE="pcm_buffer_0"]')
        node.set('BASEVALUE','0x43c00000');self.save()
        with self.assertRaisesRegex(ValueError,'address map'):verify(self.path)

    def test_wrong_audio_clock(self):
        self.param('clk_wiz_0','MMCM_CLKOUT2_DIVIDE').set('VALUE','6');self.save()
        with self.assertRaisesRegex(ValueError,'MMCM'):verify(self.path)

    def test_changed_video_stride_width(self):
        self.param('axi_vdma_0','c_m_axis_mm2s_tdata_width').set('VALUE','32');self.save()
        with self.assertRaisesRegex(ValueError,'VDMA|axi_vdma'):verify(self.path)

    def test_changed_ddr_part(self):
        self.param('processing_system7_0','PCW_UIPARAM_DDR_PARTNO').set('VALUE','not the board part');self.save()
        with self.assertRaisesRegex(ValueError,'PS configuration'):verify(self.path)

    def test_disconnected_sample_clock(self):
        node=self.tree.find('./MODULES/MODULE[@INSTANCE="pcm_buffer_0"]/PORTS/PORT[@NAME="sample_clk"]')
        node.set('SIGNAME','wrong_clock');self.save()
        with self.assertRaisesRegex(ValueError,'sample clocks'):verify(self.path)


if __name__=='__main__':unittest.main()
