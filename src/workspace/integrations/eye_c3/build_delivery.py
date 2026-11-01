"""Package the preserved source archive and the reviewed eye-device update."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-zip',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    patch=json.loads((ROOT/'patch_manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256(args.source_zip.read_bytes()).hexdigest()!=patch['source_archive_sha256']:
        raise ValueError('Different original archive')
    for name,row in patch['files'].items():
        if hashlib.sha256((ROOT/'runtime'/name).read_bytes()).hexdigest()!=row['after']:
            raise ValueError('Reviewed payload changed: '+name)
    selected=[]
    for path in ROOT.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts: continue
        name=path.relative_to(ROOT).as_posix()
        if name.startswith('runtime/') or name.startswith('tests/'):
            selected.append(path)
        elif name in ('README.md','GLOSSARY.md','install_patch.py','run_tests.py','build_delivery.py',
                       'patch_manifest.json','baseline_sha256.json'):
            selected.append(path)
        elif name in ('report/verification.md','report/tests.json','report/tests.txt','report/installer_smoke.json') or name.startswith('report/previews/'):
            selected.append(path)
    update_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in selected}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.source_zip) as original,zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as out:
        prefix=original.namelist()[0].split('/')[0]
        for info in original.infolist():out.writestr(info,original.read(info))
        for path in selected:
            out.write(path,prefix+'/eye_c3_update/'+path.relative_to(ROOT).as_posix())
        out.writestr(prefix+'/eye_c3_update/UPDATE_SHA256.json',json.dumps(update_hashes,indent=2))
        out.writestr(prefix+'/README_EYE_C3.md',
            '# 我们意念合一：眼控设备更新\n\n原工程与历史证据保持原样。本次新增眼控灵巧手和倒立摆，入口为 [安装与操作说明](eye_c3_update/README.md)。\n\n'
            '请使用 eye_c3_update/install_patch.py 在已停止的现有 Z15 运行目录安装；它只应用本次更新，并核对版本、备份和更新启动摘要。'
            'eye_c3_update/runtime 是供检查和测试的源码集合，不应整目录覆盖 SD 卡。134 项本机测试通过，上板和机械验收待进行。\n')
    with zipfile.ZipFile(args.source_zip) as original,zipfile.ZipFile(args.output) as delivered:
        assert delivered.testzip() is None
        for name in original.namelist():
            if original.read(name)!=delivered.read(name):raise ValueError('Original artifact changed: '+name)
        for name,sha in update_hashes.items():
            if hashlib.sha256(delivered.read(prefix+'/eye_c3_update/'+name)).hexdigest()!=sha:
                raise ValueError('Delivery hash mismatch: '+name)
        report=dict(original_entries=len(original.namelist()),original_entries_preserved=True,
                    update_files=len(update_hashes),payload_hashes_verified=True,zip_crc_passed=True,
                    output=str(args.output.resolve()),size_bytes=args.output.stat().st_size,
                    sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())
    (ROOT/'report/delivery_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    args.output.with_suffix('.sha256.txt').write_text(report['sha256']+'  '+args.output.name+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
