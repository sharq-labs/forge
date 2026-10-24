from pathlib import Path
import os,subprocess,json
root="/home/dev_kaeem/forge-r16-review"
p=Path("/home/dev_kaeem/br11-review/r16/S1")
env=os.environ.copy();env["PYTHONPATH"]=root+"/src:"+root;env["PYTHONDONTWRITEBYTECODE"]="1"
cmd=["/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python",str(p/"probe_followup.py")]
r=subprocess.run(cmd,cwd=root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(p/"probe_followup.log").write_text(r.stdout)
(p/"execution_followup.json").write_text(json.dumps({"command":"cd "+root+" && PYTHONPATH="+env["PYTHONPATH"]+" PYTHONDONTWRITEBYTECODE=1 "+" ".join(cmd),"exit":r.returncode,"log_path":str(p/"probe_followup.log")},indent=2))
print(r.stdout);print("EXIT",r.returncode)
