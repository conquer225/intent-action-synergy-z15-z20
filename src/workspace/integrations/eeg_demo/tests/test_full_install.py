"""Install the reviewed payload into independently reconstructed archive runtimes."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'brain_runtime')]
import install_demo as install


class FullInstallTests(unittest.TestCase):
    def test_archive_install_startup_integrity_and_byte_exact_rollback(self):
        base=Path(os.environ.get('GL_BASELINE_ROOT',str(ROOT.parent/'guardianloop_team_20261017_03')))
        if not base.exists():base=ROOT.parent
        latest=base/'latest_saved_runtime/rootfs'
        with tempfile.TemporaryDirectory() as folder:
            roots={name:Path(folder)/name for name in ('media','brain','eye')}
            shutil.copytree(base/'projects/codex_project/pynq_guardianloop',roots['brain'])
            shutil.copytree(latest/'home/xilinx/jupyter_notebooks/guardianloop_pynq',roots['brain'],dirs_exist_ok=True)
            shutil.copytree(ROOT/'runtime',roots['media'],ignore=shutil.ignore_patterns('__pycache__'))
            # Reconstruct previous reviewed media baseline, without its new demo changes.
            baseline=json.loads((ROOT/'baseline_sha256.json').read_text())
            for row in json.loads((ROOT/'update_manifest.json').read_text())['files']:
                if row['group']!='media':continue
                dst=roots['media']/row['name'];old=baseline.get('runtime/'+row['name'])
                if old is None:
                    if dst.exists():dst.unlink()
                    continue
                candidates=list(latest.rglob(Path(row['name']).name))
                source=next((p for p in candidates if p.is_file() and install.digest(p)==old),None)
                if source is not None:shutil.copy2(source,dst)
                elif install.digest(dst)!=old:
                    # Prior eye controller is available in the preserved delivery baseline.
                    source=ROOT.parent/'eye_c3/runtime'/row['name']
                    if not source.exists():source=ROOT.parent/'eye_c3_update/runtime'/row['name']
                    preserved=ROOT/'legacy_debug_hold/baseline_20261018'/Path(row['name']).name
                    if preserved.is_file() and install.digest(preserved)==old:source=preserved
                    if source.exists() and install.digest(source)==old:shutil.copy2(source,dst)
                    else:
                        original_sha=row['before'][0] if isinstance(row['before'],list) else row['before']
                        source=next((p for p in base.rglob(Path(row['name']).name) if p.is_file() and install.digest(p)==original_sha),None)
                        self.assertIsNotNone(source,row['name']);shutil.copy2(source,dst)
            guard=roots['eye']/'src/coexist_guard.py';guard.parent.mkdir(parents=True)
            shutil.copy2(latest/'home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py',guard)
            manifest=json.loads((roots['brain']/'release_manifest.json').read_text(encoding='utf-8'))
            # Private board state and boot pins are absent from the archive: explicit test fixture.
            (roots['media']/'state.json').write_text(json.dumps({'formal_hashes':manifest['files']}))
            (roots['media']/'boot-pins.json').write_text(json.dumps({'files':{str(guard):install.digest(guard)},'manifest_sha256':install.digest(roots['brain']/'release_manifest.json')}))
            before={(group,str(p.relative_to(root))):install.digest(p) for group,root in roots.items() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
            payload,expected=install.payload_files(roots,'192.168.4.2')
            backup=install.apply_transaction(roots,install.prepare(roots,payload,expected))
            spec=importlib.util.spec_from_file_location('installed_guard',guard)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.verify_release(roots['brain'])
            import guardianloop_startup
            updated=json.loads((roots['brain']/'release_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(guardianloop_startup.verify_files(roots['brain'],updated),len(updated['files']))
            for name in ('gameemo_covariance_svm.npz','cyton_fatigue_overlap4.json','guardianloop_pynq.bit','guardianloop_pynq.hwh'):
                self.assertEqual(install.digest(roots['brain']/name),before[('brain',name)])
            install.rollback(roots,backup)
            after={(group,str(p.relative_to(root))):install.digest(p) for group,root in roots.items() for p in root.rglob('*') if p.is_file() and '.eeg-demo-backups' not in p.parts and '__pycache__' not in p.parts}
            self.assertEqual(before,after)


if __name__=='__main__':unittest.main()
