"""Scientific model records for linear DC circuit analysis.

Three models are declared, each a versioned scientific claim with typed
inputs and outputs, declared assumptions and a validity domain. They are
*representations*: nothing here executes: execution belongs to the solver.

Honesty notes
-------------
* ``validation_status`` is ``SELF_CONSISTENT``, not ``BENCHMARK_VALIDATED``
  and certainly not ``EXPERIMENTALLY_VALIDATED``. Passing unit tests against
  hand-derived analytical values shows internal consistency; it is not an
  external benchmark process and involves no measurement.
* ``references`` are deliberately empty. These relations are standard
  textbook circuit theory, but this repository has no curated reference set
  yet and citations will not be invented. Reference curation is deferred. A
  source that belongs to one *condition* rather than to the model as a whole
  is cited in that condition's ``description``, which is where a reader
  auditing the bound will look for it.

Ratings and the conditions built on them
----------------------------------------
Each of these models states an idealisation in its assumptions — "unlimited
current compliance", "unlimited compliance voltage", and for the resistor an
element with no stated dissipation limit. Those are the *component's* limits,
not the relation's: two resistors obeying V = I R identically differ in what
they survive. So the bounds live on a caller-supplied :class:`ComponentRating`
and the conditions are stated over dimensionless *utilizations* of it, which is
what lets one model record serve every component. A rating that is not declared
leaves its condition UNKNOWN; it never leaves it satisfied.

Nothing here executes. The context builders below are pure functions over
records, the same character as ``models_for_circuit`` and
``assumptions_for_models``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ....scientific.errors import InvalidScientificProblem
from ....scientific.ir.problem import ScientificProblem
from ....scientific.models.definition import (
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
from ....scientific.models.registry import ModelRegistry
from ....scientific.serialization import require_schema, schema_string
from ....scientific.solvers.capability import CoreCapabilities, SolverCapability
from ....scientific.units.quantity import Quantity

#: Domain capability. Declared here, in the electrical package — the
#: universal ``CoreCapabilities`` is never extended with domain constants.
ELECTRICAL_DC_LINEAR = SolverCapability(
    "electrical:dc_linear",
    "Linear resistive DC (steady-state) circuit analysis",
)

DC_MODEL_VERSION = "0.1.0"

COMPONENT_RATING_SCHEMA = schema_string("dc_component_rating")

# --- units -------------------------------------------------------------------
POWER_UNIT = "watt"
VOLTAGE_UNIT = "volt"
CURRENT_UNIT = "ampere"
RESISTANCE_UNIT = "ohm"
DIMENSIONLESS = "dimensionless"

# --- names of the ratings a caller may declare -------------------------------
# Names, not conventions. Each is enumerated by the model record it belongs to
# as an optional ``ModelInputSpec``, so the payload boundary derives its
# description of these fields from the records instead of restating them, and
# a reader holding only the records can see which declaration unlocks which
# condition. They are the field names of :class:`ComponentRating`.
RATED_POWER = "rated_power"
MAXIMUM_WORKING_VOLTAGE = "maximum_working_voltage"
MAXIMUM_CURRENT = "maximum_current"
COMPLIANCE_VOLTAGE = "compliance_voltage"
DERATING_FACTOR = "derating_factor"

# --- names of the derived utilizations the conditions are stated over --------
DISSIPATED_POWER_UTILIZATION = "dissipated_power_utilization"
WORKING_VOLTAGE_UTILIZATION = "working_voltage_utilization"
SOURCE_CURRENT_UTILIZATION = "source_current_utilization"
COMPLIANCE_VOLTAGE_UTILIZATION = "compliance_voltage_utilization"

#: Utilization <= 1 for every rating. Not a tolerance and not a safety factor:
#: the ratio is defined as "fraction of the rating in use", so 1 is the rating.
#: Any margin the caller wants belongs in ``derating_factor``, where it is a
#: visible input rather than a number buried in a threshold.
RATING_UTILIZATION_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: The multiplier applied to a rating when the caller states no derating
#: policy. 1.0 means "the rating as published, no margin applied" — a complete
#: statement, not a substitute for a missing measurement. Derating is a policy
#: choice (ambient, altitude, mounting, expected life), and IEC 60115-1
#: publishes ratings against a stated reference ambient precisely because the
#: usable fraction away from it is the user's call.
NO_DERATING = 1.0

#: One text for one concept. ``derating_factor`` is declared by both the
#: resistor and the source, and the payload boundary derives its description
#: of a field from the model record; two wordings for the same field would
#: make that description depend on which model was consulted.
_DERATING_DESCRIPTION = (
    "Fraction of the published ratings the caller elects to use, in (0, 1]. "
    "Applies to every rating condition on this model. Defaults to 1.0, which "
    "is the complete and explicit statement 'the ratings as published, with "
    "no margin applied'."
)

_DC_ASSUMPTIONS = (
    "lumped-element circuit (no distributed or field effects)",
    "steady-state DC operation (no transients, no reactive elements)",
    "linear, time-invariant elements",
    "ideal independent sources (no internal impedance unless modelled explicitly)",
    "temperature-independent resistance",
    "no parasitics",
)


@dataclass(frozen=True)
class ComponentRating:
    """What a component is rated for, as declared by whoever specified it.

    Every field is optional and defaults to ``None``, meaning *not declared*
    and never *unlimited*. A rating left out removes its condition from
    IN_DOMAIN reach and leaves it UNKNOWN, which is the honest verdict for a
    part whose datasheet nobody supplied.

    ``derating_factor`` is the fraction of the published rating the caller
    elects to use, and it defaults to :data:`NO_DERATING`. That default is not
    an invented measurement: 1.0 is the complete and explicit statement "the
    rating as published, with no margin applied". A derating policy depends on
    ambient, mounting and expected life, all of which are the caller's to
    state, and IEC 60115-1 publishes resistor ratings against a stated
    reference ambient for exactly that reason.
    """

    rated_power: Quantity | None = None
    maximum_working_voltage: Quantity | None = None
    maximum_current: Quantity | None = None
    compliance_voltage: Quantity | None = None
    derating_factor: float = NO_DERATING

    def __post_init__(self) -> None:
        for label, unit in (
            ("rated_power", POWER_UNIT),
            ("maximum_working_voltage", VOLTAGE_UNIT),
            ("maximum_current", CURRENT_UNIT),
            ("compliance_voltage", VOLTAGE_UNIT),
        ):
            value = getattr(self, label)
            if value is None:
                continue
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem(
                    f"{label} must be a Quantity carrying {unit!r}, got "
                    f"{type(value).__name__} — a bare number is not a "
                    f"declaration"
                )
            value.require_compatible(unit, context=f"component rating {label}")
            # A zero rating is not a small rating: it is a component that may
            # not be used at all, and dividing by it would report infinity as
            # though it were a measurement.
            if value.magnitude_in(unit) <= 0.0:
                raise InvalidScientificProblem(
                    f"{label} must be strictly positive, got {value}"
                )
        factor = float(self.derating_factor)
        if not 0.0 < factor <= 1.0:
            raise InvalidScientificProblem(
                f"derating_factor must lie in (0, 1], got {factor!r}; a "
                f"factor above 1 would use more of a component than it is "
                f"rated for while reporting that it is inside its rating"
            )
        object.__setattr__(self, "derating_factor", factor)

    @property
    def is_empty(self) -> bool:
        """True when no rating was declared — every rating condition UNKNOWN."""
        return (
            self.rated_power is None
            and self.maximum_working_voltage is None
            and self.maximum_current is None
            and self.compliance_voltage is None
        )

    def to_dict(self) -> dict[str, Any]:
        def encode(value: Quantity | None) -> dict[str, Any] | None:
            return value.to_dict() if value is not None else None

        return {
            "schema": COMPONENT_RATING_SCHEMA,
            "rated_power": encode(self.rated_power),
            "maximum_working_voltage": encode(self.maximum_working_voltage),
            "maximum_current": encode(self.maximum_current),
            "compliance_voltage": encode(self.compliance_voltage),
            "derating_factor": self.derating_factor,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ComponentRating":
        require_schema(payload, COMPONENT_RATING_SCHEMA)

        def decode(key: str) -> Quantity | None:
            raw = payload.get(key)
            return Quantity.from_dict(raw) if raw else None

        return cls(
            rated_power=decode("rated_power"),
            maximum_working_voltage=decode("maximum_working_voltage"),
            maximum_current=decode("maximum_current"),
            compliance_voltage=decode("compliance_voltage"),
            derating_factor=float(payload.get("derating_factor", NO_DERATING)),
        )


RESISTOR_OHM_MODEL = ScientificModelDefinition(
    model_id="electrical.dc.resistor_ohm",
    version=DC_MODEL_VERSION,
    name="Resistor constitutive relation (Ohm's law)",
    domain="electrical",
    model_type=ModelType.CONSTITUTIVE_MODEL,
    description=(
        "Relates the voltage across an ideal linear resistor to the current "
        "through it: V = I R, with V measured node_a -> node_b and I "
        "positive in the same direction."
    ),
    inputs=(
        ModelInputSpec(
            name="resistance",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar="ohm",
            description="Element resistance; strictly positive in V0.",
        ),
        ModelInputSpec(
            name="voltage_across",
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar="volt",
            description="V(node_a) - V(node_b).",
        ),
        # ---- optional, component-supplied ratings ------------------------
        # The two rating conditions below have always existed and have always
        # been correct; what they lacked was any declared input to read. They
        # are enumerated here, `required=False`, for the same reason the
        # material limits are: a reader holding only this record can see which
        # declaration unlocks which condition, and a boundary can derive the
        # payload's description from it instead of restating it.
        #
        # Omitting one leaves its condition UNKNOWN, which is the honest
        # verdict for a part whose datasheet nobody supplied. An unrated part
        # is not an unlimited part.
        ModelInputSpec(
            name=RATED_POWER,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=POWER_UNIT,
            required=False,
            description=(
                "Rated dissipation of the element, against the reference "
                "ambient its datasheet states. Unlocks "
                f"{DISSIPATED_POWER_UTILIZATION}."
            ),
        ),
        ModelInputSpec(
            name=MAXIMUM_WORKING_VOLTAGE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=VOLTAGE_UNIT,
            required=False,
            description=(
                "Maximum working voltage across the element. Unlocks "
                f"{WORKING_VOLTAGE_UTILIZATION}, which for a high-value part "
                f"binds before the dissipation rating does."
            ),
        ),
        ModelInputSpec(
            name=DERATING_FACTOR,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=DIMENSIONLESS,
            required=False,
            description=_DERATING_DESCRIPTION,
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric="current_through",
            unit_exemplar="ampere",
            description="Current node_a -> node_b.",
        ),
        ModelOutputSpec(
            metric="dissipated_power",
            unit_exemplar="watt",
            description="Absorbed power, V*I = I^2 R (non-negative).",
        ),
    ),
    assumptions=_DC_ASSUMPTIONS,
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name="resistance",
                minimum=Quantity(0.0, "ohm"),
                minimum_inclusive=False,      # strictly R > 0
                description=(
                    "Strictly positive resistance; zero is a short and "
                    "negative resistance is an active device, both outside "
                    "V0 scope."
                ),
            ),
            # ---- what the physical element survives ----------------------
            #
            # The relation V = I R is exact for an ideal element at any
            # operating point. A real element is not exact at any operating
            # point, and these two conditions are where that is said. Both are
            # stated over a dimensionless utilization of a caller-declared
            # rating, because the bound belongs to the component and one model
            # record serves every component.
            RangeCondition(
                name=DISSIPATED_POWER_UTILIZATION,
                maximum=RATING_UTILIZATION_LIMIT,
                description=(
                    "V*I / (derating * rated_power) <= 1. Above its rated "
                    "dissipation an element's temperature rise carries it out "
                    "of the tolerance band it was specified in and, further "
                    "up, destroys it; the constant, temperature-independent "
                    "resistance this model assumes is the first casualty. "
                    "Rated dissipation is defined against a stated reference "
                    "ambient in IEC 60115-1 (Fixed resistors for use in "
                    "electronic equipment, Part 1: Generic specification), "
                    "Clause 2, which is why the derating fraction is a "
                    "declared input rather than a constant here. UNKNOWN "
                    "unless a rated_power is declared."
                ),
            ),
            RangeCondition(
                name=WORKING_VOLTAGE_UTILIZATION,
                maximum=RATING_UTILIZATION_LIMIT,
                description=(
                    "|V| / (derating * maximum_working_voltage) <= 1. A "
                    "second and independent limit: for a high-value element "
                    "the voltage rating binds long before the dissipation "
                    "rating does, and exceeding it breaks the element down "
                    "across its body or its coating rather than by "
                    "dissipation. IEC 60115-1 specifies a maximum element "
                    "voltage alongside the rated dissipation for this reason. "
                    "UNKNOWN unless a maximum_working_voltage is declared."
                ),
            ),
        ),
        description=(
            "Linear passive resistive operation, within the dissipation and "
            "working-voltage ratings the element was specified for."
        ),
    ),
    required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
)


KCL_MODEL = ScientificModelDefinition(
    model_id="electrical.dc.kcl",
    version=DC_MODEL_VERSION,
    name="Kirchhoff current law (nodal charge balance)",
    domain="electrical",
    model_type=ModelType.FUNDAMENTAL_RELATION,
    description=(
        "Algebraic current balance at a node: the signed sum of currents "
        "leaving a node through all connected elements is zero. Expresses "
        "charge conservation for a lumped circuit."
    ),
    inputs=(
        ModelInputSpec(
            name="node_voltage",
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar="volt",
            description="Potential of the node relative to the reference.",
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric="net_current_out",
            unit_exemplar="ampere",
            description="Signed sum of currents leaving the node; zero when satisfied.",
        ),
    ),
    assumptions=_DC_ASSUMPTIONS + (
        "no charge accumulation at nodes (lumped assumption)",
    ),
    validity=ValidityDomain(
        description=(
            "Valid for lumped circuits; not validated for distributed or "
            "high-frequency regimes where the lumped assumption fails."
        )
    ),
    required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
)


IDEAL_VOLTAGE_SOURCE_MODEL = ScientificModelDefinition(
    model_id="electrical.dc.ideal_voltage_source",
    version=DC_MODEL_VERSION,
    name="Ideal independent DC voltage source relation",
    domain="electrical",
    model_type=ModelType.APPROXIMATION,
    description=(
        "Imposes V(positive_node) - V(negative_node) = source_voltage "
        "irrespective of the current drawn. An idealisation: real sources "
        "have internal impedance and finite compliance."
    ),
    inputs=(
        ModelInputSpec(
            name="source_voltage",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar="volt",
            description="Imposed terminal voltage difference.",
        ),
        ModelInputSpec(
            name="terminal_voltage",
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar="volt",
            description="V(positive_node) - V(negative_node).",
        ),
        # ---- optional, source-supplied rating -----------------------------
        # `source_current_utilization` below is the condition this unlocks.
        # A source with no declared current limit is an *ideal* source, which
        # is what the model record says it models and what no real supply is.
        ModelInputSpec(
            name=MAXIMUM_CURRENT,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=CURRENT_UNIT,
            required=False,
            description=(
                "Maximum current the source can deliver. Unlocks "
                f"{SOURCE_CURRENT_UTILIZATION}."
            ),
        ),
        ModelInputSpec(
            name=DERATING_FACTOR,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=DIMENSIONLESS,
            required=False,
            description=_DERATING_DESCRIPTION,
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric="source_current",
            unit_exemplar="ampere",
            description=(
                "Branch current leaving the positive node through the "
                "source; negative when the source delivers power."
            ),
        ),
    ),
    assumptions=_DC_ASSUMPTIONS + (
        "zero internal impedance",
        "unlimited current compliance",
    ),
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name=SOURCE_CURRENT_UTILIZATION,
                maximum=RATING_UTILIZATION_LIMIT,
                description=(
                    "|I| / (derating * maximum_current) <= 1. This model's "
                    "declared assumption is *unlimited* current compliance. "
                    "No real source has it: past its current limit a supply "
                    "either folds back or drops out of regulation, and in "
                    "both cases the terminal voltage stops being the imposed "
                    "constant this model asserts. The condition is the "
                    "assumption made falsifiable against a declared rating; "
                    "it is UNKNOWN unless a maximum_current is declared, "
                    "because an undeclared limit is not an absent one."
                ),
            ),
        ),
        description=(
            "Idealisation, applicable while the source stays inside the "
            "current limit it was declared to have. Not validated against "
            "real source behaviour near that limit."
        ),
    ),
    required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
)


IDEAL_CURRENT_SOURCE_MODEL = ScientificModelDefinition(
    model_id="electrical.dc.ideal_current_source",
    version=DC_MODEL_VERSION,
    name="Ideal independent DC current source relation",
    domain="electrical",
    model_type=ModelType.APPROXIMATION,
    description=(
        "Imposes a fixed current from_node -> to_node inside the source, "
        "irrespective of the terminal voltage that develops across it. An "
        "idealisation: real sources have finite output impedance and a "
        "limited compliance voltage."
    ),
    inputs=(
        ModelInputSpec(
            name="source_current",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar="ampere",
            description="Imposed current, positive from_node -> to_node.",
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric="terminal_voltage",
            unit_exemplar="volt",
            description=(
                "V(from_node) - V(to_node) that the surrounding network "
                "develops across the source."
            ),
        ),
    ),
    assumptions=_DC_ASSUMPTIONS + (
        "infinite output impedance",
        "unlimited compliance voltage",
    ),
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name=COMPLIANCE_VOLTAGE_UTILIZATION,
                maximum=RATING_UTILIZATION_LIMIT,
                description=(
                    "|V_terminal| / (derating * compliance_voltage) <= 1. The "
                    "dual of the voltage source's limit and the direct "
                    "falsification of this model's declared *unlimited "
                    "compliance voltage*: a real current source holds its "
                    "current only while the network lets it develop a "
                    "terminal voltage inside its compliance range, and above "
                    "that range the current it delivers is set by the "
                    "network, not by the source. UNKNOWN unless a "
                    "compliance_voltage is declared."
                ),
            ),
        ),
        description=(
            "Idealisation, applicable while the network keeps the terminal "
            "voltage inside the compliance range the source was declared to "
            "have. Not validated against real source behaviour near that "
            "range."
        ),
    ),
    required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
)


DC_MODELS = (
    KCL_MODEL,
    RESISTOR_OHM_MODEL,
    IDEAL_VOLTAGE_SOURCE_MODEL,
    IDEAL_CURRENT_SOURCE_MODEL,
)


# =====================================================================
# Computed context for the rating conditions
# =====================================================================
#
# Pure functions over records, in the character of the rest of this module.
# Each returns ``None`` when it was not given what it needs, and the
# assemblers drop the key rather than inventing a value, so an undeclared
# rating reaches ``ValidityDomain.assess`` as UNKNOWN. There is no path here
# by which omitting a rating yields IN_DOMAIN.


def _magnitude(value: Any, unit: str, label: str) -> float | None:
    """A supplied quantity's magnitude in ``unit``; ``None`` stays ``None``.

    A non-``Quantity`` that is not ``None`` is refused rather than skipped: a
    caller who passed the wrong type declared something wrong, which is a
    different situation from a caller who declared nothing, and collapsing the
    two would turn a specification error into a silent UNKNOWN.
    """
    if value is None:
        return None
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(
            f"{label} must be a Quantity carrying {unit!r}, got "
            f"{type(value).__name__} — a bare number is not a declaration"
        )
    value.require_compatible(unit, context=label)
    return value.magnitude_in(unit)


def _utilization(
    used: float | None, rating: float | None, derating: float
) -> Quantity | None:
    """|used| / (derating * rating), or ``None`` if either side is absent.

    The absolute value is taken on the numerator only: a rating is a magnitude
    and a sign on the operating point is a direction, so a current of -2 A
    uses as much of a 3 A rating as +2 A does.
    """
    if used is None or rating is None:
        return None
    return Quantity(abs(used) / (derating * rating), DIMENSIONLESS)


def resistor_rating_context(
    *,
    rating: ComponentRating | None = None,
    dissipated_power: Quantity | None = None,
    voltage_across: Quantity | None = None,
) -> dict[str, Quantity]:
    """Utilizations of a resistor's ratings at one operating point.

    ``dissipated_power`` and ``voltage_across`` are *results*, not
    declarations: they are what the solve produced, which is why they arrive
    as arguments rather than out of the problem's parameters. A rating with no
    operating point, and an operating point with no rating, each yield nothing.
    """
    declared = rating or ComponentRating()
    derating = declared.derating_factor
    derived: dict[str, Quantity | None] = {
        DISSIPATED_POWER_UTILIZATION: _utilization(
            _magnitude(dissipated_power, POWER_UNIT, "dissipated_power"),
            _magnitude(declared.rated_power, POWER_UNIT, "rated_power"),
            derating,
        ),
        WORKING_VOLTAGE_UTILIZATION: _utilization(
            _magnitude(voltage_across, VOLTAGE_UNIT, "voltage_across"),
            _magnitude(
                declared.maximum_working_voltage,
                VOLTAGE_UNIT,
                "maximum_working_voltage",
            ),
            derating,
        ),
    }
    return {name: value for name, value in derived.items() if value is not None}


def voltage_source_rating_context(
    *,
    rating: ComponentRating | None = None,
    source_current: Quantity | None = None,
) -> dict[str, Quantity]:
    """Utilization of a voltage source's current rating at one operating point."""
    declared = rating or ComponentRating()
    utilization = _utilization(
        _magnitude(source_current, CURRENT_UNIT, "source_current"),
        _magnitude(declared.maximum_current, CURRENT_UNIT, "maximum_current"),
        declared.derating_factor,
    )
    return {} if utilization is None else {SOURCE_CURRENT_UTILIZATION: utilization}


def current_source_rating_context(
    *,
    rating: ComponentRating | None = None,
    terminal_voltage: Quantity | None = None,
) -> dict[str, Quantity]:
    """Utilization of a current source's compliance range at one operating point."""
    declared = rating or ComponentRating()
    utilization = _utilization(
        _magnitude(terminal_voltage, VOLTAGE_UNIT, "terminal_voltage"),
        _magnitude(
            declared.compliance_voltage, VOLTAGE_UNIT, "compliance_voltage"
        ),
        declared.derating_factor,
    )
    return (
        {} if utilization is None else {COMPLIANCE_VOLTAGE_UTILIZATION: utilization}
    )


def assess_resistor_validity(
    problem: ScientificProblem,
    *,
    rating: ComponentRating | None = None,
    dissipated_power: Quantity | None = None,
    voltage_across: Quantity | None = None,
) -> ValidityAssessment:
    """Was the ideal resistor relation applicable to this element, here?

    **Validity, not validation.** The DC solver's own
    :class:`ValidationReport` answers whether the linear system it assembled
    was solved to residual; this answers whether the element it assembled was
    being used inside what it is rated for. A network can be solved perfectly
    and still be one whose resistor is at three times its rated dissipation,
    and those two facts must be separately reportable.
    """
    context = problem.validity_context(
        extra=resistor_rating_context(
            rating=rating,
            dissipated_power=dissipated_power,
            voltage_across=voltage_across,
        )
    )
    return RESISTOR_OHM_MODEL.assess_validity(context)


def assess_voltage_source_validity(
    problem: ScientificProblem,
    *,
    rating: ComponentRating | None = None,
    source_current: Quantity | None = None,
) -> ValidityAssessment:
    """Was the ideal voltage source relation applicable at this current?"""
    context = problem.validity_context(
        extra=voltage_source_rating_context(
            rating=rating, source_current=source_current
        )
    )
    return IDEAL_VOLTAGE_SOURCE_MODEL.assess_validity(context)


def assess_current_source_validity(
    problem: ScientificProblem,
    *,
    rating: ComponentRating | None = None,
    terminal_voltage: Quantity | None = None,
) -> ValidityAssessment:
    """Was the ideal current source relation applicable at this terminal voltage?"""
    context = problem.validity_context(
        extra=current_source_rating_context(
            rating=rating, terminal_voltage=terminal_voltage
        )
    )
    return IDEAL_CURRENT_SOURCE_MODEL.assess_validity(context)


def models_for_circuit(circuit) -> tuple[ScientificModelDefinition, ...]:
    """The models a specific circuit actually invokes.

    Attaching every domain model to every circuit would overstate what a
    result depends on: a resistor-only network makes no claim about ideal
    voltage sources, and a reader auditing that result should not be told it
    does. Order is fixed, so the tuple is deterministic.

    Kirchhoff's current law is always present — it is the balance every
    nodal analysis solves, regardless of which element types appear.
    """
    active: list[ScientificModelDefinition] = [KCL_MODEL]
    if circuit.resistors:
        active.append(RESISTOR_OHM_MODEL)
    if circuit.voltage_sources:
        active.append(IDEAL_VOLTAGE_SOURCE_MODEL)
    if circuit.current_sources:
        active.append(IDEAL_CURRENT_SOURCE_MODEL)
    return tuple(active)


def assumptions_for_models(models) -> tuple[str, ...]:
    """Deterministic, de-duplicated union of the models' assumptions.

    First-seen order is preserved so the same active set always yields the
    same sequence — a result's assumption list must not depend on set
    iteration order.
    """
    seen: dict[str, None] = {}
    for model in models:
        for assumption in model.assumptions:
            seen.setdefault(assumption, None)
    return tuple(seen)


def build_dc_model_registry() -> ModelRegistry:
    """A fresh registry containing the DC models.

    Returns a new instance every call: the platform has no global mutable
    model registry, so a caller's model set can never be mutated elsewhere.
    """
    return ModelRegistry(DC_MODELS)


def dc_solver_capabilities() -> frozenset[SolverCapability]:
    """What an Electrical DC solver declares it can do.

    Both the domain capability and the mathematical shape it reduces to: a
    linear system. The latter is what makes the solver discoverable to a
    future planner reasoning about problem form rather than domain.
    """
    return frozenset({ELECTRICAL_DC_LINEAR, CoreCapabilities.LINEAR_SYSTEM})
