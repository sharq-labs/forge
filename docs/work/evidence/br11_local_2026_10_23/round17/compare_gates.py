from pathlib import Path
import json,re
ROOT=Path('/home/dev_kaeem/forge-gen2-authority-v1')
EV=ROOT/'docs/work/evidence/br11_local_2026_10_23/round17'
BASE=EV.parent/'round15/reused_base_r14'
def ids(s):return sorted({x.split(' - ',1)[0] for x in re.findall(r'^(?:FAILED|ERROR) (.+)$',s,re.M)})
rows=[]
for label,file in [('guards_local','guards_failing.txt'),('expensive_local','expensive_failing_ids.txt'),('fast_clean','fast_failing_ids.txt')]:
 text=(EV/(label+'.log')).read_text();raw=(BASE/file).read_text()
 branch=ids(text);base=ids(raw) if label=='guards_local' else sorted(x.strip() for x in raw.splitlines() if x.strip())
 row={'suite':label,'branch_failure_ids':branch,'base_failure_ids':base,'new':sorted(set(branch)-set(base)),'fixed':sorted(set(base)-set(branch)),'summary':[x for x in text.splitlines() if re.search(r'\d+ (?:failed|passed|errors|skipped)',x)][-1]}
 rows.append(row);print(label,row['summary'],'NEW',len(row['new']),'FIXED',len(row['fixed']))
report={'base_sha':'1202ea6c3d96f5c31d0b142a32438da75e020cae','source_sha':json.loads((EV/'gate_candidate.json').read_text())['sha'],'rows':rows,'verdict':'NO NEW FAILURES VS BASE' if all(not r['new'] for r in rows) else 'NEW FAILURES'}
(EV/'gate_differential.json').write_text(json.dumps(report,indent=2)+'\n')
assert all(not r['new'] for r in rows)
