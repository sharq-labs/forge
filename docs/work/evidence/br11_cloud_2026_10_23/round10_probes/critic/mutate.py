import sys
p, old, new = sys.argv[1:4]
s = open(p).read()
assert s.count(old) == 1, (s.count(old), old)
open(p, "w").write(s.replace(old, new))
