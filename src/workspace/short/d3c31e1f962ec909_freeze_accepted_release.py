"""Seal a passed release with the existing source/recovery bundle and evidence."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import zipfile

from deploy_startup import ROOT, connect, digest, sudo

BASE=ROOT.parent/'handoff/GL_Z15_20261001_153111.zip'
BASE_SHA='56b32e90fba8cb48ab256bcc2d63c4e3c4a8b5c3a87a28bc34ded328932e7bdf'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acceptance',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=args.acceptance.resolve(); output=args.output.resolve()
    audit=json.loads((source/'ACCEPTANCE.json').read_text(encoding='utf-8'))
    if not audit['passed']:
        raise RuntimeError('Acceptance has not passed; refused release freeze')
    if sha(BASE)!=BASE_SHA:
        raise RuntimeError('Previous recovery/source archive changed')
    with zipfile.ZipFile(BASE) as archive:
        top=BASE.stem+'/'
        previous=json.loads(archive.read(top+'PACKAGE_AUDIT.json'))
        inventory=json.loads(archive.read(top+'FILES_SHA256.json'))
    after=json.loads((source/'after.json').read_text(encoding='utf-8'))
    if previous['release_manifest']['files']!=after['installed_hashes']:
        raise RuntimeError('Previous bundle is not the currently tested release')
    client=connect()
    current={}
    try:
        with client.open_sftp() as sftp:
            for item in inventory:
                if not item['source'].startswith('z15:'):
                    continue
                path=item['source'][4:]
                try:
                    value=digest(sftp,path)
                except PermissionError:
                    value=sudo(client,'sha256sum '+shlex.quote(path)).split()[0]
                if value!=item['sha256']:
                    raise RuntimeError('Recovery snapshot no longer matches board: '+path)
                current[path]=value
    finally:
        client.close()
    output.mkdir(parents=True,exist_ok=False)
    shutil.copy2(BASE,output/'SOURCE_AND_BOARD_RECOVERY.zip')
    evidence=output/'acceptance'; evidence.mkdir()
    for item in source.iterdir():
        if item.is_file():
            shutil.copy2(item,evidence/item.name)
        elif item.is_dir():
            shutil.copytree(item,evidence/item.name)
    bench=ROOT/'eeg_apps_z15/output/accepted_bench_load_20260927'
    input_folder=output/'bench_input'; input_folder.mkdir()
    for name in ('bench_input.npz','manifest.json'):
        shutil.copy2(bench/name,input_folder/name)
    if sha(input_folder/'bench_input.npz')!=json.loads((source/'PLAN.json').read_text())['input_sha256']:
        raise RuntimeError('Frozen bench input mismatch')
    scripts=output/'reproduce';scripts.mkdir()
    for name in ('accept_frozen_release.py','check_frozen_release.py','freeze_accepted_release.py'):
        shutil.copy2(ROOT/'eeg_apps_z15'/name,scripts/name)
    for name in ('replay_release_audit.py','soak_service_replay.py','replay_stage_trace.py'):
        shutil.copy2(ROOT/'pynq_guardianloop'/name,scripts/name)
    frozen={'release_id':audit['release_id'],'frozen_at_pc_local':datetime.now().isoformat(),
            'board_boot_id':after['boot_id'],'passed_acceptance':True,
            'installed_runtime_sha256':after['installed_hashes'],
            'board_and_startup_config_sha256':current,
            'source_and_recovery_archive_sha256':BASE_SHA,
            'acceptance_sha256':sha(source/'ACCEPTANCE.json'),
            'boot_images_modified':False,'new_pl_candidate_promoted':False,
            'fixed_cap':['F3','F4','C3','C4','T7','T8','O1','O2'],
            'remaining_real_world_acceptance':True,
            'accuracy_claim':'No new recognition-accuracy claim; replay bench is not labeled EEG.'}
    (output/'FROZEN_RELEASE.json').write_text(json.dumps(frozen,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    readme=source/'FREEZE_README.md'
    if not readme.exists():
        raise RuntimeError('Missing human-readable restore/scope instructions')
    shutil.copy2(readme,output/'README.md')
    entries=sorted(p for p in output.rglob('*') if p.is_file())
    checksums=''.join(sha(p)+'  '+p.relative_to(output).as_posix()+'\n' for p in entries)
    (output/'SHA256SUMS.txt').write_text(checksums,encoding='utf-8')
    archive_path=output.with_suffix('.zip')
    with zipfile.ZipFile(archive_path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                archive.write(path,(Path(output.name)/path.relative_to(output)).as_posix())
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Frozen archive CRC failed')
        for line in checksums.splitlines():
            expected,name=line.split('  ',1)
            if hashlib.sha256(archive.read(output.name+'/'+name)).hexdigest()!=expected:
                raise RuntimeError('Frozen archive SHA mismatch: '+name)
    archive_path.with_suffix('.zip.sha256').write_text(sha(archive_path)+'  '+archive_path.name+'\n')
    print(json.dumps({'archive':str(archive_path),'sha256':sha(archive_path),
                      'bytes':archive_path.stat().st_size,'board_files_rechecked':len(current),
                      'crc_and_sha256':'passed'},indent=2),flush=True)


if __name__=='__main__':
    main()
