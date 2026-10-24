import os,subprocess,json
from pathlib import Path
p=Path(__file__).parent
root='/home/dev_kaeem/forge-r18-review'
env=dict(os.environ,PYTHONPATH=root+'/src:'+root,PYTHONDONTWRITEBYTECODE='1')
py='/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python'
commands=[('identity',[py,'-c',"import subprocess;from engcore.mind.world import owners;print(owners.__file__);print(subprocess.check_output(['git','rev-parse','HEAD'],text=True));assert owners.__file__.startswith('/home/dev_kaeem/forge-r18-review/');assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()=='cc7ef06b0d08398173d9448ff47d8abb7e375d44'"]),('controls',[py,'-m','pytest','-q','-p','no:cacheprovider','--basetemp='+str(p/'pt'),'tests/mind/test_authority_review_r16.py','tests/mind/test_authority_review_r17.py',str(p/'test_new.py')]),('native',[py,str(p/'probe_native.py')])]
records=[]
for name,args in commands:
 r=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=180)
 (p/(name+'.log')).write_text(r.stdout+r.stderr)
 records.append(dict(command='PYTHONPATH='+env['PYTHONPATH']+' PYTHONDONTWRITEBYTECODE=1 '+__import__('shlex').join(args),cwd=root,exit=r.returncode,log=str(p/(name+'.log'))))
 print(name,r.returncode,r.stdout[-4000:],r.stderr[-1000:])
 if name=='identity':assert r.returncode==0
p.joinpath('executions.json').write_text(json.dumps(records,indent=2))
