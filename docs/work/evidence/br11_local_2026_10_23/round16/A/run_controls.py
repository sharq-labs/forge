from pathlib import Path
import os, subprocess, json
root=Path("/home/dev_kaeem/br11-review/r16/A")
source="/home/dev_kaeem/forge-r16-review"
python="/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python"
env=dict(os.environ,PYTHONPATH=source+"/src:"+source,PYTHONDONTWRITEBYTECODE="1")
sha=subprocess.check_output(["git","-C",source,"rev-parse","HEAD"],text=True).strip()
assert sha=="b8a65bb9d02b5a18e0a8b26779773c1552204dc1"
identity=subprocess.check_output([python,"-c","import engcore.mind.world.owners as ow; print(ow.__file__)"],env=env,cwd=source,text=True).strip()
assert identity==source+"/src/engcore/mind/world/owners.py"
cmd=[python,"-m","pytest","-p","no:cacheprovider","--basetemp="+str(root/"pt"),"-n","1","-q","tests/mind/test_authority_review_r15.py","tests/mind/test_authority_state_machine_r15.py"]
r=subprocess.run(cmd,cwd=source,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=55)
(root/"controls.log").write_text("SHA: "+sha+"\nIMPORT: "+identity+"\n"+r.stdout)
print(r.stdout)
print("EXIT",r.returncode)
(root/"executions.jsonl").open("a").write(json.dumps({"command":"cd "+source+" && PYTHONPATH="+source+"/src:"+source+" PYTHONDONTWRITEBYTECODE=1 "+" ".join(cmd),"exit":r.returncode,"result":r.stdout.strip(),"log_path":str(root/"controls.log")})+"\n")
