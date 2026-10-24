import os, subprocess, json
from pathlib import Path
p=Path('/home/dev_kaeem/br11-review/r18/S1')
env=dict(os.environ,PYTHONPATH='/home/dev_kaeem/forge-r18-review/src:/home/dev_kaeem/forge-r18-review',PYTHONDONTWRITEBYTECODE='1')
py='/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python'
commands=[('matched.log',[py,str(p/'matched.py')]),('controls.log',[py,'-m','pytest','-q','-p','no:cacheprovider','--basetemp='+str(p/'pt'),'tests/mind/test_authority_review_r16.py','tests/mind/test_authority_review_r17.py'])]
records=[]
for name,cmd in commands:
    r=subprocess.run(cmd,cwd='/home/dev_kaeem/forge-r18-review',env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (p/name).write_text(r.stdout)
    records.append(dict(command=cmd,cwd='/home/dev_kaeem/forge-r18-review',environment={k:env[k] for k in ('PYTHONPATH','PYTHONDONTWRITEBYTECODE')},exit=r.returncode,log=str(p/name)))
    print(name,r.returncode,r.stdout[-2200:])
(p/'executions.json').write_text(json.dumps(records,indent=2))
