import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import install_calibration_repair as installer


class RecoveryTests(unittest.TestCase):
    def test_report_repair_allows_only_its_complete_small_target_set(self):
        base='/home/xilinx/gl-hdmi-live-20261008-ea117349'
        plan=dict(live=base,hdmi_report_update=True,web_services=['gl-hdmi-live-20261008-ea117349-server.service'])
        targets=installer.allowed(plan)
        self.assertIn(Path(base)/'hdmi_stimulus.py',targets)
        self.assertIn(Path(base)/'menu-shells-portrait-live.npz',targets)
        self.assertNotIn(installer.ROOT/'cyton_guardianloop.py',targets)
        self.assertFalse(any(p.suffix=='.bit' or str(p).startswith('/etc/') for p in targets))
        with self.assertRaisesRegex(ValueError,'narrow'):
            installer.allowed(dict(plan,input_repair_update=True))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.stage = root/'stage'; self.stage.mkdir()
        self.live = root/'live'; self.live.mkdir()
        self.media = root/'media'; self.media.mkdir()
        self.source = root/'source.py'; self.source.write_text('new source')
        (self.stage/'backup').mkdir()
        backup = self.stage/'backup/00-source.py'; backup.write_text('old source')
        self.plan = dict(live=str(self.live), web_services=[], files=[dict(
            target=str(self.source), key=backup.name, old_sha=installer.sha(backup),
            new_sha=installer.sha(self.source), old_mode=0o644)])
        (self.stage/'deployment-plan.json').write_text(json.dumps(self.plan))
        (self.stage/'installation.json').write_text(json.dumps(dict(phase='committed')))
        self.caches = []
        for index, base in enumerate((self.live,self.media)):
            target = base/'menu-shells-portrait-live.npz'; target.write_bytes(b'new cache')
            backup = self.stage/('cache-'+str(index)); backup.write_bytes(b'old cache')
            self.caches.append(dict(target=str(target),backup=str(backup),
                old_sha=installer.sha(backup),new_sha=installer.sha(target)))
        (self.stage/'menu-cache-repair.json').write_text(json.dumps(self.caches))

    def rollback(self):
        with patch.object(installer,'MEDIA',self.media), patch.object(installer,'allowed',return_value={self.source}), \
                patch.object(installer,'control') as control:
            self.control=control
            installer.rollback(self.stage)
        return control

    def test_source_and_both_caches_restore_together(self):
        self.rollback()
        self.assertEqual(self.source.read_text(),'old source')
        self.assertTrue(all(Path(row['target']).read_bytes()==b'old cache' for row in self.caches))
        self.assertEqual(json.loads((self.stage/'installation.json').read_text())['phase'],'rolled_back')

    def test_later_cache_change_blocks_before_service_stop(self):
        Path(self.caches[0]['target']).write_bytes(b'user change')
        with self.assertRaisesRegex(ValueError,'later modification'):
            self.rollback()
        self.control.assert_not_called()
        self.assertEqual(self.source.read_text(),'new source')

    def test_corrupt_cache_backup_is_rejected(self):
        Path(self.caches[1]['backup']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'checksum'):
            self.rollback()
        self.assertEqual(self.source.read_text(),'new source')


class PrimaryInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name)
        self.root=self.base/'notebooks/formal';self.root.mkdir(parents=True)
        self.live=self.base/'gl-hdmi-live-20261008-test';self.live.mkdir()
        self.stage=self.base/'stage';self.stage.mkdir();(self.stage/'payload').mkdir()
        self.override=self.base/'units/60-primary-worker.conf';self.override.parent.mkdir()
        self.startup=self.base/'startup.json'
        self.plan=dict(primary_worker_update=True,live=str(self.live),web_services=[],tests_passed=True,
            boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip() if Path('/proc/sys/kernel/random/boot_id').exists() else 'test',
            untouched_services={},files=[])
        manifest={'files':{}}
        for name in installer.PRIMARY_NAMES-{'release_manifest.json'}:
            if name not in ('primary_window.py','async_primary.py','telemetry_json.py'):
                path=self.root/name;path.write_text('old '+name);manifest['files'][name]=installer.sha(path)
        (self.root/'release_manifest.json').write_text(json.dumps(manifest))
        self.plan['previous_manifest_sha']=installer.sha(self.root/'release_manifest.json')
        self.startup.write_text('old startup')
        for name in ('state.json','boot-pins.json'):(self.live/name).write_text('old '+name)
        targets={self.root/n for n in installer.PRIMARY_NAMES}|{self.startup,self.override,
            self.live/'state.json',self.live/'boot-pins.json'}
        for index,target in enumerate(sorted(targets)):
            source=self.stage/'payload'/str(index)
            source.write_text(installer.PRIMARY_CONFIG if target==self.override else
                              json.dumps(manifest) if target.name=='release_manifest.json' else 'new '+target.name)
            self.plan['files'].append(dict(target=str(target),key=source.name,
                old_sha=installer.sha(target),new_sha=installer.sha(source),old_mode=0o644,new_mode=0o644))
        (self.stage/'deployment-plan.json').write_text(json.dumps(self.plan))

    def patches(self):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch.object(installer,'ROOT',self.root))
        stack.enter_context(patch.object(installer,'PRIMARY_OVERRIDE',self.override))
        stack.enter_context(patch.object(installer,'STARTUP',self.startup))
        stack.enter_context(patch.object(installer,'verify_running_ui'))
        stack.enter_context(patch.object(installer.subprocess,'run'))
        stack.enter_context(patch.dict('sys.modules',{'guardianloop_startup':SimpleNamespace(verify_files=lambda *a:None)}))
        if not Path('/proc/sys/kernel/random/boot_id').exists():
            original=Path.read_text
            stack.enter_context(patch.object(Path,'read_text',lambda p,*a,**kw:
                'test' if p.as_posix()=='/proc/sys/kernel/random/boot_id' else original(p,*a,**kw)))
        return stack

    def test_preserve_is_applied_before_stop_and_ui_never_restarted(self):
        commands=[]
        def control(*args):
            commands.append(args)
            if args==('stop','guardianloop-cyton.service'):
                self.assertEqual(self.override.read_text(),installer.PRIMARY_CONFIG)
                self.assertIn(('daemon-reload',),commands)
            return 'yes' if 'RuntimeDirectoryPreserve' in args else ''
        with self.patches(),patch.object(installer,'control',side_effect=control):
            installer.install(self.stage);installer.commit(self.stage)
        self.assertTrue(all('restart' not in args for args in commands))
        self.assertTrue((self.stage/'backup/release/cyton_guardianloop.py').exists())
        self.assertEqual(json.loads((self.stage/'installation.json').read_text())['phase'],'committed')

    def test_failed_install_restores_formal_files_without_touching_ui(self):
        before={row['target']:installer.sha(Path(row['target'])) for row in self.plan['files']}
        commands=[]
        def control(*args):
            commands.append(args)
            return 'yes' if 'RuntimeDirectoryPreserve' in args else ''
        with self.patches(),patch.object(installer,'control',side_effect=control), \
                patch.dict('sys.modules',{'guardianloop_startup':SimpleNamespace(
                    verify_files=lambda *a:(_ for _ in ()).throw(ValueError('fixture verification failure')))}):
            with self.assertRaisesRegex(ValueError,'fixture verification'):installer.install(self.stage)
        self.assertEqual(before,{path:installer.sha(Path(path)) for path in before})
        self.assertTrue(all('restart' not in args for args in commands))
        self.assertEqual(json.loads((self.stage/'installation.json').read_text())['phase'],'rolled_back')

    def test_primary_update_rejects_web_restart_and_other_targets(self):
        with self.patches():
            installer.verify_targets(self.plan)
            self.plan['web_services']=['guardianloop-web.service']
            with self.assertRaisesRegex(ValueError,'web services'):installer.allowed(self.plan)
            self.plan['web_services']=[]
            self.plan['files'][0]['target']=str(self.live/'media_player.py')
            with self.assertRaises(ValueError):installer.verify_targets(self.plan)


class PageTimingAdmissionTests(unittest.TestCase):
    def test_worker_schedule_changes_only_entry_and_its_boot_pin(self):
        live=Path('/home/xilinx/gl-hdmi-live-20261008-test')
        plan=dict(live=str(live),input_repair_update=True,hdmi_worker_schedule_update=True,
                  web_services=['guardianloop-web.service',live.name+'-server.service'])
        targets={live/'hdmi_live_entry.py',live/'boot-pins.json'}
        self.assertEqual(installer.allowed(plan),targets)
        plan['files']=[dict(target=str(path),key=str(i),old_sha='old')
                       for i,path in enumerate(sorted(targets))]
        with patch.object(installer,'sha',return_value='old'):
            installer.verify_targets(plan)
            plan['files'].pop()
            with self.assertRaisesRegex(ValueError,'complete pinned'):installer.verify_targets(plan)
        for mode in ('input_repair_update','primary_worker_update','report_connection_update'):
            changed=dict(plan,**{mode:mode!='input_repair_update'})
            with self.assertRaisesRegex(ValueError,'narrow calibration-preserving'):
                installer.allowed(changed)

    def test_scan_pair_requires_all_display_and_report_targets(self):
        live=Path('/home/xilinx/gl-hdmi-live-20261008-test')
        plan=dict(live=str(live),input_repair_update=True,report_connection_update=True,
                  hdmi_scan_update=True,
                  web_services=['guardianloop-web.service',live.name+'-server.service'])
        targets=installer.allowed(plan)
        self.assertEqual(len(targets),11)
        self.assertTrue({live/'native_scan.py',live/'hdmi_stimulus.py',
                         live/'libguardianloop_scan.so',live/'media_state.json'} <= targets)
        plan['files']=[dict(target=str(path),key=str(i),old_sha='old')
                       for i,path in enumerate(sorted(targets))]
        with patch.object(installer,'sha',return_value='old'):
            installer.verify_targets(plan)
            plan['files'].pop()
            with self.assertRaisesRegex(ValueError,'complete pinned'):
                installer.verify_targets(plan)
        self.assertNotIn(installer.ROOT/'cyton_guardianloop.py',targets)

    def test_scan_update_cannot_bypass_the_pinned_connection_mode(self):
        live=Path('/home/xilinx/gl-hdmi-live-20261008-test')
        with self.assertRaisesRegex(ValueError,'pinned report connection'):
            installer.allowed(dict(live=str(live),hdmi_scan_update=True))

    def test_connection_update_requires_exactly_its_seven_targets(self):
        live=Path('/home/xilinx/gl-hdmi-live-20261008-test')
        plan=dict(live=str(live),input_repair_update=True,report_connection_update=True,
                  web_services=['guardianloop-web.service',live.name+'-server.service'])
        targets={installer.ROOT/'ssvep_cue_runtime.py',installer.ROOT/'release_manifest.json',
                 installer.EYE,installer.STARTUP,live/'state.json',live/'boot-pins.json',
                 Path('/home/xilinx/gl-hdmi-software-20261008-6797e092/runtime/ssvep_cue_runtime.py')}
        self.assertEqual(installer.allowed(plan),targets)
        plan['files']=[dict(target=str(path),key=str(i),old_sha='old')
                       for i,path in enumerate(sorted(targets))]
        with patch.object(installer,'sha',return_value='old'):
            installer.verify_targets(plan)
            removed=plan['files'].pop()
            with self.assertRaisesRegex(ValueError,'complete pinned'):installer.verify_targets(plan)
            plan['files'].append(removed)
            plan['files'][0]['target']=str(installer.ROOT/'cyton_guardianloop.py')
            with self.assertRaisesRegex(ValueError,'Foreign'):installer.verify_targets(plan)

    def test_connection_update_cannot_bypass_preservation_or_mix_modes(self):
        live=Path('/home/xilinx/gl-hdmi-live-20261008-test')
        plan=dict(live=str(live),input_repair_update=True,report_connection_update=True,
                  web_services=['guardianloop-web.service',live.name+'-server.service'])
        for mode in ('page_timing_update','prewear_issue_update'):
            with self.assertRaisesRegex(ValueError,'combine narrow'):
                installer.allowed(dict(plan,**{mode:True}))
        with self.assertRaisesRegex(ValueError,'calibration-preserving'):
            installer.allowed(dict(plan,input_repair_update=False))

    def test_prewear_startup_permissions_are_part_of_the_install_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            startup=Path(directory)/'startup.json';startup.write_text('{"state":"ready"}')
            row=dict(target=str(startup),key='startup.json',old_sha=installer.sha(startup),
                     new_sha=installer.sha(startup),new_mode=0o600)
            plan=dict(input_repair_update=True,prewear_issue_update=True,files=[row])
            with patch.object(installer,'STARTUP',startup),patch.object(installer,'allowed',return_value={startup}):
                with self.assertRaisesRegex(ValueError,'readable by the web'):installer.verify_targets(plan)
                row['new_mode']=0o644
                installer.verify_targets(plan)

    @unittest.skipUnless(Path('/proc/sys/kernel/random/boot_id').exists(),'Linux permission bits')
    def test_installed_startup_content_alone_cannot_hide_unreadable_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            startup=Path(directory)/'startup.json';startup.write_text('{"state":"ready"}')
            row=dict(target=str(startup),key='startup.json',new_sha=installer.sha(startup),new_mode=0o644)
            plan=dict(input_repair_update=True,prewear_issue_update=True,files=[row])
            with patch.object(installer,'STARTUP',startup),patch.object(installer,'allowed',return_value={startup}):
                startup.chmod(0o600)
                with self.assertRaisesRegex(ValueError,'permission differs'):installer.verify_targets(plan,installed=True)
                startup.chmod(0o644)
                installer.verify_targets(plan,installed=True)

    def test_prewear_repair_has_only_four_sources_and_required_metadata(self):
        plan=dict(input_repair_update=True,prewear_issue_update=True,
                  live='/home/xilinx/gl-hdmi-live-20261008-test',
                  web_services=['guardianloop-web.service','gl-hdmi-live-20261008-test-server.service'],files=[])
        targets=installer.allowed(plan)
        self.assertEqual(len(targets),9)
        self.assertIn(installer.ROOT/'mobile.js',targets)
        self.assertIn(installer.ROOT/'async_primary.py',targets)
        self.assertNotIn(installer.ROOT/'cyton_sqi.py',targets)
        self.assertFalse(any(p.suffix in ('.bit','.hwh','.npz') for p in targets))
        plan['page_timing_update']=True
        with self.assertRaisesRegex(ValueError,'combine narrow'):installer.allowed(plan)
        plan['page_timing_update']=False;plan['input_repair_update']=False
        with self.assertRaisesRegex(ValueError,'calibration-preserving'):installer.allowed(plan)

    def test_timing_update_pins_only_two_sources_and_required_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'notebooks/formal'
            live=base/'gl-hdmi-live-20261008-test';eye=base/'eye/guard.py'
            startup=base/'startup.json'
            plan=dict(input_repair_update=True,page_timing_update=True,live=str(live),
                      web_services=['guardianloop-web.service',live.name+'-server.service'],files=[])
            targets={root/'page_policy.py',root/'release_manifest.json',eye,startup,
                     live/'state.json',live/'boot-pins.json',live/'media_player.py'}
            for index,path in enumerate(sorted(targets)):
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text('unchanged')
                plan['files'].append(dict(target=str(path),key=str(index),old_sha=installer.sha(path)))
            with patch.object(installer,'ROOT',root),patch.object(installer,'EYE',eye), \
                    patch.object(installer,'STARTUP',startup):
                self.assertEqual(installer.allowed(plan),targets)
                installer.verify_targets(plan)
                removed=plan['files'].pop()
                with self.assertRaisesRegex(ValueError,'complete pinned'):installer.verify_targets(plan)
                plan['files'].append(removed)
                plan['files'][0]['target']=str(root/'gameemo_covariance_svm.npz')
                with self.assertRaisesRegex(ValueError,'Foreign'):installer.verify_targets(plan)

    def test_timing_update_cannot_bypass_calibration_preservation_mode(self):
        plan=dict(live='/home/xilinx/gl-hdmi-live-20261008-test',page_timing_update=True)
        with self.assertRaisesRegex(ValueError,'calibration-preserving'):installer.allowed(plan)

if __name__=='__main__':
    unittest.main()
