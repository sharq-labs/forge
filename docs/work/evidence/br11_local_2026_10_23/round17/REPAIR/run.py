import os, subprocess, json, hashlib, sys
from pathlib import Path
root=Path('/home/dev_kaeem/forge-gen2-authority-v1')
d=Path('/home/dev_kaeem/br11-review/r17/REPAIR')
label=sys.argv[1]
cmd=[str(root/'.venv/bin/python'),'-m','pytest','-q','-p','no:cacheprovider','--basetemp='+str(d/('pt-'+label)),*sys.argv[2:]]
env={**os.environ,'PYTHONPATH':str(root/'src')+':'+str(root),'PYTHONDONTWRITEBYTECODE':'1'}
r=subprocess.run(cmd,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
log=d/(label+'.log');log.write_text(r.stdout)
record={'command':cmd,'cwd':str(root),'environment':{k:env[k] for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE']},'exit_code':r.returncode,'log':str(log),'source_sha256':hashlib.sha256((root/'src/engcore/mind/world/owners.py').read_bytes()).hexdigest(),'test_sha256':hashlib.sha256((root/'tests/mind/test_authority_review_r17.py').read_bytes()).hexdigest()}
(d/(label+'.json')).write_text(json.dumps(record,indent=2)+'\n')
print(r.stdout);print(json.dumps(record))
