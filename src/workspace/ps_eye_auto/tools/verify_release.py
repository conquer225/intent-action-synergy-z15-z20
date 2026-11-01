"""Check deployed payloads, generated tables, and isolated old-release hashes."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def word(data, offset): return struct.unpack_from('<I',data,offset)[0]
def elf(path):
    data=path.read_bytes()
    assert data[:6]==b'\x7fELF\x01\x01'
    start, size, count=word(data,28),struct.unpack_from('<H',data,42)[0],struct.unpack_from('<H',data,44)[0]
    segments=[]
    for i in range(count):
        typ,off,vaddr,paddr,filesz,memsz,flags,align=struct.unpack_from('<8I',data,start+i*size)
        if typ==1:
            segments.append(dict(address=paddr,filesz=filesz,memsz=memsz,data=data[off:off+filesz]))
    return word(data,24),segments

def main():
    boot=(ROOT/'build/BOOT.BIN').read_bytes()
    assert word(boot,0x20)==0xaa995566 and word(boot,0x24)==0x584c4e58
    pht=word(boot,0x9c)
    parts=[]
    for i in range(3):
        header=pht+i*64
        parts.append(dict(load=word(boot,header+12),entry=word(boot,header+16),
                          attr=word(boot,header+24),offset=word(boot,header+20)*4,
                          length=word(boot,header+4)*4))
    assert [p['attr']&0x30 for p in parts]==[0x10,0x20,0x10]
    memory=[]
    for index,path in ((0,ROOT/'hardware/fsbl.elf'),(2,ROOT/'build/ps_eye_auto.elf')):
        entry,segments=elf(path)
        assert entry==parts[index]['entry']
        for s in segments:
            off=parts[index]['offset']+s['address']-parts[index]['load']
            assert boot[off:off+s['filesz']]==s['data'],path.name
            if index==2:
                assert s['address']>=0x100000 and s['address']+s['memsz']<=0x1000000
                memory.append(dict(start=hex(s['address']),end_exclusive=hex(s['address']+s['memsz'])))
    assert parts[2]['entry']==0x100000
    with zipfile.ZipFile(ROOT/'hardware/ps_eye_auto.xsa') as z:
        names=[n for n in z.namelist() if n.endswith('.bit')]
        assert len(names)==1 and z.read(names[0])==(ROOT/'hardware/ps_eye_auto.bit').read_bytes()
        init=[n for n in z.namelist() if n.endswith('/ps7_init.tcl') or n=='ps7_init.tcl']
        assert len(init)==1 and z.read(init[0])==(ROOT/'hardware/ps7_init.tcl').read_bytes()
    # Bootgen stores bit payload in little endian words, after the .bit header.
    bit=(ROOT/'hardware/ps_eye_auto.bit').read_bytes()
    sync=bit.index(bytes.fromhex('aa995566'))
    payload=boot[parts[1]['offset']:parts[1]['offset']+parts[1]['length']]
    swapped=b''.join(payload[i:i+4][::-1] for i in range(0,len(payload),4))
    assert bit[sync:] in swapped
    old={'BOOT.BIN':'401bbab24e5aedd3a456b396444accbd94dfa9310d4fd3ce81795ba8c509bb0d',
         'ps_eye_app.elf':'90e2334f79f9350622e94c94d93af80a29dc11d8900b9f572da9f81544aff90b',
         'ps_eye.bit':'7a39723735ab79fd3b2eb0f4cbd10b30cae295e6fcb765f5d7e1045d8f86d3de',
         'ps_eye.xsa':'cc12f5cf062a9f91307b3723fa6faa732983fdcbd1b71e7b3b8ecf3a6aac531e'}
    old_dir=ROOT.parent/'ps_eye/build'
    old_check='not present in standalone release'
    if old_dir.exists():
        for name,digest in old.items(): assert sha(old_dir/name).lower()==digest, 'Previous release changed: '+name
        old_check='all four hashes unchanged'
    # Static generated tables must identify exactly the XML files delivered.
    for model,inc in [('frontalface_default','face_model'),('frontalface_alt','face_alt_model'),('eye','eye_model')]:
        digest=sha(ROOT/'model'/('haarcascade_'+model+'.xml'))
        assert digest in (ROOT/'src/app'/(inc+'.inc')).read_text()
    files=['build/BOOT.BIN','build/ps_eye_auto.elf','hardware/ps_eye_auto.bit','hardware/ps_eye_auto.xsa','hardware/fsbl.elf','hardware/ps7_init.tcl','bsp/lib/libxil.a']
    report=dict(payloads='ELF bytes match BOOT; XSA bit and PS init match release; bit payload matches BOOT',
                app_memory=memory,boot_partitions=parts,previous_release=old_check,previous_sha256=old,
                sha256={f:sha(ROOT/f) for f in files},xsa_bit_embedded=bool(names))
    (ROOT/'report/payload_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(report['payloads']);print(old_check);print('PASS release payload and memory checks')

if __name__=='__main__':main()
