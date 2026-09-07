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

from ...derived_context import (
    DomainValidityContext,
    assembled_validity_context,
    caller_declared,
)
from ...repair import (
    ConditionInversions,
    ConditionRepair,
    ModelInversionTable,
    MonotoneInversion,
    RefusedInversion,
    condition_repairs,
)
from ....scientific.composition import QuantityDependency, QuantityTransfer
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
from .components import resistor_problem_id

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
TEMPERATURE_UNIT = "kelvin"
DIMENSIONLESS = "dimensionless"

# --- names of the ratings a caller may declare -------------------------------
# Names, not conventions. Each is enumerated by the model record it belongs to
# as an optional ``ModelInputSpec``, so the payload boundary derives its
# description of these fields from the records instead of restating them, and
# a reader holding only the records can see which declaration unlocks which
# condition. They are the field names of :class:`ComponentRating`.
RATED_POWER = "rated_power"
#: The two halves of the pair that makes a rated dissipation a curve rather
#: than a number. IEC 60115-1 states a rated dissipation against a reference
#: ambient and requires a derating characteristic above it; a datasheet prints
#: "0.4 W at 70 C" and a straight line falling to zero at the permissible film
#: temperature. Declaring both turns `dissipated_power_utilization` from a
#: comparison against a constant into a comparison against that line.
RATED_POWER_TEMPERATURE = "rated_power_temperature"
#: The ambient this element sits in. Not a name this domain computes and not
#: one a circuit statement carries: it is supplied from outside, and the only
#: sanctioned way in is a declared :class:`QuantityTransfer`. See
#: :func:`ambient_transfer_declaration`.
AMBIENT_TEMPERATURE = "ambient_temperature"
ZERO_POWER_TEMPERATURE = "zero_power_temperature"
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

#: The discriminator for the lumped-circuit assumption, as a fraction of a
#: wavelength: ``L / lambda``, with ``lambda = c / f``.
LUMPED_ELECTRICAL_LENGTH = "lumped_electrical_length"

#: ``L <= lambda / 10``. The standard engineering boundary for treating a
#: circuit as lumped rather than distributed, and the one the KCL model's own
#: ValidityDomain description has always named in prose ("valid for lumped
#: circuits; not validated for distributed or high-frequency regimes"). The
#: value is not load-bearing for a DC model, where the ratio is identically
#: zero — it is written down so that the condition states a real physical
#: boundary rather than a tautology, and so that a future non-DC circuit model
#: inherits a bound rather than inventing one.
LUMPED_ELECTRICAL_LENGTH_LIMIT = Quantity(0.1, DIMENSIONLESS)

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

    **A rated dissipation is a pair, and this record now lets a caller say so.**
    ``rated_power`` alone is a number; ``rated_power`` with
    ``rated_power_temperature`` and ``zero_power_temperature`` is the derating
    line the datasheet prints — 0.4 W at 70 C falling to zero at 155 C. The two
    temperatures are declared together or not at all, because one without the
    other does not describe a line, and both require a ``rated_power`` for the
    line to pass through. Above the rating temperature the effective rating is
    lower than the printed one, and a part checked against the printed number in
    a hot ambient is checked against a rating it no longer has.

    Omitting the pair is not an error and changes nothing: the utilization stays
    the comparison against the constant it has always been. What omitting it
    costs is stated on the condition itself.
    """

    rated_power: Quantity | None = None
    rated_power_temperature: Quantity | None = None
    zero_power_temperature: Quantity | None = None
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
        for label in ("rated_power_temperature", "zero_power_temperature"):
            value = getattr(self, label)
            if value is None:
                continue
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem(
                    f"{label} must be a Quantity carrying "
                    f"{TEMPERATURE_UNIT!r}, got {type(value).__name__} — a "
                    f"bare number is not a declaration"
                )
            value.require_compatible(
                TEMPERATURE_UNIT, context=f"component rating {label}"
            )
            if value.magnitude_in(TEMPERATURE_UNIT) <= 0.0:
                raise InvalidScientificProblem(
                    f"{label} must be strictly positive on an absolute scale, "
                    f"got {value}"
                )
        # The pair is a line. Half a line is not a weaker declaration, it is an
        # incomplete one, and admitting it would leave the reader of a report
        # unable to say which rating was compared against.
        rated_at = self.rated_power_temperature
        zero_at = self.zero_power_temperature
        if (rated_at is None) != (zero_at is None):
            raise InvalidScientificProblem(
                "rated_power_temperature and zero_power_temperature are the "
                "two ends of one derating line and must be declared together; "
                "one without the other states no line"
            )
        if rated_at is not None:
            if self.rated_power is None:
                raise InvalidScientificProblem(
                    "a derating line was declared without a rated_power for it "
                    "to pass through; the two temperatures say where the line "
                    "starts and ends, not how high it is"
                )
            if (zero_at.magnitude_in(TEMPERATURE_UNIT)
                    <= rated_at.magnitude_in(TEMPERATURE_UNIT)):
                raise InvalidScientificProblem(
                    f"zero_power_temperature ({zero_at}) must be above "
                    f"rated_power_temperature ({rated_at}); a derating line "
                    f"falls with temperature and a non-positive span would "
                    f"make its slope infinite or negative"
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
            "rated_power_temperature": encode(self.rated_power_temperature),
            "zero_power_temperature": encode(self.zero_power_temperature),
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
            rated_power_temperature=decode("rated_power_temperature"),
            zero_power_temperature=decode("zero_power_temperature"),
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
            name=RATED_POWER_TEMPERATURE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            required=False,
            description=(
                "The reference ambient the rated dissipation is stated at — "
                "the 70 in a datasheet's P70. Declared together with "
                f"{ZERO_POWER_TEMPERATURE}; the pair turns "
                f"{DISSIPATED_POWER_UTILIZATION} from a comparison against a "
                "constant into a comparison against the derating line. "
                "Omitting the pair leaves that condition exactly as it was."
            ),
        ),
        ModelInputSpec(
            name=ZERO_POWER_TEMPERATURE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            required=False,
            description=(
                "The ambient at which the derating line reaches zero power, "
                "which for a film resistor is the permissible film "
                f"temperature. Declared together with {RATED_POWER_TEMPERATURE}."
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
                    "The fraction of this element's dissipation rating in "
                    "use, bounded by 1. Above its rated dissipation an "
                    "element's temperature rise carries it out of the "
                    "tolerance band it was specified in and, further up, "
                    "destroys it; the constant, temperature-independent "
                    "resistance this model assumes is the first casualty. "
                    "TWO READINGS, and which one applies depends on what the "
                    "caller declared. (1) With rated_power alone: "
                    "V*I / (derating * rated_power) <= 1, the comparison "
                    "against a constant. (2) With rated_power, "
                    f"{RATED_POWER_TEMPERATURE} and {ZERO_POWER_TEMPERATURE}: "
                    "the comparison against the derating LINE those three "
                    "points define, expressed as "
                    "(T_ambient + (V*I / derating) * R_implied) / "
                    "T_zero_power <= 1, with R_implied = (T_zero_power - "
                    "T_rated) / rated_power. That is algebraically the same "
                    "statement as V*I <= derating * rated_power * "
                    "(T_zero - T_amb) / (T_zero - T_rated), and it is written "
                    "on the temperature axis because the power form is "
                    "infinite at and above T_zero_power, where a real part "
                    "still has a real answer -- it may not be used at all. "
                    "Rated dissipation is defined against a stated reference "
                    "ambient in IEC 60115-1 (Fixed resistors for use in "
                    "electronic equipment, Part 1: Generic specification), "
                    "Clause 2, and the derating characteristic above that "
                    "ambient is required by the same clause; reading (2) is "
                    "that characteristic and reading (1) is what remains "
                    "sayable without it. UNKNOWN unless a rated_power is "
                    "declared, and also UNKNOWN when a derating line is "
                    "declared without the ambient it must be evaluated at."
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
        # Neither utilization is declarable. Both are ratios this module
        # computes from a rating and an operating point, and a caller
        # parameter of either name would decide the condition that reads it —
        # a resistor with no rating at all reporting IN_DOMAIN over two
        # numbers nobody computed. Reserving them makes the assessment refuse
        # such a problem instead of answering it.
        derived_quantities=frozenset(
            {DISSIPATED_POWER_UTILIZATION, WORKING_VOLTAGE_UTILIZATION}
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
        conditions=(
            RangeCondition(
                name=LUMPED_ELECTRICAL_LENGTH,
                maximum=LUMPED_ELECTRICAL_LENGTH_LIMIT,
                description=(
                    "L / lambda <= 0.1, the circuit's largest dimension as a "
                    "fraction of a wavelength. This is the discriminator for "
                    "the lumped assumption that the description below has "
                    "always named in prose: charge conservation at a node is "
                    "exact when the circuit is electrically small, and fails "
                    "when propagation delay across it is comparable with the "
                    "period, because then the currents at the two ends of a "
                    "conductor are not the same current. Below one tenth of a "
                    "wavelength is the standard boundary. "
                    "**Satisfied by this model's own scope, not measured from "
                    "a caller's context.** lambda = c / f, and this is a "
                    "steady-state DC model: f = 0 is an assumption of the "
                    "record rather than a value anybody supplies, so lambda "
                    "is unbounded and the ratio is identically zero for every "
                    "circuit this model is ever applied to, of any size. "
                    "The condition is stated rather than assumed because a "
                    "model that declares no conditions is UNKNOWN, and "
                    "UNKNOWN here claimed an ignorance this model does not "
                    "have: it does know where its assumption fails, and it "
                    "knows its own scope keeps it on the right side. Stating "
                    "the boundary and showing it is met is the honest form of "
                    "that; declining to look is not. A circuit model at "
                    "non-zero frequency would supply a real ratio here and "
                    "this bound would begin to bite, which is the other "
                    "reason to write it as a ratio against a limit rather "
                    "than as a flag."
                ),
            ),
        ),
        description=(
            "Valid for lumped circuits; not validated for distributed or "
            "high-frequency regimes where the lumped assumption fails."
        ),
        # Reserved even though the value is a constant zero fixed by this
        # model's own scope. The point is not that a caller could get the
        # number wrong; it is that a caller could supply it at all, and a
        # condition satisfied by the record's own assumption must not be
        # satisfiable by a parameter instead. If a distributed-circuit model
        # ever computes a real ratio here, the name is already protected.
        derived_quantities=frozenset({LUMPED_ELECTRICAL_LENGTH}),
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
        derived_quantities=frozenset({SOURCE_CURRENT_UTILIZATION}),
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
        derived_quantities=frozenset({COMPLIANCE_VOLTAGE_UTILIZATION}),
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


def _derated_power_utilization(
    *,
    dissipated: float | None,
    rated: float | None,
    rated_at: float,
    zero_at: float,
    ambient: float | None,
    derating: float,
) -> Quantity | None:
    """The dissipation utilization when the rating is a line rather than a number.

    WHY THIS IS A TEMPERATURE RATIO AND NOT A POWER RATIO
    -----------------------------------------------------
    The obvious form is ``P / P_eff`` with
    ``P_eff = P_rated (T_zero - T_amb) / (T_zero - T_rated)``. It is right
    wherever it is defined, and it is undefined exactly where the answer matters
    most: at and above ``T_zero`` the effective rating is zero or negative, the
    ratio is infinite or signed, and a condition forced to report a non-finite
    number is a condition that has stopped measuring.

    So the same statement is made in the form that stays finite. A derating line
    from ``(T_rated, P_rated)`` to ``(T_zero, 0)`` has slope
    ``-P_rated / (T_zero - T_rated)``, and the reciprocal of that slope is a
    thermal resistance, ``R_implied = (T_zero - T_rated) / P_rated`` in K/W.
    **That is what a derating curve is**: the manufacturer's statement of how
    much temperature rise the part's own construction produces per watt, drawn
    as a line instead of printed as a number. The element is inside its rating
    exactly when the temperature that line implies stays at or below ``T_zero``:

        utilization = (T_amb + (P / derating) * R_implied) / T_zero

    which is algebraically equivalent to ``P <= derating * P_eff`` wherever the
    power form is defined, is finite everywhere, and reports a number above 1
    rather than an infinity when the ambient alone has already consumed the
    rating. Both temperatures are absolute, the same convention
    ``operating_temperature_utilization`` uses in the material domain.

    Returns ``None`` -- and therefore UNKNOWN -- when the ambient is not
    supplied. A caller who declares a derating line and does not say what
    ambient the part sits in has not said enough to be told whether it is inside
    its rating, and falling back to the printed number would answer a question
    they did not ask.
    """
    if dissipated is None or rated is None or ambient is None:
        return None
    implied_thermal_resistance = (zero_at - rated_at) / rated
    implied_temperature = (
        ambient + (abs(dissipated) / derating) * implied_thermal_resistance
    )
    return Quantity(implied_temperature / zero_at, DIMENSIONLESS)


def resistor_rating_context(
    *,
    rating: ComponentRating | None = None,
    dissipated_power: Quantity | None = None,
    voltage_across: Quantity | None = None,
    ambient_temperature: Quantity | None = None,
) -> dict[str, Quantity]:
    """Utilizations of a resistor's ratings at one operating point.

    ``dissipated_power`` and ``voltage_across`` are *results*, not
    declarations: they are what the solve produced, which is why they arrive as
    arguments rather than out of the problem's parameters. A rating with no
    operating point, and an operating point with no rating, each yield nothing.

    ``ambient_temperature`` is a *declaration* and arrives the same way for a
    different reason: it belongs to the thermal environment the element sits in,
    which no electrical problem statement carries. It is read only when the
    rating declares a derating line, and it is what makes that line evaluable.

    **One condition, two readings, and which one applies depends on what was
    declared.** With no derating line, ``dissipated_power_utilization`` is
    ``P / (derating * rated_power)``, exactly as it has always been. With a
    line, it becomes the temperature form in
    :func:`_derated_power_utilization`. The same name carries both because both
    are "the fraction of this element's rating in use" and both are bounded by
    1; the domain documentation states which applies when, as it already does
    for ``convection_property_range_utilization``, whose formula likewise
    depends on which route the caller declared.
    """
    declared = rating or ComponentRating()
    derating = declared.derating_factor
    rated = _magnitude(declared.rated_power, POWER_UNIT, "rated_power")
    rated_at = _magnitude(
        declared.rated_power_temperature, TEMPERATURE_UNIT,
        "rated_power_temperature",
    )
    zero_at = _magnitude(
        declared.zero_power_temperature, TEMPERATURE_UNIT,
        "zero_power_temperature",
    )
    dissipated = _magnitude(dissipated_power, POWER_UNIT, "dissipated_power")
    ambient = _magnitude(
        ambient_temperature, TEMPERATURE_UNIT, "ambient_temperature"
    )
    if rated_at is None or zero_at is None:
        power_utilization = _utilization(dissipated, rated, derating)
    else:
        power_utilization = _derated_power_utilization(
            dissipated=dissipated, rated=rated, rated_at=rated_at,
            zero_at=zero_at, ambient=ambient, derating=derating,
        )
    derived: dict[str, Quantity | None] = {
        DISSIPATED_POWER_UTILIZATION: power_utilization,
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


def kcl_validity_context() -> dict[str, Quantity]:
    """The context :data:`KCL_MODEL` is assessed against. Takes no arguments.

    That signature is the statement. Every other validity context in this
    domain is a function of something a caller declared or a solver produced;
    this one is a function of nothing, because the quantity it supplies is
    fixed by the model's own scope rather than by any particular circuit.

    ``lumped_electrical_length`` is ``L / lambda`` with ``lambda = c / f``.
    ``KCL_MODEL`` is a steady-state DC model — ``f = 0`` is in its
    ``assumptions``, not in its inputs — so ``lambda`` is unbounded and the
    ratio is exactly zero for a circuit of any size. Returning a computed zero
    rather than hard-coding IN_DOMAIN keeps the verdict derived from a
    condition, which is the rule the platform is built on: the assessment still
    reads a quantity and compares it with a declared bound, and the reason the
    comparison always passes is visible in the number.

    A non-DC circuit model would supply a real ratio from a declared frequency
    and circuit dimension. This function is where that change would land.
    """
    return {LUMPED_ELECTRICAL_LENGTH: Quantity(0.0, DIMENSIONLESS)}


def assess_kcl_validity() -> ValidityAssessment:
    """Is nodal charge balance applicable here? Yes, and for a stated reason."""
    return KCL_MODEL.assess_validity(
        declared={}, assembled=kcl_validity_context()
    )


def ambient_transfer_declaration(
    *, source_problem_id: str, source_quantity: str, component_id: str
) -> QuantityDependency:
    """The declaration an ambient must cross under to reach this domain.

    THE CROSSING THIS EXISTS FOR. A resistor's rated dissipation is stated
    against a reference ambient and derates away from it, so a declared
    derating line cannot be evaluated without the ambient the part sits in --
    and no circuit statement carries one. It came in from whatever body shared
    the element's ``component_id``, matched in a dict comprehension. No record
    said it crossed, no reader could tell this model's verdict depended on
    another problem's declaration, and nothing checked that the two sides meant
    the same quantity at the same instant.

    This function is the electrical half of the contract: the target name and
    the unit are this domain's to state, because this domain is the one that
    reads them. The source half is the supplying domain's, and neither side
    gets to assume the other's.
    """
    return QuantityDependency(
        source_problem_id=source_problem_id,
        source_quantity=source_quantity,
        target_problem_id=resistor_problem_id(component_id),
        target_quantity=AMBIENT_TEMPERATURE,
        unit_exemplar=TEMPERATURE_UNIT,
        name=f"ambient_into_resistor:{component_id}",
        description=(
            "The ambient the element sits in, which places its derating line. "
            "Without it a declared line cannot be evaluated and "
            "dissipated_power_utilization is UNKNOWN rather than answered "
            "from the printed number."
        ),
    )


def _received_ambient(ambient: "QuantityTransfer | None") -> Quantity | None:
    """The ambient, taken out of the declaration it crossed under.

    FAIL-CLOSED, and this is the whole of it: a bare ``Quantity`` is refused.
    A caller holding a number that came from another problem must say so with
    a record, or this domain will not read it. That is the difference between
    a crossing and a coincidence of component ids.
    """
    if ambient is None:
        return None
    if not isinstance(ambient, QuantityTransfer):
        raise InvalidScientificProblem(
            f"the ambient reaching this element arrived as a "
            f"{type(ambient).__name__}, not a declared QuantityTransfer. It "
            f"is supplied by another problem, and a value that crosses a "
            f"domain boundary without a record saying where it came from and "
            f"when is a value nobody can check. Build one with "
            f"ambient_transfer_declaration()"
        )
    if ambient.dependency.target_quantity != AMBIENT_TEMPERATURE:
        raise InvalidScientificProblem(
            f"the transfer reaching this element declares its target as "
            f"{ambient.dependency.target_quantity!r}, not "
            f"{AMBIENT_TEMPERATURE!r}. A declaration that names a different "
            f"quantity is not a declaration of this one"
        )
    return ambient.received_as(TEMPERATURE_UNIT)


def assess_resistor_validity(
    problem: ScientificProblem,
    *,
    rating: ComponentRating | None = None,
    dissipated_power: Quantity | None = None,
    voltage_across: Quantity | None = None,
    ambient: "QuantityTransfer | None" = None,
) -> ValidityAssessment:
    """Was the ideal resistor relation applicable to this element, here?

    **Validity, not validation.** The DC solver's own
    :class:`ValidationReport` answers whether the linear system it assembled
    was solved to residual; this answers whether the element it assembled was
    being used inside what it is rated for. A network can be solved perfectly
    and still be one whose resistor is at three times its rated dissipation,
    and those two facts must be separately reportable.

    ``ambient`` is a :class:`QuantityTransfer` rather than a ``Quantity``: it
    is supplied by another problem, and this domain will not read a crossed
    value that arrives without the record of its crossing.
    """
    received = _received_ambient(ambient)
    declared = dict(
        problem.validity_context(
            reserved=RESISTOR_OHM_MODEL.derived_quantities
        )
    )
    if received is not None:
        # Into the DECLARED half, not the assembled one. It is not a quantity
        # this model computed; it is a condition the element is in, and it now
        # arrives with a record saying which problem stated it and when.
        declared.setdefault(AMBIENT_TEMPERATURE, received)
    return RESISTOR_OHM_MODEL.assess_validity(
        declared=declared,
        assembled=resistor_rating_context(
            rating=rating,
            dissipated_power=dissipated_power,
            voltage_across=voltage_across,
            ambient_temperature=received,
        ),
    )


def assess_voltage_source_validity(
    problem: ScientificProblem,
    *,
    rating: ComponentRating | None = None,
    source_current: Quantity | None = None,
) -> ValidityAssessment:
    """Was the ideal voltage source relation applicable at this current?"""
    return IDEAL_VOLTAGE_SOURCE_MODEL.assess_validity(
        declared=problem.validity_context(
            reserved=IDEAL_VOLTAGE_SOURCE_MODEL.derived_quantities
        ),
        assembled=voltage_source_rating_context(
            rating=rating, source_current=source_current
        ),
    )


def assess_current_source_validity(
    problem: ScientificProblem,
    *,
    rating: ComponentRating | None = None,
    terminal_voltage: Quantity | None = None,
) -> ValidityAssessment:
    """Was the ideal current source relation applicable at this terminal voltage?"""
    return IDEAL_CURRENT_SOURCE_MODEL.assess_validity(
        declared=problem.validity_context(
            reserved=IDEAL_CURRENT_SOURCE_MODEL.derived_quantities
        ),
        assembled=current_source_rating_context(
            rating=rating, terminal_voltage=terminal_voltage
        ),
    )


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


# =====================================================================
# Repair guidance
# =====================================================================
#
# The mechanism is `engcore.domains.repair`; the algebra is this domain's.
#
# EVERY UTILIZATION HERE IS |used| / (derating * rating), so it is a
# reciprocal in the rating and a reciprocal in the derating factor, and those
# invert exactly. The numerator is never a target: a dissipated power, a
# working voltage, a source current and a terminal voltage are what the
# network solve produced, and each is declared on the model record as a
# VARIABLE for precisely that reason. `RepairTarget` refuses them, so a hint
# saying "draw less current" -- which is not a declaration anyone edits -- is
# not expressible.
#
# THE DERATING LINE IS THE HONEST GAP. With `rated_power_temperature` and
# `zero_power_temperature` both declared, `dissipated_power_utilization` stops
# being P/(d*P_rated) and becomes
#
#     (T_amb + (P/d) (T_zero - T_rated)/P_rated) / T_zero
#
# which is affine in 1/P_rated rather than a power law in it. That form is
# invertible in principle -- but its offset is T_amb/T_zero, and the ambient
# temperature is NOT a declared input of this model: it arrives as an argument
# to `assess_resistor_validity`, crossing in from the thermal body that shares
# the element's component id, and never enters the assessed context. The
# offset therefore cannot be formed from what a repair sees, and the honest
# report is that this reading is not inverted here, with that reason. It is a
# real limitation of where the ambient lives, recorded rather than papered
# over by inverting the constant-rating reading and pretending the line was
# not declared.


def _no_derating_line(context: Mapping[str, Any]) -> bool:
    return not (
        isinstance(context.get(RATED_POWER_TEMPERATURE), Quantity)
        and isinstance(context.get(ZERO_POWER_TEMPERATURE), Quantity)
    )


def _dissipation_offset(context: Mapping[str, Any]) -> Quantity | None:
    """The offset ``A`` of ``dissipated_power_utilization``, for both readings.

    THIS FUNCTION IS THE CAPABILITY THAT CAME BACK. Both readings of this
    condition are reciprocal in the rating and in the derating factor, so the
    exponent was never the problem. The *offset* was:

        with no derating line   u = P / (d P_rated)                  A = 0
        with a derating line    u = T_amb/T_zero
                                    + (P/d)(T_zero - T_rated)/(T_zero P_rated)

    and on the second line ``A = T_amb / T_zero``. The ambient used to cross
    into this model's assessment undeclared, from whatever body shared the
    element's component id, so it was not in the assessed context and the
    offset could not be formed. Both inversions were therefore reported as
    unavailable -- a real capability lost to where a number happened to live.

    It is a declared input of this problem now, arriving under a
    :class:`QuantityTransfer`, so the offset forms and the inversions are real.

    Returns ``None`` when a line is declared and the ambient did NOT cross.
    That is still the honest answer for that case, and ``condition_repairs``
    refuses rather than reading a missing offset as zero -- zero is a different
    algebraic claim, and it would turn an affine form into a power law.
    """
    if _no_derating_line(context):
        # Not "no offset was found": the power-law reading genuinely has none,
        # and saying so is what keeps the two cases apart.
        return Quantity(0.0, DIMENSIONLESS)
    ambient = context.get(AMBIENT_TEMPERATURE)
    zero_at = context.get(ZERO_POWER_TEMPERATURE)
    if not isinstance(ambient, Quantity) or not isinstance(zero_at, Quantity):
        return None
    denominator = zero_at.magnitude_in(TEMPERATURE_UNIT)
    if denominator == 0.0:  # pragma: no cover - ComponentRating refuses it
        return None
    return Quantity(
        ambient.magnitude_in(TEMPERATURE_UNIT) / denominator, DIMENSIONLESS
    )


_AMBIENT_DID_NOT_CROSS = (
    "with a derating line declared this utilization is affine in the "
    "reciprocal of the rating, with offset T_ambient / T_zero_power. No "
    "ambient crossed into this assessment under a declared transfer, so the "
    "offset cannot be formed and the form is not anchored. Supply it with "
    "ambient_transfer_declaration()"
)

_A_LINE_IS_THE_PART_NOT_ITS_USE = (
    "this temperature places the derating line, which is the manufacturer's "
    "statement of what the part is. Moving it to make the element pass would "
    "change the claimed part rather than how it is being used -- the "
    "raise-the-limit move wearing a declared input's name, the same one "
    "`ComponentRating` refuses for a derating factor above 1"
)


_DERATING_ABOVE_ONE = (
    "a derating factor above 1 would use more of a component than it is "
    "rated for while reporting that it is inside its rating, which is the "
    "raise-the-limit move wearing a declared input's name. "
    "`ComponentRating` refuses it, and so does this"
)


RESISTOR_INVERSIONS = ModelInversionTable(
    model=RESISTOR_OHM_MODEL,
    rows=(
        ConditionInversions(
            condition="resistance",
            inversions=(
                MonotoneInversion(
                    target="resistance",
                    exponent=1.0,
                    justification="the condition bounds this declaration itself",
                ),
            ),
        ),
        ConditionInversions(
            condition=DISSIPATED_POWER_UTILIZATION,
            inversions=(
                MonotoneInversion(
                    target=RATED_POWER,
                    exponent=-1.0,
                    offset=_dissipation_offset,
                    justification=(
                        "both readings are reciprocal in the rating: with no "
                        "derating line the utilization is P / (d P_rated), and "
                        "with one it is T_amb/T_zero + (P/d)(T_zero - "
                        "T_rated)/(T_zero P_rated), affine in 1/P_rated"
                    ),
                ),
                MonotoneInversion(
                    target=DERATING_FACTOR,
                    exponent=-1.0,
                    offset=_dissipation_offset,
                    admissible_maximum=Quantity(
                        NO_DERATING, DIMENSIONLESS
                    ),
                    beyond_admissible=_DERATING_ABOVE_ONE,
                    justification=(
                        "both readings are reciprocal in the derating factor, "
                        "which divides the dissipation on the line reading "
                        "exactly as it divides the rating on the other"
                    ),
                ),
            ),
            refusals=(
                RefusedInversion(
                    target=RATED_POWER_TEMPERATURE,
                    reason=_A_LINE_IS_THE_PART_NOT_ITS_USE,
                ),
                RefusedInversion(
                    target=ZERO_POWER_TEMPERATURE,
                    reason=_A_LINE_IS_THE_PART_NOT_ITS_USE,
                ),
            ),
        ),
        ConditionInversions(
            condition=WORKING_VOLTAGE_UTILIZATION,
            inversions=(
                MonotoneInversion(
                    target=MAXIMUM_WORKING_VOLTAGE,
                    exponent=-1.0,
                    justification=(
                        "the utilization is |V| / (d V_max), a reciprocal in "
                        "the rating"
                    ),
                ),
                MonotoneInversion(
                    target=DERATING_FACTOR,
                    exponent=-1.0,
                    admissible_maximum=Quantity(
                        NO_DERATING, DIMENSIONLESS
                    ),
                    beyond_admissible=_DERATING_ABOVE_ONE,
                    justification=(
                        "the utilization is |V| / (d V_max), a reciprocal in "
                        "the derating factor"
                    ),
                ),
            ),
        ),
    ),
)


VOLTAGE_SOURCE_INVERSIONS = ModelInversionTable(
    model=IDEAL_VOLTAGE_SOURCE_MODEL,
    rows=(
        ConditionInversions(
            condition=SOURCE_CURRENT_UTILIZATION,
            inversions=(
                MonotoneInversion(
                    target=MAXIMUM_CURRENT,
                    exponent=-1.0,
                    justification=(
                        "the utilization is |I| / (d I_max), a reciprocal in "
                        "the rating"
                    ),
                ),
                MonotoneInversion(
                    target=DERATING_FACTOR,
                    exponent=-1.0,
                    admissible_maximum=Quantity(
                        NO_DERATING, DIMENSIONLESS
                    ),
                    beyond_admissible=_DERATING_ABOVE_ONE,
                    justification=(
                        "the utilization is |I| / (d I_max), a reciprocal in "
                        "the derating factor"
                    ),
                ),
            ),
        ),
    ),
)


CURRENT_SOURCE_INVERSIONS = ModelInversionTable(
    model=IDEAL_CURRENT_SOURCE_MODEL,
    rows=(
        ConditionInversions(
            condition=COMPLIANCE_VOLTAGE_UTILIZATION,
            refusals=(
                RefusedInversion(
                    target=COMPLIANCE_VOLTAGE_UTILIZATION,
                    reason=(
                        "this model declares no compliance_voltage input, so "
                        "the rating this group divides by is not among the "
                        "things a caller declares to it -- it arrives on a "
                        "ComponentRating beside the problem. There is nothing "
                        "here a hint could be about, and the honest report is "
                        "that this condition is not repairable through any "
                        "declared input of this model"
                    ),
                ),
            ),
        ),
    ),
)


KCL_INVERSIONS = ModelInversionTable(
    model=KCL_MODEL,
    rows=(
        ConditionInversions(
            condition=LUMPED_ELECTRICAL_LENGTH,
            refusals=(
                RefusedInversion(
                    target=LUMPED_ELECTRICAL_LENGTH,
                    reason=(
                        "this group is identically zero by the model's own "
                        "scope -- f = 0 is an assumption of the record, so "
                        "lambda is unbounded and L/lambda is zero for a "
                        "circuit of any size. No declared input enters it and "
                        "no circuit can violate it"
                    ),
                ),
            ),
        ),
    ),
)


def rating_declarations(
    rating: ComponentRating | None,
) -> dict[str, Quantity]:
    """A component's rating as the declared inputs the model record names.

    Every field below is a ``ModelInputSpec`` on the element's model, declared
    ``required=False``: they *are* caller declarations, and the only reason
    they do not already arrive through ``problem.validity_context`` is that a
    rating is carried on its own record beside the problem rather than as a
    problem parameter. A repair reads them from here so that a hint about
    ``rated_power`` is a hint about a value the caller actually wrote down.

    ``derating_factor`` is a bare float on the rating and becomes a
    dimensionless ``Quantity``, because a hint's threshold and the value it is
    compared with must share a dimension.
    """
    declared = rating or ComponentRating()
    values: dict[str, Quantity] = {
        DERATING_FACTOR: Quantity(declared.derating_factor, DIMENSIONLESS)
    }
    for name in (
        RATED_POWER,
        RATED_POWER_TEMPERATURE,
        ZERO_POWER_TEMPERATURE,
        MAXIMUM_WORKING_VOLTAGE,
        MAXIMUM_CURRENT,
        COMPLIANCE_VOLTAGE,
    ):
        value = getattr(declared, name)
        if value is not None:
            values[name] = value
    return values


def _repair_context(
    model: Any,
    problem: ScientificProblem,
    rating: ComponentRating | None,
    assembled: Mapping[str, Quantity],
    extra_declared: Mapping[str, Quantity] | None = None,
) -> DomainValidityContext:
    """The assessed context, widened by the rating the caller declared.

    The ratings that a model names as inputs but that travel on a
    ``ComponentRating`` are folded into the *declared* half, never the
    assembled one: they are the caller's numbers and a hint is about them. The
    assembled half stays exactly what `resistor_rating_context` and its
    siblings produced, so the hints are anchored to the same utilizations the
    verdict was formed from.
    """
    reserved = model.derived_quantities
    declared = dict(problem.validity_context(reserved=reserved))
    for name, value in rating_declarations(rating).items():
        declared.setdefault(name, value)
    # A quantity that crossed in under a declaration. Folded into the declared
    # half for the same reason the ratings are: a hint is about the caller's
    # numbers, and this is now one of them.
    for name, value in dict(extra_declared or {}).items():
        declared.setdefault(name, value)
    return assembled_validity_context(
        declared=caller_declared(declared, reserved),
        assembled=dict(assembled),
        reserved=reserved,
    )


def resistor_repairs(
    problem: ScientificProblem,
    *,
    subject: str,
    rating: ComponentRating | None = None,
    dissipated_power: Quantity | None = None,
    voltage_across: Quantity | None = None,
    ambient: "QuantityTransfer | None" = None,
) -> tuple[ConditionRepair, ...]:
    """What would have to change for this element's violated conditions to pass.

    The arguments are exactly :func:`assess_resistor_validity`'s -- which now
    includes the ambient, and that is what changed here. While it crossed in
    undeclared it was not in the assessed context, so the offset of the derated
    form could not be formed and both inversions of
    ``dissipated_power_utilization`` were reported as unavailable. It is a
    declared input of this problem now, so they are not.
    """
    received = _received_ambient(ambient)
    return condition_repairs(
        model=RESISTOR_OHM_MODEL,
        context=_repair_context(
            RESISTOR_OHM_MODEL,
            problem,
            rating,
            resistor_rating_context(
                rating=rating,
                dissipated_power=dissipated_power,
                voltage_across=voltage_across,
                ambient_temperature=received,
            ),
            extra_declared=(
                {} if received is None else {AMBIENT_TEMPERATURE: received}
            ),
        ),
        table=RESISTOR_INVERSIONS,
        subject=subject,
    )


def voltage_source_repairs(
    problem: ScientificProblem,
    *,
    subject: str,
    rating: ComponentRating | None = None,
    source_current: Quantity | None = None,
) -> tuple[ConditionRepair, ...]:
    """What would have to change for this source's violated conditions to pass."""
    return condition_repairs(
        model=IDEAL_VOLTAGE_SOURCE_MODEL,
        context=_repair_context(
            IDEAL_VOLTAGE_SOURCE_MODEL,
            problem,
            rating,
            voltage_source_rating_context(
                rating=rating, source_current=source_current
            ),
        ),
        table=VOLTAGE_SOURCE_INVERSIONS,
        subject=subject,
    )
