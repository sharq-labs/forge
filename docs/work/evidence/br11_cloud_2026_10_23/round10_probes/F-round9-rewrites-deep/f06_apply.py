"""Apply one f05 mutant to tree-mut, run a probe from tree-mut's root, revert."""
import pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import importlib.util
spec = importlib.util.spec_from_file_location("f05", pathlib.Path(__file__).parent / "f05_mutants.py")
src = (pathlib.Path(__file__).parent / "f05_mutants.py").read_text().split("TESTS = ")[0]
ns = {"__file__": str(pathlib.Path(__file__).parent / "f05_mutants.py")}
exec(src, ns)
MUT, T, PY = ns["MUTANTS"], ns["T"], ns["PY"]
name = next(k for k in MUT if k.startswith(sys.argv[1] + "_"))
probe, args = sys.argv[2], sys.argv[3:]
orig = {}
for path, old, new in MUT[name]:
    cur = path.read_text(); orig.setdefault(path, cur)
    assert cur.count(old) == 1, (name, old)
    path.write_text(cur.replace(old, new))
try:
    r = subprocess.run([PY, probe, *args], cwd=T, capture_output=True, text=True, timeout=600,
                       env={"PYTHONPATH": f"{T}/src:{T}", "PATH": "/usr/bin:/bin"})
    print(f"[{name}]"); print(r.stdout[-3000:]); print(r.stderr[-1500:])
finally:
    for p, t in orig.items():
        p.write_text(t)
