import os, pathlib, subprocess, sys, json
root=pathlib.Path('/home/dev_kaeem/forge-r16-review')
out=pathlib.Path('/home/dev_kaeem/br11-review/r16/E')
sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
import engcore.mind.world.owners as owners
identity={'sha':sha,'owners_file':owners.__file__,'python':sys.executable,'python_version':sys.version,'PYTHONPATH':os.environ.get('PYTHONPATH'),'PYTHONDONTWRITEBYTECODE':os.environ.get('PYTHONDONTWRITEBYTECODE')}
assert sha=='b8a65bb9d02b5a18e0a8b26779773c1552204dc1'
assert owners.__file__==str(root/'src/engcore/mind/world/owners.py')
(out/'identity.json').write_text(json.dumps(identity,indent=2))
cmd=[sys.executable,'-m','pytest','-q','-s','-p','no:cacheprovider','--basetemp='+str(out/'pt'),str(out/'test_e_replay.py')]
result=subprocess.run(cmd,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
(out/'probe_expanded.log').write_text(result.stdout)
(out/'probe_expanded_execution.json').write_text(json.dumps({'command':' '.join(cmd),'cwd':str(root),'env':identity,'exit':result.returncode,'log':str(out/'probe_expanded.log')},indent=2))
print(json.dumps(identity)); print(result.stdout); sys.exit(result.returncode)
