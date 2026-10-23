from pathlib import Path
import os, subprocess, json, time
root=Path("/home/dev_kaeem/br11-review/r16/A")
env=dict(os.environ,PYTHONPATH="/home/dev_kaeem/forge-r16-review/src:/home/dev_kaeem/forge-r16-review",PYTHONDONTWRITEBYTECODE="1")
cmd=["/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python",str(root/"probe_native_stack.py")]
r=subprocess.run(cmd,cwd="/home/dev_kaeem/forge-r16-review",env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=55)
(root/"probe_native_stack.log").write_text(r.stdout)
print(r.stdout)
print("EXIT",r.returncode)
(root/"executions.jsonl").open("a").write(json.dumps({"command":"cd /home/dev_kaeem/forge-r16-review && PYTHONPATH=/home/dev_kaeem/forge-r16-review/src:/home/dev_kaeem/forge-r16-review PYTHONDONTWRITEBYTECODE=1 "+" ".join(cmd),"exit":r.returncode,"log_path":str(root/"probe_native_stack.log")})+"\n")
