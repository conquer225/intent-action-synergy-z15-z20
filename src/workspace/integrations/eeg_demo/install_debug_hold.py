"""Verified maintenance update for an installed EEG/eye demo; never enables a device."""
import argparse
import json
from pathlib import Path

from install_demo import digest, prepare, apply_transaction

BASE=Path(__file__).resolve().parent


def plan_update(roots,debug_hold):
    if type(debug_hold) is not bool:raise ValueError('debug_hold must be boolean')
    manifest=json.loads((BASE/'debug_hold_manifest.json').read_text(encoding='utf-8'))
    payload={};expected={}
    for row in manifest['files']:
        key=(row['group'],row['name']);source=BASE/row['source']
        if digest(source)!=row['after']:raise ValueError('Reviewed payload changed: '+row['source'])
        payload[key]=source.read_bytes();expected[key]=[row['before'],row['after']]
    config=roots['media']/'eye_devices.json'
    row=json.loads(config.read_text(encoding='utf-8'))
    if (not isinstance(row,dict) or not {'version','s3_host','s3_port'}<=set(row)
            or set(row)-{'version','s3_host','s3_port','debug_hold'}
            or row['version']!=1 or row['s3_port']!=9000
            or type(row.get('debug_hold',False)) is not bool):
        raise ValueError('Unrecognized existing eye-device configuration')
    row['debug_hold']=debug_hold
    key=('media','eye_devices.json');expected[key]=digest(config)
    payload[key]=(json.dumps(row,indent=2)+'\n').encode()
    return prepare(roots,payload,expected)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('media','brain','eye'):parser.add_argument('--'+name+'-root',type=Path,required=True)
    parser.add_argument('--mode',choices=('debug','normal'),required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    roots={name:getattr(args,name+'_root').resolve() for name in ('media','brain','eye')}
    plan=plan_update(roots,args.mode=='debug')
    print(json.dumps(dict(mode=args.mode,preview=not args.apply,files=[group+'/'+name for group,name in plan]),indent=2))
    if args.apply:print('INSTALLED_BACKUP='+str(apply_transaction(roots,plan)))


if __name__=='__main__':main()
