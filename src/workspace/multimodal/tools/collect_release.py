"""Collect controlled source snapshots and verified build products for internal handoff."""
import argparse,hashlib,json,re,shutil,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(file):return hashlib.sha256(file.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--firmware',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);a=p.parse_args()
    for tree in ('esp32/MultiControlS3','esp32c3/PendulumBridgeC3','hand_nano/hand_controller','stm32','tests','tools'):
        source=a.firmware/tree
        for file in source.rglob('*'):
            if not file.is_file() or any(part in ('Objects','Listings','__pycache__','build') for part in file.relative_to(source).parts):continue
            if file.name=='WifiConfig.h' or file.suffix.lower() not in ('.h','.c','.cpp','.ino','.s','.uvprojx','.py','.cmd','.ps1','.json','.md','.txt'):continue
            target=ROOT/'firmware'/file.relative_to(a.firmware);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    # Test harnesses permit explicitly provided compiler/library paths on other PCs.
    for file in (ROOT/'firmware/tests').glob('*.cmd'):
        text=file.read_text(encoding='utf8')
        old='call "D:\\file\\01_softwares\\visual studio\\VC\\Auxiliary\\Build\\vcvars64.bat" >nul'
        text=text.replace(old,'if not defined VCVARS64 set "VCVARS64=D:\\file\\01_softwares\\visual studio\\VC\\Auxiliary\\Build\\vcvars64.bat"\ncall "%VCVARS64%" >nul')
        text=text.replace('set "JSON_INCLUDE=C:\\Users\\conquer\\Documents\\Arduino\\libraries\\ArduinoJson\\src"','if not defined JSON_INCLUDE set "JSON_INCLUDE=%USERPROFILE%\\Documents\\Arduino\\libraries\\ArduinoJson\\src"')
        text=text.replace('/I"C:\\Users\\conquer\\Documents\\Arduino\\libraries\\ArduinoJson\\src"','/I"%JSON_INCLUDE%"')
        if 'JSON_INCLUDE' in text and 'set "JSON_INCLUDE' not in text:text=text.replace('cd /d "%~dp0"','cd /d "%~dp0"\nif not defined JSON_INCLUDE set "JSON_INCLUDE=%USERPROFILE%\\Documents\\Arduino\\libraries\\ArduinoJson\\src"')
        file.write_text(text,encoding='utf8')
    for name,source in [('ArduinoJson',Path.home()/'Documents/Arduino/libraries/ArduinoJson'),('RF24',Path.home()/'Documents/Arduino/libraries/RF24'),('Servo',Path('D:/file/01_softwares/arduino/libraries/Servo'))]:
        if not source.is_dir():raise RuntimeError('required local library missing: '+str(source))
        target=ROOT/'firmware/libraries'/name
        shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','__pycache__'))
    native=a.baseline/'board_snapshot/rootfs/home/xilinx/tobii_z15'
    wanted=('is4-calibration','is4-probe','libtobii_display.so')
    provenance=json.loads((ROOT/'baseline_manifest.json').read_text(encoding='utf8'))
    by_name={x['path']:x['sha256'] for x in provenance['files']}
    for name in wanted:
        file=native/name;key=file.relative_to(a.baseline).as_posix()
        if sha(file)!=by_name[key]:raise RuntimeError('native baseline hash mismatch')
        target=ROOT/'board_runtime/eye'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    shutil.copytree(native/'src',ROOT/'board_runtime/eye/src',dirs_exist_ok=True)
    for name,folder in [('s3','multimodal_s3'),('c3','multimodal_c3'),('nano','multimodal_nano')]:
        target=ROOT/'release/firmware'/name;target.mkdir(parents=True,exist_ok=True)
        for file in (a.firmware/'build'/folder).iterdir():
            if file.suffix in ('.bin','.hex','.elf') or file.name.endswith('.json'):shutil.copy2(file,target/file.name)
        shutil.copy2(a.firmware/'build'/(folder+'_compile.log'),target/'compile.log')
    target=ROOT/'release/firmware/stm32';target.mkdir(parents=True,exist_ok=True)
    for name in ('Project.axf','Project.hex'):shutil.copy2(a.firmware/'stm32/Objects'/name,target/name)
    shutil.copy2(a.firmware/'build/multimodal_stm_compile.log',target/'compile.log')
    shutil.copy2(a.firmware/'tools/pc_client.py',ROOT/'vendor/pc_client.py')
    for name in ('timing','utilization','cdc'):shutil.copy2(ROOT/'build'/(name+'.rpt'),ROOT/'report'/(name+'.rpt'))
    build_log=ROOT/'build/three_mode_vivado.log'
    shutil.copy2(build_log if build_log.exists() else ROOT/'build/final_vivado.log',ROOT/'report/vivado.log')
    pair=[ROOT/'release'/('intent_one.'+x) for x in ('bit','hwh','xsa')]
    if any(not file.is_file() or not file.stat().st_size for file in pair):raise RuntimeError('hardware pair missing')
    timing=(ROOT/'report/timing.rpt').read_text()
    if 'All user specified timing constraints are met.' not in timing:raise RuntimeError('timing failed')
    table=timing.split('| Design Timing Summary')[1].split('| Clock Summary')[0]
    match=re.search(r'^\s*(-?\d+\.\d+)\s+\d+\.\d+\s+\d+\s+\d+\s+(-?\d+\.\d+)',table,re.M)
    if not match:raise RuntimeError('timing slack table missing')
    xml=ET.parse(pair[1]);modules={m.attrib.get('INSTANCE'):m for m in xml.findall('.//MODULE')}
    for name in ('signal_core_0','axi_dma_signal','live_osd_0','axi_gpio_keys','key_inputs_0'):
        if name not in modules:raise RuntimeError('HWH module missing: '+name)
    trees=('intent_one','hardware','vendor','firmware','board_runtime','config','skills','tools','tests')
    files={}
    for tree in trees:
        for file in (ROOT/tree).rglob('*'):
            if not file.is_file() or '__pycache__' in file.parts:continue
            if tree=='firmware' and (any(x in ('build','Objects','Listings') for x in file.relative_to(ROOT/'firmware').parts) or file.suffix.lower() in ('.obj','.exe','.pdb','.ilk')):continue
            files[file.relative_to(ROOT).as_posix()]=sha(file)
    for file in (ROOT/'release').rglob('*'):
        if file.is_file() and file.name!='manifest.json':files[file.relative_to(ROOT).as_posix()]=sha(file)
    manifest={'name':'我们意念合一','build_scope':'offline software, firmware, routed overlay; new physical integration pending',
              'baseline_archive_sha256':provenance['archive_sha256'],'files':files,'signal_clock_mhz':25,'pixel_clock_mhz':75,'wns_ns':float(match[1]),'whs_ns':float(match[2])}
    (ROOT/'release/manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps({'files':len(files),'hardware_pair':'verified','wifi_config_in_source':False}))
if __name__=='__main__':main()
