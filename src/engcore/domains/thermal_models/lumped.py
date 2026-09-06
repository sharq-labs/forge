"""Lumped first-order thermal capacity: model, realization, problem, solver.

MIN-FOUNDATION-ET. The thermal half of the minimum electro-thermal consumer.
One body, one temperature, one heat input, one ambient environment::

    C dT/dt = Q_in - hA (T - T_amb)

There is no field, no mesh, no topology and no spatial coordinate. That is
deliberate: `FIELD0` and `TOPO0` are deferred, and a lumped body is enough to
ask every question this milestone asks.

Why this is not in ``domains/thermal/``
--------------------------------------
That tree is byte-pinned by three frozen experiments (T1/T2/T3), which assert
both a digest map and set-equality over its ``*.py`` files, and no unfreeze
mechanism exists. This module sits beside it — the pattern already used by
``conduction1d_bulk.py`` and ``conduction1d_schemes.py``.

It is also a different science. The frozen `Conduction1DSolver` solves a
*dimensionless* normalized field with **no source term** and welded homogeneous
Dirichlet ends; it explicitly claims no absolute temperature scale and no
material property. Joule heat has nowhere to enter it. This model carries a
real temperature in kelvin and a real heat input in watts.

What is deliberately absent
---------------------------
No coupling scheme, no iteration, no relaxation, no rollback, no
synchronization and no knowledge of where ``heat_input`` comes from. The heat
input is declared as an **externally imposed control**, and any heat source
satisfies it — combustion, friction, a heater, or Joule dissipation. A thermal
model that *required* electrical dissipation would be electrical physics
wearing a thermal name.

What this solver's validation establishes
-----------------------------------------
``DIMENSIONALLY_VALID``    nothing here awards it yet. ``NEEDS.md`` §1.8b
                           records the ``metric_dimensions`` check that would.
``NUMERICALLY_CONVERGED``  **not earnable, by design.** There is no
                           discretization: no mesh, no step, no iteration, and
                           ``ConvergenceState.NOT_APPLICABLE`` on every solve.
                           See :mod:`lumped_reference` for why refining the
                           reference does not earn it either.
``ANALYTICALLY_VERIFIED``  earned per solve, by comparison against
                           :mod:`lumped_reference` — a reconstruction of the
                           solution from the equation's own coefficients that
                           shares no code and no derived quantity with the
                           closed form. Withheld as ``NOT_RUN`` when that
                           reference cannot be built inside its budget.
"""

from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from ...scientific.capabilities import ScientificCapability
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.conditions import InitialCondition
from ...scientific.ir.problem import ModelReference, ScientificProblem
from ...scientific.ir.variables import (
    ScientificParameter,
    ScientificVariable,
    VariableRole,
)
from ...scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    ModelValidationStatus,
    RangeCondition,
    ScientificModelDefinition,
    ValidityAssessment,
    ValidityDomain,
)
from ...scientific.models.registry import ModelRegistry
from ...scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ...scientific.realizations.registry import RealizationRegistry
from ...scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ...scientific.solvers.capability import (
    CoreCapabilities,
    SolverCapability,
    SolverCapabilityId,
)
from ...scientific.solvers.protocol import (
    ConvergenceState,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from ...scientific.units.quantity import Quantity
from ..derived_context import assembled_validity_context, caller_declared
from .context import (
    BIOT_NUMBER,
    BODY_CONDUCTIVITY,
    BODY_VOLUME,
    CAPACITY_EXCURSION_BOUND,
    CAPACITY_EXCURSION_RATIO,
    CHARACTERISTIC_LENGTH,
    CONDUCTANCE_EXCURSION_BOUND,
    CONDUCTANCE_EXCURSION_RATIO,
    CONDUCTIVITY_UNIT,
    DIMENSIONLESS,
    FORCED_CONVECTION,
    INTERNAL_FOURIER_NUMBER,
    LENGTH_UNIT,
    MELTING_TEMPERATURE,
    MELTING_TEMPERATURE_UTILIZATION,
    RADIATION_TO_CONVECTION_RATIO,
    SURFACE_AREA,
    SURFACE_AREA_UNIT,
    SURFACE_EMISSIVITY,
    VOLUME_UNIT,
    LumpedApplicabilityDeclaration,
    ASSEMBLED_QUANTITIES,
    derived_lumped_quantities,
)
from .lumped_reference import (
    REFERENCE_EXPRESSION,
    REFERENCE_ID,
    series_reference_temperature,
)

__all__ = [
    "AMBIENT_CONDUCTANCE",
    "AMBIENT_TEMPERATURE",
    "ANALYTIC_REFERENCE_CHECK",
    "BALANCE_RESIDUAL_CHECK",
    "CAPACITY_UNIT",
    "CONDUCTANCE_UNIT",
    "DURATION",
    "HEAT_CAPACITY",
    "HEAT_INPUT",
    "BODY_TEMPERATURE",
    "LUMPED_BIOT_LIMIT",
    "LUMPED_CAPACITY_TRANSIENT",
    "LUMPED_CAPACITY_MODEL",
    "LUMPED_CLOSED_FORM_REALIZATION",
    "LUMPED_MIN_FOURIER_NUMBER",
    "EXCURSION_BUDGET_LIMIT",
    "FORCED_CONVECTION",
    "PHASE_CHANGE_UTILIZATION_LIMIT",
    "POWER_UNIT",
    "RADIATION_NEGLIGIBILITY_LIMIT",
    "SOLVER_ROUNDING_ULPS",
    "STEADY_STATE_TEMPERATURE_METRIC",
    "TEMPERATURE",
    "TEMPERATURE_UNIT",
    "TEMPERATURE_METRIC",
    "TIME_CONSTANT_METRIC",
    "LumpedApplicabilityDeclaration",
    "ThermalBody",
    "LumpedThermalSolver",
    "assess_lumped_validity",
    "build_lumped_thermal_problem",
    "lumped_model_registry",
    "lumped_realizations",
    "lumped_solver_capabilities",
    "lumped_validity_context",
]

# --- units -------------------------------------------------------------------
TEMPERATURE_UNIT = "kelvin"
POWER_UNIT = "watt"
CAPACITY_UNIT = "joule/kelvin"
CONDUCTANCE_UNIT = "watt/kelvin"
TIME_UNIT = "second"

# --- quantity names ----------------------------------------------------------
# Names, not conventions: every one of these is enumerated by the problem
# record itself. Nothing anywhere parses their internal structure.
TEMPERATURE = "temperature"
HEAT_INPUT = "heat_input"
AMBIENT_TEMPERATURE = "ambient_temperature"
HEAT_CAPACITY = "heat_capacity"
AMBIENT_CONDUCTANCE = "ambient_conductance"
DURATION = "duration"

# Metric names are distinct from the declaration names above, and must stay
# distinct. ``temperature`` the STATE variable is the body's temperature at
# t0; ``final_temperature`` the metric is its temperature at t = duration.
# Both are kelvin, so a name shared between the two namespaces would let one
# endpoint denote two different time levels of the same physical quantity with
# nothing — not even a dimension check — able to notice. One name means one
# thing, across a problem's declarations and the metrics of results computed
# from it.
TEMPERATURE_METRIC = "final_temperature"
STEADY_STATE_TEMPERATURE_METRIC = "steady_state_temperature"
TIME_CONSTANT_METRIC = "time_constant"

MODEL_VERSION = "0.1.0"

# --- capabilities, declared here and nowhere else ----------------------------

#: What science this provides. A *scientific* capability: it answers "which
#: physical operation is available", not "which computational operation a
#: backend can execute".
#:
#: Deliberately ``thermal:body_temperature`` and **not**
#: ``thermal:lumped_body_temperature``. A consumer that needs a body's
#: temperature needs a temperature; whether it was produced by a lumped
#: balance or by a resolved field is a property of *this* realization, stated
#: in ``formulation`` and ``assumptions``, and compressing it into the
#: capability identity would make a spatial realization unable to satisfy the
#: same consumer. Capability identity is exact-string with no registry and no
#: subsumption, so granularity is a choice with no contract to guide it —
#: recorded as a known unknown rather than resolved here.
BODY_TEMPERATURE = ScientificCapability.parse("thermal:body_temperature")

#: What a backend must be able to do. A *solver* capability.
LUMPED_CAPACITY_TRANSIENT = SolverCapability(
    "thermal:lumped_capacity_transient",
    "Transient temperature of a lumped body with one ambient exchange path",
)


# --- applicability thresholds ------------------------------------------------
#
# Every number below is a named constant with a source, and every one of them
# is a *bound on a derived group*, never on a raw declared parameter. That is
# the difference between this domain's validity statement and the positivity
# checks it had before: "C > 0" says the declaration is well formed, "Bi <= 0.1"
# says the model is applicable to the body that was declared.

#: Bi <= 0.1. Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat and
#: Mass Transfer*, 6th ed. (Wiley, 2007), Sec. 5.1, Eq. 5.10: at this value the
#: temperature difference inside the body stays within roughly 10 % of the
#: difference between its surface and the ambient, and the text states the
#: error of the lumped method is then small. The number is the textbook
#: criterion, not a tuned tolerance.
LUMPED_BIOT_LIMIT = Quantity(0.1, DIMENSIONLESS)

#: Fo >= 0.2 — the one-term criterion, used for exactly what it establishes.
#:
#: Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007), Sec. 5.5.2: for
#: Fo > 0.2 the infinite series solution for a transient body with surface
#: convection is represented to within about 2 % by its first term. A
#: first-term-only response is a single exponential in time, which is the shape
#: a one-capacity model computes. So past this point the exact solution and the
#: lumped solution have the same shape, and the text puts the number on that.
#:
#: **What this condition therefore claims, and what it does not.** It claims
#: the horizon is long enough that the one-term criterion is met. It does *not*
#: claim that a shorter horizon makes the lumped model wrong. At small Bi the
#: higher modes are suppressed by amplitude as well as by decay — their
#: coefficients are O(Bi) — so a body at Bi = 1e-5 is very likely well
#: described at Fo well below 0.2. This domain does not certify that, and says
#: OUTSIDE_VALIDATED_DOMAIN rather than guessing: the status means *outside the
#: domain we have validated*, not *wrong*, and a conservative screen is the
#: honest use of it.
#:
#: An earlier revision of this constant claimed that below 0.2 "the body has
#: several time scales and no lumped description has the right shape, however
#: small Bi is". The final clause was an overclaim the source does not make and
#: the physics does not support; it is removed rather than re-cited.
LUMPED_MIN_FOURIER_NUMBER = Quantity(0.2, DIMENSIONLESS)

#: h_r / h <= 0.1. The linearized radiation coefficient of Incropera 6th ed.,
#: Eq. 1.9 acts in parallel with convection over the same surface, so this
#: ratio *is* the fractional error of the model's declared "no radiation"
#: assumption. The 10 % ceiling is the same neglected-mechanism convention the
#: text applies to the lumped criterion itself in Sec. 5.1; it is a convention,
#: and it is recorded as one.
RADIATION_NEGLIGIBILITY_LIMIT = Quantity(0.1, DIMENSIONLESS)

#: Ratio <= 1 for any budget the caller declared. Not a tolerance: the caller
#: states the span over which a property may be treated as constant, and the
#: condition asks whether the run stays inside the span the caller stated. The
#: bound is 1 because the ratio is defined as "fraction of the declared
#: budget consumed".
EXCURSION_BUDGET_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: T_peak / T_phase_change <= 1. A hard physical limit rather than a
#: convention: the balance C dT/dt = Q - hA (T - T_amb) has no latent-heat term
#: and no second phase, so above the phase-change temperature it is not
#: inaccurate, it is describing a body that no longer exists in the state the
#: model assumes. Incropera 6th ed., Sec. 5.1 states the formulation for a
#: single-phase solid.
PHASE_CHANGE_UTILIZATION_LIMIT = Quantity(1.0, DIMENSIONLESS)


_ASSUMPTIONS = (
    "lumped body: one uniform temperature, no internal spatial gradient",
    "Biot number small enough that internal conduction is not limiting",
    "constant heat capacity over the temperature range considered",
    "constant ambient conductance; one exchange path to one ambient",
    "no radiation, no phase change, no mass transport",
    "the heat input is externally imposed and its origin is not claimed here",
)


LUMPED_CAPACITY_MODEL = ScientificModelDefinition(
    model_id="thermal.lumped.first_order_capacity",
    version=MODEL_VERSION,
    name="Lumped first-order thermal capacity",
    domain="thermal",
    # FUNDAMENTAL_RELATION: an energy balance on a control volume. The lumped
    # assumption is an approximation of the *geometry*, declared in
    # `assumptions`; the balance itself is conservation.
    model_type=ModelType.FUNDAMENTAL_RELATION,
    description=(
        "Energy balance on a lumped body: C dT/dt = Q_in - hA (T - T_amb). "
        "One temperature, one imposed heat input, one ambient exchange path."
    ),
    inputs=(
        ModelInputSpec(
            name=HEAT_CAPACITY,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=CAPACITY_UNIT,
            description="Total heat capacity of the body; strictly positive.",
        ),
        ModelInputSpec(
            name=AMBIENT_CONDUCTANCE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=CONDUCTANCE_UNIT,
            description=(
                "Conductance to the ambient; strictly positive. Zero would be "
                "an adiabatic body, which has no steady state and is outside "
                "this model's declared validity."
            ),
        ),
        ModelInputSpec(
            name=DURATION,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TIME_UNIT,
            description="Length of the interval over which the state advances.",
        ),
        # The state coordinate. Declared as a VARIABLE with role STATE, which
        # is what makes "this quantity evolves during the solve" a typed fact
        # rather than a naming habit.
        ModelInputSpec(
            name=TEMPERATURE,
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar=TEMPERATURE_UNIT,
            role=VariableRole.STATE,
            description="Body temperature; the evolving state.",
        ),
        # Imposed from outside the thermal problem. CONTROL says exactly that
        # and says nothing about the supplier — which is correct, because any
        # heat source satisfies this model.
        ModelInputSpec(
            name=HEAT_INPUT,
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar=POWER_UNIT,
            role=VariableRole.CONTROL,
            description=(
                "Heat delivered to the body, imposed externally. Its origin "
                "is not part of this model's claim."
            ),
        ),
        ModelInputSpec(
            name=AMBIENT_TEMPERATURE,
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar=TEMPERATURE_UNIT,
            role=VariableRole.CONTROL,
            description="Temperature of the ambient the body exchanges with.",
        ),
        # ---- optional applicability declarations ------------------------
        #
        # None of these enters the balance. Every one of them exists so that a
        # condition below can be *evaluated* instead of answered UNKNOWN, and
        # every one is `required=False` so that a problem which omits it still
        # binds cleanly. Declaring them here rather than leaving them as an
        # undocumented calling convention is what makes "which declaration
        # unlocks which condition" recoverable from the model record alone.
        ModelInputSpec(
            name=CHARACTERISTIC_LENGTH,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=LENGTH_UNIT,
            required=False,
            description=(
                "L_c for the Biot number. Supply it directly when the body's "
                "conduction path is known — a slab cooled on one face has "
                "L_c equal to its thickness — or supply body_volume and "
                "surface_area and let L_c = V/A_s be derived."
            ),
        ),
        ModelInputSpec(
            name=BODY_VOLUME,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=VOLUME_UNIT,
            required=False,
            description="Volume of the body; with surface_area gives L_c = V/A_s.",
        ),
        ModelInputSpec(
            name=SURFACE_AREA,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=SURFACE_AREA_UNIT,
            required=False,
            description=(
                "Area over which the body exchanges with the ambient. The "
                "balance declares only the product hA, so without the area no "
                "coefficient h exists and every condition needing one stays "
                "UNKNOWN."
            ),
        ),
        ModelInputSpec(
            name=BODY_CONDUCTIVITY,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=CONDUCTIVITY_UNIT,
            required=False,
            description=(
                "Conductivity of the body itself, not of the surrounding "
                "fluid. Required for the Biot number."
            ),
        ),
        ModelInputSpec(
            name=SURFACE_EMISSIVITY,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=DIMENSIONLESS,
            required=False,
            description=(
                "Total hemispherical emissivity of the surface, in [0, 1]. "
                "Makes the declared no-radiation assumption falsifiable."
            ),
        ),
        # ``convection_regime`` is deliberately NOT declared here, and for a
        # better reason than it once was. It is not an input to any condition:
        # no derivation reads it, so it cannot decide a verdict, so it is not
        # a model input. It lives on ``LumpedApplicabilityDeclaration`` as
        # recorded intent — why the caller thinks their declared span is
        # credible — and travels with that record.
        #
        # The original reason it was excluded still holds and is why it must
        # never become an input: it is a category, ``ProvenanceRecord`` admits
        # only Quantity-valued inputs, and the electrothermal pack builds a
        # thermal result's provenance from ``problem.parameter_values()``
        # wholesale. Anything that decides a verdict here must be a Quantity,
        # or the verdict rests on something provenance cannot record.
        ModelInputSpec(
            name=CONDUCTANCE_EXCURSION_BOUND,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            required=False,
            description=(
                "Surface-to-ambient difference over which the caller declares "
                "hA may be treated as constant."
            ),
        ),
        ModelInputSpec(
            name=CAPACITY_EXCURSION_BOUND,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            required=False,
            description=(
                "Body-temperature span over which the caller declares the "
                "total capacity C may be treated as constant."
            ),
        ),
        ModelInputSpec(
            name=MELTING_TEMPERATURE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            required=False,
            description=(
                "Melting or other phase-change temperature of the body, as an "
                "absolute temperature."
            ),
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric=TEMPERATURE_METRIC,
            unit_exemplar=TEMPERATURE_UNIT,
            description=(
                "Body temperature at the end of the interval. Named "
                "distinctly from the `temperature` state variable, which is "
                "its value at the start."
            ),
        ),
        ModelOutputSpec(
            metric=STEADY_STATE_TEMPERATURE_METRIC,
            unit_exemplar=TEMPERATURE_UNIT,
            description=(
                "T_amb + Q_in/hA — the temperature approached as t grows, for "
                "a constant heat input."
            ),
        ),
        ModelOutputSpec(
            metric=TIME_CONSTANT_METRIC,
            unit_exemplar=TIME_UNIT,
            description="C/hA — the first-order time constant.",
        ),
    ),
    assumptions=_ASSUMPTIONS,
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name=HEAT_CAPACITY,
                minimum=Quantity(0.0, CAPACITY_UNIT),
                minimum_inclusive=False,
                description="Strictly positive; zero capacity has no dynamics.",
            ),
            RangeCondition(
                name=AMBIENT_CONDUCTANCE,
                minimum=Quantity(0.0, CONDUCTANCE_UNIT),
                minimum_inclusive=False,
                description=(
                    "Strictly positive; an adiabatic body has no steady state "
                    "and no finite time constant."
                ),
            ),
            # ---- applicability of the lumped approximation itself --------
            #
            # The two conditions above say the declaration is well formed. The
            # six below say whether the model applies to what was declared,
            # and each is a bound on a group derived in `context.py` rather
            # than on any number the caller wrote down. Every one of them is
            # UNKNOWN until the caller supplies the geometry or the property
            # bound it needs: none can be satisfied by leaving something out.
            RangeCondition(
                name=BIOT_NUMBER,
                maximum=LUMPED_BIOT_LIMIT,
                description=(
                    "Bi = h L_c / k <= 0.1. Bi compares the temperature drop "
                    "inside the body with the drop across its surface film; "
                    "this model asserts the internal drop is zero, so Bi is "
                    "the direct measure of how wrong that assertion is. "
                    "Incropera, DeWitt, Bergman & Lavine, Fundamentals of "
                    "Heat and Mass Transfer, 6th ed. (2007), Sec. 5.1, "
                    "Eq. 5.10. UNKNOWN unless surface_area, "
                    "body_conductivity and a characteristic length (declared, "
                    "or derived from body_volume/surface_area) are supplied."
                ),
            ),
            RangeCondition(
                name=INTERNAL_FOURIER_NUMBER,
                minimum=LUMPED_MIN_FOURIER_NUMBER,
                description=(
                    "Fo = (t/tau)/Bi >= 0.2: the horizon is long enough that "
                    "the exact series solution for this body is within about "
                    "2 % of its first term alone. A first-term-only response "
                    "is a single exponential in time, which is the shape a "
                    "one-capacity model computes, so past this point the two "
                    "agree in form. Incropera et al., 6th ed. (2007), "
                    "Sec. 5.5.2 (one-term approximation), with the identity "
                    "Bi*Fo = t/tau of Sec. 5.2, Eq. 5.12. A conservative "
                    "screen: below 0.2 the lumped model is not shown to be "
                    "wrong, it is outside what this criterion validates — at "
                    "small Bi the higher modes are suppressed by amplitude "
                    "too, and a shorter horizon may well be adequate."
                ),
            ),
            RangeCondition(
                name=CONDUCTANCE_EXCURSION_RATIO,
                maximum=EXCURSION_BUDGET_LIMIT,
                description=(
                    "Fraction of the caller's declared constant-hA budget "
                    "that the run consumes: max|T - T_amb| over the declared "
                    "bound. Under free convection the coefficient follows the "
                    "driving difference, h ~ dT^(1/4) for a laminar external "
                    "layer (Incropera et al., 6th ed., Sec. 9.2), so a "
                    "constant hA holds only over a stated span. UNKNOWN "
                    "unless conductance_excursion_bound is supplied and the "
                    "operating point is known. Declaring a forced-convection "
                    "regime does not substitute for either: it explains why a "
                    "wide span may be credible, and is not itself evidence "
                    "that the span was respected."
                ),
            ),
            RangeCondition(
                name=CAPACITY_EXCURSION_RATIO,
                maximum=EXCURSION_BUDGET_LIMIT,
                description=(
                    "Fraction of the caller's declared constant-C budget that "
                    "the run consumes: |T_ss - T_0| over the declared bound. "
                    "C = rho V c_p and the specific heat of a real solid "
                    "rises over engineering ranges, which is why Incropera "
                    "et al., 6th ed., Table A.1 tabulates c_p at several "
                    "temperatures rather than once. UNKNOWN unless "
                    "capacity_excursion_bound is supplied. Distinct from the "
                    "hA budget: this one is about the body, that one about "
                    "its surface."
                ),
            ),
            RangeCondition(
                name=RADIATION_TO_CONVECTION_RATIO,
                maximum=RADIATION_NEGLIGIBILITY_LIMIT,
                description=(
                    "h_r / h <= 0.1, with h_r = eps sigma (T_s + T_sur)"
                    "(T_s^2 + T_sur^2) evaluated at the hottest surface "
                    "temperature the run reaches. Radiation and convection act "
                    "in parallel over the same surface, so this ratio is the "
                    "fractional error of the declared no-radiation "
                    "assumption. Incropera et al., 6th ed. (2007), Sec. 1.2.3, "
                    "Eq. 1.9. UNKNOWN unless surface_emissivity and "
                    "surface_area are supplied."
                ),
            ),
            RangeCondition(
                name=MELTING_TEMPERATURE_UTILIZATION,
                maximum=PHASE_CHANGE_UTILIZATION_LIMIT,
                description=(
                    "max(T_0, T_ss) / T_phase_change <= 1. A hard limit, not "
                    "a tolerance: this balance carries no latent-heat term, so "
                    "at a phase change it is not inaccurate but describing "
                    "something that is not there. The trajectory is monotone "
                    "between its endpoints, so the endpoint maximum bounds it "
                    "exactly. Incropera et al., 6th ed., Sec. 5.1 (lumped "
                    "formulation for a single-phase solid). UNKNOWN unless "
                    "melting_temperature is supplied."
                ),
            ),
        ),
        description=(
            "Linear lumped exchange with a single ambient, applicable while "
            "the body is internally isothermal (Bi), has settled into a "
            "single-exponential response (Fo), stays inside the property "
            "spans the caller declared, loses a negligible share of its "
            "surface exchange to radiation, and does not change phase."
        ),
    ),
    required_capabilities=frozenset({LUMPED_CAPACITY_TRANSIENT.name}),
    # SELF_CONSISTENT: the closed form is checked against the differential
    # balance it solves. Nothing physical was measured.
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
)


LUMPED_CLOSED_FORM_REALIZATION = ModelRealizationDefinition(
    realization_id="thermal.lumped.first_order_capacity.closed_form",
    version="0.1.0",
    model=ModelReference(
        LUMPED_CAPACITY_MODEL.model_id, LUMPED_CAPACITY_MODEL.version
    ),
    # The *model* poses an ODE. That is what `formulation` records — the
    # mathematical form of the claim, not how it happens to be discharged.
    formulation=ModelFormulation.ODE,
    name="Exact integration for a piecewise-constant heat input",
    description=(
        "Integrates the linear first-order balance in closed form over one "
        "interval of constant heat input: "
        "T(t) = T_ss + (T0 - T_ss) exp(-t/tau)."
    ),
    provided_capabilities=frozenset({BODY_TEMPERATURE}),
    # An ODE realization that needs no ODE integrator. This is exactly the
    # separation MODEL0-R evidenced: the formulation is a property of the
    # claim, the required solver capability is a property of the computation,
    # and they are allowed to disagree.
    required_solver_capabilities=frozenset(
        {
            SolverCapabilityId.coerce(LUMPED_CAPACITY_TRANSIENT),
            SolverCapabilityId.coerce(CoreCapabilities.ALGEBRAIC),
        }
    ),
    assumptions=(
        "the heat input is constant over the integrated interval",
        "exact for the linear balance; no time-discretization error",
        "no linear system is solved; the update is a scalar exponential",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.thermal_models.lumped",
        version="0.1.0",
        reference="closed-form first-order step; see module docstring",
    ),
)


def lumped_model_registry() -> ModelRegistry:
    """A fresh registry. No global singleton exists."""
    return ModelRegistry((LUMPED_CAPACITY_MODEL,))


def lumped_realizations() -> RealizationRegistry:
    """A fresh registry. No global singleton exists."""
    return RealizationRegistry((LUMPED_CLOSED_FORM_REALIZATION,))


def lumped_solver_capabilities() -> frozenset[SolverCapability]:
    return frozenset({LUMPED_CAPACITY_TRANSIENT, CoreCapabilities.ALGEBRAIC})


# =====================================================================
# Declaration
# =====================================================================

def _positive(value: Any, unit: str, label: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(
            f"{label} must be a Quantity carrying {unit!r}, got "
            f"{type(value).__name__} — a bare number is not a declaration"
        )
    magnitude = value.magnitude_in(unit)
    if not math.isfinite(magnitude) or magnitude <= 0.0:
        raise InvalidScientificProblem(
            f"{label} must be finite and strictly positive, got {magnitude!r} "
            f"{unit}"
        )
    return value


@dataclass(frozen=True)
class ThermalBody:
    """One declared lumped body, with its ambient and its initial state.

    The declaration carries the numbers. It carries no solver, no scheme, no
    tolerance and no coupling: those are execution properties, and a body that
    named one would have made changing an integrator into a change of physical
    identity.

    **Not everything on this record is part of the body's identity.**
    ``heat_capacity`` and ``ambient_conductance`` are what the body *is*;
    ``ambient_temperature`` is a declared ``CONTROL``, ``initial_temperature``
    is a state at one instant, and ``duration`` is an integration window. Those
    three are an operating point, not a system, and :attr:`physical_key` is the
    part that identity is taken over — the same split the frozen
    ``ConductionSlab.fingerprint`` makes when it excludes the discretization.

    They stay on this record because a caller declaring a run needs them in one
    place. What must not follow is that changing one makes it a different body.

    ``applicability`` is optional and defaults to an empty declaration, which
    is the honest starting point: a body about which nothing beyond C and hA
    was said supports no applicability verdict except UNKNOWN. It is
    deliberately **not** part of :attr:`physical_key`, for the same reason the
    ambient is not — declaring a conductivity does not make it a different
    body, it makes it the same body known to greater depth.
    """

    body_id: str
    heat_capacity: Quantity
    ambient_conductance: Quantity
    ambient_temperature: Quantity
    initial_temperature: Quantity
    duration: Quantity
    applicability: LumpedApplicabilityDeclaration = field(
        default_factory=LumpedApplicabilityDeclaration
    )

    def __post_init__(self) -> None:
        body_id = str(self.body_id).strip()
        if not body_id:
            raise InvalidScientificProblem("thermal body requires a body_id")
        object.__setattr__(self, "body_id", body_id)
        if not isinstance(self.applicability, LumpedApplicabilityDeclaration):
            raise InvalidScientificProblem(
                f"applicability must be a LumpedApplicabilityDeclaration, got "
                f"{type(self.applicability).__name__}"
            )
        _positive(self.heat_capacity, CAPACITY_UNIT, "heat_capacity")
        _positive(self.ambient_conductance, CONDUCTANCE_UNIT, "ambient_conductance")
        _positive(self.duration, TIME_UNIT, "duration")
        _positive(self.ambient_temperature, TEMPERATURE_UNIT, "ambient_temperature")
        _positive(self.initial_temperature, TEMPERATURE_UNIT, "initial_temperature")

    @property
    def physical_key(self) -> tuple[str, float, float]:
        """What makes this *this body*: its id and its two thermal properties.

        The ambient, the initial state and the integration window are excluded
        deliberately. Including them would mean the same physical body at a
        second ambient, or over a second interval, was a second system — the
        configuration/state conflation this milestone was built to examine, and
        it would be dishonest to measure it in a sibling domain while
        committing it here.
        """
        return (
            self.body_id,
            self.heat_capacity.magnitude_in(CAPACITY_UNIT),
            self.ambient_conductance.magnitude_in(CONDUCTANCE_UNIT),
        )

    @property
    def capacity_j_per_k(self) -> float:
        return self.heat_capacity.magnitude_in(CAPACITY_UNIT)

    @property
    def conductance_w_per_k(self) -> float:
        return self.ambient_conductance.magnitude_in(CONDUCTANCE_UNIT)

    @property
    def ambient_k(self) -> float:
        return self.ambient_temperature.magnitude_in(TEMPERATURE_UNIT)

    @property
    def initial_k(self) -> float:
        return self.initial_temperature.magnitude_in(TEMPERATURE_UNIT)

    @property
    def duration_s(self) -> float:
        return self.duration.magnitude_in(TIME_UNIT)

    @property
    def time_constant_s(self) -> float:
        """C/hA. Strictly positive by construction."""
        return self.capacity_j_per_k / self.conductance_w_per_k


def _applicability_parameters(
    declaration: LumpedApplicabilityDeclaration,
) -> tuple[ScientificParameter, ...]:
    """The declared applicability facts as problem parameters, in fixed order.

    A field left as ``None`` produces **no parameter**. That is the mechanism
    by which "not declared" survives all the way to ``ValidityDomain.assess``
    as UNKNOWN: there is no placeholder value anywhere on this path, so no
    condition can be satisfied by an omission.

    Order is fixed rather than derived from a dict, so the same declaration
    always yields the same parameter sequence and two problems built from
    equal declarations serialize identically.
    """
    quantities: tuple[tuple[str, Quantity | None, str], ...] = (
        (
            CHARACTERISTIC_LENGTH,
            declaration.characteristic_length,
            "Characteristic length L_c for the Biot number.",
        ),
        (BODY_VOLUME, declaration.volume, "Volume of the body."),
        (
            SURFACE_AREA,
            declaration.surface_area,
            "Area over which the body exchanges with the ambient.",
        ),
        (
            BODY_CONDUCTIVITY,
            declaration.body_conductivity,
            "Conductivity of the body itself.",
        ),
        (
            SURFACE_EMISSIVITY,
            declaration.surface_emissivity,
            "Total hemispherical emissivity of the surface.",
        ),
        (
            CONDUCTANCE_EXCURSION_BOUND,
            declaration.conductance_excursion_bound,
            "Span over which hA is declared constant.",
        ),
        (
            CAPACITY_EXCURSION_BOUND,
            declaration.capacity_excursion_bound,
            "Span over which C is declared constant.",
        ),
        (
            MELTING_TEMPERATURE,
            declaration.melting_temperature,
            "Phase-change temperature of the body.",
        ),
    )
    return tuple(
        ScientificParameter(name=name, value=value, description=description)
        for name, value, description in quantities
        if value is not None
    )


def build_lumped_thermal_problem(
    body: ThermalBody,
    *,
    problem_id: str | None = None,
) -> ScientificProblem:
    """The universal problem statement for one lumped body.

    ``heat_input`` and ``ambient_temperature`` are declared as **variables with
    role CONTROL** rather than as parameters. A parameter is a configured value
    of the problem; these are imposed from outside it. The distinction is the
    one the electrical domain does not make for a resistance, and recording it
    honestly here is the point.

    Whatever the body's ``applicability`` declaration carries is emitted as
    extra parameters, and whatever it leaves out is emitted as nothing at all.
    The problem therefore transports exactly the evidence it was given: a
    problem serialized, sent elsewhere and rebuilt still supports the same
    applicability verdict, and one built from a bare body still supports only
    UNKNOWN.
    """
    return ScientificProblem(
        problem_id=problem_id or f"thermal-lumped-{body.body_id}",
        name=f"Lumped thermal body {body.body_id}",
        description=(
            "Transient temperature of one lumped body over a single interval "
            "of imposed heat input."
        ),
        variables=(
            ScientificVariable(
                name=TEMPERATURE,
                unit=TEMPERATURE_UNIT,
                role=VariableRole.STATE,
                description="Body temperature; evolves over the interval.",
            ),
            ScientificVariable(
                name=HEAT_INPUT,
                unit=POWER_UNIT,
                role=VariableRole.CONTROL,
                description="Externally imposed heat delivered to the body.",
            ),
            ScientificVariable(
                name=AMBIENT_TEMPERATURE,
                unit=TEMPERATURE_UNIT,
                role=VariableRole.CONTROL,
                description="Externally imposed ambient temperature.",
            ),
        ),
        parameters=(
            ScientificParameter(
                name=HEAT_CAPACITY,
                value=body.heat_capacity,
                description="Total heat capacity of the body.",
            ),
            ScientificParameter(
                name=AMBIENT_CONDUCTANCE,
                value=body.ambient_conductance,
                description="Conductance from the body to the ambient.",
            ),
            ScientificParameter(
                name=DURATION,
                value=body.duration,
                description="Length of the interval to advance.",
            ),
        )
        + _applicability_parameters(body.applicability),
        initial_conditions=(
            InitialCondition(
                variable=TEMPERATURE,
                value=body.initial_temperature,
                description="Body temperature at the start of the interval.",
            ),
        ),
        models=(
            ModelReference(
                LUMPED_CAPACITY_MODEL.model_id, LUMPED_CAPACITY_MODEL.version
            ),
        ),
        required_capabilities=frozenset({LUMPED_CAPACITY_TRANSIENT.name}),
    )


def lumped_validity_context(
    problem: ScientificProblem,
    *,
    initial_temperature: Quantity | None = None,
    ambient_temperature: Quantity | None = None,
    heat_input: Quantity | None = None,
) -> dict[str, Any]:
    """The full context :meth:`ValidityDomain.assess` consumes for this model.

    The problem's own parameters, plus the dimensionless groups
    ``context.derived_lumped_quantities`` could form from them and from the
    supplied state. The three keyword arguments are variables — a body
    temperature, an ambient and a heat input — and
    :meth:`ScientificProblem.validity_context` is built from *parameters*, so
    they cannot arrive any other way. That limitation is the electrical
    domain's too, is recorded there as a finding, and is not worked around
    here either.

    Every one of the three is a ``Quantity``, so everything this function feeds
    into a verdict is something ``ProvenanceRecord`` can record. No categorical
    declaration reaches a condition.

    Omitting an argument omits every group that needed it. It never
    substitutes one — and since F03 that is a structural property rather than
    an intention. The derived names are a **reserved namespace**: they are
    stripped from the caller's context before anything is derived, so a caller
    parameter called ``biot_number`` cannot occupy the key a failed Biot
    derivation left empty. Assembly used to start from the caller's parameters
    and overwrite only what it derived, which meant the opposite.
    """
    declared = caller_declared(problem.validity_context(), ASSEMBLED_QUANTITIES)
    return assembled_validity_context(
        declared=declared,
        assembled=derived_lumped_quantities(
            declared,
            initial_temperature=initial_temperature,
            ambient_temperature=ambient_temperature,
            heat_input=heat_input,
        ),
        reserved=ASSEMBLED_QUANTITIES,
    )


def assess_lumped_validity(
    problem: ScientificProblem,
    *,
    initial_temperature: Quantity | None = None,
    ambient_temperature: Quantity | None = None,
    heat_input: Quantity | None = None,
) -> ValidityAssessment:
    """Is the lumped model applicable to this problem at this operating point?

    **Validity, not validation** — the same separation the sibling electrical
    domain keeps with ``assess_resistance_validity``, and for the same reason:
    *was this model applicable* and *was this result checked* are different
    questions with different answers, and the platform holds them on different
    fields so that neither can quietly stand in for the other. A converged
    solve of an inapplicable model is still a converged solve, and this
    function is what makes the second half of that sentence sayable.

    Every argument is a measured or declared ``Quantity``. There is no
    parameter here through which a caller can assert their way to IN_DOMAIN.
    """
    return LUMPED_CAPACITY_MODEL.assess_validity(
        lumped_validity_context(
            problem,
            initial_temperature=initial_temperature,
            ambient_temperature=ambient_temperature,
            heat_input=heat_input,
        )
    )


# =====================================================================
# Solver
# =====================================================================

SOLVER_ID = "engcore.thermal.lumped_closed_form"
SOLVER_VERSION = "0.1.0"
BACKEND = "python.math.exp"

#: The two checks this solver emits, named once so a reader grepping for
#: either finds the constant rather than a string literal in three places.
BALANCE_RESIDUAL_CHECK = "lumped_balance_residual"
ANALYTIC_REFERENCE_CHECK = "analytic_reference_agreement"

#: The comparison tolerance against the independent reference, expressed in
#: units in the last place of the largest intermediate the closed form forms.
#:
#: WHY THIS IS A ROUND-OFF BUDGET AND NOT AN ENGINEERING TOLERANCE. The two
#: routes compute the same real number — one by the exponential ansatz, one by
#: the series recurrence — so every digit of disagreement above floating-point
#: noise is a defect in one of them. There is no discretization error to leave
#: room for on either side: the solver has no discretization, and the
#: reference's own error is bounded and added to this budget separately. A
#: tolerance chosen at an engineering level, say 1e-6 K, would pass a closed
#: form with a genuinely wrong fifteenth digit and — worse — would keep passing
#: one with a wrong sixth, so it would not be measuring what it claims to.
#:
#: WHY 128 AND NOT 1. The solver's evaluation is five floating-point
#: operations around one ``math.exp``. ``exp`` is faithfully rounded on
#: mainstream libms but is not required to be correctly rounded and differs in
#: the last place between platforms, and ``(T0 - T_ss)`` cancels, so the error
#: in the result scales with the largest intermediate rather than with the
#: result. 128 ulps of that intermediate is roughly 1e-11 K on a body near
#: 340 K: seven orders of magnitude tighter than the smallest physically
#: meaningful temperature difference, and wide enough that the check does not
#: become a report of which libm the run used.
SOLVER_ROUNDING_ULPS = 128


@dataclass(frozen=True)
class PreparedLumpedStep:
    """The body, the imposed inputs and the interval this step will advance."""

    body: ThermalBody
    realization: ModelRealizationDefinition
    heat_input_w: float


class LumpedThermalSolver:
    """Advances one lumped body over one interval. Satisfies ScientificSolver.

    The body and its imposed heat input are bound to this instance by problem
    id, exactly as the electrical domain binds a circuit. The binding table is
    instance-local state, never a global registry.
    """

    def __init__(self, settings: SolverSettings | None = None) -> None:
        self._bound: dict[str, tuple[ThermalBody, float]] = {}
        self.settings = settings or SolverSettings()

    # -- identity ---------------------------------------------------------
    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND)

    @property
    def capabilities(self) -> frozenset[SolverCapability]:
        return lumped_solver_capabilities()

    # -- binding ----------------------------------------------------------
    def bind_body(
        self, body: ThermalBody, problem_id: str, *, heat_input: Quantity
    ) -> None:
        """Associate a body and its imposed heat input with a problem id.

        Rebinding is idempotent for the same *physical* body and refused for a
        different one, keyed on :attr:`ThermalBody.physical_key`. So the same
        body at a second ambient, over a second interval, or under a second
        heat input rebinds freely — those are operating points — while swapping
        the body itself is refused, because that would let two results claim one
        identity while describing different systems.
        """
        if not isinstance(body, ThermalBody):
            raise InvalidScientificProblem("bind_body expects a ThermalBody")
        watts = heat_input.magnitude_in(POWER_UNIT)
        if not math.isfinite(watts):
            raise InvalidScientificProblem("heat input must be finite")
        key = str(problem_id)
        existing = self._bound.get(key)
        if existing is not None and existing[0].physical_key != body.physical_key:
            raise InvalidScientificProblem(
                f"problem {key!r} is already bound to a different body; "
                f"silently swapping the body behind a problem id would let "
                f"two results claim one identity while describing different "
                f"systems"
            )
        self._bound[key] = (body, watts)

    @staticmethod
    def verify_problem_matches_body(
        problem: ScientificProblem, body: ThermalBody
    ) -> None:
        """Refuse a problem that describes a different body than the one bound.

        The sibling Electrical DC domain guards exactly this with
        ``verify_problem_matches_circuit``, on the grounds that a result whose
        provenance contradicts the system that produced it is worse than no
        result. Without the guard, ``build_lumped_thermal_problem(bodyA, ...)``
        followed by ``bind_body(bodyB, ...)`` would yield a result attributed to
        a problem describing something else, with provenance mixing the two.
        """
        for name, declared in (
            (HEAT_CAPACITY, body.heat_capacity),
            (AMBIENT_CONDUCTANCE, body.ambient_conductance),
            (DURATION, body.duration),
        ):
            stated = problem.parameter(name).value
            if not isinstance(stated, Quantity) or stated.compare(declared) != 0.0:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} states {name} = {stated} "
                    f"but the bound body declares {declared}"
                )
        # The applicability declaration is checked on the same terms. A problem
        # claiming a conductivity the bound body does not have would produce a
        # validity verdict attributed to a body that never had the evidence
        # behind it — the same provenance failure the three checks above
        # refuse, one level further out. Parameters the problem does not carry
        # are not an error: the declaration is optional and a body may simply
        # have been declared with less.
        declared_names = {p.name for p in problem.parameters}
        for parameter in _applicability_parameters(body.applicability):
            if parameter.name not in declared_names:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} omits {parameter.name}, "
                    f"which the bound body declares"
                )
            stated = problem.parameter(parameter.name).value
            if stated != parameter.value:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} states "
                    f"{parameter.name} = {stated} but the bound body declares "
                    f"{parameter.value}"
                )
        initial = problem.initial_conditions
        if len(initial) != 1 or initial[0].variable != TEMPERATURE:
            raise InvalidScientificProblem(
                f"problem {problem.problem_id!r} must carry exactly one "
                f"initial condition, on {TEMPERATURE!r}"
            )
        if initial[0].value.compare(body.initial_temperature) != 0.0:
            raise InvalidScientificProblem(
                f"problem {problem.problem_id!r} starts at {initial[0].value} "
                f"but the bound body declares {body.initial_temperature}"
            )

    def supports(self, problem: ScientificProblem) -> bool:
        return LUMPED_CAPACITY_TRANSIENT.name in problem.required_capabilities

    # -- lifecycle --------------------------------------------------------
    def prepare(
        self,
        problem: ScientificProblem,
        *,
        realization: ModelRealizationDefinition = LUMPED_CLOSED_FORM_REALIZATION,
    ) -> PreparedSolve:
        bound = self._bound.get(problem.problem_id)
        if bound is None:
            raise InvalidScientificProblem(
                f"no thermal body is bound to problem "
                f"{problem.problem_id!r}; call bind_body first"
            )
        body, watts = bound
        # Refuse an inconsistent pairing before solving, not after attributing.
        self.verify_problem_matches_body(problem, body)
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=self.settings,
            payload=PreparedLumpedStep(
                body=body, realization=realization, heat_input_w=watts
            ),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        step: PreparedLumpedStep = prepared.payload
        body = step.body
        started = time.perf_counter()

        tau = body.time_constant_s
        steady = body.ambient_k + step.heat_input_w / body.conductance_w_per_k
        decay = math.exp(-body.duration_s / tau)
        final = steady + (body.initial_k - steady) * decay

        return RawSolverOutput(
            values={
                TEMPERATURE_METRIC: final,
                STEADY_STATE_TEMPERATURE_METRIC: steady,
                TIME_CONSTANT_METRIC: tau,
            },
            # NOT_APPLICABLE, not CONVERGED. This is a closed-form evaluation:
            # it neither converges nor fails to, and the core's own contract
            # says the two must not be conflated.
            convergence=ConvergenceState.NOT_APPLICABLE,
            iterations=1,
            wall_seconds=time.perf_counter() - started,
            diagnostics={
                "decay_factor": decay,
                "steps_of_tau": body.duration_s / tau,
            },
        )

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> dict[str, Quantity]:
        if not raw.succeeded:
            return {}
        return {
            TEMPERATURE_METRIC: Quantity(
                raw.values[TEMPERATURE_METRIC], TEMPERATURE_UNIT
            ),
            STEADY_STATE_TEMPERATURE_METRIC: Quantity(
                raw.values[STEADY_STATE_TEMPERATURE_METRIC], TEMPERATURE_UNIT
            ),
            TIME_CONSTANT_METRIC: Quantity(
                raw.values[TIME_CONSTANT_METRIC], TIME_UNIT
            ),
        }

    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        """Two checks, and only one of them establishes anything.

        ``lumped_balance_residual`` evaluates the residual of
        ``C dT/dt = Q - hA (T - T_amb)`` at the end of the interval using the
        analytic derivative. It is self-consistency of the solution against its
        own differential equation, it establishes no level, and the check says
        so where it is built.

        ``analytic_reference_agreement`` compares the emitted temperature
        against :mod:`lumped_reference`, which rebuilds the solution from the
        equation's coefficients by a series recurrence that shares no code and
        no derived quantity with the closed form. That comparison is what earns
        ``ANALYTICALLY_VERIFIED``; the independence argument, what the
        comparison can and cannot detect, and why ``NUMERICALLY_CONVERGED`` is
        not earnable by either side are all set out in that module's docstring.

        **The reference is a third outcome, not a softer pass.** If it cannot
        be constructed inside its declared budget the check is ``NOT_RUN`` and
        establishes nothing; if it can be constructed and disagrees, the check
        ``FAIL``s. Degrading a disagreement into a level-free pass would let a
        wrong closed form travel as a clean report, which is exactly what a
        reference comparison exists to prevent.
        """
        step: PreparedLumpedStep = prepared.payload
        body = step.body
        if not raw.succeeded:
            return ValidationReport(
                checks=(
                    ValidationCheck(
                        name=BALANCE_RESIDUAL_CHECK,
                        outcome=ValidationOutcome.FAIL,
                        detail="the solve did not succeed; no residual exists",
                    ),
                )
            )

        final = raw.values[TEMPERATURE_METRIC]
        steady = raw.values[STEADY_STATE_TEMPERATURE_METRIC]
        tau = raw.values[TIME_CONSTANT_METRIC]
        # dT/dt of the closed form at t = duration.
        derivative = -(body.initial_k - steady) * math.exp(
            -body.duration_s / tau
        ) / tau
        residual = abs(
            body.capacity_j_per_k * derivative
            - step.heat_input_w
            + body.conductance_w_per_k * (final - body.ambient_k)
        )
        scale = max(abs(step.heat_input_w), 1.0)
        passed = residual <= 1e-9 * scale
        return ValidationReport(
            checks=(
                ValidationCheck(
                    name=BALANCE_RESIDUAL_CHECK,
                    outcome=(
                        ValidationOutcome.PASS if passed else ValidationOutcome.FAIL
                    ),
                    # ESTABLISHES NO LEVEL, deliberately.
                    #
                    # A first draft claimed ANALYTICALLY_VERIFIED. The residual
                    # is not circular — a wrong tau, a wrong steady state or a
                    # flipped exponent each leave it non-zero, so the check does
                    # real work — but it compares the closed form against the
                    # equation the closed form was derived from, with no
                    # independent reference. The level now comes from the check
                    # below, which has one; this one keeps its honest silence
                    # rather than borrowing that reference's credit.
                    establishes=None,
                    residual=residual,
                    tolerance=1e-9 * scale,
                    detail=(
                        f"|C dT/dt - Q + hA (T - T_amb)| = {residual:.3e} W "
                        f"against a scale of {scale:.3e} W. Verification of "
                        f"the closed form against the balance it solves; no "
                        f"physical validation and no coupled-convergence claim."
                    ),
                ),
                self._reference_check(body, step.heat_input_w, final, steady),
            )
        )

    @staticmethod
    def _reference_check(
        body: ThermalBody,
        heat_input_w: float,
        final_k: float,
        steady_k: float,
    ) -> ValidationCheck:
        """The emitted temperature against the independent series reference."""
        reference = series_reference_temperature(
            capacity_j_per_k=body.capacity_j_per_k,
            conductance_w_per_k=body.conductance_w_per_k,
            heat_input_w=heat_input_w,
            ambient_k=body.ambient_k,
            initial_k=body.initial_k,
            duration_s=body.duration_s,
        )
        evidence = (f"{REFERENCE_ID}: {REFERENCE_EXPRESSION}",)
        if not reference.available:
            return ValidationCheck(
                name=ANALYTIC_REFERENCE_CHECK,
                outcome=ValidationOutcome.NOT_RUN,
                detail=(
                    f"{reference.detail}. No comparison was made, so nothing "
                    f"was established: an absent reference is a gap in the "
                    f"evidence, not a result in its favour"
                ),
                establishes=None,
                evidence=evidence,
            )

        # The round-off budget scales with the largest intermediate the closed
        # form forms, not with the answer: (T0 - T_ss) cancels, and a body
        # whose steady state is far outside its own temperature range carries
        # that cancellation into the result.
        magnitude = max(
            abs(final_k), abs(body.initial_k), abs(steady_k), 1.0
        )
        tolerance = (
            reference.error_bound_k
            + SOLVER_ROUNDING_ULPS * sys.float_info.epsilon * magnitude
        )
        difference = abs(final_k - reference.value_k)
        agrees = difference <= tolerance
        return ValidationCheck(
            name=ANALYTIC_REFERENCE_CHECK,
            outcome=(
                ValidationOutcome.PASS if agrees else ValidationOutcome.FAIL
            ),
            residual=difference,
            tolerance=tolerance,
            establishes=(
                ValidationLevel.ANALYTICALLY_VERIFIED if agrees else None
            ),
            detail=(
                f"closed form gives {final_k:.12g} K; {reference.detail}. "
                f"They differ by {difference:.3e} K against a tolerance of "
                f"{tolerance:.3e} K, which is the reference's own error bound "
                f"plus {SOLVER_ROUNDING_ULPS} ulps of the largest intermediate "
                f"the closed form forms ({magnitude:.6g} K). The two routes "
                f"share the governing equation and nothing else — no code, no "
                f"steady state, no time constant, no exponential — so this is "
                f"code verification of the closed form and not physical "
                f"validation of the model."
            ),
            evidence=evidence,
        )
