import os, subprocess, json
from pathlib import Path
root=Path('/home/dev_kaeem/forge-r17-review'); out=Path('/home/dev_kaeem/br11-review/r17/D')
env=dict(os.environ,PYTHONPATH=str(root/'src')+':'+str(root),PYTHONDONTWRITEBYTECODE='1')
py='/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python'
sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
assert sha=='98d72b2ef854012780f4222706884b911c4a2f03'
identity=subprocess.run([py,'-c',"from engcore.mind.world import owners; print(owners.__file__); assert owners.__file__.startswith('/home/dev_kaeem/forge-r17-review/')"],cwd=root,env=env,capture_output=True,text=True)
(out/'identity.log').write_text(sha+'\n'+identity.stdout+identity.stderr); assert identity.returncode==0
runs=[]
for name,files in [('identity',['tests/mind/test_authority_review_r16.py',str(out/'test_identity.py')]),('open',[str(out/'test_open.py')])]:
 cmd=[py,'-m','pytest','-q','-p','no:cacheprovider','--basetemp='+str(out/'pt'),*files]
 r=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True,timeout=90)
 (out/(name+'.log')).write_text(r.stdout+r.stderr)
 runs.append(dict(command='PYTHONPATH='+env['PYTHONPATH']+' PYTHONDONTWRITEBYTECODE=1 '+' '.join(cmd),cwd=str(root),exit=r.returncode,log=str(out/(name+'.log'))))
 print(name,r.returncode,r.stdout[-3500:])
(out/'executions.json').write_text(json.dumps(runs,indent=2))
