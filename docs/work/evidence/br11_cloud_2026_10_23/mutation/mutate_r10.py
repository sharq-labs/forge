"""Apply one named mutation to owners.py in a tree copy; print whether it applied."""
import sys
p, name = sys.argv[1], sys.argv[2]
s = open(p).read()
M = {
 "no_wait": ("            if pending and accepted:\n                if not self._changed.wait_for(lambda: not pending & self._in_flight, timeout=self.WAIT_S):",
             "            if pending and accepted:\n                if True:"),
 "start_order": ("            pending = set(self._in_flight)", "            pending = {t for t in self._in_flight if t < ticket}"),
 "no_recheck": ("                    elif len(self._seen.get(key, ())) > len(history):\n                        observed[key] = self._behind(key)",
                "                    elif False:\n                        observed[key] = self._behind(key)"),
 "not_for_good": ("                out[key] = _NotRead(str(exc), True)", "                out[key] = _NotRead(str(exc), False)"),
 "shared_cache": ("            current._readback = dict(self._readback)", "            current._readback = self._readback"),
 "readback_locked": ("        read = snapshot._read_back()\n", "        with self._lock:\n            read = snapshot._read_back()\n"),
 "flag_early_reset": ("            current._readback = dict(self._readback)", "            self._in_follow.active = False\n            current._readback = dict(self._readback)"),
 "no_key_check": ("        if any(type(i) is not str for i in [*self._ledgers, *self._experiments]):", "        if False:"),
 "ledger_not_detached": ("                back = BudgetLedger.from_dict(json.loads(text_))", "                back = BudgetLedger.from_dict(ledger.to_dict())"),
 "no_notify": ("            self._in_flight.discard(ticket)\n            self._changed.notify_all()\n\n", "            self._in_flight.discard(ticket)\n\n"),
}
old, new = M[name]
assert s.count(old) == 1, (name, s.count(old))
open(p, "w").write(s.replace(old, new))
print("applied", name)
