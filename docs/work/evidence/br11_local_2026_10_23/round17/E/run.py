import json, pathlib, subprocess, sys
from engcore.mind.world import owners
root=pathlib.Path("/home/dev_kaeem/forge-r17-review")
out=pathlib.Path("/home/dev_kaeem/br11-review/r17/E")
sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
assert sha=="98d72b2ef854012780f4222706884b911c4a2f03"
assert owners.__file__==str(root/"src/engcore/mind/world/owners.py")
identity={"sha":sha,"owners_file":owners.__file__,"executable":sys.executable}
(out/"identity.json").write_text(json.dumps(identity,indent=2))
cmd=[sys.executable,"-m","pytest","-p","no:cacheprovider","--basetemp="+str(out/"pt"),"-q","-s",str(out/"test_replay.py"),"tests/mind/test_authority_review_r16.py"]
r=subprocess.run(cmd,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(out/"tests.log").write_text(r.stdout)
(out/"execution.json").write_text(json.dumps({"command":cmd,"cwd":str(root),"exit_code":r.returncode,"log":str(out/"tests.log")},indent=2))
print(json.dumps(identity));print(r.stdout);sys.exit(r.returncode)
