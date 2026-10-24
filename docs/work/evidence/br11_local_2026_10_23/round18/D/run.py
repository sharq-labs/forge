import os, subprocess, json
from pathlib import Path
p=Path(__file__).parent
root="/home/dev_kaeem/forge-r18-review"
sha=subprocess.check_output(["git","-C",root,"rev-parse","HEAD"],text=True).strip()
assert sha=="cc7ef06b0d08398173d9448ff47d8abb7e375d44"
env=dict(os.environ,PYTHONPATH=root+"/src:"+root,PYTHONDONTWRITEBYTECODE="1")
py="/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python"
commands=[[py,"-c","import engcore.mind.world.owners as o; print(o.__file__); assert o.__file__ == '/home/dev_kaeem/forge-r18-review/src/engcore/mind/world/owners.py'"], [py,"-m","pytest","-q","-p","no:cacheprovider","--basetemp="+str(p/"pt"),str(p/"test_identity.py"),"tests/mind/test_authority_review_r17.py"], [py,str(p/"native.py")]]
records=[]
for name,cmd in zip(["identity","controls","native"],commands):
 r=subprocess.run(cmd,cwd=root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 log=p/(name+".log"); log.write_text(r.stdout)
 records.append(dict(command=cmd,cwd=root,environment={k:env[k] for k in ["PYTHONPATH","PYTHONDONTWRITEBYTECODE"]},exit=r.returncode,log=str(log)))
 print(name,r.returncode,r.stdout)
p.joinpath("executions.json").write_text(json.dumps(records,indent=2))
