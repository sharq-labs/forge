import os,sys,subprocess,json,pathlib
p=pathlib.Path('/home/dev_kaeem/br11-review/r17/B');src='/home/dev_kaeem/forge-r17-review';py='/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python'
env=dict(os.environ,PYTHONPATH=src+'/src:'+src,PYTHONDONTWRITEBYTECODE='1')
sha=subprocess.check_output(['git','-C',src,'rev-parse','HEAD'],text=True).strip();assert sha=='98d72b2ef854012780f4222706884b911c4a2f03'
identity=subprocess.run([py,'-c',"import sys;from engcore.mind.world import owners;print(sys.version);print(owners.__file__);assert owners.__file__=='/home/dev_kaeem/forge-r17-review/src/engcore/mind/world/owners.py'"],env=env,cwd=src,capture_output=True,text=True);assert identity.returncode==0
(p/'identity.log').write_text(sha+'\n'+identity.stdout)
executions=[]
for label,cmd in [('probe_handing_boundary',[py,str(p/'probe_handing_boundary.py')]),('r16_controls',[py,'-m','pytest','tests/mind/test_authority_review_r16.py','-q','-p','no:cacheprovider','--basetemp='+str(p/'pt'),'-n','1'])]:
 r=subprocess.run(cmd,env=env,cwd=src,text=True,capture_output=True);(p/(label+'.log')).write_text(r.stdout+r.stderr);executions.append(dict(command=cmd,cwd=src,env_overrides={k:env[k] for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE']},exit_code=r.returncode,log=str(p/(label+'.log'))));print(label,r.returncode,r.stdout,r.stderr)
(p/'executions.json').write_text(json.dumps(executions,indent=2))
