"""Narrow report-path update, using the existing calibration-preserving installer."""
import argparse
import json
from pathlib import Path
import re
import stat

import deploy_input_repair as repair

OUT=repair.ROOT/'phone_video_upload/output/hdmi_report_repair_20261012'
STAGE=OUT/'stage.json'
INSTALL=OUT/'installation-stage.json'
repair.OUT=OUT
repair.live.STATE=repair.ROOT/'phone_video_upload/output/hdmi_live_user_controlled_20261008/state.json'


def tests(client):
    stage=json.loads(STAGE.read_text())
    unit=stage['unit']+'.service'
    status=repair.execute(client,['systemctl','show',unit,'-p','ActiveState','-p','Result','-p','ExecMainStatus'])
    log=repair.execute(client,['journalctl','-u',unit,'--no-pager','-n','30','-o','cat'])
    passed=('ActiveState=inactive' in status and 'Result=success' in status
            and 'ExecMainStatus=0' in status and '\nOK' in log)
    repair.save('linux-tests.json',dict(status=status,output=log,passed=passed))
    print(status);print(log)
    return passed


def plan(client):
    if INSTALL.exists():raise ValueError('Do not overwrite a retained repair plan')
    if not tests(client):raise ValueError('Board regression has not passed')
    tested=json.loads(STAGE.read_text())
    pairs=[('pynq_guardianloop/ssvep_hdmi.py','runtime/ssvep_hdmi.py')]
    pairs += [('phone_video_upload/'+n,'runtime/'+n) for n in
              ('media_player.py','system_hdmi.py','system_mobile.js','hdmi_stimulus.py')]
    pairs += [('guardianloop_system/core.py','runtime/system_runtime/guardianloop_system/core.py')]
    for local,relative in pairs:
        if repair.digest((repair.ROOT/local).read_bytes())!=tested['hashes'][relative]:
            raise ValueError('Source changed after private tests: '+local)
    remote=repair.live.board.execute(client,'mktemp -d /home/xilinx/gl-calibration-install-hdmi-report-XXXXXX').strip()
    raw=repair.read(client,repair.FORMAL+'/release_manifest.json');manifest=json.loads(raw)
    current=json.loads(repair.read(client,repair.BASE+'/state.json'))
    if current['formal_hashes']!=manifest['files']:raise ValueError('Formal release changed')
    boot=repair.execute(client,['cat','/proc/sys/kernel/random/boot_id']).strip()
    if current['boot']!=boot:raise ValueError('Board boot changed')
    player=json.loads(repair.read(client,repair.BASE+'/player_status.json'))
    ident=player['session_id']
    if not re.fullmatch('play-[a-f0-9]{8}',ident):raise ValueError('Unknown display owner')
    plan=dict(live=repair.BASE,boot=boot,tests_passed=True,hdmi_report_update=True,
        previous_manifest_sha=repair.digest(raw),display_unit=ident+'.service',files=[],
        web_services=[Path(repair.BASE).name+'-server.service'])
    payload=OUT/'payload';payload.mkdir(exist_ok=True)
    with client.open_sftp() as ftp:
        def add(target,data,mode=None):
            info=ftp.lstat(target)
            if not stat.S_ISREG(info.st_mode):raise ValueError('Nonregular target: '+target)
            old=repair.read(client,target)
            key='%02d-%s'%(len(plan['files']),Path(target).name)
            (OUT/('before-'+key)).write_bytes(old)
            (payload/key).write_bytes(data)
            plan['files'].append(dict(target=target,key=key,old_sha=repair.digest(old),
                new_sha=repair.digest(data),old_mode=stat.S_IMODE(info.st_mode),
                new_mode=stat.S_IMODE(info.st_mode) if mode is None else mode))
        hdmi=(repair.ROOT/'pynq_guardianloop/ssvep_hdmi.py').read_bytes()
        add(repair.FORMAL+'/ssvep_hdmi.py',hdmi)
        add(repair.CANDIDATE+'/ssvep_hdmi.py',hdmi)
        manifest['files']['ssvep_hdmi.py']=repair.digest(hdmi)
        manifest['previous_release_id']=manifest['release_id']
        manifest['release_id']='guardianloop-hdmi-report-repair-20261012'
        encoded=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
        add(repair.FORMAL+'/release_manifest.json',encoded)
        guard=repair.read(client,repair.EYE).decode()
        guard,count=re.subn(r"PRIMARY_MANIFEST = '[a-f0-9]{64}'",
                            "PRIMARY_MANIFEST = '"+repair.digest(encoded)+"'",guard)
        if count!=1:raise ValueError('Unexpected coexistence guard')
        add(repair.EYE,guard.encode())
        startup=json.loads(repair.read(client,'/run/guardianloop-startup/status.json'))
        if startup['state']!='ready' or startup['boot_id']!=boot:raise ValueError('Startup changed')
        startup.update(release_id=manifest['release_id'],verified_files=len(manifest['files']))
        add('/run/guardianloop-startup/status.json',json.dumps(startup,indent=2).encode(),0o644)
        current['formal_hashes']=manifest['files']
        current['module_hashes']['ssvep_hdmi']=repair.digest(hdmi)
        add(repair.BASE+'/state.json',json.dumps(current,indent=2).encode())
        media=json.loads(repair.read(client,repair.BASE+'/media_state.json'))
        media['direction_idle_enabled']=False
        add(repair.BASE+'/media_state.json',json.dumps(media,indent=2).encode())
        for name in ('media_player.py','system_hdmi.py','system_mobile.js','hdmi_stimulus.py'):
            add(repair.BASE+'/'+name,(repair.ROOT/'phone_video_upload'/name).read_bytes())
        add(repair.BASE+'/system_runtime/guardianloop_system/core.py',
            (repair.ROOT/'guardianloop_system/core.py').read_bytes())
        add(repair.BASE+'/menu-shells-portrait-live.npz',
            repair.read(client,tested['remote']+'/runtime/menu-shells-portrait-live.npz'))
        pins=json.loads(repair.read(client,repair.BASE+'/boot-pins.json'))
        pins['manifest_sha256']=repair.digest(encoded)
        for row in plan['files']:
            if row['target'] not in (repair.BASE+'/state.json',repair.BASE+'/media_state.json',
                                     '/run/guardianloop-startup/status.json'):
                pins['files'][row['target']]=row['new_sha']
        add(repair.BASE+'/boot-pins.json',json.dumps(pins,indent=2).encode())
        ftp.mkdir(remote+'/payload',mode=0o700)
        for row in plan['files']:ftp.put(str(payload/row['key']),remote+'/payload/'+row['key'])
        repair.save('deployment-plan.json',plan)
        ftp.put(str(OUT/'deployment-plan.json'),remote+'/deployment-plan.json')
        ftp.chmod(remote+'/deployment-plan.json',0o600)
        ftp.put(str(repair.ROOT/'pynq_guardianloop/install_calibration_repair.py'),remote+'/install_calibration_repair.py')
    repair.save('installation-stage.json',dict(remote=remote,display_unit=plan['display_unit']))
    print('CHECKSUMMED_REPORT_REPAIR_PLAN_READY',len(plan['files']))


def operate(client,action):
    repair.STATE=INSTALL
    repair.run(client,action)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('tests','plan','install','commit','rollback'))
    args=parser.parse_args();client=repair.live.board.upload.trial.connect('192.168.2.99')
    try:
        if args.action in ('tests','plan'):globals()[args.action](client)
        else:operate(client,args.action)
    finally:client.close()
