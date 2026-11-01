"""Stage a private ARM build toolchain and pinned source archives, without installation."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import lzma
import re
from pathlib import Path
import tarfile
import urllib.request

ROOT=Path('artifacts/wifi-build')
MIRROR='https://archive.debian.org/debian/'
PACKAGES=('gcc-8 cpp-8 gcc-8-base libgcc-8-dev libgcc1 libstdc++6 '
          'libisl19 libmpc3 libmpfr6 libgmp10 zlib1g binutils binutils-arm-linux-gnueabihf '
          'binutils-common libbinutils make flex bison m4 libfl2 libtinfo6 '
          'perl perl-base perl-modules-5.28 libperl5.28 libgdbm6 libgdbm-compat4 '
          'libdb5.3 libbz2-1.0 liblzma5 libzstd1 libc6 libc6-dev linux-libc-dev '
          'bc libreadline7 libssl-dev libssl1.1 pkg-config').split()


def fetch(url,path,expected=None):
    if not path.exists():
        temporary=path.with_suffix(path.suffix+'.part')
        with urllib.request.urlopen(url,timeout=45) as response,temporary.open('wb') as out:
            while True:
                data=response.read(1024*1024)
                if not data:break
                out.write(data)
        temporary.replace(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if expected is not None and digest!=expected:raise ValueError('download digest mismatch: '+str(path))
    return dict(url=url,file=path.name,sha256=digest,bytes=path.stat().st_size)


def ar_data(payload):
    if not payload.startswith(b'!<arch>\n'):raise ValueError('not a Debian ar archive')
    offset=8
    while offset+60<=len(payload):
        header=payload[offset:offset+60];name=header[:16].decode().strip().rstrip('/')
        size=int(header[48:58]);offset+=60
        if name.startswith('data.tar'):return payload[offset:offset+size]
        offset+=size+(size%2)
    raise ValueError('Debian data archive missing')


def append_data_tar(output,payload):
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:*') as archive:
        for item in archive:
            clean=item.name.removeprefix('./')
            if not clean or '..' in Path(clean).parts or clean.startswith('/'):continue
            item.name='native/'+clean
            if item.islnk():item.linkname='native/'+item.linkname.removeprefix('./')
            output.addfile(item,archive.extractfile(item) if item.isfile() else None)


def library_dependencies(records,seeds):
    selected=set(seeds)
    pending=list(seeds)
    while pending:
        record=records[pending.pop()]
        text=record.get('Depends','')+','+record.get('Pre-Depends','')
        for field in text.split(','):
            options=[re.split(r'[\s:(]',part.strip())[0] for part in field.split('|') if part.strip()]
            candidates=[name for name in options if name in records]
            if not candidates:continue
            name=candidates[0]
            if name.startswith('lib') and name not in selected:
                selected.add(name);pending.append(name)
    return sorted(selected)


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    index=ROOT/'Packages-armhf.xz'
    sources=[fetch(MIRROR+'dists/buster/main/binary-armhf/Packages.xz',index)]
    records={}
    for paragraph in lzma.decompress(index.read_bytes()).decode().split('\n\n'):
        fields={}
        for line in paragraph.splitlines():
            if line and not line[0].isspace() and ': ' in line:
                key,value=line.split(': ',1);fields[key]=value
        if fields.get('Package') and 'Filename' in fields:
            records[fields['Package']]=fields
    missing=set(PACKAGES)-set(records)
    if missing:raise ValueError('missing native build packages: '+str(sorted(missing)))
    packages=library_dependencies(records,PACKAGES)
    def package(name):
        record=records[name]
        filename=record['Filename']
        if not filename.startswith('pool/') or '..' in filename:raise ValueError('bad package path')
        item=fetch(MIRROR+filename,ROOT/Path(filename).name,record['SHA256'])
        item.update(package=name,version=record['Version']);return item
    with ThreadPoolExecutor(max_workers=4) as pool:sources+=list(pool.map(package,packages))
    bundle=ROOT/'native-build-tools.tar.gz'
    with tarfile.open(bundle,'w:gz') as output:
        for name in packages:
            payload=(ROOT/Path(records[name]['Filename']).name).read_bytes()
            append_data_tar(output,ar_data(payload))
    sources.append(fetch('https://codeload.github.com/Xilinx/linux-xlnx/tar.gz/refs/tags/xilinx-v2020.2',
                         ROOT/'linux-xilinx-v2020.2.tar.gz'))
    repo='wirenboard/rtl8733bu'
    with urllib.request.urlopen('https://api.github.com/repos/'+repo+'/commits/v5.13.0.1-112',timeout=30) as response:
        commit=json.load(response)['sha']
    sources.append(fetch('https://codeload.github.com/'+repo+'/tar.gz/'+commit,ROOT/'rtl8733bu.tar.gz'))
    sources[-1]['commit']=commit
    (ROOT/'sources.json').write_text(json.dumps(dict(scope='staged only; no module built or loaded',
        native_tools_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),sources=sources),indent=2),encoding='utf-8')
    print(json.dumps(dict(packages=len(packages),tool_archive_bytes=bundle.stat().st_size,driver_commit=commit)),flush=True)


if __name__=='__main__':main()
