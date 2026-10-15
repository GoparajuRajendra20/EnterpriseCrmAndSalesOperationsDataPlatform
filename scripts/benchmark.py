"""Reproducible scale check; reports elapsed time, without claiming production throughput."""
import argparse,json,os,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--leads',type=int,default=100000);a=p.parse_args()
base=Path(__file__).resolve().parents[1];state=base/'state';state.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    start=time.monotonic()
    subprocess.run([str(base/'.venv/bin/python'),str(base/'generate.py'),'--out',tmp+'/raw','--leads',str(a.leads)],check=True)
    env=dict(os.environ,RAW_DIR=tmp+'/raw',CURATED_DIR=tmp+'/curated');env.pop('JDBC_URL',None)
    subprocess.run([str(base/'.venv/bin/spark-submit'),'--master','local[2]',str(base/'pipeline.py')],env=env,check=True)
    result={'lead_rows':a.leads,'elapsed_seconds':round(time.monotonic()-start,2),'mode':'local[2]','limitation':'Single-host batch measurement, not distributed/production capacity.'}
    (state/'benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
