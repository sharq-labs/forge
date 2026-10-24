import os,subprocess,json
from pathlib import Path
p=Path('/home/dev_kaeem/br11-review/r18/B');root='/home/dev_kaeem/forge-r18-review';py='/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python'
env=dict(os.environ,PYTHONPATH=root+'/src:'+root,PYTHONDONTWRITEBYTECODE='1')
rows=[]
for name,args in [('probe',[str(p/'probe.py')]),('native',[str(p/'native.py')]),('controls',['-m','pytest','tests/mind/test_authority_review_r16.py','tests/mind/test_authority_review_r17.py','-q','-p','no:cacheprovider','--basetemp='+str(p/'pt')])]:
 cmd=[py,*args];r=subprocess.run(cmd,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 (p/(name+'.log')).write_text(r.stdout)
 rows.append(dict(command='cd '+root+' && PYTHONPATH='+env['PYTHONPATH']+' PYTHONDONTWRITEBYTECODE=1 '+' '.join(cmd),exit_code=r.returncode,log=str(p/(name+'.log'))))
 print(name,r.returncode,r.stdout[-1600:])
(p/'executions.json').write_text(json.dumps(rows,indent=2))
