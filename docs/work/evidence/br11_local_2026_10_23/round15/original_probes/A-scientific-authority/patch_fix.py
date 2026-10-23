import sys
p = sys.argv[1]
s = open(p, "rb").read().decode("utf-8")
old = "        with self._changed:\n            pending = self._in_flight - {ticket}\n"
new = ("        with self._changed:\n            pending = self._in_flight - {ticket}\n"
       "            if self._sealed is not None:\n"
       "                self._in_flight.discard(ticket)\n"
       "                self._changed.notify_all()\n"
       "                return {k: self._sealed for k in read}\n")
assert s.count(old) == 1
open(p, "wb").write(s.replace(old, new).encode("utf-8"))
print("patched")
