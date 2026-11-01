"""Same block, initialization and integer arithmetic on PS and the loaded PL."""
import math,time
from .reference import fixed_iir,WindowStatistics
def compare(runner,samples):
    if not samples or len(samples)%50:raise ValueError('complete 50-sample windows required')
    runner.configure(coefficient=16384,channels=1,window=50)
    cpu=time.process_time();start=time.perf_counter()
    expected,_=fixed_iir(samples);stats=WindowStatistics(50).process(expected)
    ps=time.perf_counter()-start;ps_cpu=time.process_time()-cpu
    actual=[];actual_stats=[];cpu=time.process_time();start=time.perf_counter()
    for pos in range(0,len(samples),50):
        actual.extend(runner.process(samples[pos:pos+50]));actual_stats.append(runner.stats())
    pl=time.perf_counter()-start;pl_cpu=time.process_time()-cpu
    error=max(abs(a-b) for a,b in zip(expected,actual))
    rms_error=max(abs(a['rms']-math.sqrt(max(0,b['squares']/50.-(b['sum']/50.)**2))) for a,b in zip(stats,actual_stats))
    if error or rms_error>1e-6 or any(b['saturations'] for b in actual_stats):raise RuntimeError('PS/PL arithmetic parity failed')
    return {'origin':'live_board','samples':len(samples),'PS_ms':round(ps*1000,3),'PS_PL_ms':round(pl*1000,3),
            'PS_CPU_ms':round(ps_cpu*1000,3),'PS_PL_CPU_ms':round(pl_cpu*1000,3),'max_integer_error':error,'max_rms_error':rms_error}
