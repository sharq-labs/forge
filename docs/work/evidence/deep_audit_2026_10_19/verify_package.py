"""Stdlib-only integrity check of the audit scratch package (reads only scratch files)."""
import hashlib, json, os, sys
from collections import Counter

A = sys.argv[1]
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
required = (["package/" + n for n in ("FORGE_DEEP_SCIENTIFIC_DEFECT_AUDIT.md", "FORGE_NEW_FINDINGS_REGISTER.json",
             "FORGE_SCIENTIFIC_RISK_MATRIX.md", "FORGE_ADVERSARIAL_REPRODUCTION_PLAN.md", "FORGE_BUILD_VS_BUY_DEFECT_OPPORTUNITIES.md")]
            + [f"reviewer_{x}.md" for x in "ABCDE"] + [f"crossreview_X{i}.md" for i in (1, 2, 3)])
for r in required:
    p = os.path.join(A, r)
    print("present" if os.path.isfile(p) and os.path.getsize(p) > 0 else "MISSING", r)
for rid, scr in (("R-03", "r03_material_arbitration.py"), ("R-04", "r04_mcp_uq.py"),
                 ("R-05", "r05_vacuous_pair.py"), ("R-06", "r06_spurious_cap.py")):
    d = json.load(open(os.path.join(A, "repro", rid + ".json")))
    ok = (d["stdout_sha256"] == h(os.path.join(A, "repro", rid + ".out"))
          and d["stderr_sha256"] == h(os.path.join(A, "repro", rid + ".err"))
          and d["script_sha256"] == h(os.path.join(A, "repro", scr))
          and d["source"]["tracked_hash_before"] == d["source"]["tracked_hash_after"]
          and d["exit_code"] == 0 and d["source"]["new_pyc_in_repo"] == 0
          and d["source"]["head_before"] == d["source"]["head_after"] == "abed661f0d551f352e7a2c451d0df7fcc22bde5c")
    v = [l.strip() for l in open(os.path.join(A, "repro", rid + ".out")) if l.startswith(("VERDICT", "CONTROL_OK"))]
    print(rid, "record-consistent" if ok else "MISMATCH", v)
reg = json.load(open(os.path.join(A, "package", "FORGE_NEW_FINDINGS_REGISTER.json")))
sev = Counter(f["severity"].split(" ")[0] for f in reg["findings"])
print("severity:", dict(sev), "observations:", len(reg["observations"]), "counts:", reg["counts"])
print("executed:", [f["f1_id"] for f in reg["findings"] if "execution" in f])
print("ids unique:", len(reg["findings"]) == len({f["f1_id"] for f in reg["findings"]}), len(reg["findings"]))
print("BLOCKER-labelled:", [f["f1_id"] for f in reg["findings"] if "BLOCKER" in f["severity"]])
