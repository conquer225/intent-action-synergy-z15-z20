import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import install_unified_link as installer


@unittest.skipUnless(Path('/proc/sys/kernel/random/boot_id').exists(), 'Board-local Linux installer')
class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.base=self.root/'live';self.base.mkdir()
        self.stage=self.root/'stage';self.stage.mkdir();(self.stage/'payload').mkdir()
        self.targets={self.base/n for n in ['server.py','pins.json','new-link.py']}
        self.protected=self.root/'model';self.protected.write_bytes(b'unchanged-model')
        self.sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        self.plan=dict(boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),tests_passed=True,
            files=[],protected={str(self.protected):self.sha(self.protected)},untouched_services={})
        for n,target in enumerate(sorted(self.targets)):
            if target.name!='new-link.py':target.write_bytes(b'old-'+target.name.encode())
            payload=self.stage/'payload'/str(n);payload.write_bytes(b'new-'+target.name.encode())
            self.plan['files'].append(dict(target=str(target),key=str(n),old_sha=self.sha(target),
                new_sha=self.sha(payload),old_mode=0o644,new_mode=0o644))
        self.before={str(p):self.sha(p) for p in self.targets}

    def patches(self):
        def replace(source,target,mode):
            target.write_bytes(source.read_bytes());target.chmod(mode)
        return patch.multiple(installer,BASE=self.base,TARGETS=self.targets,sha=self.sha,replace=replace,
            write_json=lambda p,r:p.write_text(json.dumps(r)),create=True)

    def test_install_commit_only_restarts_web_and_keeps_models(self):
        with self.patches(),patch.object(installer,'control',create=True) as control,\
             patch.object(installer.subprocess,'run'):
            installer.install(self.stage,self.plan);installer.commit(self.stage,self.plan)
        self.assertEqual(control.call_args_list[0].args,('restart','live-server.service'))
        self.assertFalse(any('guardianloop-cyton.service' in c.args for c in control.call_args_list))
        self.assertEqual(self.protected.read_bytes(),b'unchanged-model')
        self.assertEqual(json.loads((self.stage/'installation.json').read_text())['phase'],'committed')

    def test_web_restart_failure_restores_all_files(self):
        def control(*args):
            if not hasattr(control,'failed') and args[0]=='restart':
                control.failed=True;raise RuntimeError('injected web failure')
        with self.patches(),patch.object(installer,'control',side_effect=control,create=True),\
             patch.object(installer.subprocess,'run'):
            with self.assertRaisesRegex(RuntimeError,'injected'):installer.install(self.stage,self.plan)
        self.assertEqual({str(p):self.sha(p) for p in self.targets},self.before)
        self.assertEqual(json.loads((self.stage/'installation.json').read_text())['phase'],'rolled_back')

    def test_changed_protected_model_blocks_before_restart(self):
        self.protected.write_bytes(b'changed')
        with self.patches(),patch.object(installer,'control',create=True) as control:
            with self.assertRaisesRegex(ValueError,'Protected'):installer.install(self.stage,self.plan)
        control.assert_not_called();self.assertFalse((self.stage/'backup').exists())

    def test_out_of_scope_and_corrupt_payload_block_install(self):
        with self.patches():
            self.plan['files'][0]['target']=str(self.root/'foreign')
            with self.assertRaisesRegex(ValueError,'scope'):installer.install(self.stage,self.plan)
            self.plan['files'][0]['target']=str(sorted(self.targets)[0])
            (self.stage/'payload'/'0').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'Payload'):installer.install(self.stage,self.plan)


if __name__=='__main__':unittest.main()
