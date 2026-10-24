import os, subprocess, json
from pathlib import Path
p=Path(__file__).parent
root='/home/dev_kaeem/forge-r18-review'
python='/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python'
env=dict(os.environ,PYTHONPATH=root+'/src:'+root,PYTHONDONTWRITEBYTECODE='1')
identity=subprocess.run([python,'-c','import engcore.mind.world.owners as o; print(o.__file__)'],cwd=root,env=env,capture_output=True,text=True)
sha=subprocess.check_output(['git','-C',root,'rev-parse','HEAD'],text=True).strip()
assert sha=='cc7ef06b0d08398173d9448ff47d8abb7e375d44'
assert identity.stdout.strip()==root+'/src/engcore/mind/world/owners.py'
(p/'identity.json').write_text(json.dumps({'sha':sha,'import':identity.stdout.strip()}))
cmd=[python,'-m','pytest','-q','-s','-p','no:cacheprovider','--basetemp='+str(p/'pt'),str(p/'test_e.py'),'tests/mind/test_authority_review_r17.py','tests/mind/test_authority_review_r16.py']
r=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True)
(p/'tests.log').write_text(r.stdout+r.stderr)
(p/'execution.json').write_text(json.dumps({'command':cmd,'cwd':root,'environment':{k:env[k] for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE']},'exit_code':r.returncode,'log':str(p/'tests.log')},indent=2))
print(r.stdout+r.stderr)
