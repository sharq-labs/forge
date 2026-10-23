from pathlib import Path
import hashlib,json,re
ROOT=Path("/home/dev_kaeem/forge-gen2-authority-v1")
EV=ROOT/"docs/work/evidence/br11_local_2026_10_23/round15"
def ids(text):
    return sorted({line.split(" - ",1)[0] for line in re.findall(r"^(?:FAILED|ERROR) (.+)$",text,re.M)})
rows=[]
for label,filename in [("guards","guards_failing.txt"),("expensive","expensive_failing_ids.txt"),("fast_final","fast_failing_ids.txt")]:
    path=EV/(label+".log")
    if not path.exists():continue
    branch=path.read_text()
    base=(EV/"reused_base_r14"/filename).read_text()
    branch_ids=ids(branch)
    base_ids=ids(base) if label=="guards" else sorted(x.strip() for x in base.splitlines() if x.strip())
    row={"suite":label,"branch_failures":branch_ids,"base_failures":base_ids,
         "new_failures":sorted(set(branch_ids)-set(base_ids)),"fixed_failures":sorted(set(base_ids)-set(branch_ids)),
         "branch_summary":[x for x in branch.splitlines() if re.search(r"\d+ (?:failed|passed|errors|skipped)",x)][-1]}
    row["verdict"]="NO NEW FAILURES VS BASE" if not row["new_failures"] else "NEW FAILURES"
    rows.append(row)
summary={"base_sha":"1202ea6c3d96f5c31d0b142a32438da75e020cae","initial_changed_run":"INVALIDATED: copied historical pytest basetemp contaminated collection; interrupted; never gate evidence",
         "source_sha256":hashlib.sha256((ROOT/"src/engcore/mind/world/owners.py").read_bytes()).hexdigest(),"suites":rows}
(EV/"gate_differential.json").write_text(json.dumps(summary,indent=2)+"\n")
for row in rows:print(row["suite"],row["branch_summary"],"NEW",len(row["new_failures"]),"FIXED",len(row["fixed_failures"]),row["verdict"])
assert all(not row["new_failures"] for row in rows)

