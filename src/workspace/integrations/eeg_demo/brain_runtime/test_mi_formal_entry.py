import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import guardianloop_acquisition as entry
import guardianloop_web as web
import mi_service_config as config
import mi_web_bridge as bridge_module
from mi_web_bridge import MIWebBridge, unavailable
from mi_cued_server import make_handler


class ConfigTests(unittest.TestCase):
    def test_absent_is_off_and_off_does_not_read_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            arguments = ['--windows', '0', '--status-file', '/run/guardianloop/status.json']
            self.assertFalse(config.enabled(root/'config'))
            self.assertEqual(entry.acquisition_args(arguments, root, root/'config'), arguments+['--wait-for-data'])
            (root/'config').write_text('{"enabled":false}')
            self.assertEqual(entry.acquisition_args(arguments, root, root/'config'), arguments+['--wait-for-data'])
            self.assertEqual(entry.acquisition_args(['--wait-for-data'], root, root/'config'), ['--wait-for-data'])

    def test_malformed_or_non_boolean_config_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config'
            for text in ('{', '[]', '{}', '{"enabled":1}', '{"enabled":"false"}',
                         '{"enabled":false,"port":80}'):
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(ValueError):
                        config.enabled(path)

    def test_enabled_is_fixed_live_endpoint_and_verified_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'config').write_text('{"enabled":true}')
            (root/config.MODEL_NAME).write_bytes(b'fixture')
            with self.assertRaisesRegex(ValueError, 'weights'):
                entry.acquisition_args([], root, root/'config')
            with patch.object(entry, 'MODEL_SHA256', hashlib.sha256(b'fixture').hexdigest()):
                args = entry.acquisition_args(['--windows','0'], root, root/'config')
            self.assertEqual(args[:2], ['--windows','0'])
            self.assertIn('--allow-experimental-mi', args)
            self.assertEqual(args[args.index('--mi-source')+1], 'live')
            self.assertEqual(args[args.index('--mi-web-host')+1], '0.0.0.0')
            self.assertEqual(args[args.index('--mi-web-port')+1], '9104')
            self.assertEqual(args[args.index('--mi-audit-log')+1], str(root/'mi-events.jsonl'))
            self.assertTrue(bridge_module.BACKEND.startswith('http://127.0.0.1:'))

    def test_cli_cannot_bypass_off_switch(self):
        with tempfile.TemporaryDirectory() as folder:
            for args in (['--allow-experimental-mi'], ['--mi-source=replay'], ['--mi-web-port','80']):
                with self.assertRaises(ValueError):
                    entry.acquisition_args(args, Path(folder), Path(folder)/'config')


class FakeSession:
    def __init__(self):
        self.value = dict(unavailable('cue_required', True), model_status='experimental_unpromoted')
        self.value['candidate_model'] = dict(name='fixed8_shared_rms_eegnet', sha256=config.MODEL_SHA256,
                                            input_transform='fixed8_shared_window_rms_v1',
                                            personal_head_enabled=False, promoted=False)
        self.commands = []

    def snapshot(self):
        return self.value

    def command(self, command):
        self.commands.append(command)
        if command.get('action') != 'start':
            raise ValueError('fixture rejects command')
        return dict(self.value, id='test', target=command['target'])


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        self.path = self.root/'config'
        self.path.write_text('{"enabled":true}')
        self.session = FakeSession()
        self.backend = ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.session))
        self.worker = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.worker.start()
        self.address = 'http://127.0.0.1:%s' % self.backend.server_port
        self.patch = patch.object(bridge_module, 'BACKEND', self.address)
        self.patch.start()
        self.bridge = MIWebBridge(self.path)

    def tearDown(self):
        self.patch.stop()
        self.backend.shutdown()
        self.backend.server_close()
        self.worker.join(2)
        self.scratch.cleanup()

    def test_off_never_queries_a_running_backend(self):
        self.path.write_text('{"enabled":false}')
        with patch.object(self.bridge.opener, 'open', side_effect=AssertionError('must not query')):
            code, value = self.bridge.request()
            self.assertEqual(code,200)
            self.assertFalse(value['enabled'])
            self.assertIsNone(value['result'])
            self.assertEqual(self.bridge.request({'action':'start','target':'left'})[0],409)
        self.assertIn('默认关闭'.encode(), self.bridge.page())
        self.assertNotIn(b'<script>', self.bridge.page())

    def test_real_http_get_post_and_no_cache_after_loss(self):
        self.assertEqual(self.bridge.request()[0],200)
        code, value = self.bridge.request({'action':'start','target':'right'})
        self.assertEqual((code,value['id'],value['target']), (200,'test','right'))
        self.assertEqual(self.session.commands[-1]['target'],'right')
        self.backend.shutdown()
        self.backend.server_close()
        code, value = self.bridge.request()
        self.assertEqual(code,200)
        self.assertEqual(value['reason'],'mi_backend_unavailable')
        self.assertIsNone(value['result'])

    def test_backend_command_rejection_has_no_old_result(self):
        code,value = self.bridge.request({'action':'unknown'})
        self.assertEqual(code,400)
        self.assertIsNone(value['result'])

    def test_foreign_source_control_and_nonfinite_payload_rejected(self):
        original = dict(self.session.value)
        for change in ({'source':'replay'}, {'control_enabled':True}, {'production_eligible':True},
                       {'channels':['C3']}, {'model_status':'production'},
                       {'result':{'source':'replay','control_enabled':False}},
                       {'result':{'source':'live','control_enabled':False,'logits':[float('nan')]}}):
            with self.subTest(change=change):
                self.session.value = dict(original, **change)
                # The upstream JSON writer also rejects NaN rather than emitting it.
                value = self.bridge.request()[1]
                self.assertIsNone(value['result'])
                self.assertEqual(value['reason'],'mi_backend_unavailable')

    def test_bad_config_fail_closed_without_backend(self):
        self.path.write_text('{"enabled":"yes"}')
        with patch.object(self.bridge.opener,'open',side_effect=AssertionError('must not query')):
            self.assertEqual(self.bridge.request()[1]['reason'],'mi_configuration_invalid')

    def test_other_model_or_personal_head_is_not_proxied(self):
        original = self.session.value['candidate_model']
        for change in ({'sha256':'wrong'}, {'personal_head_enabled':True}, {'promoted':True},
                       {'input_transform':'none'}, {'name':'personal_ridge'}):
            self.session.value['candidate_model'] = dict(original, **change)
            value = self.bridge.request()[1]
            self.assertIsNone(value['result'])
            self.assertEqual(value['reason'], 'mi_backend_unavailable')

    def test_formal_page_keeps_experimental_boundary(self):
        page = self.bridge.page().decode()
        self.assertIn('MI实验入口已安装到正式ARM程序',page)
        self.assertIn('模型未晋升',page)
        self.assertNotIn('不替换正式9102服务',page)


class FormalHTTPTests(unittest.TestCase):
    def test_disabled_endpoints_and_origin_body_guards(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(web,'system_status',return_value={}):
            root=Path(folder)
            bridge=MIWebBridge(root/'missing')
            server=ThreadingHTTPServer(('127.0.0.1',0),web.make_handler(root/'status',root/'telemetry',20,mi_bridge=bridge))
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            address='http://127.0.0.1:%s'%server.server_port
            try:
                with urlopen(address+'/') as response:
                    self.assertIn(b'href="/mi-cued"',response.read())
                with urlopen(address+'/mi-cued') as response:
                    self.assertIn('默认关闭'.encode(),response.read())
                with urlopen(address+'/api/mi-cue') as response:
                    value=json.load(response)
                self.assertEqual(value['state'],'disabled');self.assertIsNone(value['result'])
                for origin,body,expected in ((None,b'{}',403),('http://foreign',b'{}',403),
                        (address,b'x'*4097,400),(address,b'[]',400),(address,b'{}',409)):
                    headers={'Content-Type':'application/json'}
                    if origin is not None: headers['Origin']=origin
                    request=Request(address+'/api/mi-cue',data=body,headers=headers)
                    with self.assertRaises(HTTPError) as raised: urlopen(request)
                    self.assertEqual(raised.exception.code,expected)
                    raised.exception.close()
                with urlopen(address+'/api/status') as response:
                    self.assertTrue(json.load(response)['stale'])
            finally:
                server.shutdown();server.server_close();worker.join(2)

    def test_boot_report_does_not_claim_new_arm_version_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'boot').write_text('same')
            (root/'status').write_text('{"boot_id":"same","state":"ready","release_id":"old"}')
            (root/'manifest').write_text('{"release_id":"new"}')
            with patch.object(web,'STARTUP_PATH',root/'status'),patch.object(web,'BOOT_ID_PATH',root/'boot'),patch.object(web,'MANIFEST_PATH',root/'manifest'):
                value=web.startup_status()
            self.assertEqual(value['release_id'],'old')
            self.assertEqual(value['installed_release_id'],'new')
            self.assertTrue(value['arm_update_pending_boot'])


if __name__ == '__main__':
    unittest.main()
