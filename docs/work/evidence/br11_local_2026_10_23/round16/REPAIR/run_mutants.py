import os, shutil, subprocess, json, hashlib
from pathlib import Path
root=Path('/home/dev_kaeem/forge-gen2-authority-v1')
out=Path('/home/dev_kaeem/br11-review/r16/REPAIR')
tree=out/'mutant_source'
shutil.copytree(root/'src',tree/'src',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
path=tree/'src/engcore/mind/world/owners.py'
base=(root/'src/engcore/mind/world/owners.py').read_text()
cases={
 'baseline':None,
 'raw_history':('self._history(owner.from_dict(entry.to_dict()) for entry in entries)','self._history(entries)'),
 'identity_is_divergence':('self._unread_entries[key] = (_PendingHistories((*kept, entries)) if kept else entries)','self._diverged[key] = self._rewrote_unread(key)'),
 'discard_earlier':('self._unread_entries[key] = (_PendingHistories((*kept, entries)) if kept else entries)','self._unread_entries[key] = entries'),
 'unguarded_reconciliation':('if self._unread_entries.get(key) is not barrier:', 'if False:'),
 'incompatible_is_prefix':('elif seen[:len(history)] != history:', 'elif False:'),
 'lose_post_return':('if ticket not in self._uncompared:', 'if False:'),
}
results=[]
for name, edit in cases.items():
 source=base
 if edit:
  assert source.count(edit[0])==1, (name,source.count(edit[0]))
  source=source.replace(*edit)
 path.write_text(source)
 env=dict(os.environ,PYTHONPATH=str(tree/'src')+':'+str(root),PYTHONDONTWRITEBYTECODE='1')
 cmd=[str(root/'.venv/bin/python'),'-m','pytest','-o','pythonpath='+str(tree/'src'),'-p','no:cacheprovider','--basetemp='+str(out/('pt-mutant-'+name)),'-q','tests/mind/test_authority_review_r16.py']
 with (out/('mutant-stable-'+name+'.log')).open('w') as log:
  run=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
 result={'name':name,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'command':cmd,'cwd':str(root),'env':{k:env[k] for k in ('PYTHONPATH','PYTHONDONTWRITEBYTECODE')},'exit_code':run.returncode,'log':str(out/('mutant-stable-'+name+'.log'))}
 results.append(result)
 print(name,run.returncode,flush=True)
(out/'mutants-stable.json').write_text(json.dumps(results,indent=2)+'\n')
path.write_text(base)
