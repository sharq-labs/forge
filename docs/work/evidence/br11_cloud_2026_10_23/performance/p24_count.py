import collections, runpy, sys
from engcore.mind.world import owners as ow
stats = collections.Counter()
real = ow.BudgetReader._read_once
def counted(self, key):
    try:
        out = real(self, key)
        stats["ok"] += 1
        return out
    except ow._Failed as f:
        stats["failed:" + ("moving" if f.moving else f.why[:60])] += 1
        raise
ow.BudgetReader._read_once = counted
sys.argv = ["p24", "8", "6", "2500", "0.1"]
runpy.run_path(sys.argv_path if hasattr(sys, "argv_path") else "/tmp/claude-0/-home-user-forge/e352a8b8-4d77-5787-bd23-1bcc1dda83b7/scratchpad/review_r11/B-architecture/p24_contention_large_account.py", run_name="__main__")
print(dict(stats))
