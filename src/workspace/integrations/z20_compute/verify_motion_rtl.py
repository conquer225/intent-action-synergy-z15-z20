"""Offline motion RTL red/green checks with Icarus; no bitstream or board I/O."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
VISION=ROOT.parent/'vision_demo'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'build/feedback-motion-rtl')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    compiler=args.compiler.resolve();runner=compiler.with_name('vvp.exe' if sys.platform=='win32' else 'vvp')
    if not compiler.is_file() or not runner.is_file():raise FileNotFoundError('Icarus compiler and vvp must exist')
    pixel=VISION/'hardware/vision_stream_pixels.sv';text=pixel.read_text()
    old=text.replace("8'd220,1'b1)","8'd220,1'b0)")
    if old==text:raise ValueError('motion dark-background anchor missing')
    red=out/'old-motion.sv';red.write_text(old)
    sys.path.insert(0,str(VISION));from run_stream_sim import vectors
    vectors(out);checks={};sources={}
    for name,source,top in (('red_history',red,'tb_stream_history'),('pixels',pixel,'tb_stream_pixels'),
                            ('vectors',pixel,'tb_stream_vectors'),('history',pixel,'tb_stream_history')):
        paths=[VISION/'hardware/vision_stream_histogram.sv',source,VISION/('hardware/'+top+'.sv')]
        for path in paths:sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        target=out/(name+'.vvp')
        compiled=subprocess.run([str(compiler),'-g2012','-s',top,'-o',str(target),*[str(p) for p in paths]],
                                cwd=out,capture_output=True,text=True,timeout=60)
        if compiled.returncode:raise RuntimeError(compiled.stdout+compiled.stderr)
        executed=subprocess.run([str(runner),str(target)],cwd=out,capture_output=True,text=True,timeout=60)
        log=executed.stdout+executed.stderr;(out/(name+'.txt')).write_text(log)
        checks[name]=dict(exit_code=executed.returncode,output=log)
    passed=(checks['red_history']['exit_code']!=0 and 'expected 1f1f1f' in checks['red_history']['output']
            and all(checks[n]['exit_code']==0 and 'STREAM_' in checks[n]['output'] for n in ('pixels','vectors','history')))
    report=dict(passed=passed,checks=checks,source_sha256=sources,physical_board=False,bitstream_built=False)
    (out/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
