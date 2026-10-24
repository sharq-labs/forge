import os,subprocess,pathlib,json
p=pathlib.Path('/home/dev_kaeem/br11-review/r17/B');src='/home/dev_kaeem/forge-r17-review';py='/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python'
env=dict(os.environ,PYTHONPATH=src+'/src:'+src,PYTHONDONTWRITEBYTECODE='1');cmd=[py,str(p/'probe_dispatch_histories.py')]
r=subprocess.run(cmd,env=env,cwd=src,capture_output=True,text=True);log=p/'probe_dispatch_histories.log';log.write_text(r.stdout+r.stderr)
e=json.loads((p/'executions.json').read_text());e.append(dict(command=cmd,cwd=src,env_overrides={k:env[k] for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE']},exit_code=r.returncode,log=str(log)));(p/'executions.json').write_text(json.dumps(e,indent=2));print(r.returncode,r.stdout,r.stderr)
