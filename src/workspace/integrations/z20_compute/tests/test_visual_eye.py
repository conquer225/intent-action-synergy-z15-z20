import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'integrations/eye_c3/runtime/system_runtime'))
sys.path.insert(0,str(ROOT/'ps_tobii/src'))
from z20_compute.z15_visual_menu import VisualEyeController,patch_system_hdmi


class EyeMenuTests(unittest.TestCase):
    def test_device_feedback_distinguishes_enable_connection_and_rejected_requests(self):
        from z20_compute.z15_visual_menu import device_status_text
        self.assertIn('重新连接',device_status_text(dict(connected=False,enabled=None,pending=False,message='等待注视启用')))
        self.assertIn('等待设备回执',device_status_text(dict(connected=True,enabled=None,pending=True,message='')))
        self.assertIn('灵巧手可操作',device_status_text(dict(connected=True,enabled='hand',pending=False,message='ok')))
        self.assertIn('连接未建立',device_status_text(dict(connected=False,enabled=None,pending=False,message='ACK timeout')))

    def test_external_entry_keeps_presentation_gate_and_stops_device(self):
        events=[]
        class Link:
            def stop(self,reason):events.append(('stop',reason))
            def snapshot(self):return dict(enabled=None,connected=True)
        class Visual:
            def send(self,name):events.append(('visual',name));return True
            def snapshot(self):return dict(connected=True,menu=True,mode='fluid',epoch=1)
        controller=VisualEyeController(Link(),Visual(),0)
        def choose(page,region,now):
            controller._enter(page,now);controller.presented(controller.page_id,now)
            self.assertFalse(controller.choose(region,now+.1))
            self.assertTrue(controller.choose(region,now+2))
        choose('media',2,10)
        self.assertEqual(controller.page,'visual_sources')
        choose('visual_sources',2,20)
        self.assertEqual(controller.page,'z20_menu')
        choose('z20_menu',1,30)
        self.assertEqual(events[-1],('visual','enter'))
        self.assertTrue(any(event[0]=='stop' for event in events))
        self.assertNotIn('emg',' '.join(controller.labels()))

    def test_patch_is_idempotent_and_both_actual_runtime_variants_parse(self):
        import ast
        for name in ('eye_c3','eeg_demo'):
            source=(ROOT/'integrations'/name/'runtime/system_hdmi.py').read_text(encoding='utf-8')
            patched=patch_system_hdmi(source)
            ast.parse(patched,feature_version=(3,8))
            self.assertEqual(patched,patch_system_hdmi(patched))

    def test_patched_actual_display_constructs_and_draws_mode_specific_labels(self):
        import types,time,tempfile
        from unittest.mock import patch
        folder=ROOT/'integrations/eeg_demo/runtime'
        sys.path.insert(0,str(folder))
        source=(folder/'system_hdmi.py').read_text(encoding='utf-8')
        module=types.ModuleType('visual_test_hdmi');module.__file__=str(folder/'system_hdmi.py')
        exec(compile(patch_system_hdmi(source),module.__file__,'exec'),module.__dict__)
        class Link:
            def stop(self,reason):pass
            def snapshot(self):return dict(enabled=None,connected=True,pending=None,message='test')
        class Visual:
            def send(self,name):return True
            def snapshot(self):return dict(connected=True,menu=False,mode='spatial',epoch=1)
        def attach(original,link,base,**options):return VisualEyeController(link,Visual(),time.monotonic(),**options)
        with tempfile.TemporaryDirectory() as temporary,patch('z20_compute.z15_visual_menu.attach_from_environment',side_effect=attach):
            old_cache=Path(temporary)/'old-shells.npz';old_cache.write_bytes(b'previous menu contract')
            display=module.UnifiedDisplay(ROOT/'ps_tobii',device_link=Link(),live=True,shell_cache=old_cache)
            self.assertEqual(old_cache.read_bytes(),b'previous menu contract')
        display.controller._enter('z20_active',time.monotonic())
        display.controller.device_update(time.monotonic())
        self.assertTrue(display.refresh_labels({}, {},''))
        self.assertIn('z20_active',display.overlays)
        self.assertEqual(display.controller.labels(),('拍摄并生成','返回选择','切换视图'))
