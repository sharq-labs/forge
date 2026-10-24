"""Round-12 local mutation challenge: apply one mutant to src/engcore/mind/world/owners.py in a tree copy.

Usage: python mutate_r12_local.py <tree> <mutant>.  Every mutant restores one defect the round-12 fixes (or an earlier
round's guard whose mutant survived round 12) removed; each replacement must match exactly once."""
import sys

root, name = sys.argv[1], sys.argv[2]
O = "src/engcore/mind/world/owners.py"
M = {
    # R12-1: render the failure with the exception's own code (escapes when __str__ raises)
    "render_raw": [("            why = _described(exc)\n",
                    "            why = f\"{type(exc).__name__}: {exc}\"\n")],
    "moving_raw_str": [("    return type(exc) is RuntimeError and any(m in described for m in _MUTATION)",
                        "    return type(exc) is RuntimeError and any(m in str(exc) for m in _MUTATION)")],
    # R12-2: two entries spelling one id
    "no_spelled_check": [("                if key in spelled:", "                if False:")],
    "ctor_no_spelling_check": [("        if len(self._ledgers) != len(raw[0]) or len(self._experiments) != len(raw[1]):",
                                "        if False:")],
    # R12-3: the length a state not read back stated
    "no_floor_record": [("                        self._reached[key] = max(self._reached.get(key, 0), got.length)",
                         "                        pass")],
    "no_floor_compare": [("                    if len(history) < self._reached.get(key, 0):\n"
                          "                        observed[key] = self._behind(key)\n"
                          "                    elif key in snapshot._aliased:",
                          "                    if key in snapshot._aliased:")],
    "no_floor_post_wait": [("                    elif max(len(self._seen.get(key, ())), self._reached.get(key, 0)) > len(history):",
                            "                    elif len(self._seen.get(key, ())) > len(history):")],
    "unreadable_length_floor_zero": [("                out[key] = _NotRead(str(exc), False, length) if length is not None else \\",
                                      "                out[key] = _NotRead(str(exc), False, length or 0) if True else \\")],
    # R12-4: the fresh-thread wait
    "join_unbounded": [("        thread.join(self.WAIT_S)", "        thread.join()")],
    "timeout_for_good": [("                raise OwnerUnavailable(f\"{what} was not read back within {self.WAIT_S} s on a fresh thread\")",
                          "                raise _Unreadable(f\"{what} was not read back within {self.WAIT_S} s on a fresh thread\")")],
    "shared_cache": [("        cache = dict(self._readback)\n", "        cache = self._readback\n")],
    # R12-5: the fresh-thread attempts and wrapped recursion
    "fresh_single_attempt": [("                box[\"result\"] = self._attempts(key, cache)\n",
                              "                try:\n"
                              "                    box[\"result\"] = (self._read_once(key, cache), [])\n"
                              "                except _Failed as failed:\n"
                              "                    box[\"result\"] = (None, [failed])\n")],
    "recursion_direct_only": [("    pending, seen = [exc], set()\n",
                               "    return issubclass(type(exc), RecursionError)\n    pending, seen = [exc], set()\n")],
    # R12-6: the mutants that survived the interrupted round (adapted to the current text where it moved)
    "id_str_call": [("                key = (kind, str.__str__(raw_id))    # the plain str it spells (no code of the id runs)",
                     "                key = (kind, str(raw_id))")],
    "differ_not_moving": [("        if any(f.moving for f in failures) or len({(f.why, f.text) for f in failures}) > 1:",
                           "        if any(f.moving for f in failures):")],
    "why_only": [("        if any(f.moving for f in failures) or len({(f.why, f.text) for f in failures}) > 1:",
                  "        if any(f.moving for f in failures) or len({f.why for f in failures}) > 1:")],
    "alias_not_recorded2": [("                    self._seen[key] = history\n"
                             "                    if len(history) < self._reached.get(key, 0):",
                             "                    if key not in snapshot._aliased:\n"
                             "                        self._seen[key] = history\n"
                             "                    if len(history) < self._reached.get(key, 0):")],
    "fresh_thread_no_flag": [("        def run() -> None:\n            self._in_follow.active = True\n",
                              "        def run() -> None:\n            self._in_follow.active = False\n")],
}
path = f"{root}/{O}"
with open(path, "rb") as f:
    s = f.read().decode("utf-8")
for old, new in M[name]:
    assert s.count(old) == 1, (name, old[:70], s.count(old))
    s = s.replace(old, new)
with open(path, "wb") as f:
    f.write(s.encode("utf-8"))
print("applied", name)
