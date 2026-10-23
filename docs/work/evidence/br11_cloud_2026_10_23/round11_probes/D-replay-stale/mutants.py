"""R11-D mutants of the round-10 code, applied one at a time to a tree copy (argv[1]) from the pristine copies saved
next to this script; argv[2]: mutant name, or 'restore'."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
tree, name = sys.argv[1], sys.argv[2]
OW = "src/engcore/mind/world/owners.py"
PR = "src/engcore/mind/world/projection.py"
M = {
    "torn_for_good": (OW, '                raise OwnerUnavailable(f"{what} was serialized while it moved',
                      '                raise _Unreadable(f"{what} was serialized while it moved'),
    "runtime_for_good": (OW, '        raise OwnerUnavailable(f"{what} moved while it was serialized: {exc}") from None',
                         '        raise _Unreadable(f"{what} moved while it was serialized: {exc}") from None'),
    "decide_without_wait": (OW, "            if pending and accepted:\n", "            if False:\n"),
    "no_diverged_first": (OW, "                if key in self._diverged:\n                    observed[key] = self._diverged[key]\n"
                              "                    continue\n                if type(got) is _NotRead:",
                          "                if type(got) is _NotRead:"),
    "lower_rev_false": (PR, '    if not all(type(r) is str and r.isascii() and r.isdigit() for r in (stated, in_force)):',
                        '    if True:'),
    "lower_rev_le": (PR, "    return (len(stated), stated) < (len(in_force), in_force)",
                     "    return (len(stated), stated) <= (len(in_force), in_force)"),
    "lower_rev_no_lstrip": (PR, '    stated, in_force = stated.lstrip("0") or "0", in_force.lstrip("0") or "0"\n', ""),
    "lower_rev_lexical": (PR, "    return (len(stated), stated) < (len(in_force), in_force)",
                          "    return stated < in_force"),
    "readback_not_detached_copy": (OW, "        back = copy.deepcopy(back)                   # JSON data this reader parsed",
                                   "        back = back                   # JSON data this reader parsed"),
}
for f, orig in ((OW, "owners_orig.py"), (PR, "projection_orig.py")):
    open(os.path.join(tree, f), "w").write(open(os.path.join(HERE, orig)).read())
if name == "restore":
    print("restored")
    sys.exit(0)
f, old, new = M[name]
path = os.path.join(tree, f)
s = open(path).read()
assert s.count(old) == 1, (name, s.count(old))
open(path, "w").write(s.replace(old, new))
print("applied", name)
