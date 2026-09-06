"""The input boundary: a JSON description of a case becomes a problem, or is refused.

The V&V layer's other half. :mod:`engcore.mcp.evidence` reports what a run
established; this module decides whether a caller has said enough for a run to
be posed at all, and says exactly what is missing when they have not.

Why this is a boundary and not a parser
---------------------------------------
The consumer here is frequently an agent assembling a payload from a natural
description, with no access to the source and no way to tell a value that was
rejected from one that was quietly reinterpreted. That asymmetry decides every
rule below:

* **Every physical value carries a unit.** ``"10 ohm"``, never ``10``. There is
  no implicit SI and no reasonable default, because a caller who wrote a bare
  number has not stated a physical quantity, and choosing the unit on their
  behalf is the substitution the whole platform exists to refuse. The units
  backend already refuses it — :meth:`Quantity.parse` rejects a bare numeric
  literal — and this module only has to name the field.

* **Unknown fields are refused, never ignored.** This is the rule that matters
  most and it is the least obvious. Dropping a misspelled ``conductivty``
  presents downstream as a body whose conductivity was never declared: the
  Biot number cannot be formed, the condition reports UNKNOWN, and the report
  reports INSUFFICIENT_EVIDENCE. That is a *correct* verdict about a case the
  caller never described, produced from a typo, and nothing in the output
  points at the spelling. A refusal costs one round trip; the alternative
  costs the caller their confidence in a verdict.

* **Optional stays optional.** Every field the models mark ``required=False``
  may be omitted, and omitting it is not an error. The applicability
  conditions are built so a missing declaration yields UNKNOWN and never
  IN_DOMAIN; supplying a default here would convert an honest gap into a false
  verdict, which is worse than the gap.

What is derived and what is written down
----------------------------------------
The *shape* of the payload is a design choice and is written down here: which
key sits in which object. Everything else about a field — whether it is
required, what dimension it must carry, what it is for, and which validity
conditions it unlocks — is read from the model records at import time and at
call time. :func:`describe_electrothermal_case` reports those facts, and
:data:`_BINDINGS` is checked against the registries by
:func:`_audit_bindings`, so a model input added, removed or re-dimensioned in a
domain shows up here as a failure rather than as a description that has
quietly stopped being true.

What this module does not do
----------------------------
It computes no physics and evaluates no condition. It builds declaration
records that the domains already validate, hands them to the systems pack that
already knows how to run them, and assembles the result through
:class:`~engcore.mcp.evidence.CredibilityEvidenceReport`. Every refusal below
is about whether a *statement* is complete, never about whether a case is a
good idea.
"""

from __future__ import annotations

import dataclasses
import difflib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..domains.electrical import material as mat
from ..domains.electrical.dc import circuit as dc_circuit
from ..domains.electrical.dc import models as dc_models
from ..domains.electrical.dc import problem as dc_problem
from ..domains.electrical.dc import solver as dc_solver
from ..domains.thermal_models import context as thermal_ctx
from ..domains.thermal_models import lumped as lump
from ..scientific.errors import ScientificCoreError
from ..scientific.models.definition import (
    ModelInputSpec,
    ScientificModelDefinition,
    ValidityAssessment,
)
from ..scientific.results.validation import (
    ValidationCheck,
    ValidationOutcome,
)
from ..scientific.units.quantity import Quantity, dimension_of, dimensionality
from ..systems.electrothermal import coupled as cp
from ..systems.electrothermal.resistor_body import RESISTOR_POWER_METRIC
from .errors import (
    MalformedPayloadError,
    MissingFieldError,
    MissingUnitError,
    UnknownFieldError,
    WrongDimensionError,
)
from .evidence import (
    AssertedContext,
    CouplingEvidence,
    CredibilityEvidenceReport,
    ModelValidityRecord,
    combine_assessments,
)

__all__ = [
    "COUPLING_SUPPLIED_INPUTS",
    "Binding",
    "CaseDescription",
    "ElectroThermalCaseRun",
    "FieldDescription",
    "build_electrothermal_problems",
    "build_electrothermal_system",
    "describe_electrothermal_case",
    "example_electrothermal_payload",
    "run_electrothermal_case",
    "audit_bindings",
]

#: The payload machinery below is shared with every other system's boundary.
#: Named without the underscore where a sibling module reads it, so the
#: sharing is visible rather than a convention about private names.


# =====================================================================
# The model records this boundary reads
# =====================================================================

_LUMPED = lump.LUMPED_CAPACITY_MODEL
_RATED_TCR = mat.RATED_LINEAR_TCR_MODEL
_LINEAR_TCR = mat.LINEAR_TCR_MODEL
_VOLTAGE_SOURCE = dc_models.IDEAL_VOLTAGE_SOURCE_MODEL
_RESISTOR = dc_models.RESISTOR_OHM_MODEL
_KCL = dc_models.KCL_MODEL

#: Every model this boundary poses a problem for. The audit below reads
#: their inputs; widening this tuple is how a new participant becomes the
#: description's problem rather than the caller's surprise.
_MODELS = (_LUMPED, _LINEAR_TCR, _RATED_TCR, _VOLTAGE_SOURCE, _RESISTOR, _KCL)

#: Model inputs a caller **must not** supply, and why. Each is solved for
#: rather than declared: the body temperature is the state the thermal model
#: advances, the heat input is what the electrical solve delivers, and the
#: conductor's temperature is what the coupling transports back. A payload
#: field for any of them would let a caller assert an operating point the run
#: is supposed to find, which is how a fixed point stops being one.
COUPLING_SUPPLIED_INPUTS: Mapping[str, str] = {
    lump.TEMPERATURE: (
        "the body temperature is the state the thermal model advances; the "
        "coupling seeds it and iterates it"
    ),
    lump.HEAT_INPUT: (
        "the heat delivered to the body is the electrical solve's dissipation, "
        "transported by the coupling"
    ),
    mat.TEMPERATURE: (
        "the conductor's temperature is the body temperature transported back "
        "by the coupling; declaring it would fix the fixed point"
    ),
    "resistance": (
        "each resistor's resistance is R(T) from the property solve, computed "
        "from the conductor's declared reference resistance and coefficient"
    ),
    "voltage_across": (
        "solved by the DC network; declaring it would assert the answer"
    ),
    "terminal_voltage": (
        "solved by the DC network at the source's terminals"
    ),
    "node_voltage": (
        "solved by the DC network; the unknowns of the MNA system"
    ),
}


def _input_spec(model: ScientificModelDefinition, name: str) -> ModelInputSpec:
    """The model's own declaration of one input, or a loud failure.

    Deliberately not tolerant of a missing name. Every lookup here is a claim
    that a model declares an input, and a claim that has stopped being true is
    exactly the drift this module is arranged to catch.
    """
    for spec in model.inputs:
        if spec.name == name:
            return spec
    raise ScientificCoreError(
        f"model {model.model_id!r} declares no input {name!r}; the payload "
        f"binding table in engcore.mcp.problem is out of step with the model "
        f"record"
    )


# =====================================================================
# The payload shape
# =====================================================================

#: Where each section of the payload lives, as a dotted path for messages.
ROOT = ""
STAGE = "stages[]"
CONDUCTOR = "stages[].conductor"
LIMITS = "stages[].conductor.limits"
RATINGS = "stages[].conductor.ratings"
BODY = "stages[].body"
APPLICABILITY = "stages[].body.applicability"
COUPLING = "coupling"
SOURCE_RATINGS = "source_ratings"

#: Execution defaults for the coupling block, resolved at this boundary rather
#: than at the call site so that what is validated here is what the runner
#: receives. A caller who declares neither still gets a configuration that has
#: been through the runner's own admissibility rule.
DEFAULT_COUPLING_TOLERANCE = Quantity(1e-6, "kelvin")
DEFAULT_COUPLING_BUDGET = 50


@dataclass(frozen=True)
class Binding:
    """One payload key, and the model input it supplies.

    ``section`` and ``key`` are the shape — a design decision, written down.
    ``model``/``input_name`` are the *authority*: required, dimension, unit
    exemplar and prose all come from that record, so this table carries no
    duplicate of anything a model already states.

    ``target`` is the constructor keyword on the declaration record being
    built, which differs from ``key`` in exactly one place — ``body_volume``
    is the model's name for what
    :class:`~engcore.domains.thermal_models.context.LumpedApplicabilityDeclaration`
    calls ``volume``. The model's name wins in the payload, because that is the
    name a caller reading the model record will look for.
    """

    section: str
    key: str
    kind: str  # "quantity" | "identifier" | "count" | "category" | "fraction"
    model: ScientificModelDefinition | None = None
    input_name: str | None = None
    target: str | None = None
    #: Dimension for a field no model declares, borrowed from the input whose
    #: value it states. Only ever set together with ``kind == "quantity"`` and
    #: ``model is None``.
    dimension_of_input: tuple[ScientificModelDefinition, str] | None = None
    required: bool | None = None
    note: str = ""
    #: Admissible values for ``kind == "category"``. Declared per binding
    #: because a second system has its own vocabularies; ``None`` keeps the
    #: thermal convection regimes, which is what every electro-thermal
    #: category binding means.
    vocabulary: tuple[str, ...] | None = None

    @property
    def target_name(self) -> str:
        return self.target or self.key

    @property
    def spec(self) -> ModelInputSpec | None:
        if self.model is None or self.input_name is None:
            return None
        return _input_spec(self.model, self.input_name)

    @property
    def is_required(self) -> bool:
        spec = self.spec
        if spec is not None:
            return spec.required
        if self.required is None:  # pragma: no cover - table is exhaustive
            raise ScientificCoreError(
                f"binding {self.section}.{self.key} declares neither a model "
                f"input nor an explicit required flag"
            )
        return self.required

    @property
    def unit_exemplar(self) -> str | None:
        spec = self.spec
        if spec is not None:
            return spec.unit_exemplar
        if self.dimension_of_input is not None:
            return _input_spec(*self.dimension_of_input).unit_exemplar
        return None

    @property
    def description(self) -> str:
        spec = self.spec
        if spec is not None and spec.description:
            return spec.description
        return self.note


#: The private alias the rest of this module was written against.
_Binding = Binding

_BINDINGS: tuple[Binding, ...] = (
    # ---- system ------------------------------------------------------
    Binding(
        section=ROOT,
        key="source_voltage",
        kind="quantity",
        model=_VOLTAGE_SOURCE,
        input_name="source_voltage",
    ),
    # ---- stage identity ----------------------------------------------
    Binding(
        section=STAGE,
        key="component_id",
        kind="identifier",
        required=True,
        note=(
            "Names the conductor and the body together. This systems pack "
            "requires the two to share an id; no universal record states that "
            "a conductor declaration and a body declaration describe one "
            "object, so the shared id is the pack's convention and is checked "
            "by it."
        ),
    ),
    # ---- conductor ---------------------------------------------------
    Binding(
        section=CONDUCTOR,
        key="reference_resistance",
        kind="quantity",
        model=_LINEAR_TCR,
        input_name="reference_resistance",
    ),
    Binding(
        section=CONDUCTOR,
        key="temperature_coefficient",
        kind="quantity",
        model=_LINEAR_TCR,
        input_name="temperature_coefficient",
    ),
    Binding(
        section=CONDUCTOR,
        key="reference_temperature",
        kind="quantity",
        model=_LINEAR_TCR,
        input_name="reference_temperature",
    ),
    # ---- material limits ---------------------------------------------
    Binding(
        section=LIMITS,
        key="linearization_band",
        kind="quantity",
        model=_RATED_TCR,
        input_name="linearization_band",
    ),
    Binding(
        section=LIMITS,
        key="maximum_operating_temperature",
        kind="quantity",
        model=_RATED_TCR,
        input_name="maximum_operating_temperature",
    ),
    Binding(
        section=LIMITS,
        key="debye_temperature",
        kind="quantity",
        model=_RATED_TCR,
        input_name="debye_temperature",
    ),
    # ---- component ratings -------------------------------------------
    #
    # Separate from `limits` because they are facts about a different thing.
    # A material limit is shared by every component made of the alloy; a
    # rating belongs to the one part. Two resistors wound from the same wire
    # have the same linearization band and may have quite different rated
    # dissipations, and one object holding both would make that unsayable.
    Binding(
        section=RATINGS,
        key=dc_models.RATED_POWER,
        kind="quantity",
        model=_RESISTOR,
        input_name=dc_models.RATED_POWER,
    ),
    Binding(
        section=RATINGS,
        key=dc_models.MAXIMUM_WORKING_VOLTAGE,
        kind="quantity",
        model=_RESISTOR,
        input_name=dc_models.MAXIMUM_WORKING_VOLTAGE,
    ),
    Binding(
        section=RATINGS,
        key=dc_models.DERATING_FACTOR,
        kind="fraction",
        model=_RESISTOR,
        input_name=dc_models.DERATING_FACTOR,
    ),
    # ---- source rating -----------------------------------------------
    #
    # At the root beside `source_voltage`, because that is where the source
    # is. The payload has one source and describes it with a scalar rather
    # than an object, and this block follows that shape instead of inventing
    # a `source` object for one new field.
    Binding(
        section=SOURCE_RATINGS,
        key=dc_models.MAXIMUM_CURRENT,
        kind="quantity",
        model=_VOLTAGE_SOURCE,
        input_name=dc_models.MAXIMUM_CURRENT,
    ),
    Binding(
        section=SOURCE_RATINGS,
        key=dc_models.DERATING_FACTOR,
        kind="fraction",
        model=_VOLTAGE_SOURCE,
        input_name=dc_models.DERATING_FACTOR,
    ),
    # ---- body --------------------------------------------------------
    Binding(
        section=BODY,
        key="heat_capacity",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.HEAT_CAPACITY,
    ),
    Binding(
        section=BODY,
        key="ambient_conductance",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.AMBIENT_CONDUCTANCE,
    ),
    Binding(
        section=BODY,
        key="ambient_temperature",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.AMBIENT_TEMPERATURE,
    ),
    Binding(
        section=BODY,
        key="duration",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.DURATION,
    ),
    Binding(
        section=BODY,
        key="initial_temperature",
        kind="quantity",
        dimension_of_input=(_LUMPED, lump.TEMPERATURE),
        required=True,
        note=(
            "The body temperature at the start of the interval. Not a model "
            "input of its own: it is the initial condition on the "
            "'temperature' state, and takes that input's dimension."
        ),
    ),
    # ---- applicability declaration ------------------------------------
    Binding(
        section=APPLICABILITY,
        key="characteristic_length",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.CHARACTERISTIC_LENGTH,
    ),
    Binding(
        section=APPLICABILITY,
        key="body_volume",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.BODY_VOLUME,
        target="volume",
    ),
    Binding(
        section=APPLICABILITY,
        key="surface_area",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.SURFACE_AREA,
    ),
    Binding(
        section=APPLICABILITY,
        key="body_conductivity",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.BODY_CONDUCTIVITY,
    ),
    Binding(
        section=APPLICABILITY,
        key="surface_emissivity",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.SURFACE_EMISSIVITY,
    ),
    Binding(
        section=APPLICABILITY,
        key="conductance_excursion_bound",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.CONDUCTANCE_EXCURSION_BOUND,
    ),
    Binding(
        section=APPLICABILITY,
        key="capacity_excursion_bound",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.CAPACITY_EXCURSION_BOUND,
    ),
    Binding(
        section=APPLICABILITY,
        key="melting_temperature",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.MELTING_TEMPERATURE,
    ),
    # ---- how the ambient conductance was obtained ---------------------
    #
    # Six optional fields that let a convection correlation be evaluated and
    # compared against the declared ambient_conductance. Which correlation is
    # selected by which of them is supplied, not by convection_regime below:
    # fluid_expansion_coefficient selects the natural route and fluid_velocity
    # the forced one, so no verdict here rests on a category the caller
    # asserted. Every one is optional and omitting them leaves the four
    # correlation conditions UNKNOWN, exactly as before they existed.
    Binding(
        section=APPLICABILITY,
        key="fluid_conductivity",
        kind="quantity",
        model=_LUMPED,
        input_name=thermal_ctx.FLUID_CONDUCTIVITY,
    ),
    Binding(
        section=APPLICABILITY,
        key="fluid_kinematic_viscosity",
        kind="quantity",
        model=_LUMPED,
        input_name=thermal_ctx.FLUID_VISCOSITY,
        target="fluid_kinematic_viscosity",
    ),
    Binding(
        section=APPLICABILITY,
        key="fluid_prandtl_number",
        kind="quantity",
        model=_LUMPED,
        input_name=thermal_ctx.FLUID_PRANDTL_NUMBER,
    ),
    Binding(
        section=APPLICABILITY,
        key="fluid_expansion_coefficient",
        kind="quantity",
        model=_LUMPED,
        input_name=thermal_ctx.FLUID_EXPANSION_COEFFICIENT,
    ),
    Binding(
        section=APPLICABILITY,
        key="fluid_velocity",
        kind="quantity",
        model=_LUMPED,
        input_name=thermal_ctx.FLUID_VELOCITY,
    ),
    Binding(
        section=APPLICABILITY,
        key="convection_length",
        kind="quantity",
        model=_LUMPED,
        input_name=thermal_ctx.CONVECTION_LENGTH,
    ),
    Binding(
        section=APPLICABILITY,
        key="convection_regime",
        kind="category",
        required=False,
        note=(
            "One of "
            f"{list(thermal_ctx.CONVECTION_REGIME_VOCABULARY)}. Declared but "
            "not modelled: no validity condition reads it, and it unlocks "
            "nothing. It records why the caller believes their "
            "conductance_excursion_bound is credible, and it is carried into "
            "the report as caller-asserted context. It never substitutes for "
            "that bound."
        ),
    ),
    # ---- coupling (execution, not physics) ----------------------------
    Binding(
        section=COUPLING,
        key="seed_temperature",
        kind="quantity",
        dimension_of_input=(_LUMPED, lump.TEMPERATURE),
        required=False,
        note=(
            "Starting temperature for the fixed-point iteration. An execution "
            "property, not a declaration: it changes how the answer is found "
            "and not what is being asked. Defaults to the body's initial "
            "temperature."
        ),
    ),
    Binding(
        section=COUPLING,
        key="tolerance",
        kind="quantity",
        dimension_of_input=(_LUMPED, lump.TEMPERATURE),
        required=False,
        note=(
            "Convergence tolerance on the torn temperature edge. Execution "
            "property. Defaults to 1e-6 kelvin."
        ),
    ),
    Binding(
        section=COUPLING,
        key="max_iterations",
        kind="count",
        required=False,
        note=(
            "Iteration budget for the fixed point. A count, not a physical "
            "quantity, so it carries no unit. Defaults to 50."
        ),
    ),
)


def _section(
    name: str, bindings: Sequence[Binding] | None = None
) -> tuple[Binding, ...]:
    """Every binding in one section of one table.

    ``bindings`` defaults to the electro-thermal table, which is what every
    call in this module wants. It is a parameter because a second system has
    its own table and the same machinery reads both: see
    :mod:`engcore.mcp.battery`, which passes its own.
    """
    table = _BINDINGS if bindings is None else bindings
    return tuple(b for b in table if b.section == name)


def _audit_bindings() -> None:
    """Every model input is bound, coupling-supplied, or a loud failure.

    The drift guard. A domain that adds an input, renames one, or flips one
    from optional to required changes what a caller must say, and a boundary
    that kept describing the old shape would be lying in the one place a
    caller cannot check. Run at import, so the failure is at the earliest
    possible moment rather than inside somebody's run.
    """
    audit_bindings(
        _BINDINGS, _MODELS, COUPLING_SUPPLIED_INPUTS, where="engcore.mcp.problem"
    )


def audit_bindings(
    bindings: Sequence[Binding],
    models: Sequence[ScientificModelDefinition],
    supplied: Mapping[str, str],
    *,
    where: str,
) -> None:
    """One table against its own models. Shared by every system's boundary.

    Parameterized rather than closed over the electro-thermal table because a
    second system needs the identical guard over a different table, and a
    guard that only ran for one system would let the other's description
    quietly stop describing its models — which is the exact failure this
    exists to prevent, one system over.
    """
    bound = {b.input_name for b in bindings if b.input_name is not None}
    unaccounted = [
        f"{model.model_id}.{spec.name}"
        for model in models
        for spec in model.inputs
        if spec.name not in bound and spec.name not in supplied
    ]
    if unaccounted:
        raise ScientificCoreError(
            f"{where} neither accepts nor accounts for model "
            f"inputs {sorted(unaccounted)}; every declared input must be a "
            f"payload field or an entry in the supplied-inputs table, so that "
            f"the description cannot silently stop describing the models"
        )

    # A binding must also still name an input the model declares. `spec`
    # raises when it does not, which turns a renamed input into an import
    # failure here rather than a wrong dimension in somebody's payload.
    for binding in bindings:
        binding.spec  # noqa: B018 - the lookup is the assertion


_audit_bindings()


# =====================================================================
# Reading one value
# =====================================================================

def _path(section: str, key: str) -> str:
    return f"{section}.{key}" if section else key


def _require_mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise MalformedPayloadError(
            f"{where} must be an object, got {type(value).__name__}"
        )
    return value


def _reject_unknown_keys(
    supplied: Mapping[str, Any], bindings: Sequence[Binding], *, section: str,
    extra: Sequence[str] = (),
) -> None:
    """Refuse anything not named, with the closest accepted names.

    The suggestion is the difference between a refusal an agent can act on and
    one it has to guess at, and it costs nothing: the accepted set is already
    in hand.
    """
    accepted = {b.key for b in bindings} | set(extra)
    for key in supplied:
        if key in accepted:
            continue
        close = difflib.get_close_matches(str(key), sorted(accepted), n=3, cutoff=0.6)
        suggestion = f"; did you mean {close}?" if close else ""
        raise UnknownFieldError(
            f"{_path(section, str(key))} is not a field this boundary accepts"
            f"{suggestion} Accepted here: {sorted(accepted)}. Unknown fields "
            f"are refused rather than ignored: dropping one would present as a "
            f"declaration you never made and report UNKNOWN for a condition "
            f"you meant to satisfy."
        )


def _read_quantity(
    supplied: Mapping[str, Any], binding: Binding, label: str
) -> Quantity | None:
    """One declared value, unit-checked against the model's own exemplar."""
    where = _path(label, binding.key)
    exemplar = binding.unit_exemplar
    if binding.key not in supplied or supplied[binding.key] is None:
        if binding.is_required:
            raise MissingFieldError(
                f"{where} is required and was not supplied; it must be a "
                f"string carrying a unit of [{dimensionality(exemplar)}], "
                f"for example '1 {exemplar}'"
            )
        return None

    raw = supplied[binding.key]
    if not isinstance(raw, str):
        raise MissingUnitError(
            f"{where} must be a string carrying a unit, for example "
            f"'1 {exemplar}'; got {raw!r} ({type(raw).__name__}). A bare "
            f"number is not a physical quantity and this boundary will not "
            f"choose a unit on your behalf"
        )
    try:
        quantity = Quantity.parse(raw)
    except ScientificCoreError as exc:
        raise MissingUnitError(
            f"{where}: cannot read {raw!r} as a quantity ({exc}); expected a "
            f"magnitude and a unit of [{dimensionality(exemplar)}], for "
            f"example '1 {exemplar}'"
        ) from exc

    if dimension_of(quantity.units) != dimension_of(exemplar):
        raise WrongDimensionError(
            f"{where} has the wrong dimension: {raw!r} is "
            f"[{quantity.dimensionality}], but this field must be "
            f"[{dimensionality(exemplar)}] (any unit of that dimension, for "
            f"example '1 {exemplar}')"
        )
    return quantity


def _read_identifier(
    supplied: Mapping[str, Any], binding: Binding, label: str
) -> str:
    where = _path(label, binding.key)
    raw = supplied.get(binding.key)
    if raw is None:
        raise MissingFieldError(f"{where} is required and was not supplied")
    if not isinstance(raw, str) or not raw.strip():
        raise MalformedPayloadError(
            f"{where} must be a non-empty string, got {raw!r}"
        )
    return raw.strip()


def _read_category(
    supplied: Mapping[str, Any], binding: Binding, label: str
) -> str | None:
    where = _path(label, binding.key)
    raw = supplied.get(binding.key)
    if raw is None:
        return None
    # The binding names its own vocabulary. It used to be the thermal
    # domain's, closed over from this module, which was correct while one
    # system had one categorical field and silently wrong the moment a second
    # system declared a chemistry.
    vocabulary = list(binding.vocabulary or
                      thermal_ctx.CONVECTION_REGIME_VOCABULARY)
    if not isinstance(raw, str) or raw.strip() not in vocabulary:
        raise MalformedPayloadError(
            f"{where} must be one of {vocabulary}, got {raw!r}"
        )
    return raw.strip()


def _read_count(
    supplied: Mapping[str, Any], binding: Binding, label: str
) -> int | None:
    where = _path(label, binding.key)
    raw = supplied.get(binding.key)
    if raw is None:
        return None
    # bool is an int in Python and is not a count anybody meant to write.
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise MalformedPayloadError(
            f"{where} must be a positive integer count and carries no unit, "
            f"got {raw!r}"
        )
    return raw


def _read_fraction(
    supplied: Mapping[str, Any], binding: Binding, label: str
) -> float | None:
    """A bare dimensionless fraction, such as a derating policy.

    Written without a unit, unlike every physical value at this boundary, and
    the exception is deliberate. A derating factor is not a measurement of
    anything: it is the share of a published rating the caller elects to use,
    the same kind of number as ``coupling.max_iterations``. Requiring
    ``"0.5 dimensionless"`` would dress a policy choice as an observation, and
    the record behind it stores a ``float`` for that reason.

    The admissible interval is *not* checked here. ``ComponentRating`` refuses
    a factor outside ``(0, 1]`` with the reason attached, and duplicating the
    rule would give this boundary a second copy to drift from.
    """
    where = _path(label, binding.key)
    raw = supplied.get(binding.key)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise MalformedPayloadError(
            f"{where} must be a bare number in (0, 1] and carries no unit — "
            f"it is the fraction of the published rating in use, not a "
            f"physical quantity — got {raw!r}"
        )
    return float(raw)


def _read_section(
    supplied: Mapping[str, Any],
    section: str,
    *,
    extra: Sequence[str] = (),
    label: str | None = None,
    bindings: Sequence[Binding] | None = None,
) -> dict[str, Any]:
    """Every binding in one section, read and checked. Absent optionals omitted.

    ``extra`` names the sub-objects that live beside this section's own keys
    (``stages``, ``conductor``, ``limits``…) so they are not refused as unknown
    fields. ``label`` carries the *indexed* path — ``stages[0].body`` rather
    than ``stages[].body`` — so a refusal points at the stage that caused it.
    """
    bindings = _section(section, bindings)
    where = label if label is not None else section
    _reject_unknown_keys(supplied, bindings, section=where, extra=extra)
    values: dict[str, Any] = {}
    for binding in bindings:
        if binding.kind == "quantity":
            value = _read_quantity(supplied, binding, where)
        elif binding.kind == "identifier":
            value = _read_identifier(supplied, binding, where)
        elif binding.kind == "category":
            value = _read_category(supplied, binding, where)
        elif binding.kind == "count":
            value = _read_count(supplied, binding, where)
        elif binding.kind == "fraction":
            value = _read_fraction(supplied, binding, where)
        else:  # pragma: no cover - kinds are a closed set
            raise ScientificCoreError(f"unknown binding kind {binding.kind!r}")
        if value is not None:
            values[binding.target_name] = value
    return values


# =====================================================================
# Building the declarations
# =====================================================================

def build_electrothermal_system(
    payload: Mapping[str, Any],
) -> cp.CoupledElectroThermalSystem:
    """The declaration records, or a refusal naming the field that stopped it.

    Every value goes through the domains' own constructors afterwards, so this
    function is not the only thing standing between a payload and a bad
    declaration — it is the thing that makes the refusal say *which key in
    which stage* rather than which constructor argument.
    """
    root = _require_mapping(payload, where="payload")
    root_values = _read_section(
        root, ROOT, extra=("stages", "coupling", SOURCE_RATINGS)
    )
    _read_ratings(root)  # checked here; consumed when the report is assembled

    raw_stages = root.get("stages")
    if raw_stages is None:
        raise MissingFieldError(
            "stages is required: a coupled system needs at least one stage, "
            "each an object with 'component_id', 'conductor' and 'body'"
        )
    if not isinstance(raw_stages, Sequence) or isinstance(raw_stages, (str, bytes)):
        raise MalformedPayloadError(
            f"stages must be a list of stage objects, got "
            f"{type(raw_stages).__name__}"
        )
    if not raw_stages:
        raise MalformedPayloadError(
            "stages must not be empty: a coupled system requires a stage"
        )

    stages = tuple(
        _build_stage(_require_mapping(entry, where=f"stages[{index}]"), index)
        for index, entry in enumerate(raw_stages)
    )
    _read_coupling(root)  # validated here; consumed by run_electrothermal_case
    return cp.CoupledElectroThermalSystem(
        stages=stages, source_voltage=root_values["source_voltage"]
    )


def _read_coupling(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The execution block, read and checked.

    Called by :func:`build_electrothermal_system` as well as by the runner,
    even though building uses none of it. A payload is either accepted or
    refused as a whole: a misspelled ``max_iteratons`` that the builder waved
    through and the runner refused would make the boundary's answer depend on
    which entry point the caller happened to use.

    **That rule was stated here and then only half applied.** Field names were
    checked at both entry points; the *values* were not. A zero ``tolerance``
    passed the builder and was refused three layers down by
    ``FixedPointCouplingPlan``, which is the same defect in the same block. So
    the coupling values are now checked here too — and checked by the runner's
    own rule, :func:`~engcore.systems.electrothermal.coupled.validate_coupling_configuration`,
    rather than by a copy of it that could drift. The defaults are resolved
    first, because a default a caller did not write is still a configuration
    this boundary hands to the runner.
    """
    coupling = _read_section(
        _require_mapping(
            _require_mapping(payload, where="payload").get("coupling"),
            where="coupling",
        ),
        COUPLING,
    )
    try:
        cp.validate_coupling_configuration(
            tolerance=coupling.get("tolerance", DEFAULT_COUPLING_TOLERANCE),
            max_iterations=coupling.get(
                "max_iterations", DEFAULT_COUPLING_BUDGET
            ),
            tolerance_label="coupling.tolerance",
            budget_label="coupling.max_iterations",
        )
    except ScientificCoreError as exc:
        # Re-raised as this boundary's own error type, because that is what a
        # caller of a payload API catches. The message is the runner's rule
        # verbatim, already naming the payload field through the labels above:
        # nothing about what is wrong is restated here.
        raise MalformedPayloadError(str(exc)) from exc
    return coupling


DECLARED_LIMITS_CHECK = "declared_limits_are_mutually_consistent"


def _declared_limit_checks(
    stage: cp.CoupledStage,
) -> tuple[ValidationCheck, ...]:
    """A melting point below the operating ceiling, as a finding in the report.

    **Why this lives here and in neither domain.** ``melting_temperature`` is
    declared in the thermal applicability record and
    ``maximum_operating_temperature`` in the electrical material limits.
    Neither domain has any business knowing the other's limit exists, and
    making one co-declare the other would couple two domains for a check that
    belongs to whoever assembled the payload. One caller wrote both numbers
    about one physical part, and this boundary is where that caller's
    declaration is a single object.

    **Why it is a contradiction and not a tolerance.** The ceiling is declared
    as the temperature above which "the conductor itself is not intact"; the
    melting point is where the body stops being the solid the lumped balance
    describes. A part rated to operate at or above its own melting point is not
    a part operated aggressively — it is two statements about one body that
    cannot both hold, and no operating point reconciles them.

    **Why a check and not a refusal.** An earlier form of this raised at build
    time, and that was wrong in a way worth recording: cases whose real defect
    is that the run exceeds the melting point, or that a constant-hA budget
    breaks *and* the melting point is passed, also declare a low melting point
    beside a high ceiling. Refusing at build time pre-empted the more
    informative finding with a less informative one and cost 112 correct
    verdicts. A design that contradicts itself is a finding about the design,
    and findings belong beside the others rather than in place of them.

    Both limits are optional and the check is simply absent unless the caller
    declared both — an undeclared limit stays UNKNOWN and is never read as
    agreement.
    """
    ceiling = stage.conductor.limits.maximum_operating_temperature
    melting = stage.body.applicability.melting_temperature
    if ceiling is None or melting is None:
        return ()
    ceiling_k = ceiling.magnitude_in("kelvin")
    melting_k = melting.magnitude_in("kelvin")
    if melting_k > ceiling_k:
        return (
            ValidationCheck(
                name=DECLARED_LIMITS_CHECK,
                outcome=ValidationOutcome.PASS,
                detail=(
                    f"melting_temperature {melting} is above "
                    f"maximum_operating_temperature {ceiling}"
                ),
            ),
        )
    return (
        ValidationCheck(
            name=DECLARED_LIMITS_CHECK,
            outcome=ValidationOutcome.FAIL,
            detail=(
                f"stages[].body.applicability.melting_temperature is "
                f"{melting}, which is not above "
                f"stages[].conductor.limits.maximum_operating_temperature "
                f"{ceiling}. The ceiling is the temperature above which the "
                f"conductor is not intact and the melting point is where the "
                f"body stops being the solid the thermal balance describes, "
                f"so a ceiling at or above the melting point asserts the part "
                f"is rated to operate in a state it cannot be in. One of the "
                f"two declarations is wrong."
            ),
        ),
    )


def _read_component_rating(
    conductor_raw: Mapping[str, Any], index: int
) -> dc_models.ComponentRating:
    """One stage's declared ratings, or an empty record.

    An absent ``ratings`` object and an empty one mean the same thing and both
    are legal: every rating condition stays UNKNOWN, which is the honest
    verdict for a part whose datasheet nobody supplied. Supplying the block
    can only move a condition off UNKNOWN — never turn a violated one into a
    satisfied one, since the utilizations are ratios against what is declared.
    """
    return dc_models.ComponentRating(
        **_read_section(
            _require_mapping(
                conductor_raw.get("ratings"),
                where=f"stages[{index}].conductor.ratings",
            ),
            RATINGS,
            label=f"stages[{index}].conductor.ratings",
        )
    )


def _read_ratings(
    payload: Mapping[str, Any],
) -> tuple[dict[str, dc_models.ComponentRating], dc_models.ComponentRating]:
    """``({component_id: rating}, source_rating)`` for one payload.

    Read from the payload rather than carried on the system, because a rating
    is not part of the declaration a coupled run needs: the run solves the
    same circuit whether or not anybody wrote down what the parts survive.
    It is evidence the *report* needs, which is where it is used.
    """
    root = _require_mapping(payload, where="payload")
    per_component: dict[str, dc_models.ComponentRating] = {}
    for index, entry in enumerate(root.get("stages") or ()):
        stage = _require_mapping(entry, where=f"stages[{index}]")
        conductor_raw = _require_mapping(
            stage.get("conductor"), where=f"stages[{index}].conductor"
        )
        identity = _read_section(
            stage, STAGE, extra=("conductor", "body"), label=f"stages[{index}]"
        )
        per_component[identity["component_id"]] = _read_component_rating(
            conductor_raw, index
        )
    source_rating = dc_models.ComponentRating(
        **_read_section(
            _require_mapping(
                root.get(SOURCE_RATINGS), where=SOURCE_RATINGS
            ),
            SOURCE_RATINGS,
        )
    )
    return per_component, source_rating


def _build_stage(entry: Mapping[str, Any], index: int) -> cp.CoupledStage:
    identity = _read_section(
        entry, STAGE, extra=("conductor", "body"), label=f"stages[{index}]"
    )
    component_id = identity["component_id"]

    conductor_raw = _require_mapping(
        entry.get("conductor"), where=f"stages[{index}].conductor"
    )
    limits = mat.MaterialLimits(
        **_read_section(
            _require_mapping(
                conductor_raw.get("limits"),
                where=f"stages[{index}].conductor.limits",
            ),
            LIMITS,
            label=f"stages[{index}].conductor.limits",
        )
    )
    # `ratings` is read here only to be *checked* here — an unknown key or a
    # malformed value must be refused by the same pass that refuses every
    # other field, not later and not by a different entry point. The record it
    # builds is discarded; :func:`_read_ratings` builds the one that is used,
    # because a rating belongs to the electrical assessment rather than to the
    # conductor declaration, and CoupledStage has no field for it.
    _read_component_rating(conductor_raw, index)
    conductor = mat.TemperatureDependentConductor(
        component_id=component_id,
        limits=limits,
        **_read_section(
            conductor_raw, CONDUCTOR, extra=("limits", "ratings"),
            label=f"stages[{index}].conductor",
        ),
    )

    body_raw = _require_mapping(entry.get("body"), where=f"stages[{index}].body")
    applicability = thermal_ctx.LumpedApplicabilityDeclaration(
        **_read_section(
            _require_mapping(
                body_raw.get("applicability"),
                where=f"stages[{index}].body.applicability",
            ),
            APPLICABILITY,
            label=f"stages[{index}].body.applicability",
        )
    )
    body = lump.ThermalBody(
        body_id=component_id,
        applicability=applicability,
        **_read_section(
            body_raw, BODY, extra=("applicability",),
            label=f"stages[{index}].body",
        ),
    )
    return cp.CoupledStage(conductor=conductor, body=body)


def build_electrothermal_problems(payload: Mapping[str, Any]):
    """``(electrical, property…, thermal…)`` — the ``2N + 1`` posed problems.

    The system's own :func:`~engcore.systems.electrothermal.coupled.coupled_problems`
    does the posing; this module's contribution ends at handing it declarations
    it can trust. Returned at the nominal resistances, which is where the
    coupling starts.
    """
    system = build_electrothermal_system(payload)
    return cp.coupled_problems(
        system,
        {s.component_id: s.conductor.reference_resistance for s in system.stages},
    )


# =====================================================================
# Running, and reporting
# =====================================================================

@dataclass(frozen=True)
class ElectroThermalCaseRun:
    """A run and one credibility report per stage, in the payload's order."""

    run: cp.CoupledRun
    reports: tuple[CredibilityEvidenceReport, ...]



# ---------------------------------------------------------------------
# The dependency closure, and what every model in it says about itself
# ---------------------------------------------------------------------

def _electrical_assessments(
    system: cp.CoupledElectroThermalSystem,
    electrical: "ScientificResult",
    run: "cp.CoupledRun",
    ratings: Mapping[str, dc_models.ComponentRating] | None = None,
    source_rating: dc_models.ComponentRating | None = None,
) -> dict[str, ValidityAssessment]:
    """A verdict for every electrical model the circuit invoked.

    One record per **model**, not per element, because that is the granularity
    a report has: ``electrical.dc.resistor_ohm`` governs every resistor, and
    :func:`~engcore.mcp.evidence.combine_assessments` reduces the per-element
    answers to one by the rule that a condition satisfied everywhere and
    questioned nowhere is the only one that stays satisfied.

    Every operating-point value comes from the electrical result — the power,
    the voltage across each element, the current out of the source. The
    *ratings* come from the payload's ``ratings`` and ``source_ratings``
    blocks, matched to each element by ``component_id``.

    Both blocks are optional, and a part with no declared rating leaves its
    conditions UNKNOWN rather than satisfied. That is still the honest answer
    for a part whose datasheet nobody supplied — an unrated part is not an
    unlimited part — and it is why a payload that declares no ratings is
    INSUFFICIENT_EVIDENCE rather than SUPPORTED. What has changed is that a
    caller who *can* state the ratings is no longer forced into that verdict
    by the boundary having nowhere to put them.
    """
    # The elements as the RUN had them, not as the caller declared them. Each
    # stage's R(T) is read back out of its converged property result — the
    # same move ``_material_assessments`` makes for the temperature, and for
    # the same reason: an assessment states something about the operating point
    # that was solved, and the reference resistance is a different point. This
    # is ``NEEDS.md`` A2.9, and A2.9's own reading of its blast radius holds:
    # the only resistor condition reading ``resistance`` is ``resistance > 0``
    # and both values are strictly positive in any run that gets this far, so
    # no verdict moves. What changes is that the report no longer names a
    # value the circuit did not use.
    circuit = system.circuit_at(cp.converged_resistances(system, run))
    assessments: dict[str, ValidityAssessment] = {}

    resistors = []
    for resistor in circuit.resistors:
        cid = resistor.component_id
        resistors.append(
            dc_models.assess_resistor_validity(
                dc_problem.resistor_relation_problem(resistor),
                rating=(ratings or {}).get(cid),
                dissipated_power=electrical.value(
                    RESISTOR_POWER_METRIC.format(component_id=cid)
                ),
                voltage_across=electrical.value(f"resistor_voltage:{cid}"),
            )
        )
    if resistors:
        assessments[_RESISTOR.model_id] = combine_assessments(resistors)

    sources = []
    for source in circuit.voltage_sources:
        sources.append(
            dc_models.assess_voltage_source_validity(
                dc_problem.voltage_source_relation_problem(source),
                rating=source_rating,
                source_current=electrical.value(
                    f"{dc_solver.SOURCE_CURRENT_METRIC}:{source.component_id}"
                ),
            )
        )
    if sources:
        assessments[_VOLTAGE_SOURCE.model_id] = combine_assessments(sources)

    # Kirchhoff's law is always invoked, and its condition is satisfied by the
    # DC model's own scope rather than by anything in this payload — which is
    # why the domain supplies the context and this boundary passes nothing
    # into it. It is assessed rather than omitted because a model left out of
    # the report is a model the report silently claims nothing about.
    assessments[_KCL.model_id] = dc_models.assess_kcl_validity()
    return assessments


def _material_assessments(
    system: cp.CoupledElectroThermalSystem, run: "cp.CoupledRun"
) -> dict[str, ValidityAssessment]:
    """The unrated and rated conductor verdicts, over every stage.

    Both are asked, because they are different questions about the same
    arithmetic: *is a linear TCR form declared over this temperature at all*
    and *does this material's own band, rating and low-temperature floor cover
    this operating point*. The second is the one that reads
    ``maximum_operating_temperature``, and a report that asked only the first
    could carry a conductor declared good to 301 K and run to 338 K with the
    declared limit appearing nowhere.

    The temperature each conductor was evaluated at is read back out of the
    property solve's own provenance, so the assessment is made at the operating
    point the run actually used rather than at one recomputed here.
    """
    unrated: list[ValidityAssessment] = []
    rated: list[ValidityAssessment] = []
    for stage, prop_problem, _thermal in cp.stage_problems(system):
        result = run.final.result_for(prop_problem.problem_id)
        temperature = result.provenance.inputs[mat.TEMPERATURE]
        # The coldest state this body occupies. The lumped trajectory is
        # monotone between its endpoints, so the two endpoints bound it
        # exactly and the colder of them is the coldest state — no sampling
        # of the interior is needed to know it. The Debye floor is assessed
        # there rather than at the converged temperature, because the single
        # coefficient is read at every point of the path and a floor is bound
        # by the coldest point of it. Every other condition on the model keeps
        # the operating point.
        coldest = min(
            (stage.body.initial_temperature, temperature),
            key=lambda value: value.magnitude_in(mat.TEMPERATURE_UNIT),
        )
        unrated.append(
            mat.assess_resistance_validity(prop_problem, temperature)
        )
        if any(
            model.model_id == _RATED_TCR.model_id
            for model in prop_problem.models
        ):
            rated.append(
                mat.assess_rated_resistance_validity(
                    prop_problem, temperature, coldest
                )
            )

    assessments = {_LINEAR_TCR.model_id: combine_assessments(unrated)}
    if rated:
        assessments[_RATED_TCR.model_id] = combine_assessments(rated)
    return assessments


def _contributing_models(
    problems: Sequence[Any], closure: frozenset[str]
) -> tuple[tuple[str, str], ...]:
    """Every model declared by a problem in the closure.

    Read off the problem records rather than asserted here, and deliberately
    wider than ``provenance.models``: a problem may declare a model that
    governs a value without computing it — ``build_resistance_problem`` adds
    the *rated* material claim beside the unrated one whenever the caller
    declared limits, and no execution binding names it because the same
    arithmetic serves both.
    """
    return tuple(
        sorted(
            {
                (model.model_id, model.version)
                for problem in problems
                if problem.problem_id in closure
                for model in problem.models
            }
        )
    )


def _coupling_evidence(run: "cp.CoupledRun") -> CouplingEvidence:
    """The coupled run's own statement about itself, transported unaltered.

    ``outcome`` is the pack's token carried verbatim, so a reader scanning the
    serialized report finds ``iteration_limit_reached`` in it. Nothing here
    interprets that token: the criterion the report derives is derived from the
    numbers beside it, and the two are separately readable on purpose.
    """
    return CouplingEvidence(
        outcome=run.outcome.value,
        iterations_run=run.iterations_run,
        iteration_limit=run.plan.max_iterations,
        largest_iterate_change=run.final_iterate_change,
        tolerance=run.plan.absolute_tolerance,
    )


def _refused_case_run(
    system: cp.CoupledElectroThermalSystem,
    run: "cp.CoupledRun",
    problems,
) -> ElectroThermalCaseRun:
    """The report for a coupled run that stopped at the transfer boundary.

    **A design that stops the loop is a finding about the design**, and the
    report says so rather than the caller catching an exception and being told
    nothing. Three things go in it, and nothing else does.

    *The values the run did produce*, which is whatever the refused result
    carries — possibly none. They are **absent**, not zero and not null with a
    unit: a body that was never solved has no temperature, and inventing one so
    the shape of the report stays familiar is the substitution this whole
    boundary exists to refuse.

    *The coupling's own statement*, carried verbatim as ``transfer_refused``,
    naming the edge, the iteration and the checks that rejected the result.

    *The finding that stopped it.* The refused result's validation is a FAIL,
    which reaches ``derive_verdict`` by the ordinary rules and returns
    NOT_SUPPORTED — a violated condition is a finding, not a gap, and this is
    the distinction the whole task turns on. The material verdicts are computed
    at the temperature the refused solve actually used, so
    ``linear_resistance_ratio`` appears in the report as violated, named, and
    attributed to the model that declares it.

    One report, not one per stage: the sweep did not finish, so there is no
    per-stage result to be about. Reporting one report per stage would claim
    the loop reached stages it never entered.
    """
    refusal = run.refusal
    assert refusal is not None  # the outcome is what selects this path
    refused = refusal.result

    assessments: dict[str, ValidityAssessment] = {}
    for stage, prop_problem, _thermal in cp.stage_problems(system):
        if prop_problem.problem_id != refused.problem_id:
            continue
        temperature = refused.provenance.inputs.get(mat.TEMPERATURE)
        assessments[_LINEAR_TCR.model_id] = mat.assess_resistance_validity(
            prop_problem, temperature
        )
        if any(
            model.model_id == _RATED_TCR.model_id
            for model in prop_problem.models
        ):
            assessments[_RATED_TCR.model_id] = (
                mat.assess_rated_resistance_validity(prop_problem, temperature)
            )
        break

    versions = {
        model.model_id: model.version
        for problem in problems
        for model in problem.models
    }
    report = CredibilityEvidenceReport.from_result(
        refused,
        provenance=run.provenance,
        coupling=_coupling_evidence(run),
        # Only the models of the problem that was refused. The closure of a
        # value this report carries stops there, because the run stopped
        # there: naming the electrical or thermal models would claim they
        # contributed to a value they never saw.
        contributing_models=tuple(
            (model.model_id, versions.get(model.model_id, ""))
            for problem in problems
            if problem.problem_id == refused.problem_id
            for model in problem.models
        ),
        validity=tuple(
            ModelValidityRecord(
                model_id=model_id,
                version=versions.get(model_id, ""),
                assessment=assessment,
            )
            for model_id, assessment in sorted(assessments.items())
        ),
        validation=(
            ValidationCheck(
                name="coupling_transfer_refused",
                outcome=ValidationOutcome.FAIL,
                detail=(
                    f"iteration {refusal.iteration}: "
                    f"{refusal.dependency.source_quantity!r} could not leave "
                    f"{refusal.dependency.source_problem_id!r} for "
                    f"{refusal.dependency.target_problem_id!r}."
                    f"{refusal.dependency.target_quantity}, because that "
                    f"result's own validation failed "
                    f"({', '.join(refusal.failed_checks)}). The loop stopped "
                    f"here; the values it had produced are reported and the "
                    f"ones it never produced are absent."
                ),
            ),
        ),
        notes=(
            "This coupled run stopped at the transfer boundary and did not "
            "complete a sweep. Quantities the run never produced are absent "
            "from this report rather than defaulted."
        ),
    )
    return ElectroThermalCaseRun(run=run, reports=(report,))


def run_electrothermal_case(
    payload: Mapping[str, Any], *, run_id: str = "mcp-electrothermal"
) -> ElectroThermalCaseRun:
    """Payload in, credibility reports out. The whole boundary, end to end.

    **A report is assembled over the dependency closure of the values it
    reports**, and this is the paragraph that used to be wrong. The report was
    built from the thermal sub-result alone, so everything the coupled run knew
    about itself was lost here: whether the coupling reached its criterion,
    which models had taken part, and what any of them said about applying. The
    consequences were not gaps but false statements — ``unassessed_models``
    reported ``()`` on a six-model run, a capped iteration produced a SUPPORTED
    report with no trace of the cap, and a conductor declared good to 301 K and
    run to 338 K produced a SUPPORTED report in which its own declared limit
    appeared nowhere.

    So each report now carries:

    * the **coupling's** own statement, as a typed field, distinct from every
      participant's numerical convergence and outside ``validation``;
    * the **closure** of the reported values, read off the declared dependency
      edges rather than assumed — which for this coupled cycle is the whole
      composition, because a series circuit's second stage really does set the
      first stage's temperature;
    * a **verdict for every model in it** — thermal, unrated and rated
      material, resistor, voltage source and Kirchhoff — each computed here,
      at the operating point the run used, from declarations this boundary
      already holds.

    What has not changed: the thermal sub-result still supplies the values, the
    checks and their notes, because those are what this report is *about*; and
    the caller's applicability declaration still goes in as asserted context,
    marked as the caller's claim and consumed by no verdict.

    This is more restrictive than it was, and the restriction is the finding
    rather than a side effect. Nothing in the payload declares a resistor's
    rated dissipation or a source's current limit, and ``electrical.dc.kcl``
    declares no conditions at all, so the nominal case is now
    INSUFFICIENT_EVIDENCE with those gaps named — instead of SUPPORTED with the
    models that would have raised them left out of the report.
    """
    system = build_electrothermal_system(payload)
    coupling = _read_coupling(payload)

    problems = cp.coupled_problems(
        system,
        {s.component_id: s.conductor.reference_resistance for s in system.stages},
    )
    first_body = system.stages[0].body
    plan = cp.nominal_plan(
        system,
        cp.coupled_dependencies(system, problems),
        seed=coupling.get("seed_temperature", first_body.initial_temperature),
        tolerance=coupling.get("tolerance", DEFAULT_COUPLING_TOLERANCE),
        max_iterations=coupling.get("max_iterations", DEFAULT_COUPLING_BUDGET),
    )
    run = cp.run_fixed_point_coupling(system, plan, run_id=run_id)
    if run.outcome is cp.CouplingOutcome.TRANSFER_REFUSED:
        return _refused_case_run(system, run, problems)

    electrical_id = problems[0].problem_id
    electrical = run.final.result_for(electrical_id)
    dependencies = cp.coupled_dependencies(system, problems)
    coupling_evidence = _coupling_evidence(run)

    # Computed once: every one of these is a verdict about the whole coupled
    # composition, which is what the closure of any reported value here is.
    ratings, source_rating = _read_ratings(payload)
    shared = _electrical_assessments(
        system, electrical, run, ratings, source_rating
    )
    shared.update(_material_assessments(system, run))

    versions = {
        model.model_id: model.version
        for problem in problems
        for model in problem.models
    }

    reports = []
    for stage, (_, _prop, thermal_problem) in zip(
        system.stages, cp.stage_problems(system)
    ):
        power = electrical.value(
            RESISTOR_POWER_METRIC.format(component_id=stage.component_id)
        )
        assessments = dict(shared)
        assessments[_LUMPED.model_id] = lump.assess_lumped_validity(
            thermal_problem,
            initial_temperature=stage.body.initial_temperature,
            ambient_temperature=stage.body.ambient_temperature,
            heat_input=power,
        )
        thermal_result = run.final.result_for(thermal_problem.problem_id)
        closure = cp.dependency_closure(thermal_problem.problem_id, dependencies)
        reports.append(
            CredibilityEvidenceReport.from_result(
                thermal_result,
                # The **run's** provenance, not the sub-solve's: these values
                # were produced by the coupled run, and the sub-solve's own
                # record names one of the six models they rest on. The
                # sub-result's identity stays visible in ``run_id``.
                provenance=run.provenance,
                contributing_models=_contributing_models(problems, closure),
                coupling=coupling_evidence,
                validity=tuple(
                    ModelValidityRecord(
                        model_id=model_id,
                        version=versions[model_id],
                        assessment=assessment,
                    )
                    for model_id, assessment in sorted(assessments.items())
                ),
                validation=_declared_limit_checks(stage),
                declarations=(
                    AssertedContext(
                        source="LumpedApplicabilityDeclaration",
                        payload=stage.body.applicability.to_dict(),
                        description="caller-declared applicability context",
                    ),
                ),
            )
        )
    return ElectroThermalCaseRun(run=run, reports=tuple(reports))


# =====================================================================
# Describing what this boundary accepts
# =====================================================================

@dataclass(frozen=True)
class FieldDescription:
    """One accepted field, as the models describe it.

    Nothing here is written down twice. ``required``, ``dimension``,
    ``unit_exemplar`` and ``description`` are the model record's; ``unlocks``
    is measured against the model's own validity domain.
    """

    section: str
    key: str
    kind: str
    required: bool
    dimension: str | None
    unit_exemplar: str | None
    #: Validity conditions that go from decidable to UNKNOWN without this
    #: field, everything else declared. Empty for a required field (the case
    #: cannot be posed at all), for a declared-but-unmodelled one, and for one
    #: whose job another field can also do — see :attr:`alternative_to`.
    unlocks: tuple[str, ...]
    #: Other payload keys this field is interchangeable with. Non-empty only
    #: when omitting this field alone changes nothing but omitting it together
    #: with those does: the derived quantity has more than one route.
    alternative_to: tuple[str, ...]
    #: What the whole alternative group unlocks. Equal to :attr:`unlocks` when
    #: the field stands alone.
    group_unlocks: tuple[str, ...]
    model_id: str | None
    model_input: str | None
    description: str

    @property
    def path(self) -> str:
        return _path(self.section, self.key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "section": self.section,
            "key": self.key,
            "kind": self.kind,
            "required": self.required,
            "dimension": self.dimension,
            "unit_exemplar": self.unit_exemplar,
            "unlocks_conditions": list(self.unlocks),
            "alternative_to": list(self.alternative_to),
            "group_unlocks_conditions": list(self.group_unlocks),
            "model_id": self.model_id,
            "model_input": self.model_input,
            "description": self.description,
        }


@dataclass(frozen=True)
class CaseDescription:
    """Everything a caller needs to write a payload without reading the source."""

    fields: tuple[FieldDescription, ...]
    #: Model inputs the caller must not supply, and why.
    coupling_supplied: Mapping[str, str]
    models: tuple[str, ...]
    #: One complete runnable payload for THIS system. A field on the record
    #: rather than a call to one system's builder, because a description that
    #: could only ever hand back the electro-thermal example was never a
    #: description of anything else.
    example: Mapping[str, Any] = field(default_factory=dict)

    def field(self, path: str) -> FieldDescription:
        for candidate in self.fields:
            if candidate.path == path:
                return candidate
        raise KeyError(path)

    @property
    def required(self) -> tuple[FieldDescription, ...]:
        return tuple(f for f in self.fields if f.required)

    @property
    def optional(self) -> tuple[FieldDescription, ...]:
        return tuple(f for f in self.fields if not f.required)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": [f.to_dict() for f in self.fields],
            "coupling_supplied_inputs": dict(self.coupling_supplied),
            "models": list(self.models),
            "example": dict(self.example),
        }


#: A fully-declared body at an operating point, used only to *measure* which
#: condition each optional declaration unlocks. Not a default, not a template,
#: and never merged into a caller's payload: the numbers are irrelevant, only
#: the decidability of each condition with and without a field is read from it.
_PROBE_TEMPERATURE = Quantity(320.0, "kelvin")
_PROBE_AMBIENT = Quantity(300.0, "kelvin")
_PROBE_HEAT = Quantity(1.0, "watt")

#: One element and one source for the rating probe, for the same purpose.
_PROBE_RESISTOR = dc_circuit.Resistor("probe", "n1", "gnd", Quantity(1.0, "kohm"))
_PROBE_SOURCE = dc_circuit.DCVoltageSource(
    "probe-v", "n1", "gnd", Quantity(10.0, "volt")
)


def _probe_declaration(
    *, forced: bool = False
) -> thermal_ctx.LumpedApplicabilityDeclaration:
    """The probe, on one convection route.

    Two are needed rather than one. The declaration record refuses a body
    carrying both an expansion coefficient and a velocity -- that is mixed
    convection and neither correlation covers it -- so no single probe can
    measure what each of those two fields unlocks. Each route is measured on
    its own probe and the results are unioned, which reports both correctly:
    either route unlocks the same three correlation conditions.

    What that costs is the ``alternative_to`` grouping. Both fields report a
    non-empty solo unlock, so neither is silent, so the pair pass that finds
    alternatives never sees them. A reader gets two fields unlocking the same
    three conditions instead of one alternative group. NEEDS.md records it.
    """
    route = (
        {"fluid_velocity": Quantity(2.0, "meter/second")}
        if forced
        else {"fluid_expansion_coefficient": Quantity(1.0 / 300.0, "1/kelvin")}
    )
    return thermal_ctx.LumpedApplicabilityDeclaration(
        characteristic_length=Quantity(0.002, "meter"),
        volume=Quantity(2e-5, "meter**3"),
        surface_area=Quantity(0.01, "meter**2"),
        body_conductivity=Quantity(200.0, "watt/meter/kelvin"),
        surface_emissivity=Quantity(0.05, "dimensionless"),
        convection_regime=thermal_ctx.FORCED_CONVECTION,
        conductance_excursion_bound=Quantity(60.0, "kelvin"),
        capacity_excursion_bound=Quantity(100.0, "kelvin"),
        melting_temperature=Quantity(900.0, "kelvin"),
        # Air near 300 K. The route field is supplied by `route` above; every
        # other field is carried because the probe measures which conditions
        # become decidable when a field is present, and a field the probe
        # omits would report that it unlocks nothing.
        fluid_conductivity=Quantity(0.0263, "watt/meter/kelvin"),
        fluid_kinematic_viscosity=Quantity(1.589e-5, "meter**2/second"),
        fluid_prandtl_number=Quantity(0.707, "dimensionless"),
        convection_length=Quantity(0.05, "meter"),
        **route,
    )


def _probe_body(
    declaration: thermal_ctx.LumpedApplicabilityDeclaration,
) -> lump.ThermalBody:
    return lump.ThermalBody(
        body_id="probe",
        heat_capacity=Quantity(2.5, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        ambient_temperature=_PROBE_AMBIENT,
        initial_temperature=_PROBE_AMBIENT,
        duration=Quantity(120.0, "second"),
        applicability=declaration,
    )


def _unknown_conditions(
    declaration: thermal_ctx.LumpedApplicabilityDeclaration,
) -> frozenset[str]:
    problem = lump.build_lumped_thermal_problem(_probe_body(declaration))
    assessment = lump.assess_lumped_validity(
        problem,
        initial_temperature=_PROBE_TEMPERATURE,
        ambient_temperature=_PROBE_AMBIENT,
        heat_input=_PROBE_HEAT,
    )
    return frozenset(assessment.unknown)


def _probe_conductor(limits: mat.MaterialLimits) -> mat.TemperatureDependentConductor:
    return mat.TemperatureDependentConductor(
        component_id="probe",
        reference_resistance=Quantity(10.0, "ohm"),
        temperature_coefficient=Quantity(0.00393, "1/kelvin"),
        reference_temperature=Quantity(293.15, "kelvin"),
        limits=limits,
    )


def _unknown_rated_conditions(limits: mat.MaterialLimits) -> frozenset[str]:
    """Through the domain's own assessor, which supplies the derived ratios.

    Not ``assess_validity`` over a bare parameter context: the rated
    conditions are bounds on *derived* quantities, and a context without them
    reports every one of them UNKNOWN regardless of what was declared — which
    would make every limit look like it unlocks nothing.
    """
    assessment = mat.assess_rated_resistance_validity(
        mat.build_resistance_problem(_probe_conductor(limits)),
        _PROBE_TEMPERATURE,
    )
    return frozenset(assessment.unknown)


#: An operating point for the rating probe. As with the thermal probe the
#: numbers are irrelevant — only which conditions become decidable when a
#: rating is present is read from them.
_PROBE_POWER = Quantity(0.1, "watt")
_PROBE_VOLTAGE = Quantity(10.0, "volt")
_PROBE_CURRENT = Quantity(0.01, "ampere")


def _unknown_rating_conditions(
    rating: dc_models.ComponentRating,
) -> frozenset[str]:
    """Rating conditions still UNKNOWN with this rating declared.

    Both electrical models in one probe. They declare disjoint rating
    conditions, so the union is unambiguous and one measurement serves the
    ``ratings`` and ``source_ratings`` sections alike.
    """
    resistor = dc_models.assess_resistor_validity(
        dc_problem.resistor_relation_problem(_PROBE_RESISTOR),
        rating=rating,
        dissipated_power=_PROBE_POWER,
        voltage_across=_PROBE_VOLTAGE,
    )
    source = dc_models.assess_voltage_source_validity(
        dc_problem.voltage_source_relation_problem(_PROBE_SOURCE),
        rating=rating,
        source_current=_PROBE_CURRENT,
    )
    return frozenset(resistor.unknown) | frozenset(source.unknown)


def _measure_omissions(bindings, build, baseline_of, full):
    """Which conditions each field's omission makes UNKNOWN, and in pairs.

    Lifted out of ``_measure_unlocks`` so a second system's boundary can use
    it. Nothing about it is electro-thermal: ``build`` makes a declaration
    record with some fields dropped, ``baseline_of`` turns one into the set of
    conditions still UNKNOWN, and the difference is what the field unlocked.

    **Solo omission is not the whole story**, which is why the second pass
    exists. A field whose job another field can also do — a characteristic
    length against a volume and an area — reports nothing when dropped alone,
    indistinguishable to a reader from a field nothing reads. Dropping each
    such field together with each other such field finds the pair.

    **Pairs only.** A three-way alternative would need a larger search; no
    domain here has one, and one that appeared would show up as a set of
    fields all reporting nothing rather than as a wrong answer.
    """
    baseline = baseline_of(full)
    solo: dict[str, frozenset[str]] = {}
    for binding in bindings:
        if binding.spec is None:
            # Declared but not modelled: no input, so nothing to measure.
            solo[binding.key] = frozenset()
            continue
        solo[binding.key] = baseline_of(
            build(full, {binding.target_name: None})
        ) - baseline

    silent = [b for b in bindings if b.spec is not None and not solo[b.key]]
    alternates: dict[str, set[str]] = {b.key: set() for b in bindings}
    joint: dict[str, frozenset[str]] = {b.key: frozenset() for b in bindings}
    for i, left in enumerate(silent):
        for right in silent[i + 1:]:
            together = baseline_of(
                build(full, {left.target_name: None, right.target_name: None})
            ) - baseline
            if not together:
                continue
            alternates[left.key].add(right.key)
            alternates[right.key].add(left.key)
            joint[left.key] = joint[left.key] | together
            joint[right.key] = joint[right.key] | together
    return solo, alternates, joint


def _measure_section_unlocks(bindings, build, baseline_of, full):
    """:func:`_measure_omissions`, flattened into the description's shape."""
    solo, alternates, joint = _measure_omissions(
        bindings, build, baseline_of, full
    )
    return {
        binding.key: (
            tuple(sorted(solo[binding.key])),
            tuple(sorted(alternates[binding.key])),
            tuple(sorted(solo[binding.key] or joint[binding.key])),
        )
        for binding in bindings
    }


def _measure_unlocks() -> dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]]:
    """Per optional field: what it unlocks, what it substitutes for, what the group unlocks.

    Measured by omission against the model's own validity domain rather than
    read off a table, so it is a statement about the domain as it is now. A
    condition that starts UNKNOWN for an unrelated reason cancels out: the
    comparison is between the same operating point with and without a field.

    **Solo omission is not the whole story**, and saying only that would be
    misleading. ``characteristic_length`` can be declared directly *or* derived
    from ``body_volume`` and ``surface_area``, so dropping either one alone
    leaves every condition decidable and a solo measurement reports that it
    unlocks nothing — indistinguishable, to a reader, from a field nothing
    reads. So a second pass drops each such field together with each other
    such field and reports the pair when the joint omission does bite.

    **Pairs only.** A three-way alternative would need a larger search; this
    domain has none, and a group that appeared would show up as a set of
    fields all reporting nothing rather than as a wrong answer.
    """
    thermal_optional = [b for b in _section(APPLICABILITY) if not b.is_required]
    limits_optional = list(_section(LIMITS))

    measure = _measure_omissions

    measured: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {}

    # Measured on both convection routes and unioned. One probe cannot carry
    # both an expansion coefficient and a velocity, so one probe cannot
    # measure what both unlock; see _probe_declaration.
    thermal_solo: dict[str, set[str]] = {b.key: set() for b in thermal_optional}
    thermal_alternates: dict[str, set[str]] = {
        b.key: set() for b in thermal_optional
    }
    thermal_joint: dict[str, set[str]] = {b.key: set() for b in thermal_optional}
    for forced in (False, True):
        solo, alternates, joint = measure(
            thermal_optional,
            lambda full, drop: dataclasses.replace(full, **drop),
            _unknown_conditions,
            _probe_declaration(forced=forced),
        )
        for binding in thermal_optional:
            key = binding.key
            thermal_solo[key] |= solo[key]
            thermal_alternates[key] |= alternates[key]
            thermal_joint[key] |= joint[key]
    for binding in thermal_optional:
        key = binding.key
        measured[key] = (
            tuple(sorted(thermal_solo[key])),
            tuple(sorted(thermal_alternates[key])),
            tuple(sorted(thermal_solo[key] or thermal_joint[key])),
        )

    full_limits = mat.MaterialLimits(
        linearization_band=Quantity(80.0, "kelvin"),
        maximum_operating_temperature=Quantity(400.0, "kelvin"),
        debye_temperature=Quantity(343.0, "kelvin"),
    )
    solo, alternates, joint = measure(
        limits_optional,
        lambda full, drop: dataclasses.replace(full, **drop),
        _unknown_rated_conditions,
        full_limits,
    )
    for binding in limits_optional:
        key = binding.key
        measured[key] = (
            tuple(sorted(solo[key])),
            tuple(sorted(alternates[key])),
            tuple(sorted(solo[key] or joint[key])),
        )

    # The ratings, measured the same way. `derating_factor` is deliberately
    # among them and correctly measures nothing: it has a default, so omitting
    # it leaves every rating condition decidable. It narrows a rating rather
    # than unlocking one.
    rating_bindings = list(_section(RATINGS)) + list(_section(SOURCE_RATINGS))
    full_rating = dc_models.ComponentRating(
        rated_power=Quantity(1.0, "watt"),
        maximum_working_voltage=Quantity(100.0, "volt"),
        maximum_current=Quantity(1.0, "ampere"),
    )
    def drop_rating(full, drop):
        # `derating_factor` is a float with a default rather than an optional
        # Quantity, so "omitted" for it means back to NO_DERATING, not None.
        # Passing None would fail the record's own constructor and report the
        # field as unlockable rather than as unlocking nothing.
        adjusted = {
            name: (dc_models.NO_DERATING if name == dc_models.DERATING_FACTOR
                   else value)
            for name, value in drop.items()
        }
        return dataclasses.replace(full, **adjusted)

    solo, alternates, joint = measure(
        rating_bindings, drop_rating, _unknown_rating_conditions, full_rating
    )
    for binding in rating_bindings:
        key = binding.key
        measured[key] = (
            tuple(sorted(solo[key])),
            tuple(sorted(alternates[key])),
            tuple(sorted(solo[key] or joint[key])),
        )
    return measured


def describe_electrothermal_case() -> CaseDescription:
    """Every field this boundary accepts, as the models declare it.

    Step 9's ``describe_capabilities`` serves this. It is computed, not
    written: the field list comes from the binding table (audited against the
    registries at import), and required-ness, dimension, prose and unlocked
    conditions come from the model records themselves. A domain change that
    would make this description wrong makes it *different* instead.
    """
    measured = _measure_unlocks()
    fields = []
    for binding in _BINDINGS:
        exemplar = binding.unit_exemplar
        spec = binding.spec
        unlocks, alternates, group = measured.get(binding.key, ((), (), ()))
        fields.append(
            FieldDescription(
                section=binding.section,
                key=binding.key,
                kind=binding.kind,
                required=binding.is_required,
                dimension=dimensionality(exemplar) if exemplar else None,
                unit_exemplar=exemplar,
                unlocks=unlocks,
                alternative_to=alternates,
                group_unlocks=group,
                model_id=binding.model.model_id if binding.model else None,
                model_input=spec.name if spec else None,
                description=binding.description,
            )
        )
    return CaseDescription(
        example=example_electrothermal_payload(),
        fields=tuple(fields),
        coupling_supplied=dict(COUPLING_SUPPLIED_INPUTS),
        models=tuple(sorted({m.model_id for m in _MODELS})),
    )


def example_electrothermal_payload() -> dict[str, Any]:
    """One complete, runnable payload with every optional field supplied.

    Every value carries a unit, including the dimensionless one. Kept as data
    rather than prose so the description can hand a caller something that has
    been through :func:`build_electrothermal_system` in the test suite.
    """
    return {
        "source_voltage": "5 volt",
        "stages": [
            {
                "component_id": "R1",
                "conductor": {
                    "reference_resistance": "10 ohm",
                    "temperature_coefficient": "0.00393 1/kelvin",
                    "reference_temperature": "293.15 kelvin",
                    "limits": {
                        "linearization_band": "80 kelvin",
                        "maximum_operating_temperature": "400 kelvin",
                        "debye_temperature": "343 kelvin",
                    },
                },
                "body": {
                    "heat_capacity": "2.5 joule/kelvin",
                    "ambient_conductance": "0.05 watt/kelvin",
                    "ambient_temperature": "300 kelvin",
                    "initial_temperature": "300 kelvin",
                    "duration": "120 second",
                    "applicability": {
                        "characteristic_length": "0.002 meter",
                        "body_volume": "2e-5 meter**3",
                        "surface_area": "0.01 meter**2",
                        "body_conductivity": "200 watt/meter/kelvin",
                        "surface_emissivity": "0.05 dimensionless",
                        "convection_regime": "forced",
                        "conductance_excursion_bound": "60 kelvin",
                        "capacity_excursion_bound": "100 kelvin",
                        "melting_temperature": "900 kelvin",
                        # Where the ambient conductance came from. Air near
                        # 300 K over a 0.6 m plate at 1 m/s: Re = 3.78e4,
                        # Nu = 0.664 Re^(1/2) Pr^(1/3) = 114.9, and
                        # h = Nu k_f / L = 5.00 W/(m^2 K), which is exactly
                        # the 0.05 W/K over 0.01 m^2 declared above. A worked
                        # example that did not close that loop would be
                        # teaching a caller to declare an unsupported
                        # coefficient.
                        "fluid_conductivity": "0.0261 watt/meter/kelvin",
                        "fluid_kinematic_viscosity": "1.589e-5 meter**2/second",
                        "fluid_prandtl_number": "0.707 dimensionless",
                        "fluid_velocity": "1 meter/second",
                        "convection_length": "0.6 meter",
                    },
                },
            }
        ],
        "coupling": {
            "seed_temperature": "300 kelvin",
            "tolerance": "1e-6 kelvin",
            "max_iterations": 50,
        },
    }
