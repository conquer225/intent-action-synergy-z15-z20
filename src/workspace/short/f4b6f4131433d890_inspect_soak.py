"""Read-only progress snapshot of the isolated board soak."""
from eeg_apps_z15.run_soak_stage import OUT, connect, command, json


def main():
    m=json.loads((OUT/'manifest.json').read_text())
    c=connect()
    try:
        print(command(c,"ps -eo pid,ppid,stat,etime,pcpu,rss,args | grep '[s]oak_service'"))
        for name in ('monitor.jsonl','offline-replay.log','report.json'):
            print(name)
            print(command(c,'if test -f '+m['stage']+'/soak/'+name+'; then tail -c 1800 '+m['stage']+'/soak/'+name+'; fi'))
        print(command(c,'tail -c 1800 '+m['stage']+'/launcher.log'))
    finally:c.close()


if __name__=='__main__':main()
