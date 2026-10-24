import os, subprocess, json, hashlib, shutil
from pathlib import Path
root=Path('/home/dev_kaeem/forge-gen2-authority-v1'); out=Path('/home/dev_kaeem/br11-review/r17/REPAIR')
source=(root/'src/engcore/mind/world/owners.py').read_text()
mutants={
 'ledger_skip_json': ('return BudgetCharge.from_dict(json.loads(written))','return normalized'),
 'experiment_skip_json': ('rebuilt = ScientificEvaluation.from_dict(json.loads(to_json(entry)))','rebuilt = ScientificEvaluation.from_dict(entry.to_dict())'),
 'ledger_scientific_json': ('written = json.dumps(normalized.to_dict(), sort_keys=True, separators=(",", ":"), default=str)','written = to_json(normalized)'),
 'experiment_default_string': ('rebuilt = ScientificEvaluation.from_dict(json.loads(to_json(entry)))','rebuilt = ScientificEvaluation.from_dict(json.loads(json.dumps(entry.to_dict(), sort_keys=True, default=str)))'),
 'experiment_nonfinite_allowed': ('rebuilt = ScientificEvaluation.from_dict(json.loads(to_json(entry)))\n        to_json(rebuilt)','rebuilt = ScientificEvaluation.from_dict(json.loads(json.dumps(entry.to_dict(), sort_keys=True)))\n        json.dumps(rebuilt.to_dict(), sort_keys=True)'),
 'ledger_json_before_owner': ('normalized = BudgetCharge.from_dict(entry.to_dict())','normalized = BudgetCharge.from_dict(json.loads(json.dumps(entry.to_dict(), sort_keys=True, default=str)))'),
 'discard_retained_histories': ('resolved[key] = (barrier, histories)','resolved[key] = (barrier, ())'),
}
records=[]
for name, (before, after) in mutants.items():
 assert source.count(before)==1, name
 isolated=out/'mutants'/name
 shutil.copytree(root/'src',isolated/'src',ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=False)
 path=isolated/'src/engcore/mind/world/owners.py'; path.write_text(source.replace(before,after))
 env={**os.environ,'PYTHONPATH':str(isolated/'src')+':'+str(root),'PYTHONDONTWRITEBYTECODE':'1'}
 check=[str(root/'.venv/bin/python'),'-c',"import engcore.mind.world.owners as o; from engcore.mind.world import BudgetReader; from engcore.sria.campaign.budget import BudgetCharge; assert o.BudgetReader is BudgetReader; assert o.BudgetCharge is BudgetCharge; print(o.__file__)"]
 identity=subprocess.run(check,cwd=isolated,env=env,capture_output=True,text=True)
 assert identity.returncode==0 and str(path) in identity.stdout, identity.stdout+identity.stderr
 cmd=[str(root/'.venv/bin/python'),'-m','pytest','-q','-p','no:cacheprovider','-o','pythonpath='+str(isolated/'src'),'--basetemp='+str(isolated/'pt'),'tests/mind/test_authority_review_r17.py','tests/mind/test_authority_review_r16.py']
 result=subprocess.run(cmd,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 log=isolated/'pytest.log';log.write_text(result.stdout)
 record={'name':name,'command':cmd,'cwd':str(root),'environment':{k:env[k] for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE']},'exit_code':result.returncode,'log':str(log),'identity_command':check,'identity_exit_code':identity.returncode,'identity_result':identity.stdout,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'summary':result.stdout.splitlines()[-1],'failures':[l for l in result.stdout.splitlines() if l.startswith('FAILED ')]}
 (isolated/'execution.json').write_text(json.dumps(record,indent=2)+'\n');records.append(record)
 print(name,record['summary'],flush=True)
(out/'mutants.json').write_text(json.dumps(records,indent=2)+'\n')
assert all(r['exit_code']==1 and r['failures'] for r in records)
