"""Build an MBR/FAT16 image file, never a physical drive.

The RAM root keeps the vendor ARM userspace and needs one FAT partition only.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import stat
import struct
import tarfile
from build_stereo_package import HERE, INIT, overlay_files


def fat16_image(path, files):
    path = Path(path)
    if path.suffix.lower() != '.img':
        raise ValueError('output must be a regular .img file')
    if path.exists() and not path.is_file():
        raise ValueError('refuse non-file output')
    sector, sectors, first, spc, reserved, fats, entries = 512,1048576,2048,32,1,2,512
    total = sectors-first
    fat_sectors=128
    root_sectors=entries*32//sector
    data_start=first+reserved+fats*fat_sectors+root_sectors
    clusters=(sectors-data_start)//spc
    if not 4085 <= clusters < 65525: raise ValueError('FAT16 cluster count')
    mbr=bytearray(sector)
    struct.pack_into('<B3sB3sII',mbr,446,0x80,b'\xfe\xff\xff',0x0e,b'\xfe\xff\xff',first,total)
    mbr[510:]=b'\x55\xaa'
    bpb=bytearray(sector);bpb[:11]=b'\xeb\x3c\x90Z20SD   '
    struct.pack_into('<HBHBHHBHHHII',bpb,11,sector,spc,reserved,fats,entries,0,0xf8,fat_sectors,63,255,first,total)
    struct.pack_into('<BBB I 11s 8s',bpb,36,0x80,0,0x29,0x5a323053,b'Z20STEREO  ',b'FAT16   ')
    bpb[510:]=b'\x55\xaa'
    fat=bytearray(fat_sectors*sector);struct.pack_into('<HH',fat,0,0xfff8,0xffff)
    directory=bytearray(root_sectors*sector)
    next_cluster=2
    manifest={}
    with path.open('wb') as output:
        output.truncate(sectors*sector)
        output.seek(0);output.write(mbr)
        output.seek(first*sector);output.write(bpb)
        for index,(name,source) in enumerate(files.items()):
            parts=name.upper().split('.')
            if (index>=entries or len(parts)>2 or not 1<=len(parts[0])<=8
                    or (len(parts)==2 and len(parts[1])>3)
                    or any(not (c.isascii() and (c.isalnum() or c=='_')) for p in parts for c in p)):
                raise ValueError('only unique DOS 8.3 filenames are supported')
            short=parts[0].ljust(8)+(parts[1] if len(parts)==2 else '').ljust(3)
            length=Path(source).stat().st_size
            needed=max(1,(length+spc*sector-1)//(spc*sector))
            if next_cluster+needed>clusters+2:raise ValueError('files exceed image data partition')
            start=next_cluster
            for cluster in range(start,start+needed):
                struct.pack_into('<H',fat,cluster*2,cluster+1 if cluster<start+needed-1 else 0xffff)
            directory[index*32:index*32+11]=short.encode('ascii')
            directory[index*32+11]=0x20
            struct.pack_into('<H',directory,index*32+24,0x21)
            struct.pack_into('<HI',directory,index*32+26,start,length)
            output.seek((data_start+(start-2)*spc)*sector)
            digest=hashlib.sha256()
            with Path(source).open('rb') as stream:
                while True:
                    data=stream.read(1024*1024)
                    if not data:break
                    output.write(data);digest.update(data)
            manifest[name]=dict(bytes=length,sha256=digest.hexdigest(),first_cluster=start,clusters=needed)
            next_cluster+=needed
        for copy in range(fats):
            output.seek((first+reserved+copy*fat_sectors)*sector);output.write(fat)
        output.seek((first+reserved+fats*fat_sectors)*sector);output.write(directory)
    return manifest


def _record(stream,name,data,mode,ino,devmajor=0,devminor=0):
    name=name.encode()+b'\0'
    fields=[ino,mode,0,0,1,0,len(data),0,0,devmajor,devminor,len(name),0]
    header=b'070701'+b''.join(('%08x'%v).encode() for v in fields)+name
    stream.write(header);stream.write(b'\0'*(-len(header)%4))
    stream.write(data);stream.write(b'\0'*(-len(data)%4))


def ram_root(rootfs,output):
    extra=overlay_files();extra['init']=INIT
    index=1
    with gzip.open(output,'wb',compresslevel=1) as stream,tarfile.open(rootfs) as source:
        for item in source:
            name=item.name.removeprefix('./').rstrip('/')
            if not name or name in extra:continue
            major=minor=0
            if item.isdir():mode=stat.S_IFDIR|item.mode;data=b''
            elif item.issym():mode=stat.S_IFLNK|item.mode;data=item.linkname.encode()
            elif item.isfile() or item.islnk():mode=stat.S_IFREG|item.mode;data=source.extractfile(item).read()
            elif item.ischr() or item.isblk():
                mode=(stat.S_IFCHR if item.ischr() else stat.S_IFBLK)|item.mode
                data=b'';major=item.devmajor;minor=item.devminor
            else:continue
            _record(stream,name,data,mode,index,major,minor);index+=1
        for name in ('opt','opt/z20','opt/z20/z20_compute','usr/local','usr/local/bin'):
            _record(stream,name,b'',stat.S_IFDIR|0o755,index);index+=1
        for name,data in extra.items():
            mode=0o755 if name=='init' or name.startswith('usr/') else 0o644
            _record(stream,name,data,stat.S_IFREG|mode,index);index+=1
        _record(stream,'TRAILER!!!',b'',0,index)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=Path,default=HERE/'build/stereo_release')
    parser.add_argument('--rootfs',type=Path,default=HERE/'build/official_linux/zynq_petalinux/3_linux_lcd_qt/ready_to_test/rootfs.tar.gz')
    parser.add_argument('--output',type=Path,default=HERE/'artifacts/z20-stereo-sd.img')
    args=parser.parse_args()
    ram_root(args.rootfs,args.release/'boot/rootfs.gz')
    print('RAM_ROOT_READY',flush=True)
    files={name.upper():args.release/'boot'/name for name in ('BOOT.BIN','zImage','system.dtb','boot.scr','rootfs.gz')}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result=dict(board_executed=False,kind='stereo-fat16-ramroot',
        rootfs_source_sha256=hashlib.sha256(args.rootfs.read_bytes()).hexdigest(),
        files=fat16_image(args.output,files),image_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())
    (HERE/'report/stereo_sd_image.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(dict(path=str(args.output),sha256=result['image_sha256'])))
