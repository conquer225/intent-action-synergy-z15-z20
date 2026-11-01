import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import media_server as media
from upload_server import make_server


class FakeController:
    def __init__(self):self.lock=threading.Lock();self.wheelchair_lock=threading.Lock();self.calls=[];self.rows=[];self.state={}
    def videos(self):return self.rows
    def snapshot(self):return {'silent':True,'files':[]}
    def prepare(self,ident):self.calls.append(('prepare',ident));return {'state':'preparing'}
    def play(self,ident):self.calls.append(('play',ident));return {'state':'starting'}
    def start_home(self):self.calls.append(('display_start',None));return {'state':'starting'}
    def command(self,action,value=None):self.calls.append((action,value));return {'accepted':action}
    def wearing(self,action,value=None):self.calls.append((action,value));return {'state':'unchanged'}
    def manual_wheelchair(self,value):
        if type(value) is not str or value not in {'stop','forward','backward','left','right','ssvep'}:
            raise ValueError('Invalid wheelchair direction')
        self.calls.append(('wheelchair_manual',value));return {'queued':'wheelchair_manual'}


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=media.MediaStore(self.tmp.name,'test-private-key','unused')
        self.server=make_server('127.0.0.1',0,self.store)
        self.server.RequestHandlerClass=media.MediaHandler;self.controller=FakeController()
        self.server.controller=self.controller
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.finish)

    def finish(self):self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,body=None,key='test-private-key',origin=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={'X-Media-Key':key}
        if origin:headers['Origin']=origin
        try:
            c.request('POST' if body else 'GET','/api/player',body,headers)
            r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()

    def test_authenticated_status_is_silent(self):
        code,data=self.request();self.assertEqual(code,200);self.assertTrue(data['silent'])

    def test_volume_requires_enabled_audio_and_integer_percentage(self):
        self.assertEqual(self.request(json.dumps(dict(action='volume',value=40)))[0],409)
        self.controller.state['hdmi_audio']={'candidate':True}
        for invalid in (-1,101,True,12.5,'40',None):
            self.assertEqual(self.request(json.dumps(dict(action='volume',value=invalid)))[0],409)
        self.assertFalse(self.controller.calls)
        self.assertEqual(self.request(json.dumps(dict(action='volume',value=40)))[0],202)
        self.assertEqual(self.controller.calls,[('volume',40)])
        self.assertEqual(self.request(json.dumps(dict(action='volume',value=20)),key='bad')[0],403)

    def test_manual_wheelchair_requires_key_and_fixed_direction(self):
        body=json.dumps({'action':'wheelchair_manual','value':'forward'})
        self.assertEqual(self.request(body,key='bad')[0],403)
        self.assertEqual(self.request(body,origin='http://foreign')[0],403)
        for value in ('/start',None,{},'http://other'):
            self.assertEqual(self.request(json.dumps({'action':'wheelchair_manual','value':value}))[0],409)
        self.assertFalse(self.controller.calls)
        for value in ('forward','backward','left','right','stop','ssvep'):
            self.assertEqual(self.request(json.dumps({'action':'wheelchair_manual','value':value}))[0],202)
        self.assertEqual(self.controller.calls,[('wheelchair_manual',v) for v in ('forward','backward','left','right','stop','ssvep')])

    def test_manual_queue_has_boot_identity_and_does_not_claim_delivery(self):
        controller=media.Controller.__new__(media.Controller);controller.state={'wheelchair_link':True}
        with patch.object(Path,'read_text',return_value='current-boot'),patch.object(media,'write_json') as write:
            result=controller.manual_wheelchair('stop')
        path,row=write.call_args.args
        self.assertEqual(path.name,media.BASE.name+'-wheelchair-manual.json')
        self.assertEqual(row['boot'],'current-boot');self.assertEqual(row['value'],'stop')
        self.assertEqual(result['command_id'],row['id']);self.assertTrue(result['not_yet_confirmed'])
        self.assertFalse(result['physical_output_enabled'])
        controller.state={}
        with patch.object(media,'write_json') as write:
            with self.assertRaises(ValueError):controller.manual_wheelchair('forward')
        write.assert_not_called()

    def test_manual_stop_is_not_blocked_by_display_snapshot_lock(self):
        with self.controller.lock:
            code,_=self.request(json.dumps(dict(action='wheelchair_manual',value='stop')))
        self.assertEqual(code,202)

    def test_manual_heartbeat_requires_private_key(self):
        self.assertEqual(self.request(json.dumps(dict(action='wheelchair_heartbeat',value='old')),key='bad')[0],403)

    def test_eye_missing_maintenance_and_runtime_are_distinguished(self):
        root=Path(self.tmp.name)/'usb';root.mkdir()
        self.assertEqual(media.eye_device(root)['state'],'missing')
        device=root/'1-1.4';device.mkdir()
        for name,value in [('idVendor','2104'),('serial','CN033F74DTOB186P0822A00'),('idProduct','0102')]:
            (device/name).write_text(value)
        self.assertEqual(media.eye_device(root)['state'],'maintenance')
        (device/'idProduct').write_text('0124')
        self.assertEqual(media.eye_device(root)['state'],'runtime')
        (device/'serial').write_text('different')
        self.assertEqual(media.eye_device(root)['state'],'missing')

    def test_maintenance_eye_is_rejected_before_starting_native_sampler(self):
        controller=media.Controller.__new__(media.Controller)
        with patch.object(controller,'active',return_value=True),\
                patch.object(media,'eye_device',return_value={'state':'maintenance','pid':'0102'}),\
                patch.object(media,'write_json') as write:
            with self.assertRaisesRegex(ValueError,'0102'):controller.command('eye_start')
        write.assert_not_called()

    def test_display_start_requires_authentication(self):
        body=json.dumps({'action':'display_start'})
        self.assertEqual(self.request(body,key='bad')[0],403)
        self.assertEqual(self.request(body)[0],202)
        self.assertEqual(self.controller.calls,[('display_start',None)])

    def test_home_entry_reuses_existing_display_or_starts_static_home(self):
        controller=media.Controller({});self.addCleanup(controller.brain.close)
        with patch.object(controller,'active',return_value=True),patch.object(controller,'command') as command,patch.object(controller,'play') as play:
            controller.start_home();command.assert_called_once_with('home');play.assert_not_called()
        with patch.object(controller,'active',return_value=False),patch.object(controller,'play') as play:
            controller.start_home();play.assert_called_once_with('sd02',initial_page='home')

    def test_wearing_actions_require_authentication(self):
        self.assertEqual(self.request(json.dumps({'action':'wear_continue'}),key='bad')[0],403)
        self.assertEqual(self.request(json.dumps({'action':'wear_continue'}))[0],202)
        self.assertEqual(self.controller.calls,[('wear_continue',None)])

    def test_new_wearing_is_explicit_and_stops_active_controls_first(self):
        controller=media.Controller({});self.addCleanup(controller.brain.close)
        with patch.object(controller,'active',return_value=True),\
             patch.object(controller,'command') as command,\
             patch.object(controller.wear,'request_new',return_value={'state':'queued'}) as reset:
            with self.assertRaises(ValueError):controller.wearing('wear_new',{'expected_id':'current'})
            command.assert_not_called();reset.assert_not_called()
            result=controller.wearing('wear_new',{'confirm':True,'expected_id':'current'})
        command.assert_called_once_with('force_stop')
        reset.assert_called_once_with('current');self.assertEqual(result['state'],'queued')

    def test_no_key_and_cross_origin_cannot_start_player(self):
        self.assertEqual(self.request(json.dumps({'action':'play','id':'fixture60'}),key='bad')[0],403)
        self.assertEqual(self.request(json.dumps({'action':'play','id':'fixture60'}),origin='http://foreign')[0],403)
        self.assertFalse(self.controller.calls)

    def test_only_fixed_actions_are_exposed(self):
        self.assertEqual(self.request(json.dumps({'action':'shell','id':'rm'}))[0],409)
        self.assertEqual(self.request(json.dumps({'action':'play','id':'x','path':'/boot'}))[0],409)
        self.assertFalse(self.controller.calls)

    def test_pause_resume_stop_dispatch_without_path_parameters(self):
        for action in ('pause','resume','stop'):
            self.assertEqual(self.request(json.dumps({'action':action}))[0],202)
        self.assertEqual(self.controller.calls,[(a,None) for a in ('pause','resume','stop')])

    def test_force_stop_and_fatigue_confirmation_remain_authenticated(self):
        self.assertEqual(self.request(json.dumps({'action':'force_stop'}),key='bad')[0],403)
        for action in ('force_stop','fatigue_warning'):
            self.assertEqual(self.request(json.dumps({'action':action}))[0],202)
        self.assertEqual(self.request(json.dumps({'action':'ack','value':'fatigue'}))[0],202)
        self.assertEqual(self.request(json.dumps({'action':'ack','value':'all'}))[0],409)
        self.assertEqual(self.controller.calls,[('force_stop',None),('fatigue_warning',None),('ack','fatigue')])

    def test_hdmi_candidate_requires_configuration_key_and_explicit_consent(self):
        command=json.dumps({'action':'hdmi_start','value':True})
        self.assertEqual(self.request(command)[0],409)
        self.controller.state['hdmi_candidate']=True
        self.assertEqual(self.request(command,key='bad')[0],403)
        self.assertEqual(self.request(json.dumps({'action':'hdmi_start'}))[0],409)
        self.assertEqual(self.request(command)[0],202)
        self.assertEqual(self.controller.calls,[('hdmi_start',True)])

    def test_download_is_header_authenticated_and_known_id_only(self):
        p=Path(self.tmp.name)/'video.mp4';p.write_bytes(b'private-video')
        self.controller.rows=[{'id':'sd01','download':str(p)}]
        def get(path,key):
            c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
            try:
                c.request('GET',path,headers={'X-Media-Key':key})
                r=c.getresponse();return r.status,r.read()
            finally:c.close()
        self.assertEqual(get('/download/sd01','bad')[0],403)
        self.assertEqual(get('/download/../BOOT.BIN','test-private-key')[0],404)
        self.assertEqual(get('/download/sd01?key=secret','test-private-key')[0],400)
        self.assertEqual(get('/download/sd01','test-private-key'),(200,b'private-video'))

    def test_real_controller_rejects_unverified_id_before_any_system_command(self):
        controller=media.Controller({});controller.store=self.store
        self.addCleanup(controller.brain.close)
        with patch.object(media,'run',side_effect=AssertionError('must not execute')):
            with self.assertRaises(ValueError):controller.cache('../BOOT.BIN')
            with self.assertRaises(ValueError):controller.prepare('0'*32)

    def test_unprepared_native_candidate_never_arms_timer_or_loads_pl(self):
        controller=media.Controller({'hdmi_candidate':True})
        self.addCleanup(controller.brain.close)
        with patch.object(controller,'active',return_value=False),patch.object(media,'run') as command:
            with self.assertRaisesRegex(ValueError,'not prepared'):controller.play('sd01')
        command.assert_not_called()

    def test_default_diagnostic_never_silently_selects_failed_delta(self):
        controller=media.Controller({})
        self.addCleanup(controller.brain.close)
        self.assertEqual(controller.cache('fixture60'),media.BASE/'fixture60compact')
        self.assertEqual(controller.cache('fixture60yuv'),media.BASE/'fixture60')

    def test_user_controlled_play_has_no_timer_and_default_keeps_timer(self):
        for user_controlled in (True,False):
            controller=media.Controller({'user_controlled':user_controlled})
            self.addCleanup(controller.brain.close)
            with patch.object(controller,'active',return_value=False),\
                 patch.object(controller,'videos',return_value=[{'id':'sd01','cache':'/private/cache'}]),\
                 patch.object(controller.library,'snapshot',return_value=[{'id':'sd01','prepared':True}]),\
                 patch.object(media,'manifest',return_value={'width':288,'height':512}),\
                 patch.object(media,'write_json'),patch.object(media,'run') as command:
                controller.play('sd01')
            calls=[call.args for call in command.call_args_list]
            timers=[args for args in calls if '--on-active=650s' in args]
            self.assertEqual(len(timers),0 if user_controlled else 1)
            self.assertEqual(controller.session['seconds'],None if user_controlled else 600)
            self.assertTrue(any('OPENBLAS_NUM_THREADS=1' in args for args in calls))


class RemoteManualTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.controller=media.Controller.__new__(media.Controller)
        self.controller.state=dict(wheelchair_link=True,wheelchair_motor_test=True)
        self.controller.wheelchair_epoch='initial'
        def resolve(value):
            if value=='/dev/shm':return self.root
            if value=='/proc/sys/kernel/random/boot_id':return SimpleNamespace(read_text=lambda:'current-boot')
            return Path(value)
        self.patch=patch.object(media,'Path',side_effect=resolve);self.patch.start();self.addCleanup(self.patch.stop)

    def select(self,direction):
        return self.controller.manual_wheelchair(dict(direction=direction,epoch=self.controller.wheelchair_epoch))

    def row(self):return json.loads((self.root/(media.BASE.name+'-wheelchair-manual.json')).read_text())

    def test_heartbeat_cannot_recreate_stopped_or_superseded_command(self):
        with patch.object(media.time,'monotonic',return_value=10.):
            first=self.select('forward');old_epoch=self.controller.wheelchair_epoch
            self.assertFalse(self.row()['heartbeat_confirmed'])
        with patch.object(media.time,'monotonic',return_value=10.2):
            self.controller.wheelchair_heartbeat(first['command_id'])
            self.assertTrue(self.row()['heartbeat_confirmed'])
            self.controller.manual_wheelchair('stop')
            with self.assertRaises(ValueError):self.controller.wheelchair_heartbeat(first['command_id'])
            with self.assertRaises(ValueError):self.controller.manual_wheelchair(dict(direction='right',epoch=old_epoch))
        self.assertEqual(self.row()['value'],'stop')

    def test_expired_heartbeat_and_old_page_cannot_restart_motion(self):
        with patch.object(media.time,'monotonic',return_value=10.):first=self.select('left')
        with patch.object(media.time,'monotonic',return_value=10.8):
            with self.assertRaises(ValueError):self.controller.wheelchair_heartbeat(first['command_id'])
        self.assertEqual(self.row()['heartbeat_monotonic'],10.)
        for value in ('forward',dict(direction='forward',epoch='previous-server'),dict(direction='left',epoch=self.controller.wheelchair_epoch,extra=True)):
            with self.assertRaises(ValueError):self.controller.manual_wheelchair(value)


if __name__=='__main__':unittest.main()
