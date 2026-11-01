import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hdmi_boot import verified_state, wait_local_network, start_static_home, main


class BootTests(unittest.TestCase):
    def test_boot_refreshes_only_its_media_identity_pin(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);override=base/'absent-override.conf'
            state=dict(remote=str(base),boot='old',before_pid=10,user_controlled=True)
            media=dict(boot='old',unchanged_configuration='keep',auto_hdmi_on_drive=True)
            (base/'state.json').write_text(json.dumps(state))
            (base/'media_state.json').write_text(json.dumps(media))
            module=base/'module.py';module.write_bytes(b'# pinned')
            files={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (base/'media_state.json',module)}
            (base/'boot-pins.json').write_text(json.dumps(dict(files=files)))
            read_text=Path.read_text
            def read(path,*args,**kwargs):
                if str(path)=='/proc/sys/kernel/random/boot_id':return 'new'
                return read_text(path,*args,**kwargs)
            with patch('hdmi_boot.BASE',base),patch('hdmi_boot.OVERRIDE',override),\
                 patch('hdmi_boot.run',return_value='99'),patch.object(Path,'read_text',read),\
                 patch('hdmi_boot.wait_local_network'),patch('hdmi_boot.activate') as activate,\
                 patch('hdmi_boot.start_static_home',return_value={'session_id':'test'}):
                main()
            self.assertEqual(activate.call_count,1)
            self.assertEqual(json.loads((base/'media_state.json').read_text()),dict(media,boot='new'))
            pins=json.loads((base/'boot-pins.json').read_text())['files']
            self.assertEqual(pins[str(module)],files[str(module)])
            self.assertEqual(pins[str(base/'media_state.json')],
                             hashlib.sha256((base/'media_state.json').read_bytes()).hexdigest())
            self.assertEqual(verified_state(base,'next',100,pins)['boot'],'next')

    def test_boot_requests_static_home_without_starting_eye_or_flicker(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);(base/'access.key').write_text('test-key')
            from unittest.mock import MagicMock
            response=MagicMock();response.status=202;response.read.return_value=b'{"session_id":"test"}'
            response.__enter__.return_value=response
            with patch('hdmi_boot.BASE',base),patch('hdmi_boot.urllib.request.urlopen',return_value=response) as open_url:
                self.assertEqual(start_static_home()['session_id'],'test')
            request=open_url.call_args.args[0]
            self.assertEqual(json.loads(request.data),{'action':'display_start'})
            self.assertEqual(request.get_header('X-media-key'),'test-key')

    def test_local_ap_is_enough_without_hotspot_or_internet(self):
        rows=[json.dumps([{'addr_info':[]}]),json.dumps([{'ifname':'wlan0','addr_info':[{'scope':'global','local':'192.168.50.1'}]}])]
        with patch('hdmi_boot.run',side_effect=rows) as command,patch('hdmi_boot.time.sleep'):
            wait_local_network()
        self.assertEqual(command.call_count,2)

    def test_missing_local_network_fails_without_any_pl_action(self):
        with patch('hdmi_boot.run',return_value='[]') as command,\
             patch('hdmi_boot.time.monotonic',side_effect=[10,10]):
            with self.assertRaises(ValueError):wait_local_network(timeout=0)
        command.assert_called_once_with('ip','-j','-4','addr','show','up')

    def test_fresh_boot_identity_requires_exact_software_pins(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);artifact=base/'module.py';artifact.write_bytes(b'# pinned')
            old=dict(remote=str(base),boot='old',before_pid=10,user_controlled=True)
            (base/'state.json').write_text(json.dumps(old))
            pins={str(artifact):hashlib.sha256(artifact.read_bytes()).hexdigest()}
            new=verified_state(base,'new',99,pins)
            self.assertEqual(new['boot'],'new');self.assertEqual(new['before_pid'],99)
            self.assertEqual(json.loads((base/'state.json').read_text()),old)
            artifact.write_bytes(b'# changed')
            with self.assertRaises(ValueError):verified_state(base,'new',99,pins)
