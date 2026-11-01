"""Package the installed default-off ARM entry plus unchanged FPGA/recovery sources."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import zipfile

from run_soak_stage import ROOT, connect, command
from run_mi_arm_acceptance import digest, dump
from deploy_mi_formal_entry import OUT, postflight

HANDOFF=ROOT.parent/'handoff/GuardianLoop_MI_ENTRY_20261002'
BASE=ROOT.parent/'handoff/GuardianLoop_FROZEN_20261001.zip'
BASE_SHA='6ab91f2dceceeb96f199190f888035213eabf1195bc75146a1a766d9684c6530'
OLD_MI=ROOT.parent/'handoff/GuardianLoop_MI_CUED_EXPERIMENTAL_20261002.zip'
OLD_MI_SHA='d0cf8ef8797f69a9832d0b02bb88d29e9c36d6f0a9e3c6cc3bb2376b5a9c797d'


def main():
    ledger=json.loads((OUT/'deployment.json').read_text())
    if ledger['phase']!='installed_verified' or not ledger['passed']:
        raise ValueError('Installed default-off version has not passed')
    if digest(BASE)!=BASE_SHA or digest(OLD_MI)!=OLD_MI_SHA:
        raise ValueError('Original recovery archives changed')
    HANDOFF.mkdir(exist_ok=False)
    shutil.copy2(BASE,HANDOFF/'BASE_FROZEN_20261001.zip')
    shutil.copytree(OUT/'package/runtime',HANDOFF/'runtime')
    shutil.copytree(OUT/'package/systemd',HANDOFF/'systemd')
    shutil.copytree(OUT/'original',HANDOFF/'rollback_original')
    shutil.copy2(ROOT/'eeg_apps_z15/MI_FORMAL_ENTRY_README.md',HANDOFF/'README.md')
    shutil.copy2(ROOT/'eeg_apps_z15/restore_mi_entry_bundle.py',HANDOFF/'restore_mi_entry_bundle.py')
    evidence=HANDOFF/'evidence';evidence.mkdir()
    for name in ('deployment.json','before.json','postflight.json','arm-tests.log','pc-tests.log',
                 'stage-arm-check.json','stage-arm-check.stderr','stop-timeout-diagnostic.txt'):
        shutil.copy2(OUT/name,evidence/name)
    shutil.copy2(ROOT/'eeg_apps_z15/MI_FORMAL_ENTRY_PLAN.md',evidence/'PLAN.md')
    previous=evidence/'accepted_mi_multitask';previous.mkdir()
    for name in ('RESULTS.md','VERIFICATION.json','FINAL_PROTECTION.json'):
        shutil.copy2(ROOT/'eeg_apps_z15/output/mi_multitask_20261002_retry8'/name,previous/name)
    client=connect()
    try:
        result=postflight(client,ledger)
        dump(OUT/'reverification.json',result)
        dump(evidence/'reverification.json',result)
        test_root=ledger['stage']+'/recovery-check'
        with client.open_sftp() as s:
            s.mkdir(test_root)
            for folder in ('runtime','systemd','rollback_original','evidence'):
                s.mkdir(test_root+'/'+folder)
            sources=list((HANDOFF/'runtime').iterdir())+list((HANDOFF/'systemd').iterdir())+\
                list((HANDOFF/'rollback_original').iterdir())+[evidence/'deployment.json',HANDOFF/'restore_mi_entry_bundle.py']
            for path in sources:
                s.put(str(path),test_root+'/'+path.relative_to(HANDOFF).as_posix())
        output=command(client,'python3 '+shlex.quote(test_root+'/restore_mi_entry_bundle.py')+' check')
        if 'ARM_RESTORE_PREFLIGHT_OK' not in output:raise ValueError('Recovery preflight did not pass')
        recovery=dict(passed=True,read_only=True,actual_restore_executed=False,
                      actual_rollback_executed=False,output=output,board_stage=test_root)
        dump(OUT/'recovery-check.json',recovery);dump(evidence/'recovery-check.json',recovery)
    finally:client.close()
    for name,value in ledger['application_hashes'].items():
        if digest(HANDOFF/'runtime'/name)!=value:raise ValueError('Copied runtime mismatch: '+name)
    files=sorted(p for p in HANDOFF.rglob('*') if p.is_file())
    sums=''.join(digest(p)+'  '+p.relative_to(HANDOFF).as_posix()+'\n' for p in files)
    (HANDOFF/'SHA256SUMS.txt').write_text(sums,encoding='utf-8')
    archive=HANDOFF.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as target:
        for p in sorted(HANDOFF.rglob('*')):
            if p.is_file():
                target.write(p,(Path(HANDOFF.name)/p.relative_to(HANDOFF)).as_posix(),
                    compress_type=zipfile.ZIP_STORED if p.name=='BASE_FROZEN_20261001.zip' else zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(archive) as target:
        if target.testzip() is not None:raise ValueError('Archive CRC mismatch')
        for row in sums.splitlines():
            expected,name=row.split('  ',1)
            if hashlib.sha256(target.read(HANDOFF.name+'/'+name)).hexdigest()!=expected:
                raise ValueError('Archived SHA mismatch: '+name)
    report=dict(passed=True,archive=str(archive),sha256=digest(archive),bytes=archive.stat().st_size,
                original_archives_unchanged=digest(BASE)==BASE_SHA and digest(OLD_MI)==OLD_MI_SHA,
                default_mi_enabled=False,pl_changed=False,actual_restore_executed=False)
    dump(OUT/'PACKAGE_VERIFICATION.json',report)
    archive.with_suffix('.zip.sha256').write_text(report['sha256']+'  '+archive.name+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
