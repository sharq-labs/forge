import sys
root, name = sys.argv[1], sys.argv[2]
O = "src/engcore/mind/world/owners.py"
P = "src/engcore/mind/world/projection.py"
M = {
 "one_attempt": (O, [("_ATTEMPTS = 3 ", "_ATTEMPTS = 1 ")]),
 "alike_is_moving": (O, [("        raise _Unreadable(f\"{what} is not one its owner writes down and reads back ({_ATTEMPTS} read-backs failed \"",
                          "        raise OwnerUnavailable(f\"{what} is not one its owner writes down and reads back ({_ATTEMPTS} read-backs failed \"")]),
 "no_baseline_retry": (O, [("        if all(f.recursion for f in failures):       # the state's depth, or this verification's caller's?",
                            "        if False:")]),
 "never_moving": (O, [("    return type(exc) is RuntimeError and any(m in str(exc) for m in _MUTATION)", "    return False")]),
 "strict_snapshot": (O, [("                current = BudgetReader._handed(mapping, self.owner_id, skip)",
                          "                current = BudgetReader(*mapping, owner_id=self.owner_id)")]),
 "no_abandon": (O, [("                        waiter[1] = True", "                        pass")]),
 "no_alias_refusal": (O, [("                    if key in snapshot._aliased:", "                    if False:")]),
 "serve_shared": (O, [("            back = json.loads(back_text)             # parsed from the owner's text at every read: never shared",
                       "            back = _SHARED.setdefault(back_text, json.loads(back_text))"),
                      ("_ATTEMPTS = 3 ", "_SHARED: dict = {}\n_ATTEMPTS = 3 ")]),
 "leave_first": (O, [("            self._in_follow.active = False\n            try:\n                self._leave(ticket, handed)\n            finally:\n                self._in_flight.discard(ticket)      # (atomic): never left in flight if the lock wait is interrupted",
                      "            self._leave(ticket, handed)\n            self._in_follow.active = False")]),
 "no_diverged_recheck": (O, [("                    if key in self._diverged:\n                        observed[key] = self._diverged[key]\n                    elif len(self._seen.get(key, ())) > len(history):",
                              "                    if False:\n                        observed[key] = self._diverged[key]\n                    elif len(self._seen.get(key, ())) > len(history):")]),
 "lexical_revision": (P, [("    return (len(stated), stated) < (len(in_force), in_force)", "    return stated < in_force")]),
 "skip_not_used": (O, [("            if key in self._skip:                    # refused for good already: not read again", "            if False:")]),
 "torn_check_dropped": (O, [("                if type(written) is not dict or back.get(\"accounting\") != written.get(\"accounting\") \\\n                        or back.get(\"budget\") != written.get(\"budget\"):",
                             "                if False:")]),
}
f, edits = M[name]
path = f"{root}/{f}"
s = open(path).read()
for old, new in edits:
    assert s.count(old) == 1, (name, old[:60], s.count(old))
    s = s.replace(old, new)
open(path, "w").write(s)
print("applied", name)
