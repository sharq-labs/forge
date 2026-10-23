import sys
root, name = sys.argv[1], sys.argv[2]
O = "src/engcore/mind/world/owners.py"
M = {
 "id_str_call": (O, [("                key = (kind, str.__str__(raw_id))    # the plain str it spells (no code of the id runs)",
                      "                key = (kind, str(raw_id))")]),
 "differ_not_moving": (O, [("        if any(f.moving for f in failures) or len({(f.why, f.text) for f in failures}) > 1:",
                            "        if any(f.moving for f in failures):")]),
 "why_only": (O, [("        if any(f.moving for f in failures) or len({(f.why, f.text) for f in failures}) > 1:",
                   "        if any(f.moving for f in failures) or len({f.why for f in failures}) > 1:")]),
 "text_only": (O, [("        if any(f.moving for f in failures) or len({(f.why, f.text) for f in failures}) > 1:",
                    "        if any(f.moving for f in failures) or len({f.text for f in failures}) > 1:")]),
}
f, edits = M[name]
path = f"{root}/{f}"
s = open(path).read()
for old, new in edits:
    assert s.count(old) == 1, (name, old[:60], s.count(old))
    s = s.replace(old, new)
open(path, "w").write(s)
print("applied", name)
