import os,subprocess,json
from pathlib import Path
p=Path('/home/dev_kaeem/br11-review/r17/C'); root='/home/dev_kaeem/forge-r17-review'
env=dict(os.environ,PYTHONPATH=root+'/src:'+root,PYTHONDONTWRITEBYTECODE='1')
py='/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python'
commands=[([py,'-c',"import subprocess;from engcore.mind.world import owners;print(owners.__file__);print(subprocess.check_output(['git','rev-parse','HEAD'],text=True));assert owners.__file__=='/home/dev_kaeem/forge-r17-review/src/engcore/mind/world/owners.py';assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()=='98d72b2ef854012780f4222706884b911c4a2f03'"],'identity.log'),([py,'-m','pytest','-q','-p','no:cacheprovider','--basetemp='+str(p/'pt'),'tests/mind/test_authority_review_r16.py',str(p/'test_lifecycle.py')],'controls.log'),([py,str(p/'probe_native_depth.py')],'native.log')]
rows=[]
for args,log in commands:
    r=subprocess.run(args,cwd=root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (p/log).write_text(r.stdout); rows.append(dict(command=args,cwd=root,env={k:env[k] for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE']},exit=r.returncode,log=str(p/log)));print(log,r.returncode,r.stdout,flush=True)
    if log=='identity.log' and r.returncode:break
(p/'executions.json').write_text(json.dumps(rows,indent=2))
