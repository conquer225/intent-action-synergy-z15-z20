"""Preview transport has no socket and never touches a board."""
class SimulatedPeer:
    def __init__(self,source):
        self.source=source;self.connected=False;self.commands=[]
        self.latest_status={'hand':{'enabled':False,'angles':[0]*5},'pendulum':{'enabled':False,'state':0}}
    def connect(self):self.connected=True
    def send(self,device,action,**fields):
        self.commands.append((device,action,fields))
        if action=='estop':
            for row in self.latest_status.values():row['enabled']=False
        elif action=='enable':self.latest_status[device]['enabled']=True
        elif action in ('open','close'):self.latest_status['hand']['angles']=[90 if action=='close' else 0]*5
        elif action=='start':self.latest_status['pendulum']['state']=14
        return dict(ok=True,status=self.latest_status)
    def close(self):self.connected=False

class SimulatedAudio:
    """Preview acknowledges a media choice without opening a sound device."""
    status='idle';error=''
    def start(self,path):self.status='playing';return True
    def poll(self):return None
    def stop(self):self.status='idle'
    close=stop
