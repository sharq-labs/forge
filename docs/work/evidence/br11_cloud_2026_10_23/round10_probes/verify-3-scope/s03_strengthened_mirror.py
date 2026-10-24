"""verify-3-scope s03: the finding's proposed strengthening (earlier = bool(in_flight)) applied in-process, then the
s01 mirror order and its no-T2 control re-run."""
import inspect, runpy, textwrap
import engcore.mind.world.owners as ow

SRC = textwrap.dedent(inspect.getsource(ow.BudgetReader._observe_all))
ORIG = "earlier = any(t < ticket for t in self._in_flight)"
ns = {}
exec(compile(SRC.replace(ORIG, "earlier = bool(self._in_flight)"), ow.__file__, "exec"), vars(ow), ns)
ow.BudgetReader._observe_all = ns["_observe_all"]
runpy.run_path("/tmp/claude-0/-home-user-forge/e352a8b8-4d77-5787-bd23-1bcc1dda83b7/scratchpad/review_r10/verify-3-scope/s01_mirror_and_controls.py")
