"""Audit stream "hybrid": identifiability of the local route (HUQ-03, HUQ-14).

HUQ-03  the 95% width of a log-declared parameter was divided by its inference point ln(value / unit), so the
        same data gave NOT_IDENTIFIABLE declared in one unit and IDENTIFIABLE declared in its multiple;
HUQ-14  RoutedIdentifiability.digest left out ``why``, so two records with opposite explanations shared an identity.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np

import hybrid_synthetic as S
from engcore.hybrid_uq import MultistartPolicy, RouteDecision, assess_routed_identifiability, route_uncertainty

Q95 = 1.959963984540054


def _log_rate(scale):
    return S.Problem(f"log{scale:g}", lambda t, x, s=scale: (t[0] / s) * x, np.linspace(0.1, 1.0, 8), (1.0 * scale,), 0.02,
                     (1e-3 * scale,), (5.0 * scale,), (1.2 * scale,), transforms=("log",), seed=7)


def test_huq03_a_log_parameter_is_as_identifiable_in_one_unit_as_in_its_multiple():
    results = []
    for scale in (1.0, 1000.0, 1.0e-6):
        P = _log_rate(scale)
        routed = route_uncertainty(calibration=P.calibrate(), observations=P.observations, forward=P.forward,
                                   multistart=MultistartPolicy())
        assert routed.decision is RouteDecision.LOCAL_GAUSSIAN
        results.append(routed)
    statuses = {r.identifiability.status for r in results}
    assert len(statuses) == 1, statuses
    widths = [r.identifiability.report.relative_widths[0] for r in results]
    assert all(math.isclose(w, widths[0], rel_tol=1e-6) for w in widths), widths
    # the width is the natural-scale relative width of the log-normal interval: exp(z + q sd) / exp(z) - exp(z - q sd) / exp(z)
    sd = math.sqrt(results[0].covariance[0][0])
    assert math.isclose(widths[0], math.exp(Q95 * sd) - math.exp(-Q95 * sd), rel_tol=1e-9)


def test_huq14_the_explanation_is_part_of_the_identity():
    P = S.affine()
    routed = route_uncertainty(calibration=P.calibrate(), observations=P.observations, forward=P.forward,
                               multistart=MultistartPolicy())
    ident = routed.identifiability
    contradicted = dataclasses.replace(ident, report=dataclasses.replace(ident.report, why="NOT IDENTIFIABLE: do not use these"))
    assert contradicted.digest != ident.digest
    assert assess_routed_identifiability(routed.local_posterior).digest == ident.digest
