"""verify-3-scope s02: does the CLAIMED guarantee (a spend an EARLIER-started verification was handed is never
overtaken by a rollback) have an effective control?  Weaken the ticket rule in-process (earlier = False) and run
test_authority_review_r9's control; then strengthen it (earlier = bool(in_flight)) and run the s01 mirror order."""
import inspect, sys, textwrap, subprocess

import engcore.mind.world.owners as ow
from tests.mind import test_authority_review_r9 as t9

SRC = textwrap.dedent(inspect.getsource(ow.BudgetReader._observe_all))
ORIG = "earlier = any(t < ticket for t in self._in_flight)"
assert SRC.count(ORIG) == 1


def patch(new):
    ns = {}
    exec(compile(SRC.replace(ORIG, new), ow.__file__, "exec"), vars(ow), ns)
    ow.BudgetReader._observe_all = ns["_observe_all"]


for label, new in (("weakened (earlier = False)", "earlier = False"),
                   ("original", ORIG)):
    patch(new)
    try:
        t9.test_a_rollback_read_while_an_earlier_verification_holds_the_spend_never_redispatches()
        print(f"{label}: r9 control PASSES")
    except BaseException as e:  # noqa
        print(f"{label}: r9 control FAILS ({type(e).__name__}: {str(e)[:100]})")
