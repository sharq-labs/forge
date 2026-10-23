import os,subprocess,pathlib
p=pathlib.Path('/home/dev_kaeem/br11-review/r17/S1');os.chdir('/home/dev_kaeem/forge-r17-review')
env=dict(os.environ,PYTHONPATH='/home/dev_kaeem/forge-r17-review/src:/home/dev_kaeem/forge-r17-review',PYTHONDONTWRITEBYTECODE='1')
cmd=['/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python',str(p/'probe.py')]
r=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(p/'probe.log').write_text(r.stdout); print(r.stdout);print('exit',r.returncode)
