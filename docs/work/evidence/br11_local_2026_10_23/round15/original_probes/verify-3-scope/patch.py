import sys
p = sys.argv[1] + "/src/engcore/mind/world/owners.py"
s = open(p, "rb").read()
old = b"        with self._changed:\n            pending = self._in_flight - {ticket}\n"
new = (b"        with self._changed:\n            if self._sealed is not None:\n"
       b"                self._in_flight.discard(ticket); self._changed.notify_all()\n"
       b"                return {k: self._sealed for k in read}\n"
       b"            pending = self._in_flight - {ticket}\n")
assert s.count(old) == 1
open(p, "wb").write(s.replace(old, new))
print("patched")
