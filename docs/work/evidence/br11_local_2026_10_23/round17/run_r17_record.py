"""Capture bounded campaign commands and append exact execution records."""
from pathlib import Path
import subprocess, sys, os, json
ROOT = Path("/home/dev_kaeem/forge-gen2-authority-v1")
EVIDENCE = ROOT / "docs/work/evidence/br11_local_2026_10_23/round17"
label, cwd, *command = sys.argv[1:]
env = dict(os.environ, PYTHONPATH=f"{cwd}/src:{cwd}", PYTHONDONTWRITEBYTECODE="1")
result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
log = EVIDENCE / (label + ".log")
log.write_text(result.stdout)
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()
source_hash = __import__("hashlib").sha256((Path(cwd)/"src/engcore/mind/world/owners.py").read_bytes()).hexdigest()
record = {"owners_sha256":source_hash,"label":label,"cwd":cwd,"sha":sha,"command":command,"environment":{"PYTHONPATH":env["PYTHONPATH"],"PYTHONDONTWRITEBYTECODE":"1"},"exit_code":result.returncode,"log":str(log.relative_to(ROOT))}
with (EVIDENCE/"executions.jsonl").open("a") as f: f.write(json.dumps(record)+"\n")
with (ROOT/"docs/work/PROGRESS.md").open("a") as f:
 f.write("\n- R17 continuation execution: `"+label+"`, source HEAD `"+sha+"`; cwd `"+cwd+"`; `PYTHONPATH="+env["PYTHONPATH"]+" PYTHONDONTWRITEBYTECODE=1 "+__import__("shlex").join(command)+"`; exit "+str(result.returncode)+". Exact output/failure names: `"+str(log.relative_to(ROOT))+"`.\n")
print(json.dumps(record))
print(result.stdout[-4000:])
sys.exit(result.returncode)

