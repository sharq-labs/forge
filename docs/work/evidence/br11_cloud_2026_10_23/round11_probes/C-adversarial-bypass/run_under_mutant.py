"""Apply mutant NAME (from mutants.py) to the tree copy, run probe PATH from the tree root, restore."""
import pathlib, subprocess, sys
sys.argv = sys.argv
here = pathlib.Path(__file__).parent
import importlib.util
spec = importlib.util.spec_from_file_location("m", here / "mutants.py")
src_text = (here / "mutants.py").read_text().split("\n\ndef run(name):")[0]
ns = {}
ns["__file__"] = str(here / "mutants.py"); exec(src_text, ns)
name, probe = sys.argv[1], sys.argv[2]
owners = ns["OWNERS"]
orig = owners.read_text()
if name != "none":
    old, new = ns["MUTANTS"][name]
    assert orig.count(old) == 1
    owners.write_text(orig.replace(old, new))
try:
    tree = ns["TREE"]
    p = subprocess.run(["/home/user/.forge-venv/bin/python", probe], cwd=tree, capture_output=True, text=True,
                       env={"PYTHONPATH": f"{tree}/src:{tree}", "PATH": "/usr/bin:/bin", "HOME": "/root"}, timeout=300)
    print(f"[{name}]", p.stdout.strip(), p.stderr.strip()[-300:])
finally:
    owners.write_text(orig)
