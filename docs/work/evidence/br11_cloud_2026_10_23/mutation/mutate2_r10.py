import sys
p, name = sys.argv[1], sys.argv[2]
M = {
 "no_detach": ("src/engcore/mind/world/owners.py", [
    ("                rebuilt = ScientificExperiment.from_dict(json.loads(text_))\n                back = json.loads(to_json(rebuilt))",
     "                rebuilt = ScientificExperiment.from_dict(exp.to_dict())\n                back = rebuilt.to_dict()")]),
 "no_finally_leave": ("src/engcore/mind/world/owners.py", [
    ("        finally:\n            self._leave(ticket)\n            self._in_follow.active = False",
     "        finally:\n            self._in_follow.active = False")]),
 "bind_own_conversion": ("src/engcore/mind/world/actions.py", [
    ("        return executed_level(domain, value, unit_, also=domain.levels)\n", "        pass\n")]),
}
f, edits = M[name]
path = p + "/" + f
s = open(path).read()
for old, new in edits:
    assert s.count(old) == 1, (name, old[:50])
    s = s.replace(old, new)
open(path, "w").write(s)
print("applied", name)
