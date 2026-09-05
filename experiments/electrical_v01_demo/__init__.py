"""Electrical V0.1 — the end-to-end demonstration.

Not an experiment and not a milestone. Everything here has already been built,
tested and frozen; the only thing this package adds is a single coherent run
that makes the whole path visible in one place:

    scientific question -> terminal decision -> Electrical model -> prior
      -> real ElectricalDCSolver -> predictive -> EVPI/EVSI -> CampaignRunner
      -> action selection -> real execution -> execution validity -> evidence
      -> critic -> Arbiter -> belief -> posterior -> certification requirement
      -> VALIDATE action if required -> model adequacy -> stop / certification

It is deliberately NOT three experiment reports stapled together. One campaign,
one belief store, one budget, one runner, two hidden worlds.

WHAT IS REUSED, UNMODIFIED
    E1   the divider, the terminal decision and loss, the solver-as-forward-map
    E2   posterior, predictive, EVPI/EVSI, the commitment ledger, the corrected
         joint adequacy rule, and both grader worlds
    E3   the shape of the obligation and its coverage rule
    V0.1 CertificationRequirement and the CampaignRunner routing it enables

    src/ is not touched. The demo owns only its own scenario constants and the
    wiring that any campaign has to write for itself.

WHAT THE DEMO IS FOR
    Making the existing system reproducible and legible. If reading this
    package feels like it is designing something, it has left its remit.
"""

from __future__ import annotations

DEMO_VERSION = "0.1.0"

#: The frozen commit this demo runs against.
BASE_COMMIT = "4ac821b8b3fbbc06fb784d9d66a7e12a5fe391cc"
