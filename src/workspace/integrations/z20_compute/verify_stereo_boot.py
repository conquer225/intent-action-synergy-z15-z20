"""Independently audit generated Zynq headers, ELF memory and PL payload."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def _loads(path):
    data=Path(path).read_bytes()
    if data[:6]!=b'\x7fELF\x01\x01' or struct.unpack_from('<H',data,18)[0]!=40:
        raise ValueError('not ARM little-endian ELF32')
    offset=struct.unpack_from('<I',data,28)[0]
    size,count=struct.unpack_from('<HH',data,42)
    loads=[]
    for index in range(count):
        p=struct.unpack_from('<8I',data,offset+index*size)
        if p[0]==1:loads.append((p[3],p[3]+p[5]))
    return loads


def _bit_payload(path):
    data=Path(path).read_bytes()
    offset=2+int.from_bytes(data[:2],'big')+2
    while offset<len(data):
        tag=data[offset:offset+1];offset+=1
        width=4 if tag==b'e' else 2
        length=int.from_bytes(data[offset:offset+width],'big');offset+=width
        if tag==b'e':
            if length%4 or offset+length!=len(data):raise ValueError('invalid .bit payload length')
            return data[offset:]
        offset+=length
    raise ValueError('missing .bit payload')


def audit(directory,uboot):
    directory=Path(directory)
    raw=(directory/'BOOT.BIN').read_bytes()
    if struct.unpack_from('<II',raw,0x20)!=(0xaa995566,0x584c4e58):raise ValueError('boot magic')
    if sum(struct.unpack_from('<11I',raw,0x20))&0xffffffff!=0xffffffff:raise ValueError('boot header checksum')
    iht,pht=struct.unpack_from('<II',raw,0x98)
    version,count,first=struct.unpack_from('<III',raw,iht)
    if count!=4 or first*4!=pht:raise ValueError('expected FSBL, PL, video initializer, U-Boot')
    partitions=[]
    for index in range(count):
        words=struct.unpack_from('<16I',raw,pht+index*64)
        if sum(words)&0xffffffff!=0xffffffff:raise ValueError('partition header checksum')
        offset,length=words[5]*4,words[2]*4
        if offset+length>len(raw):raise ValueError('partition payload outside BOOT')
        partitions.append(dict(load=words[3],entry=words[4],offset=offset,size=length,attribute=words[6]))
    if [p['entry'] for p in partitions]!=[0,0,0x00100000,0x04000000]:raise ValueError('handoff entries differ')
    bit=_bit_payload(directory/'system.bit')
    swapped=b''.join(bit[i:i+4][::-1] for i in range(0,len(bit),4))
    pl=partitions[1]
    if pl['attribute']&0x30!=0x20 or raw[pl['offset']:pl['offset']+len(bit)]!=swapped:
        raise ValueError('PCAP partition differs from paired .bit payload')
    ranges=[]
    for name,path in [('fsbl',directory/'fsbl.elf'),('video',directory/'dual_video.elf'),('uboot',uboot)]:
        for start,end in _loads(path):
            high_ocm = name=='fsbl' and 0xffff0000<=start<end<=0xfffffe00
            if (end>0x40000000 and not high_ocm) or start<0 or end<=start:
                raise ValueError('ELF memory outside low DDR or vendor FSBL OCM region')
            if start<0x017e9000 and end>0x01000000:raise ValueError('ELF overlaps video ring')
            if any(start<e and end>s for _,s,e in ranges):raise ValueError('PS ELF memory overlaps')
            ranges.append((name,start,end))
    return dict(board_executed=False,boot_header_checksum=True,partition_header_checksums=True,
        partition_count=count,pl_payload_matches_bit=True,ps_memory_disjoint=True,
        boot_sha256=hashlib.sha256(raw).hexdigest(),partitions=partitions,elf_memory=ranges,
        note='PL attribute selects PCAP; nominal PL address0 is excluded from PS memory overlap checks. Bootgen warnings remain in commands.json.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot',type=Path,default=Path('build/stereo_linux_boot'))
    parser.add_argument('--uboot',type=Path,default=Path('build/official_linux/zynq_petalinux/1_customize_linux/software/linux_boot/u-boot.elf'))
    parser.add_argument('--output',type=Path,default=Path('report/stereo_linux_boot_verification.json'))
    args=parser.parse_args();result=audit(args.boot,args.uboot)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
