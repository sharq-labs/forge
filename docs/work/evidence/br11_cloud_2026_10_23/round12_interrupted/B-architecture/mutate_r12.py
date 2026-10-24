import sys
root, name = sys.argv[1], sys.argv[2]
O = "src/engcore/mind/world/owners.py"
M = {
 # round-11's own (re-checked)
 "alike_is_moving": [("        raise _Unreadable(f\"{what} is not one its owner writes down and reads back ({_ATTEMPTS} read-backs failed \"",
                      "        raise OwnerUnavailable(f\"{what} is not one its owner writes down and reads back ({_ATTEMPTS} read-backs failed \"")],
 "no_diverged_recheck": [("                    if key in self._diverged:\n                        observed[key] = self._diverged[key]\n                    elif len(self._seen.get(key, ())) > len(history):",
                          "                    if False:\n                        observed[key] = self._diverged[key]\n                    elif len(self._seen.get(key, ())) > len(history):")],
 "no_abandon": [("                        waiter[1] = True", "                        pass")],
 # new, round 12
 "fresh_failure_transient": [("                raise _Unreadable(f\"{what} is not one its owner writes down and reads back (it exceeds the \"",
                              "                raise OwnerUnavailable(f\"{what} is not one its owner writes down and reads back (it exceeds the \"")],
 "alias_not_recorded": [("                else:\n                    self._seen[key] = history\n                    if key in snapshot._aliased:",
                         "                elif key in snapshot._aliased:\n                    observed[key] = 'aliased, not recorded'\n                else:\n                    self._seen[key] = history\n                    if key in snapshot._aliased:")],
 "fresh_thread_no_flag": [("        def run() -> None:\n            self._in_follow.active = True\n",
                           "        def run() -> None:\n            self._in_follow.active = False\n")],
 "id_subclass_kept": [("                key = (kind, str.__str__(raw_id))    # the plain str it spells (no code of the id runs)",
                       "                key = (kind, raw_id)")],
 "leave_marks_compared": [("            if handed and ticket in self._in_flight:", "            if handed:")],
 "entry_refusal_once": [("                                                             f\"{owner_type.__name__}\", True)",
                         "                                                             f\"{owner_type.__name__}\", False)")],
 "handed_never_set": [("            handed = True\n", "            handed = False\n")],
 "skip_empty": [("                skip = frozenset(self._diverged)", "                skip = frozenset()")],
 "alias_not_recorded2": [("                else:\n                    self._seen[key] = history\n                    if key in snapshot._aliased:",
                          "                else:\n                    if key not in snapshot._aliased:\n                        self._seen[key] = history\n                    if key in snapshot._aliased:")],
 "moving_any_runtimeerror": [("    return type(exc) is RuntimeError and any(m in str(exc) for m in _MUTATION)", "    return isinstance(exc, RuntimeError) and not isinstance(exc, RecursionError)")],
}
path = f"{root}/{O}"
s = open(path).read()
for old, new in M[name]:
    assert s.count(old) == 1, (name, old[:70], s.count(old))
    s = s.replace(old, new)
open(path, "w").write(s)
print("applied", name)
