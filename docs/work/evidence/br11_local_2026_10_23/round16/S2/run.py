import os,subprocess,json
from pathlib import Path
p=Path('/home/dev_kaeem/br11-review/r16/S2')
env=dict(os.environ,PYTHONPATH='/home/dev_kaeem/forge-r16-review/src:/home/dev_kaeem/forge-r16-review',PYTHONDONTWRITEBYTECODE='1')
cmd=['/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python',str(p/'probe.py')]
r=subprocess.run(cmd,cwd='/home/dev_kaeem/forge-r16-review',env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(p/'probe.log').write_text(r.stdout);print(r.stdout);print('EXIT',r.returncode)
