"""The non-isothermal CSTR: reactor declaration, model, and problem statement.

THE PHYSICS, STATED ONCE
------------------------
A perfectly mixed continuous stirred-tank reactor holds a liquid in which one
irreversible exothermic reaction ``A -> B`` proceeds, first order in A, with an
Arrhenius rate constant. Two coupled ordinary differential equations follow
from a species balance on A and an energy balance on the tank contents:

    dC_A/dt = (q/V) (C_Af - C_A) - k(T) C_A
    dT/dt   = (q/V) (T_f  - T  ) + beta k(T) C_A - gamma (T - T_c)
    k(T)    = k0 exp(-E / (R T))

with

    beta  = (-dH) / (rho cp)      [m**3 K / mol]   adiabatic rise per unit conc.
    gamma = UA / (V rho cp)       [1 / s]          jacket cooling rate

This is the Aris-Amundson reactor, in the parameterization tabulated by Seborg,
Edgar, Mellichamp and Doyle, *Process Dynamics and Control*. It is the standard
worked example for exactly the two behaviours this milestone needs: Arrhenius
stiffness, and multiplicity of steady states.

WHY THIS PROBLEM AND NOT A GENTLER ONE
---------------------------------------
The exponential in ``k(T)`` couples the two states through

    dk/dT = k E / (R T**2)

which over the model's validity envelope rises steeply with temperature: k
climbs by orders of magnitude between 300 K and 900 K. During an ignition
transient the chemical mode is therefore orders of magnitude faster than the
flow mode ``q/V``, while the horizon of interest is set by the *slow* mode.
That ratio is the definition of stiffness, and it is a property of the physics
rather than something imposed on the problem to make it look hard.

``dk/dT`` does NOT grow without bound in T, and it is worth being exact about
why. As ``T -> infinity`` the exponential saturates, ``k -> k0`` and
``dk/dT -> 0``; the derivative is maximised at ``T = E/(2R)`` and decays
beyond it. For this parameterization ``E/(2R) = 4375 K``, which is far above
the 1000 K ceiling of the declared envelope, so ``dk/dT`` is monotonically
increasing everywhere this model is allowed to be used. The steepness is a
statement about the operating range, not an unbounded growth.

DIMENSIONAL CHECK, PERFORMED ON THE EQUATIONS
----------------------------------------------
    (q/V)(C_Af - C_A)   (m**3/s / m**3)(mol/m**3)              = mol/(m**3 s)
    k C_A               (1/s)(mol/m**3)                        = mol/(m**3 s)
    (q/V)(T_f - T)      (1/s)(K)                               = K/s
    beta k C_A          (m**3 K/mol)(1/s)(mol/m**3)            = K/s
    gamma (T - T_c)     (1/s)(K)                               = K/s

Both equations are dimensionally homogeneous, and a test asserts the two
composite groups carry those dimensionalities through :class:`Quantity` rather
than through this comment.

TEMPERATURE IS AN ABSOLUTE THERMODYNAMIC TEMPERATURE
-----------------------------------------------------
Every temperature here is in kelvin and is used inside ``exp(-E/(R T))``, which
is meaningless on a relative scale. The validity envelope therefore refuses
non-positive temperatures at the declaration boundary rather than letting the
Arrhenius term produce a silently absurd rate.

WHAT IS DECLARED WHERE
-----------------------
``ReactorChemistry``  the reaction and the fluid: k0, E, dH, rho, cp
``ReactorOperation``  how the tank is run: q, V, feed state, jacket, horizon
``ReactorRun``        chemistry + operation + initial state + numerics

The split is not cosmetic. Chemistry and operation are physics; the numerical
declaration (method, tolerances, budget) is how finely the physics is being
resolved. A domain that cannot separate those cannot report a numerical
adequacy claim about itself, which is the whole point of the milestone.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from ....scientific.ir.problem import ModelReference, ScientificProblem
from ....scientific.ir.variables import (
    ScientificParameter,
    ScientificVariable,
    VariableRole,
)
from ....scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    ModelValidationStatus,
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
)
from ....scientific.solvers.capability import CoreCapabilities, SolverCapability
from ....scientific.units.quantity import Quantity
from .errors import ReactorConfigurationError

# =====================================================================
# Units — every one of these is a real physical dimension
# =====================================================================

CONCENTRATION_UNIT = "mol/m**3"
TEMPERATURE_UNIT = "kelvin"
TIME_UNIT = "second"
VOLUME_UNIT = "m**3"
FLOW_UNIT = "m**3/s"
RATE_CONSTANT_UNIT = "1/s"
MOLAR_ENERGY_UNIT = "J/mol"
DENSITY_UNIT = "kg/m**3"
HEAT_CAPACITY_UNIT = "J/(kg*K)"
UA_UNIT = "W/K"
GAS_CONSTANT_UNIT = "J/(mol*K)"
DIMENSIONLESS = "dimensionless"

#: CODATA / SI-exact molar gas constant. Declared here as a Quantity because it
#: enters the Arrhenius exponent and must be dimensionally checkable like every
#: other input. It is a defining constant of the SI and carries no uncertainty.
MOLAR_GAS_CONSTANT = Quantity(8.314462618, GAS_CONSTANT_UNIT)

# =====================================================================
# Validity envelope bounds — DOMAIN-OWNED, declared here and nowhere else
# =====================================================================

#: The model assumes a single liquid phase with constant density and heat
#: capacity and no boiling. Below the lower bound an aqueous-like liquid would
#: freeze; above the upper bound the constant-property and no-phase-change
#: assumptions are indefensible for any ordinary solvent at moderate pressure.
#: These are assumptions of the MODEL, not limits of the integrator, which is
#: why they live in the model's ValidityDomain and are enforced on declaration.
MIN_VALID_TEMPERATURE_K = 250.0
MAX_VALID_TEMPERATURE_K = 1000.0

#: Absolute zero is excluded, not merely approached: ``exp(-E/(R T))`` has an
#: essential singularity at T = 0 and no meaning below it.
ABSOLUTE_ZERO_K = 0.0

# =====================================================================
# Capability — declared in this package and nowhere else
# =====================================================================

KINETICS_CSTR_NONISOTHERMAL = SolverCapability(
    "kinetics:cstr_nonisothermal_transient",
    "Transient non-isothermal CSTR with Arrhenius kinetics",
)

MODEL_VERSION = "0.1.0"

_ASSUMPTIONS = (
    "perfectly mixed tank: no spatial gradients in concentration or temperature",
    "constant liquid volume; inflow and outflow volumetric rates are equal",
    "single liquid phase, constant density and constant heat capacity",
    "one irreversible reaction A -> B, first order in A, no reverse reaction "
    "and no side reactions",
    "Arrhenius temperature dependence with a temperature-independent "
    "pre-exponential factor and activation energy",
    "heat of reaction independent of temperature",
    "jacket at a prescribed, constant temperature with a constant overall "
    "heat-transfer coefficient-area product; the jacket's own dynamics are "
    "not modelled",
    "no heat loss other than through the jacket; no viscous dissipation",
    "no phase change, no boiling, no vapour space",
)

_REFERENCES = (
    "Aris, R. and Amundson, N.R. (1958) An analysis of chemical reactor "
    "stability and control. Chemical Engineering Science 7(3), 121-155.",
    "Uppal, A., Ray, W.H. and Poore, A.B. (1974) On the dynamic behaviour of "
    "continuous stirred tank reactors. Chemical Engineering Science 29(4), "
    "967-985.",
    "Seborg, D.E., Edgar, T.F., Mellichamp, D.A. and Doyle, F.J. Process "
    "Dynamics and Control. The tabulated CSTR example parameterization.",
)

CSTR_MODEL = ScientificModelDefinition(
    model_id="kinetics.cstr.nonisothermal_first_order",
    version=MODEL_VERSION,
    name="Non-isothermal CSTR, first-order exothermic reaction",
    domain="kinetics",
    # FUNDAMENTAL_RELATION: species and energy balances on a well-mixed control
    # volume are conservation statements. The Arrhenius form inside them is an
    # empirical correlation, which is recorded in the assumptions rather than
    # by downgrading the whole model — the balances are not a fit to anything.
    model_type=ModelType.FUNDAMENTAL_RELATION,
    description=(
        "Coupled species and energy balances for a perfectly mixed constant-"
        "volume liquid-phase CSTR carrying one irreversible exothermic "
        "first-order reaction with Arrhenius kinetics and jacket cooling."
    ),
    inputs=(
        ModelInputSpec(
            name="k0",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=RATE_CONSTANT_UNIT,
            description="Arrhenius pre-exponential factor; strictly positive.",
        ),
        ModelInputSpec(
            name="activation_energy",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=MOLAR_ENERGY_UNIT,
            description="Arrhenius activation energy; non-negative.",
        ),
        ModelInputSpec(
            name="heat_of_reaction",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=MOLAR_ENERGY_UNIT,
            description="Molar enthalpy of reaction; negative when exothermic.",
        ),
        ModelInputSpec(
            name="feed_concentration",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=CONCENTRATION_UNIT,
            description="Concentration of A in the feed; non-negative.",
        ),
        ModelInputSpec(
            name="feed_temperature",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            description="Absolute feed temperature.",
        ),
        ModelInputSpec(
            name="coolant_temperature",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            description="Absolute jacket temperature.",
        ),
        ModelInputSpec(
            name="residence_time",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TIME_UNIT,
            description="V/q; strictly positive.",
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric="C_A",
            unit_exemplar=CONCENTRATION_UNIT,
            description="Concentration of reactant A in the tank and outlet.",
        ),
        ModelOutputSpec(
            metric="T",
            unit_exemplar=TEMPERATURE_UNIT,
            description="Absolute temperature of the tank contents and outlet.",
        ),
        ModelOutputSpec(
            metric="conversion",
            unit_exemplar=DIMENSIONLESS,
            description=(
                "Fractional conversion of A, (C_Af - C_A)/C_Af. Genuinely "
                "dimensionless: a ratio of two concentrations."
            ),
        ),
    ),
    assumptions=_ASSUMPTIONS,
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name="temperature",
                minimum=Quantity(MIN_VALID_TEMPERATURE_K, TEMPERATURE_UNIT),
                maximum=Quantity(MAX_VALID_TEMPERATURE_K, TEMPERATURE_UNIT),
                description=(
                    "Single-phase liquid with constant properties and no "
                    "boiling. Outside this band the constant-density, "
                    "constant-cp and no-phase-change assumptions fail, and the "
                    "model is not merely inaccurate but inapplicable."
                ),
            ),
            RangeCondition(
                name="concentration",
                minimum=Quantity(0.0, CONCENTRATION_UNIT),
                description=(
                    "Concentrations are non-negative. A negative concentration "
                    "is not a small error; it is not a state of the system."
                ),
            ),
            RangeCondition(
                name="k0",
                minimum=Quantity(0.0, RATE_CONSTANT_UNIT),
                minimum_inclusive=False,
                description="Strictly positive pre-exponential factor.",
            ),
            RangeCondition(
                name="activation_energy",
                minimum=Quantity(0.0, MOLAR_ENERGY_UNIT),
                description=(
                    "Non-negative activation energy. A negative barrier would "
                    "make the rate fall with temperature, which is not the "
                    "Arrhenius model."
                ),
            ),
            RangeCondition(
                name="residence_time",
                minimum=Quantity(0.0, TIME_UNIT),
                minimum_inclusive=False,
                description="Strictly positive residence time V/q.",
            ),
        ),
        description=(
            "Well-mixed constant-volume liquid-phase operation with constant "
            "physical properties and Arrhenius kinetics."
        ),
    ),
    required_capabilities=frozenset({KINETICS_CSTR_NONISOTHERMAL.name}),
    # SELF_CONSISTENT and not BENCHMARK_VALIDATED: this milestone compares the
    # integrator against an independently derived algebraic steady state and an
    # exact invariant of the same equations. That establishes that the numerics
    # solve what they claim to solve. Nothing here has been compared against a
    # measurement of a real reactor, and BENCHMARK_VALIDATED would claim it had.
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
    references=_REFERENCES,
)

CSTR_MODELS = (CSTR_MODEL,)


def cstr_solver_capabilities() -> frozenset[SolverCapability]:
    """What a solver must declare to take this domain.

    ``core:ode`` is included because the mathematical form genuinely is an
    initial-value ODE problem and the core knows that shape; the domain name is
    what actually gates admission.
    """
    return frozenset({KINETICS_CSTR_NONISOTHERMAL, CoreCapabilities.ODE})


# =====================================================================
# Declarations
# =====================================================================

def _quantity(value: Any, unit: str, label: str) -> Quantity:
    """Require a Quantity carrying ``unit``. A bare number is not a declaration."""
    if not isinstance(value, Quantity):
        raise ReactorConfigurationError(
            f"{label} must be a Quantity carrying {unit!r}, got "
            f"{type(value).__name__} — a bare number is not a declaration"
        )
    try:
        value.magnitude_in(unit)
    except Exception as exc:
        raise ReactorConfigurationError(
            f"{label} must be dimensionally compatible with {unit!r}: {exc}"
        ) from exc
    return value


def _positive(value: Quantity, unit: str, label: str) -> float:
    magnitude = value.magnitude_in(unit)
    if not math.isfinite(magnitude) or magnitude <= 0.0:
        raise ReactorConfigurationError(
            f"{label} must be finite and strictly positive, got "
            f"{magnitude!r} {unit}"
        )
    return magnitude


def _non_negative(value: Quantity, unit: str, label: str) -> float:
    magnitude = value.magnitude_in(unit)
    if not math.isfinite(magnitude) or magnitude < 0.0:
        raise ReactorConfigurationError(
            f"{label} must be finite and non-negative, got {magnitude!r} {unit}"
        )
    return magnitude


def _require_integer(value: Any, label: str) -> int:
    """A count must be declared as a genuine integer.

    ``int(500.9)`` is 500, and accepting that would silently run a different
    experiment from the one declared — a budget or an output count is a
    discrete quantity, and a fractional one is a mistake in the caller rather
    than a value to round. NaN and infinity raise inside ``int()`` at best and
    would be meaningless as counts at worst.

    ``bool`` is refused explicitly. It is a subclass of ``int`` in Python, so
    ``n_output_points=True`` would otherwise be silently accepted as 1.
    """
    if isinstance(value, bool):
        raise ReactorConfigurationError(
            f"{label} must be an int, got a bool ({value!r}); bool is an int "
            f"subclass in Python and would be read as {int(value)}"
        )
    if not isinstance(value, int):
        raise ReactorConfigurationError(
            f"{label} must be declared as an int, got "
            f"{type(value).__name__} ({value!r}); a count is discrete and is "
            f"not rounded for the caller"
        )
    return int(value)


def _valid_temperature(value: Quantity, label: str) -> float:
    """Enforce the model's declared temperature envelope at the boundary."""
    kelvin = value.magnitude_in(TEMPERATURE_UNIT)
    if not math.isfinite(kelvin):
        raise ReactorConfigurationError(f"{label} must be finite, got {kelvin!r} K")
    if kelvin <= ABSOLUTE_ZERO_K:
        raise ReactorConfigurationError(
            f"{label} must be a positive absolute temperature, got {kelvin!r} K; "
            f"exp(-E/(R T)) has no meaning at or below absolute zero"
        )
    if not (MIN_VALID_TEMPERATURE_K <= kelvin <= MAX_VALID_TEMPERATURE_K):
        raise ReactorConfigurationError(
            f"{label} = {kelvin!r} K is outside the model's declared validity "
            f"envelope [{MIN_VALID_TEMPERATURE_K}, {MAX_VALID_TEMPERATURE_K}] K; "
            f"the constant-property single-phase assumptions do not hold there"
        )
    return kelvin


@dataclass(frozen=True)
class ReactorChemistry:
    """The reaction and the fluid it happens in. Physics, not operation."""

    k0: Quantity                 # 1/s
    activation_energy: Quantity  # J/mol
    heat_of_reaction: Quantity   # J/mol, negative when exothermic
    density: Quantity            # kg/m**3
    heat_capacity: Quantity      # J/(kg*K)

    def __post_init__(self) -> None:
        _positive(_quantity(self.k0, RATE_CONSTANT_UNIT, "k0"),
                  RATE_CONSTANT_UNIT, "k0")
        _non_negative(
            _quantity(self.activation_energy, MOLAR_ENERGY_UNIT,
                      "activation_energy"),
            MOLAR_ENERGY_UNIT, "activation_energy",
        )
        _quantity(self.heat_of_reaction, MOLAR_ENERGY_UNIT, "heat_of_reaction")
        if not math.isfinite(self.heat_of_reaction.magnitude_in(MOLAR_ENERGY_UNIT)):
            raise ReactorConfigurationError("heat_of_reaction must be finite")
        _positive(_quantity(self.density, DENSITY_UNIT, "density"),
                  DENSITY_UNIT, "density")
        _positive(
            _quantity(self.heat_capacity, HEAT_CAPACITY_UNIT, "heat_capacity"),
            HEAT_CAPACITY_UNIT, "heat_capacity",
        )

    # -- base-unit accessors ------------------------------------------------
    @property
    def k0_per_s(self) -> float:
        return self.k0.magnitude_in(RATE_CONSTANT_UNIT)

    @property
    def e_j_per_mol(self) -> float:
        return self.activation_energy.magnitude_in(MOLAR_ENERGY_UNIT)

    @property
    def dh_j_per_mol(self) -> float:
        return self.heat_of_reaction.magnitude_in(MOLAR_ENERGY_UNIT)

    @property
    def rho_kg_per_m3(self) -> float:
        return self.density.magnitude_in(DENSITY_UNIT)

    @property
    def cp_j_per_kg_k(self) -> float:
        return self.heat_capacity.magnitude_in(HEAT_CAPACITY_UNIT)

    @property
    def e_over_r_k(self) -> float:
        """E/R in kelvin — the group that actually appears in the exponent."""
        return self.e_j_per_mol / MOLAR_GAS_CONSTANT.magnitude_in(GAS_CONSTANT_UNIT)

    @property
    def beta_m3_k_per_mol(self) -> float:
        """(-dH)/(rho cp): the adiabatic temperature rise per unit concentration."""
        return -self.dh_j_per_mol / (self.rho_kg_per_m3 * self.cp_j_per_kg_k)

    @property
    def is_exothermic(self) -> bool:
        return self.dh_j_per_mol < 0.0

    def rate_constant_per_s(self, temperature_k: float) -> float:
        """k(T) = k0 exp(-E/(R T)). Plain floats: this is the numeric kernel."""
        return self.k0_per_s * math.exp(-self.e_over_r_k / float(temperature_k))

    def to_dict(self) -> dict[str, Any]:
        return {
            "k0_per_s": self.k0_per_s,
            "activation_energy_j_per_mol": self.e_j_per_mol,
            "e_over_r_k": self.e_over_r_k,
            "heat_of_reaction_j_per_mol": self.dh_j_per_mol,
            "density_kg_per_m3": self.rho_kg_per_m3,
            "heat_capacity_j_per_kg_k": self.cp_j_per_kg_k,
            "beta_m3_k_per_mol": self.beta_m3_k_per_mol,
            "exothermic": self.is_exothermic,
        }


@dataclass(frozen=True)
class ReactorOperation:
    """How the tank is run. Physics, not numerics."""

    volume: Quantity              # m**3
    flow_rate: Quantity           # m**3/s
    feed_concentration: Quantity  # mol/m**3
    feed_temperature: Quantity    # K
    coolant_temperature: Quantity # K
    ua: Quantity                  # W/K  (zero means adiabatic)
    end_time: Quantity            # s

    def __post_init__(self) -> None:
        _positive(_quantity(self.volume, VOLUME_UNIT, "volume"),
                  VOLUME_UNIT, "volume")
        _positive(_quantity(self.flow_rate, FLOW_UNIT, "flow_rate"),
                  FLOW_UNIT, "flow_rate")
        _non_negative(
            _quantity(self.feed_concentration, CONCENTRATION_UNIT,
                      "feed_concentration"),
            CONCENTRATION_UNIT, "feed_concentration",
        )
        _valid_temperature(
            _quantity(self.feed_temperature, TEMPERATURE_UNIT,
                      "feed_temperature"),
            "feed_temperature",
        )
        _valid_temperature(
            _quantity(self.coolant_temperature, TEMPERATURE_UNIT,
                      "coolant_temperature"),
            "coolant_temperature",
        )
        _non_negative(_quantity(self.ua, UA_UNIT, "ua"), UA_UNIT, "ua")
        _positive(_quantity(self.end_time, TIME_UNIT, "end_time"),
                  TIME_UNIT, "end_time")

    # -- base-unit accessors ------------------------------------------------
    @property
    def volume_m3(self) -> float:
        return self.volume.magnitude_in(VOLUME_UNIT)

    @property
    def flow_m3_per_s(self) -> float:
        return self.flow_rate.magnitude_in(FLOW_UNIT)

    @property
    def caf_mol_per_m3(self) -> float:
        return self.feed_concentration.magnitude_in(CONCENTRATION_UNIT)

    @property
    def tf_k(self) -> float:
        return self.feed_temperature.magnitude_in(TEMPERATURE_UNIT)

    @property
    def tc_k(self) -> float:
        return self.coolant_temperature.magnitude_in(TEMPERATURE_UNIT)

    @property
    def ua_w_per_k(self) -> float:
        return self.ua.magnitude_in(UA_UNIT)

    @property
    def end_time_s(self) -> float:
        return self.end_time.magnitude_in(TIME_UNIT)

    @property
    def dilution_rate_per_s(self) -> float:
        """q/V — the reciprocal residence time, the slow mode of the system."""
        return self.flow_m3_per_s / self.volume_m3

    @property
    def residence_time_s(self) -> float:
        return self.volume_m3 / self.flow_m3_per_s

    @property
    def is_adiabatic(self) -> bool:
        return self.ua_w_per_k == 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "volume_m3": self.volume_m3,
            "flow_m3_per_s": self.flow_m3_per_s,
            "feed_concentration_mol_per_m3": self.caf_mol_per_m3,
            "feed_temperature_k": self.tf_k,
            "coolant_temperature_k": self.tc_k,
            "ua_w_per_k": self.ua_w_per_k,
            "end_time_s": self.end_time_s,
            "residence_time_s": self.residence_time_s,
            "dilution_rate_per_s": self.dilution_rate_per_s,
            "adiabatic": self.is_adiabatic,
        }


@dataclass(frozen=True)
class IntegrationSettings:
    """The numerical declaration. Deliberately separate from the physics.

    ``method`` is restricted to the stiff integrators plus the explicit probe.
    The probe is admissible as a *measurement instrument* for stiffness — the
    ratio of its work to a stiff method's work is how stiffness is evidenced —
    and it is never the production method for a stiff regime. Nothing here
    chooses a method; a caller declares one.
    """

    method: str = "BDF"
    rtol: float = 1.0e-8
    atol_concentration: float = 1.0e-8   # mol/m**3
    atol_temperature: float = 1.0e-8     # K
    #: Hard cap on right-hand-side evaluations. An explicit computational
    #: limit, recorded in provenance, enforced inside the RHS closure.
    max_rhs_evaluations: int = 2_000_000
    #: Number of uniformly spaced output points on [0, t_end]. Output density
    #: never changes the integration path — solve_ivp integrates adaptively and
    #: interpolates onto t_eval — so this is reporting resolution only.
    n_output_points: int = 2001

    #: Methods this domain will run. LSODA is excluded deliberately: it
    #: switches between stiff and non-stiff internally, so a work count from it
    #: cannot be attributed to one method and would corrupt the stiffness
    #: measurement this domain relies on.
    ALLOWED_METHODS = ("BDF", "Radau", "RK45")
    #: Methods admissible as a production integrator for a stiff regime. Both
    #: damp the fast chemical mode rather than oscillating on it, which is what
    #: this problem requires and what rules out the trapezoidal family.
    #:
    #: The two get there differently, and the difference is not cosmetic.
    #: Radau IIA (order 5) is A-stable AND L-stable. BDF is A-stable only at
    #: orders 1-2; at the higher orders SciPy uses it is A(alpha)-stable with
    #: alpha shrinking as the order rises, and it is *stiffly stable* in Gear's
    #: sense — its stability region contains the whole negative real axis and a
    #: wedge around it, which is what makes it the standard choice for stiff
    #: chemical kinetics. Claiming BDF is L-stable at every order it uses would
    #: be false.
    STIFF_METHODS = ("BDF", "Radau")

    def __post_init__(self) -> None:
        method = str(self.method).strip()
        if method not in self.ALLOWED_METHODS:
            raise ReactorConfigurationError(
                f"method {method!r} is not one of {self.ALLOWED_METHODS}"
            )
        object.__setattr__(self, "method", method)
        for label in ("rtol", "atol_concentration", "atol_temperature"):
            value = float(getattr(self, label))
            if not math.isfinite(value) or value <= 0.0:
                raise ReactorConfigurationError(
                    f"{label} must be finite and strictly positive, got {value!r}"
                )
            object.__setattr__(self, label, value)
        budget = _require_integer(self.max_rhs_evaluations, "max_rhs_evaluations")
        if budget < 1:
            raise ReactorConfigurationError(
                f"max_rhs_evaluations must be at least 1, got {budget}"
            )
        object.__setattr__(self, "max_rhs_evaluations", budget)
        points = _require_integer(self.n_output_points, "n_output_points")
        if points < 2:
            raise ReactorConfigurationError(
                f"n_output_points must be at least 2, got {points}"
            )
        object.__setattr__(self, "n_output_points", points)

    @property
    def is_stiff_method(self) -> bool:
        return self.method in self.STIFF_METHODS

    @property
    def atol_vector(self) -> tuple[float, float]:
        """Per-state absolute tolerances, in state order (C_A, T).

        A single scalar atol would be wrong here: concentration and temperature
        differ by orders of magnitude in both scale and unit, and one number
        cannot mean the same thing for both.
        """
        return (float(self.atol_concentration), float(self.atol_temperature))

    def with_tolerances(
        self, *, rtol: float, atol_concentration: float, atol_temperature: float
    ) -> "IntegrationSettings":
        """Same declaration at a different tolerance — the tolerance ladder."""
        return IntegrationSettings(
            method=self.method,
            rtol=rtol,
            atol_concentration=atol_concentration,
            atol_temperature=atol_temperature,
            max_rhs_evaluations=self.max_rhs_evaluations,
            n_output_points=self.n_output_points,
        )

    def with_method(self, method: str) -> "IntegrationSettings":
        return IntegrationSettings(
            method=method,
            rtol=self.rtol,
            atol_concentration=self.atol_concentration,
            atol_temperature=self.atol_temperature,
            max_rhs_evaluations=self.max_rhs_evaluations,
            n_output_points=self.n_output_points,
        )

    def as_tolerance_mapping(self) -> dict[str, float]:
        return {
            "rtol": float(self.rtol),
            "atol_concentration": float(self.atol_concentration),
            "atol_temperature": float(self.atol_temperature),
            "max_rhs_evaluations": float(self.max_rhs_evaluations),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "rtol": self.rtol,
            "atol_concentration": self.atol_concentration,
            "atol_temperature": self.atol_temperature,
            "max_rhs_evaluations": self.max_rhs_evaluations,
            "n_output_points": self.n_output_points,
            "is_stiff_method": self.is_stiff_method,
        }


@dataclass(frozen=True)
class ReactorRun:
    """One fully declared reactor experiment: physics + initial state + numerics."""

    run_label: str
    chemistry: ReactorChemistry
    operation: ReactorOperation
    initial_concentration: Quantity   # mol/m**3
    initial_temperature: Quantity     # K
    integration: IntegrationSettings = field(default_factory=IntegrationSettings)

    def __post_init__(self) -> None:
        if not str(self.run_label).strip():
            raise ReactorConfigurationError("run requires a non-empty run_label")
        object.__setattr__(self, "run_label", str(self.run_label).strip())
        for label, kind in (
            ("chemistry", ReactorChemistry),
            ("operation", ReactorOperation),
            ("integration", IntegrationSettings),
        ):
            if not isinstance(getattr(self, label), kind):
                raise ReactorConfigurationError(
                    f"{label} must be a {kind.__name__}"
                )
        _non_negative(
            _quantity(self.initial_concentration, CONCENTRATION_UNIT,
                      "initial_concentration"),
            CONCENTRATION_UNIT, "initial_concentration",
        )
        _valid_temperature(
            _quantity(self.initial_temperature, TEMPERATURE_UNIT,
                      "initial_temperature"),
            "initial_temperature",
        )

    # -- base-unit accessors ------------------------------------------------
    @property
    def ca0_mol_per_m3(self) -> float:
        return self.initial_concentration.magnitude_in(CONCENTRATION_UNIT)

    @property
    def t0_k(self) -> float:
        return self.initial_temperature.magnitude_in(TEMPERATURE_UNIT)

    @property
    def gamma_per_s(self) -> float:
        """UA/(V rho cp) — the jacket cooling rate constant."""
        return self.operation.ua_w_per_k / (
            self.operation.volume_m3
            * self.chemistry.rho_kg_per_m3
            * self.chemistry.cp_j_per_kg_k
        )

    @property
    def adiabatic_rise_k(self) -> float:
        """beta * C_Af — the full-conversion adiabatic temperature rise."""
        return self.chemistry.beta_m3_k_per_mol * self.operation.caf_mol_per_m3

    @property
    def damkohler_at_feed_temperature(self) -> float:
        """k(T_f) / (q/V). Order unity is where the interesting behaviour is."""
        return (
            self.chemistry.rate_constant_per_s(self.operation.tf_k)
            / self.operation.dilution_rate_per_s
        )

    #: The maximum concentration the tank can hold. A consuming reaction with a
    #: feed at C_Af and an initial charge no richer than the feed can never
    #: exceed it, which makes this an upper physical bound on the state.
    @property
    def concentration_ceiling_mol_per_m3(self) -> float:
        return max(self.operation.caf_mol_per_m3, self.ca0_mol_per_m3)

    def with_integration(self, integration: IntegrationSettings) -> "ReactorRun":
        """The same physics resolved differently. Used by the tolerance ladder
        and the cross-method arm: everything physical is held identical, so any
        difference between the two is numerical by construction."""
        return ReactorRun(
            run_label=self.run_label,
            chemistry=self.chemistry,
            operation=self.operation,
            initial_concentration=self.initial_concentration,
            initial_temperature=self.initial_temperature,
            integration=integration,
        )

    def physics_fingerprint(self) -> str:
        """Identity of the PHYSICAL problem, excluding all numerics."""
        blob = json.dumps(
            {
                "run_label": self.run_label,
                "chemistry": self.chemistry.to_dict(),
                "operation": self.operation.to_dict(),
                "initial_concentration_mol_per_m3": self.ca0_mol_per_m3,
                "initial_temperature_k": self.t0_k,
                "reaction": "A -> B, irreversible, first order in A",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def validity_context(self) -> dict[str, Quantity]:
        """The declaration expressed for ``ValidityDomain.assess``.

        The temperatures offered are the DECLARED ones. A trajectory can still
        leave the envelope during integration, and that is a different question
        answered after the solve by the state-admissibility check — a valid
        declaration does not promise a valid trajectory.
        """
        return {
            "temperature": self.initial_temperature,
            "concentration": self.initial_concentration,
            "k0": self.chemistry.k0,
            "activation_energy": self.chemistry.activation_energy,
            "residence_time": Quantity(
                self.operation.residence_time_s, TIME_UNIT
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_label": self.run_label,
            "chemistry": self.chemistry.to_dict(),
            "operation": self.operation.to_dict(),
            "initial_concentration_mol_per_m3": self.ca0_mol_per_m3,
            "initial_temperature_k": self.t0_k,
            "integration": self.integration.to_dict(),
            "derived": {
                "gamma_per_s": self.gamma_per_s,
                "adiabatic_rise_k": self.adiabatic_rise_k,
                "damkohler_at_feed_temperature":
                    self.damkohler_at_feed_temperature,
                "concentration_ceiling_mol_per_m3":
                    self.concentration_ceiling_mol_per_m3,
            },
            "physics_fingerprint": self.physics_fingerprint(),
        }


# =====================================================================
# The universal problem statement
# =====================================================================

CA_FINAL_METRIC = "C_A:final"
T_FINAL_METRIC = "T:final"
T_MAX_METRIC = "T:max"
T_AT_MAX_METRIC = "t:T_max"
CONVERSION_METRIC = "conversion:final"

#: Every metric this domain reports, with the unit it must carry. One table, so
#: the solver, the problem statement and the unit test cannot drift apart.
METRIC_UNITS: Mapping[str, str] = {
    CA_FINAL_METRIC: CONCENTRATION_UNIT,
    T_FINAL_METRIC: TEMPERATURE_UNIT,
    T_MAX_METRIC: TEMPERATURE_UNIT,
    T_AT_MAX_METRIC: TIME_UNIT,
    CONVERSION_METRIC: DIMENSIONLESS,
}


def build_cstr_problem(
    run: ReactorRun, *, problem_id: str | None = None
) -> ScientificProblem:
    """Express the reactor in the domain-neutral IR.

    The integration declaration travels as metadata, not as a parameter: the
    method and tolerance are properties of how the problem is being solved, not
    of the problem being posed.
    """
    variables = (
        ScientificVariable(
            name=CA_FINAL_METRIC,
            unit=CONCENTRATION_UNIT,
            role=VariableRole.OBSERVABLE,
            description="Concentration of A at the end of the horizon",
        ),
        ScientificVariable(
            name=T_FINAL_METRIC,
            unit=TEMPERATURE_UNIT,
            role=VariableRole.OBSERVABLE,
            description="Tank temperature at the end of the horizon",
        ),
        ScientificVariable(
            name=T_MAX_METRIC,
            unit=TEMPERATURE_UNIT,
            role=VariableRole.OBSERVABLE,
            description="Peak tank temperature over the horizon",
        ),
        ScientificVariable(
            name=CONVERSION_METRIC,
            unit=DIMENSIONLESS,
            role=VariableRole.OBSERVABLE,
            description="Fractional conversion of A at the end of the horizon",
        ),
    )
    parameters = (
        ScientificParameter(
            name="k0", value=run.chemistry.k0,
            description="Arrhenius pre-exponential factor",
        ),
        ScientificParameter(
            name="activation_energy", value=run.chemistry.activation_energy,
            description="Arrhenius activation energy",
        ),
        ScientificParameter(
            name="heat_of_reaction", value=run.chemistry.heat_of_reaction,
            description="Molar enthalpy of reaction",
        ),
        ScientificParameter(
            name="feed_concentration", value=run.operation.feed_concentration,
            description="Concentration of A in the feed",
        ),
        ScientificParameter(
            name="feed_temperature", value=run.operation.feed_temperature,
            description="Feed temperature",
        ),
        ScientificParameter(
            name="coolant_temperature", value=run.operation.coolant_temperature,
            description="Jacket temperature",
        ),
        ScientificParameter(
            name="residence_time",
            value=Quantity(run.operation.residence_time_s, TIME_UNIT),
            description="V/q",
        ),
    )
    return ScientificProblem(
        problem_id=problem_id or f"kinetics-cstr-{run.run_label}",
        name="Transient non-isothermal CSTR with Arrhenius kinetics",
        description=(
            "Coupled species and energy balances for a perfectly mixed "
            "constant-volume liquid-phase CSTR with one irreversible "
            "exothermic first-order reaction and jacket cooling."
        ),
        variables=variables,
        parameters=parameters,
        models=tuple(
            ModelReference(model.model_id, model.version) for model in CSTR_MODELS
        ),
        required_capabilities=frozenset({KINETICS_CSTR_NONISOTHERMAL.name}),
        validation_requirements=frozenset(
            {
                "dimensional_consistency",
                "integration_reported_success",
                "state_physically_admissible",
                "trajectory_finite",
            }
        ),
        metadata={
            "domain": "kinetics",
            "run_label": run.run_label,
            "physics_fingerprint": run.physics_fingerprint(),
            "reaction": "A -> B, irreversible, first order in A",
            "integration_method": run.integration.method,
            "rtol": repr(run.integration.rtol),
            "residence_time_s": repr(run.operation.residence_time_s),
            "adiabatic": str(run.operation.is_adiabatic),
        },
    )


def verify_problem_matches_run(problem: ScientificProblem, run: ReactorRun) -> None:
    """Refuse a problem/run pairing that describes different physics."""
    declared = problem.metadata.get("physics_fingerprint")
    actual = run.physics_fingerprint()
    if declared and declared != actual:
        raise ReactorConfigurationError(
            f"problem {problem.problem_id!r} declares physics fingerprint "
            f"{str(declared)[:12]}… but was paired with {actual[:12]}…; the "
            f"problem and the run describe different reactors"
        )
