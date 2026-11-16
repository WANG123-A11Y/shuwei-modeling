"""Run all practice scripts and retain observable execution records."""
from pathlib import Path
import datetime, hashlib, json, os, subprocess, sys, time, importlib.metadata

HERE=Path(__file__).resolve().parent
def main():
    run_id=datetime.datetime.now(datetime.timezone.utc).strftime('practice-%Y%m%dT%H%M%SZ')
    records=[];rundir=HERE/'runs';rundir.mkdir(exist_ok=True)
    for filename in ['analyze_a.py','analyze_b.py','analyze_c.py','verify_practice.py']:
        start=datetime.datetime.now(datetime.timezone.utc).isoformat();beg=time.perf_counter();p=HERE/filename
        digest=hashlib.sha256(p.read_bytes()).hexdigest();command=[sys.executable,'-X','utf8',str(p)]
        env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env.setdefault('MPLCONFIGDIR',str(HERE/'mplconfig'))
        res=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (rundir/f'{run_id}-{p.stem}.log').write_bytes(res.stdout)
        records.append({'code_artifact':filename,'code_sha256':digest,'command':command,'start_utc':start,'duration_s':time.perf_counter()-beg,
            'returncode':res.returncode,'status':'completed' if res.returncode==0 else 'failed'})
        if res.returncode:raise RuntimeError(f'{filename} failed: {res.stdout.decode("utf-8","replace")[-3000:]}')
    artifacts=[{'path':str(p.relative_to(HERE)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((HERE/'results').glob('*')) if p.is_file()]
    deps={n:importlib.metadata.version(n) for n in ['numpy','scipy','matplotlib','Pillow','openpyxl']}
    report={'run_id':run_id,'scope':'Bounded A/B/C practice, not complete contest solutions','records':records,'dependencies':deps,'artifacts':artifacts}
    (rundir/'latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'run_id':run_id,'records':records,'dependencies':deps,'artifacts_count':len(artifacts)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
