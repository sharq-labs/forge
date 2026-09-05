"""E3 — Adequacy evidence vs parameter EVSI.

E2 ended in a state that looks, from inside the decision theory, like success:
the conditional posterior is sharp, EVPI is at the floor, and every candidate
measurement has negative net value. E1's campaign loop would pause there with
NO_ACTION_WORTH_BUYING — *before* buying the measurements that revealed the
model family was wrong.

E3 asks whether a campaign can tell

    "nothing useful remains to learn about theta under this model"

apart from

    "the model itself has not yet earned scientific certification".

THE ONE THING E3 MUST NOT DO
----------------------------
It must not answer that question by inventing value. A measurement that cannot
sharpen the posterior genuinely HAS almost no expected information value about
theta, and saying otherwise would corrupt the only honest number in the system.
E3's whole premise is that such a measurement can still be *mandatory* — not
because it is worth buying, but because a preregistered scientific obligation
says the model may not be certified until it has been tested at conditions it
has never been tested at.

    A measurement may have almost zero value for estimating theta and still be
    mandatory evidence for deciding whether the model containing theta
    deserves certification. E3 does not fake the former to justify the latter.

So parameter EVSI is computed by E2's unmodified machinery and reported exactly
as it comes out, at the floor, for the adequacy probes too. What changes is not
the number but who is allowed to act on it.

THREE AXES, KEPT APART
----------------------
    EXECUTION VALIDITY  was the run computationally trustworthy?
    MODEL ADEQUACY      did the precommitted predictions survive?
    OBLIGATION STATUS   was the required scientific test actually performed?

The third is new in E3, and the one that is easiest to get wrong: an obligation
is satisfied by *performing* the test, not by passing it. A campaign that
obtained its required evidence and was refuted by it has discharged its
obligation completely and must still be denied certification.

Module roles, enforced by test:

    e3_config.py      decision path — preregistered constants and the
                      adequacy obligation specification (no truth value)
    e3_obligation.py  decision path — obligation ledger, probe selection rule,
                      the Arbiter-facing stopping-criterion evaluator, and the
                      certification gate
    e3_harness.py     grader+integration — CampaignHarness, executor, campaign
                      wiring, probe execution through the M1/M3 chain
    e3_run.py         orchestration, worlds, controls, injections, artifacts

E3 reuses E2 v1.1.0 wholesale for the science — solver, posterior, predictive,
EVPI/EVSI, the commitment ledger and the corrected joint adequacy rule — and
adds only the campaign-governance layer. E2's files are pinned by digest and
are not modified.
"""

from __future__ import annotations

#: Modules that participate in inference, prediction, obligation status and the
#: certification verdict. None may import a grader truth — E3's own or E2's —
#: and a test checks the import graph transitively through both packages.
DECISION_PATH_MODULES = ("e3_config", "e3_obligation")

#: Decision-path modules E3 inherits from E2. The AST test follows into these.
E2_DECISION_PATH_MODULES = ("e2_config", "e2_model", "e2_adequacy")

E3_VERSION = "1.0.0"
