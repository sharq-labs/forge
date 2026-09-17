"""The words a routed uncertainty result is written in.

Three approximation classes, never merged; three claims; one closed list of reasons. A result that could
not say which class produced it, or why a route was refused, would be a number without a meaning.
"""

from __future__ import annotations

from enum import Enum

from ..uq.predictive import UQProblemError

#: The three sources every predictive record names. Model discrepancy is never estimated here: it is
#: named as not modelled, so a reader cannot mistake "no discrepancy term" for "no discrepancy".
PARAMETER_UNCERTAINTY = "PARAMETER_UNCERTAINTY"
MEASUREMENT_UNCERTAINTY = "MEASUREMENT_UNCERTAINTY"
MODEL_DISCREPANCY_NOT_MODELLED = "MODEL_DISCREPANCY_NOT_MODELLED"
UNCERTAINTY_SOURCES = (PARAMETER_UNCERTAINTY, MEASUREMENT_UNCERTAINTY, MODEL_DISCREPANCY_NOT_MODELLED)

#: The dimension the repaired V1 grid route was validated at (Battery B3 P4 and T5, p = 5). A grid of
#: more parameters is not routed, however it was built.
GRID_ROUTE_MAXIMUM_PARAMETERS = 5


class HybridUQError(UQProblemError):
    """A routed-UQ request that cannot be posed, or a V2 record that cannot be read."""


class RouteRefusedError(HybridUQError):
    """Numbers were asked of a route that refused. A refused route has none to give."""


class ApproximationClass(str, Enum):
    """Which approximation produced a number. No member is an exact posterior."""

    POSTERIOR_GRID = "POSTERIOR_GRID"
    LOCAL_GAUSSIAN_APPROXIMATION = "LOCAL_GAUSSIAN_APPROXIMATION"
    LINEARIZED_PREDICTIVE_UQ = "LINEARIZED_PREDICTIVE_UQ"

    @property
    def exact_posterior(self) -> bool:
        # A resolved grid is a discretization of the posterior on its support and the local route is a
        # Gaussian approximation of it. Neither is the continuous posterior, and no member may say so.
        return False

    @property
    def describes(self) -> str:
        return "predictions" if self is ApproximationClass.LINEARIZED_PREDICTIVE_UQ else "parameters"


class RouteClaim(str, Enum):
    """What a route is prepared to stand behind."""

    SUPPORTED = "SUPPORTED"
    DOWNGRADED = "DOWNGRADED"
    REFUSED = "REFUSED"


class RouteDecision(str, Enum):
    """Which route produced a :class:`HybridUQResult`."""

    GRID_AS_SUPPLIED = "GRID_AS_SUPPLIED"
    LOCAL_GAUSSIAN = "LOCAL_GAUSSIAN"
    GRID_REBUILT_FROM_LOCAL_COVARIANCE = "GRID_REBUILT_FROM_LOCAL_COVARIANCE"
    REFUSED = "REFUSED"


class RouteReason(str, Enum):
    """Every reason a route is refused, downgraded or passed over. See docs/CORE_V2_API_DESIGN.md section 4."""

    # local route: refusals
    CALIBRATION_NOT_CONVERGED = "CALIBRATION_NOT_CONVERGED"
    FORWARD_INADMISSIBLE_NEAR_ESTIMATE = "FORWARD_INADMISSIBLE_NEAR_ESTIMATE"
    NO_RESIDUAL_DEGREES_OF_FREEDOM = "NO_RESIDUAL_DEGREES_OF_FREEDOM"
    STRUCTURALLY_UNIDENTIFIABLE = "STRUCTURALLY_UNIDENTIFIABLE"
    NUMERICALLY_SINGULAR_JACOBIAN = "NUMERICALLY_SINGULAR_JACOBIAN"
    PARAMETER_AT_BOUND = "PARAMETER_AT_BOUND"
    NOT_STATIONARY = "NOT_STATIONARY"
    NOT_A_LOCAL_MINIMUM = "NOT_A_LOCAL_MINIMUM"
    NONLINEAR_BEYOND_LOCAL_GAUSSIAN = "NONLINEAR_BEYOND_LOCAL_GAUSSIAN"
    SECOND_MODE_FOUND = "SECOND_MODE_FOUND"
    BETTER_OPTIMUM_FOUND = "BETTER_OPTIMUM_FOUND"
    #: CORE-001: chi2_min is implausible under the declared noise (p < 0.01) AND exceeds four times its degrees of
    #: freedom, so the covariance understates the parameter uncertainty by more than a factor 2 however it is scaled.
    MODEL_MISFIT_BEYOND_DECLARED_NOISE = "MODEL_MISFIT_BEYOND_DECLARED_NOISE"
    #: CORE-003: the chi2 rise at 3 or 6 sd along a principal axis is below half the Gaussian's r^2.
    TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN = "TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN"
    # local route: downgrades
    BOUND_WITHIN_3_SD = "BOUND_WITHIN_3_SD"
    NONLINEAR_WITHIN_2_SD = "NONLINEAR_WITHIN_2_SD"
    NONLINEARITY_PROBE_INCOMPLETE = "NONLINEARITY_PROBE_INCOMPLETE"
    POORLY_SCALED_PARAMETERIZATION = "POORLY_SCALED_PARAMETERIZATION"
    GLOBAL_UNIQUENESS_NOT_ASSESSED = "GLOBAL_UNIQUENESS_NOT_ASSESSED"
    MULTISTART_INCOMPLETE = "MULTISTART_INCOMPLETE"
    PREDICTIVE_NONLINEAR = "PREDICTIVE_NONLINEAR"
    #: CORE-001: chi2_min is implausible under the declared noise (p < 0.01) with a variance ratio of at most 4.
    RESIDUALS_EXCEED_DECLARED_NOISE = "RESIDUALS_EXCEED_DECLARED_NOISE"
    #: CORE-003: the chi2 rise at 3 or 6 sd along a principal axis is below 0.9 of the Gaussian's r^2.
    TAIL_HEAVIER_WITHIN_6_SD = "TAIL_HEAVIER_WITHIN_6_SD"
    #: CORE-002/005: a grid predicted from without the observations and forward model that bind it to its evidence.
    GRID_NOT_BOUND_TO_EVIDENCE = "GRID_NOT_BOUND_TO_EVIDENCE"
    #: CORE-006: nothing shows where the prediction sits relative to what was calibrated.
    PREDICTION_DOMAIN_NOT_DECLARED = "PREDICTION_DOMAIN_NOT_DECLARED"
    #: CORE-006: a prediction condition lies outside the calibration's range of that condition.
    PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS = "PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS"
    # router: why a route was passed over
    GRID_NOT_SUPPLIED = "GRID_NOT_SUPPLIED"
    GRID_BEYOND_VALIDATED_DIMENSION = "GRID_BEYOND_VALIDATED_DIMENSION"
    GRID_UNRESOLVED = "GRID_UNRESOLVED"
    LOCAL_INPUTS_NOT_SUPPLIED = "LOCAL_INPUTS_NOT_SUPPLIED"
    GRID_REBUILD_OVER_BUDGET = "GRID_REBUILD_OVER_BUDGET"
    GRID_REBUILD_UNRESOLVED = "GRID_REBUILD_UNRESOLVED"
    #: CORE-002: posterior density reaches a face of a supplied grid within ln 1e6 of its peak.
    GRID_DOES_NOT_CONTAIN_POSTERIOR = "GRID_DOES_NOT_CONTAIN_POSTERIOR"
    #: CORE-002: on a rebuilt grid, the posterior reaches both declared bounds of an axis within ln 1e6 of its peak.
    GRID_POSTERIOR_BOUND_DOMINATED = "GRID_POSTERIOR_BOUND_DOMINATED"
    #: CORE-010: a supplied grid's axes are not evenly spaced in the declared inference coordinates, so its equal node
    #: mass is an undeclared prior.
    GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES = "GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES"
    #: R-06 (re-audit 2026-09-16): a uniqueness search found a mode outside a supplied grid's box, so the grid describes
    #: one mode of a posterior that has more than one. Appended, not inserted: the member order is frozen.
    GRID_MISSES_A_FOUND_MODE = "GRID_MISSES_A_FOUND_MODE"
    #: R-06 (re-audit 2026-09-16): nothing establishes that a supplied grid narrower than the declared bounds holds the
    #: whole posterior -- no adequate uniqueness search ran -- and a grid route has no DOWNGRADED claim to say so with.
    GRID_UNIQUENESS_NOT_ASSESSED = "GRID_UNIQUENESS_NOT_ASSESSED"
    #: R-20 (re-audit 2026-09-16): at one or two residual degrees of freedom the CORE-001 gate is more likely to miss a
    #: variance ratio of 4 than to catch it, so the declared noise model was not tested and found adequate -- it was
    #: essentially untestable. A downgrade: with a correct declared sigma the covariance is valid at any dof, and what
    #: is missing is the falsifier, not the premise. Appended, not inserted: the member order is frozen.
    GOODNESS_OF_FIT_UNDERPOWERED = "GOODNESS_OF_FIT_UNDERPOWERED"
    #: R-03 (re-audit 2026-09-16): the goodness of fit could not be tested WHERE THE INFORMATION IS, because the
    #: curvature at the point its chi-square minimum comes from could not be built. A grid claim is SUPPORTED or
    #: absent, so a grid whose fit cannot be tested that way is passed over rather than downgraded.
    GOODNESS_OF_FIT_NOT_MEASURABLE = "GOODNESS_OF_FIT_NOT_MEASURABLE"
    #: R-05 (re-audit 2026-09-16): a local maximum of the grid's node log-likelihood within ln 1e6 of the peak whose own
    #: curvature fails V1's aliasing bound, or about which no curvature can be fitted at all. The V1 resolution check
    #: fits ONE quadratic about the global argmax over a window of 50 nats or more, so a second mode in the box pollutes
    #: that fit and switches the aliasing check off. Appended, not inserted: the member order is frozen.
    GRID_MODE_UNRESOLVED = "GRID_MODE_UNRESOLVED"
    #: R-17 (re-audit 2026-09-16): the posterior is cut off INSIDE the grid's box by the forward model's admissible
    #: region -- an admissible node the posterior reaches has an inadmissible lattice neighbour. A declared-bound face
    #: is already refused on a supplied grid and refined across in a rebuild; this is the same hard edge, and growing
    #: the box cannot fix it, which is why it is not GRID_DOES_NOT_CONTAIN_POSTERIOR.
    GRID_CUT_BY_INADMISSIBILITY = "GRID_CUT_BY_INADMISSIBILITY"
    #: R-15 (re-audit 2026-09-16, I-08 part B): a declared bound stopped a 3 or 6 sd tail probe inside
    #: PROBE_SD, the radius the +/-2 sd probes already cover, so there was no tail left for it to measure and
    #: it was not used. A DOWNGRADE and a member of its own, not NONLINEARITY_PROBE_INCOMPLETE: along any of
    #: the fixed probe directions a tail probe is stopped that early only when that direction's own +/-2 sd
    #: probe was stopped too, so folding the two together made this fact unobservable -- two guard mutations
    #: removing the rule survived, which is what put this member here. Appended, not inserted: the member
    #: order is frozen.
    TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS = "TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS"

    @property
    def severity(self) -> RouteClaim:
        return RouteClaim.DOWNGRADED if self.value in _DOWNGRADES else RouteClaim.REFUSED


_DOWNGRADES = frozenset({
    "BOUND_WITHIN_3_SD", "NONLINEAR_WITHIN_2_SD", "NONLINEARITY_PROBE_INCOMPLETE", "POORLY_SCALED_PARAMETERIZATION",
    "GLOBAL_UNIQUENESS_NOT_ASSESSED", "MULTISTART_INCOMPLETE", "PREDICTIVE_NONLINEAR",
    "RESIDUALS_EXCEED_DECLARED_NOISE", "TAIL_HEAVIER_WITHIN_6_SD", "GRID_NOT_BOUND_TO_EVIDENCE",
    "PREDICTION_DOMAIN_NOT_DECLARED", "PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS",
    "GOODNESS_OF_FIT_UNDERPOWERED", "TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS",
})


def claim_for(reasons) -> RouteClaim:
    """The claim a set of reasons allows: any refusal refuses, any downgrade downgrades."""
    severities = {RouteReason(r).severity for r in reasons}
    if RouteClaim.REFUSED in severities:
        return RouteClaim.REFUSED
    if RouteClaim.DOWNGRADED in severities:
        return RouteClaim.DOWNGRADED
    return RouteClaim.SUPPORTED
