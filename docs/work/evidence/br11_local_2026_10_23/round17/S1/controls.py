import os,subprocess,pathlib
from engcore.mind.world import owners
p=pathlib.Path('/home/dev_kaeem/br11-review/r17/S1');os.chdir('/home/dev_kaeem/forge-r17-review')
assert owners.__file__=='/home/dev_kaeem/forge-r17-review/src/engcore/mind/world/owners.py'
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()=='98d72b2ef854012780f4222706884b911c4a2f03'
cmd=['/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python','-m','pytest','tests/mind/test_authority_review_r16.py','-q','-p','no:cacheprovider','--basetemp='+str(p/'pt'),'-n','1']
r=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(p/'controls.log').write_text(r.stdout);print(r.stdout);print('exit',r.returncode)
