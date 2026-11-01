"""Exercise the actual shipped bundle and strict rollback in isolated roots."""
from pathlib import Path
import hashlib,importlib.util,json,sys,tempfile
release=Path(__file__).resolve().parents[2]
v=release/'integrations/vision_demo';sys.path.insert(0,str(v))
from install_vision import plan_update,transaction
spec=importlib.util.spec_from_file_location('fixture',v.parent/'eeg_demo/tests/test_install_demo.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
name='system_runtime/guardianloop_system/device_link.py'
results=[]
for control in ('old','current'):
 with tempfile.TemporaryDirectory() as temp:
  roots,_,_=fixture.InstallDemoTests().fixture(Path(temp));media=roots['media']
  for n in ('media_player.py','page_audio.py'):
   (media/n).write_bytes((v.parent/'eeg_demo/runtime'/n).read_bytes())
  for n in json.loads((v/'presentation_baseline.json').read_text()):
   path=media/n;path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes((release/'local/presentation_before_20261020'/n).read_bytes())
  path=media/name;path.parent.mkdir(parents=True,exist_ok=True)
  before_control=(release/'local/device_control_before_20261021'/name if control=='old' else v.parent/'eeg_demo/runtime'/name)
  path.write_bytes(before_control.read_bytes())
  (media/'media_state.json').write_text('{"hardware_hashes":{},"hdmi_audio":true}')
  before={p:p.read_bytes() for root in roots.values() for p in root.rglob('*') if p.is_file()}
  plan=plan_update(roots,release/'bundle')
  backup=transaction.apply_transaction(roots,plan)
  state=json.loads((media/'media_state.json').read_text())
  assert state['vision_demo']['streaming'] and state['vision_demo']['signal_pages']
  pins=json.loads((media/'boot-pins.json').read_text())['files']
  for n,d in pins.items():assert transaction.digest(Path(n))==d,n
  changed={transaction.target(roots,k) for k in plan}
  for p,data in before.items():
   if p not in changed:assert p.read_bytes()==data,p
  created=[p for p in changed if p not in before]
  transaction.rollback(roots,backup)
  for p,data in before.items():assert p.read_bytes()==data,p
  for p in created:assert not p.exists(),p
  path.write_bytes(before_control.read_bytes()+b'\n# unknown revision\n')
  try:plan_update(roots,release/'bundle')
  except ValueError as exc:assert 'Installed baseline differs' in str(exc)
  else:raise AssertionError('Unreviewed control baseline was accepted')
  results.append(dict(baseline=control,transaction_files=len(plan),boot_pins=len(pins),
      strict_rollback=True,unrelated_files_unchanged=True,unknown_baseline_rejected=True))
print(json.dumps(dict(passed=True,cases=results),indent=2))
