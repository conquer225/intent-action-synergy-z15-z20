"""Reference calculations use original ADC units; never infer grip force."""
import math

class WindowStatistics:
    def __init__(self,size=50):
        if type(size) is not int or size<1: raise ValueError('positive integer window required')
        self.size=size; self.reset()
    def reset(self): self.count=0; self.mean=0.; self.m2=0.
    def process(self,samples):
        result=[]
        for value in samples:
            if type(value) not in (int,float) or not math.isfinite(value): self.reset(); raise ValueError('nonfinite input')
            self.count+=1; delta=value-self.mean; self.mean+=delta/self.count; self.m2+=delta*(value-self.mean)
            if self.count==self.size:
                variance=max(0.,self.m2/self.count)
                result.append(dict(count=self.count,mean=self.mean,variance=variance,rms=math.sqrt(variance)))
                self.reset()
        return result

def fixed_iir(samples,coefficient=16384,state=0):
    """Q16 one-pole reference. Independent arbitrary-precision integer oracle."""
    output=[]
    for value in samples:
        state=state+((coefficient*(int(value)-state))>>16)
        state=max(-(2**31),min(2**31-1,state)); output.append(state)
    return output,state
