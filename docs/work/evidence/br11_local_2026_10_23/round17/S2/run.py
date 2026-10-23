import os,subprocess,json
from pathlib import Path
root=Path("/home/dev_kaeem/forge-r17-review"); scratch=Path("/home/dev_kaeem/br11-review/r17/S2")
os.chdir(root)
from engcore.mind.world import owners
sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
assert sha=="98d72b2ef854012780f4222706884b911c4a2f03"
assert owners.__file__==str(root/"src/engcore/mind/world/owners.py")
scratch.joinpath("identity.json").write_text(json.dumps(dict(sha=sha,import_path=owners.__file__)))
cmd=["/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python","-m","pytest","-q","-s","-p","no:cacheprovider","--basetemp="+str(scratch/"pt"),str(scratch/"test_independent.py"),"tests/mind/test_authority_review_r16.py"]
r=subprocess.run(cmd,capture_output=True,text=True);scratch.joinpath("tests.log").write_text(r.stdout+r.stderr)
scratch.joinpath("execution.json").write_text(json.dumps(dict(command=cmd,cwd=str(root),exit_code=r.returncode,log=str(scratch/"tests.log"))))
print(r.stdout+r.stderr);print("EXIT",r.returncode)
