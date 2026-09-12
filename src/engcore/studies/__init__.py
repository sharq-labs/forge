"""Orchestration: the layer that composes inference, UQ and adequacy.

Where this sits, and why it is a new package rather than a new function in an
existing one
-------------------------------------------------------------------------------
The dependency direction the repository already had, and which this round
keeps::

    scientific/            primitives -- units, results, validation, twins
        ↓
    inference/             admission boundary, observations, split, grid
                           posterior, parameter identity, calibration result
        ↓
    uq/                    posterior-predictive uncertainty
        ↓
    adequacy/              held-out predictive scoring, evidence identity
        ↓
    studies/               THIS PACKAGE -- orchestration

Every arrow runs one way. ``inference`` imports nothing above it, which is why
:mod:`engcore.inference.calibration` takes a caller-supplied forward evaluator
instead of importing :mod:`engcore.execution`: the sweep belongs to whoever is
orchestrating, and pulling it down into a certified inference module to serve
one caller would invert the direction for the convenience of one workflow.

``adequacy`` was, and remains, imported by nothing below it. Wiring a workflow
through it from up here connects it without changing that: the arrow added
points DOWN from ``studies`` into ``adequacy``, never up.

Certified scope, stated so the placement is not mistaken for evasion
---------------------------------------------------------------------
``inference/`` and ``adequacy/`` are CORE_CERTIFIED; ``uq/`` and this package
are not. Nothing was put here *because* it is uncertified -- the parameter
identity, the split guard, the admission route and the calibration result all
went into certified ``inference/`` precisely because that is where they belong,
and each of them turned the certificate red. What lives here is orchestration,
which is the one thing that genuinely sits above all of it.
"""

from .tcr import (
    TCR_MODEL_REF,
    TcrTruth,
    build_tcr_parameter_set,
    ols_reference_estimate,
    synthesize_tcr_observations,
    tcr_forward_evaluator,
    tcr_forward_table,
    tcr_prediction,
)

__all__ = [
    "TCR_MODEL_REF",
    "TcrTruth",
    "build_tcr_parameter_set",
    "ols_reference_estimate",
    "synthesize_tcr_observations",
    "tcr_forward_evaluator",
    "tcr_forward_table",
    "tcr_prediction",
]
