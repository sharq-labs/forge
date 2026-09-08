"""The battery boundary: a JSON description of a cell under load, or a refusal.

The second system this transport exposes, and the reason the machinery in
:mod:`engcore.mcp.problem` is parameterized rather than closed over one table.
Every rule that module's docstring states applies here unchanged: every
physical value carries a unit, unknown fields are refused rather than ignored,
and optional stays optional — a field the models mark ``required=False`` may
be omitted, and omitting it yields UNKNOWN rather than a default.

What this module adds
---------------------
Nothing scientific. It builds a :class:`~engcore.domains.battery.cell.
CellSpecification`, a :class:`~engcore.domains.battery.cell.DischargeLoad` and
the thermal declaration the coupled march needs, hands them to
:func:`~engcore.domains.battery.coupling.run_self_heating_discharge`, and
assembles the result into a
:class:`~engcore.mcp.evidence.CredibilityEvidenceReport`. **The battery domain
is not touched**: no condition is evaluated here, no threshold is read, and the
four validity verdicts are the ones the march itself recorded.

Two things about this system that the electro-thermal one does not have
------------------------------------------------------------------------
**The coupling is a one-way march, not a fixed point.** The cell heats itself,
the body carries the temperature into the next step, and nothing iterates to
convergence. :class:`~engcore.mcp.evidence.CouplingEvidence` describes a fixed
point — iterations run against a budget, the largest iterate change against a
tolerance — and none of those numbers exists here. Forcing the march into it
would report a converged iteration where there was none, so the report carries
``coupling=None`` and the response carries the march's own outcome as its own
field. ``NEEDS.md`` records the gap.

**The thermal model's applicability cannot be declared.**
``run_self_heating_discharge`` takes no applicability declaration, so the
lumped body it builds internally has an empty one and the thermal half of a
coupled battery run can never be better than UNKNOWN. Adding the parameter is a
change to the battery domain, which this task is forbidden to make. The lumped
model is still reported — a model left out of a report is a model the report
silently claims nothing about — and it is reported as what it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..domains.battery import cell as bat
from ..domains.battery import context as bctx
from ..domains.battery import coupling as bcp
from ..domains.battery import models as bmdl
from ..domains.battery import solver as bsol
from ..domains.thermal_models import lumped as lump
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.provenance import ProvenanceRecord
from ..scientific.units.quantity import Quantity, dimensionality
from .errors import MalformedPayloadError, MissingFieldError
from .evidence import (
    AssertedContext,
    CredibilityEvidenceReport,
    ModelValidityRecord,
)
from .problem import (
    Binding,
    CaseDescription,
    FieldDescription,
    _measure_section_unlocks,
    _path,
    _read_section,
    _require_mapping,
    audit_bindings,
)

__all__ = [
    "BATTERY_SUPPLIED_INPUTS",
    "BatteryCaseRun",
    "build_battery_case",
    "describe_battery_case",
    "example_battery_payload",
    "run_battery_case",
]

# =====================================================================
# The model records this boundary reads
# =====================================================================

_MODELS = bmdl.BATTERY_MODELS
_LUMPED = lump.LUMPED_CAPACITY_MODEL

#: Model inputs a caller must not supply, and why. Short, because this system
#: solves for less than the electro-thermal one does: the march advances the
#: temperature and the state of charge, and the caller declares where both
#: start rather than where they end.
BATTERY_SUPPLIED_INPUTS: Mapping[str, str] = {
    bctx.OCV_CURVE: (
        "not supplied at this boundary at all, and the honest entry for that "
        "is here rather than a payload field nobody can fill. Every field of "
        "this payload is one quantity; a declared curve is a form, an "
        "interpolation, a set of samples and the interval they are evidence "
        "over, and there is no field shape here that carries one. A caller "
        "through this boundary declares the two endpoint voltages and gets "
        "the affine chord between them, exactly as before. A caller "
        "constructing a CellSpecification directly may declare the curve."
    ),
}

# =====================================================================
# The payload shape
# =====================================================================

ROOT = ""
CELL = "cell"
LIMITS = "cell.limits"
LOAD = "load"
THERMAL = "thermal"
MARCH = "march"

#: How many intervals the march is cut into when the caller does not say. The
#: temperature rise is resolved by the march rather than solved for, so the
#: step count is a numerical declaration and not a physical one.
DEFAULT_STEPS = 10


def _limit_binding(spec) -> Binding:
    """One of the cell's twenty declared limits.

    Built from ``LIMIT_SPECS`` rather than written out, so a limit added to the
    battery domain becomes a payload field without this file being edited —
    and one removed becomes an import failure in ``audit_bindings`` rather
    than a description that has quietly stopped being true.
    """
    return Binding(
        section=LIMITS,
        key=spec.name,
        kind="quantity",
        model=_owning_model(spec.name),
        input_name=spec.name,
    )


def _owning_model(input_name: str):
    """The first battery model declaring this input, for its prose and unit.

    Several limits are declared by more than one model — ``usable_soc_minimum``
    by three of the four — and any of them is an equally good authority for the
    dimension and the description. Taking the first in a fixed order keeps the
    description stable across runs.
    """
    for model in _MODELS:
        for spec in model.inputs:
            if spec.name == input_name:
                return model
    raise InvalidScientificProblem(
        f"no battery model declares an input {input_name!r}; the binding "
        f"table in engcore.mcp.battery is out of step with the model records"
    )


_BINDINGS: tuple[Binding, ...] = (
    # ---- the cell ----------------------------------------------------
    Binding(
        section=CELL,
        key="cell_id",
        kind="identifier",
        required=True,
        note=(
            "Names the cell. Carried into the problem id and the thermal "
            "body's id, so one run's records can be tied together."
        ),
    ),
    Binding(section=CELL, key="nominal_capacity", kind="quantity",
            model=_owning_model("nominal_capacity"),
            input_name="nominal_capacity"),
    Binding(section=CELL, key="internal_resistance", kind="quantity",
            model=_owning_model("internal_resistance"),
            input_name="internal_resistance"),
    Binding(section=CELL, key="open_circuit_voltage_at_full", kind="quantity",
            model=_owning_model("open_circuit_voltage_at_full"),
            input_name="open_circuit_voltage_at_full"),
    Binding(section=CELL, key="open_circuit_voltage_at_empty", kind="quantity",
            model=_owning_model("open_circuit_voltage_at_empty"),
            input_name="open_circuit_voltage_at_empty"),
    Binding(section=CELL, key="coulombic_efficiency", kind="quantity",
            model=_owning_model("coulombic_efficiency"),
            input_name="coulombic_efficiency"),
    Binding(
        section=CELL,
        key="chemistry",
        kind="category",
        required=False,
        vocabulary=tuple(bctx.CHEMISTRY_VOCABULARY),
        note=(
            "One of "
            f"{list(bctx.CHEMISTRY_VOCABULARY)}. Declared but not modelled: no "
            "validity condition reads it and it unlocks nothing. It records "
            "why the caller believes their declared ratings and spans are "
            "credible; a verdict a chemistry string could move would be a "
            "verdict resting on an unverifiable claim by the party being "
            "assessed."
        ),
    ),
    # ---- the cell's declared limits ----------------------------------
    *tuple(_limit_binding(spec) for spec in bctx.LIMIT_SPECS),
    Binding(
        section=LIMITS,
        key="cooling_mode",
        kind="category",
        required=False,
        vocabulary=tuple(bctx.COOLING_MODE_VOCABULARY),
        note=(
            "One of "
            f"{list(bctx.COOLING_MODE_VOCABULARY)}. Inert on the same terms as "
            "chemistry: it records why the caller believes their "
            "cell_thermal_conductance and self_heating_rise_bound are "
            "credible, and no condition consults it."
        ),
    ),
    # ---- the load ----------------------------------------------------
    Binding(
        section=LOAD,
        key="load_id",
        kind="identifier",
        required=True,
        note="Names this operating point. Carried into the problem id.",
    ),
    Binding(section=LOAD, key="discharge_current", kind="quantity",
            model=_owning_model("discharge_current"),
            input_name="discharge_current", target="current"),
    Binding(section=LOAD, key="state_of_charge", kind="quantity",
            model=_owning_model("state_of_charge"),
            input_name="state_of_charge", target="initial_state_of_charge"),
    Binding(section=LOAD, key="cell_temperature", kind="quantity",
            model=_owning_model("cell_temperature"),
            input_name="cell_temperature"),
    # THE STEP DURATION, not the horizon. The march advances `steps`
    # intervals of this length, so the discharge lasts `duration * steps` and
    # a caller who reads this as the total gets a run `steps` times too long.
    # Named as the models name it, because that is what a reader holding the
    # model record will look for.
    Binding(section=LOAD, key="duration", kind="quantity",
            model=_owning_model("duration"), input_name="duration"),
    Binding(section=LOAD, key="pulse_current", kind="quantity",
            model=_owning_model("pulse_current"), input_name="pulse_current"),
    Binding(section=LOAD, key="pulse_duration", kind="quantity",
            model=_owning_model("pulse_duration"), input_name="pulse_duration"),
    Binding(section=LOAD, key="cutoff_voltage", kind="quantity",
            model=_owning_model("cutoff_voltage"), input_name="cutoff_voltage"),
    Binding(section=LOAD, key="cutoff_state_of_charge", kind="quantity",
            model=_owning_model("cutoff_state_of_charge"),
            input_name="cutoff_state_of_charge"),
    Binding(
        section=LOAD,
        key="duty_type",
        kind="category",
        required=False,
        vocabulary=tuple(bctx.DUTY_TYPE_VOCABULARY),
        note=(
            "One of "
            f"{list(bctx.DUTY_TYPE_VOCABULARY)}. Inert. Declaring 'pulsed' "
            "does not satisfy the pulse conditions -- a declared pulse current "
            "and a declared pulse duration do, and a string never does."
        ),
    ),
    # ---- the body the cell heats -------------------------------------
    Binding(
        section=THERMAL,
        key="heat_capacity",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.HEAT_CAPACITY,
    ),
    Binding(
        section=THERMAL,
        key="ambient_temperature",
        kind="quantity",
        model=_LUMPED,
        input_name=lump.AMBIENT_TEMPERATURE,
    ),
    # ---- how finely the march resolves the rise ----------------------
    Binding(
        section=MARCH,
        key="steps",
        kind="count",
        required=False,
        note=(
            f"Intervals the march advances; {DEFAULT_STEPS} if omitted. Each is "
            "load.duration long, so the discharge lasts duration * steps -- "
            "raising this lengthens the run rather than resolving the same run "
            "more finely, which is the opposite of what a step count usually "
            "means and is why it is said here."
        ),
    ),
)

audit_bindings(
    _BINDINGS, _MODELS, BATTERY_SUPPLIED_INPUTS, where="engcore.mcp.battery"
)


# =====================================================================
# Building the declarations
# =====================================================================

def _section_of(payload: Mapping[str, Any], name: str, *, extra=()) -> dict:
    return _read_section(
        _require_mapping(payload.get(name), where=name),
        name,
        extra=extra,
        bindings=_BINDINGS,
    )


def build_battery_case(payload: Mapping[str, Any]):
    """``(cell, load, thermal, steps)`` from one payload, or a refusal.

    Every value is read through the shared machinery, so a missing unit, a
    wrong dimension or an unrecognised key is refused here with the same
    vocabulary the electro-thermal boundary uses.
    """
    _read_section(payload, ROOT, extra=("cell", "load", "thermal", "march"),
                  bindings=_BINDINGS)

    cell_values = _section_of(payload, CELL, extra=("limits",))
    limit_values = _read_section(
        _require_mapping(
            _require_mapping(payload.get("cell"), where="cell").get("limits"),
            where=_path(CELL, "limits"),
        ),
        LIMITS,
        bindings=_BINDINGS,
    )
    load_values = _section_of(payload, LOAD)
    thermal_values = _section_of(payload, THERMAL)
    march_values = _section_of(payload, MARCH)

    limits = bctx.CellLimits(**limit_values)
    cell = bat.CellSpecification(limits=limits, **cell_values)
    load = bat.DischargeLoad(**load_values)

    # The body exchanges through the conductance the CELL declared -- the
    # domain will not accept a second source for that number. Named here as a
    # missing field rather than left to the domain's own refusal, so an agent
    # is told which payload key to add.
    if limits.cell_thermal_conductance is None:
        raise MissingFieldError(
            f"{_path(LIMITS, bctx.CELL_THERMAL_CONDUCTANCE)} is required for a "
            f"coupled run and was not supplied: the conductance the "
            f"self-heating condition is stated over and the conductance the "
            f"thermal body exchanges through are the same number, and this "
            f"runtime will not invent it. Declare it, or the cell cannot be "
            f"coupled to a body at all"
        )
    return cell, load, thermal_values, march_values.get("steps", DEFAULT_STEPS)


# =====================================================================
# Running one case
# =====================================================================

@dataclass(frozen=True)
class BatteryCaseRun:
    """One marched discharge and the report assembled around it."""

    run: bcp.SelfHeatingRun
    report: CredibilityEvidenceReport


def _provenance(
    cell: bat.CellSpecification,
    load: bat.DischargeLoad,
    thermal: Mapping[str, Quantity],
    run_id: str,
    steps: int,
    march: bcp.SelfHeatingRun,
) -> ProvenanceRecord:
    """What ran, and on what.

    ``run_self_heating_discharge`` returns steps, not a
    :class:`~engcore.scientific.results.result.ScientificResult`, so there is
    still no producer-written provenance record to carry, and the inputs below
    are declared values read back out of the records this boundary built.

    **What is no longer assembled here is who ran.** This function used to name
    ``BatteryCellSolver`` and ``LumpedThermalSolver`` as participants because
    those are the solvers a marched run *ought* to involve -- and one of them
    did not: the march called ``evaluate_step`` directly, so
    ``BatteryCellSolver.validate`` never executed, and the record named a
    solver that had done nothing. A boundary assembling participants after the
    fact can only name what it believes ran, and belief is what was wrong.

    ``march.bindings`` are produced by the executions themselves, through
    ``ExecutionBinding.from_execution``, which reads the solver identity off
    each prepared solve. ``ProvenanceRecord`` derives ``models`` and ``solvers``
    from them and refuses any solver they do not cover, so this record cannot
    name a participant the march did not run.
    """
    inputs: dict[str, Quantity] = {
        bctx.NOMINAL_CAPACITY: cell.nominal_capacity,
        bctx.INTERNAL_RESISTANCE: cell.internal_resistance,
        bctx.OCV_AT_FULL: cell.open_circuit_voltage_at_full,
        bctx.OCV_AT_EMPTY: cell.open_circuit_voltage_at_empty,
        bctx.COULOMBIC_EFFICIENCY: cell.coulombic_efficiency,
        bctx.DISCHARGE_CURRENT: load.current,
        bctx.STATE_OF_CHARGE: load.initial_state_of_charge,
        bctx.CELL_TEMPERATURE: load.cell_temperature,
        bctx.DURATION: load.duration,
        lump.HEAT_CAPACITY: thermal["heat_capacity"],
        lump.AMBIENT_TEMPERATURE: thermal["ambient_temperature"],
    }
    for spec in bctx.LIMIT_SPECS:
        value = getattr(cell.limits, spec.name)
        if value is not None:
            inputs[spec.name] = value
    for label in ("pulse_current", "pulse_duration", "cutoff_voltage",
                  "cutoff_state_of_charge"):
        value = getattr(load, label)
        if value is not None:
            inputs[label] = value

    return ProvenanceRecord(
        run_id=run_id,
        # `models` and `solvers` are left to be derived from the bindings.
        # Naming them here would be a second place to write the same fact, and
        # the place the wrong one was written.
        bindings=march.bindings,
        inputs=inputs,
        assumptions=tuple(
            sorted({a for model in _MODELS for a in model.assumptions})
        ),
        metadata={
            "system": "battery",
            "steps": str(steps),
            "cell_id": cell.cell_id,
            "load_id": load.load_id,
        },
    )


def run_battery_case(
    payload: Mapping[str, Any], *, run_id: str | None = None
) -> BatteryCaseRun:
    """March one cell's self-heating discharge and report its credibility.

    The four battery verdicts are the **march's own**, combined over EVERY
    step rather than read off the last one — which is the distinction
    :class:`~engcore.domains.battery.coupling.SelfHeatingStep` exists to keep,
    and which this function got wrong. Nothing here re-assesses anything the
    domain already assessed.

    It read ``final.validity``, and the docstring claimed that was "combined
    over that whole interval". It was not: it is combined over the two
    INSTANTS of the final step, and every earlier step was discarded. A march
    that entered an inadmissible region and settled out of it therefore
    reported a clean domain. Seventeen benchmark cases constructed to be
    caught by ``polarization_unmodelled_fraction`` were reported SUPPORTED
    while the march itself had recorded step 1 as
    OUTSIDE_VALIDATED_DOMAIN.

    The lumped model is assessed here, because the march does not return its
    body and the coupling API accepts no applicability declaration for it. It
    is reported as UNKNOWN, which is the truth: an empty declaration supports
    no thermal verdict, and leaving the model out would be a report claiming
    nothing about a model that produced half its numbers.
    """
    cell, load, thermal, steps = build_battery_case(payload)
    identifier = run_id or f"battery-{cell.cell_id}-{load.load_id}"

    run = bcp.run_self_heating_discharge(
        cell,
        load,
        heat_capacity=thermal["heat_capacity"],
        ambient_temperature=thermal["ambient_temperature"],
        steps=steps,
    )
    final = run.final

    # The same body the march built internally, rebuilt here only so the
    # thermal model can be assessed at all. Same constructor, same arguments.
    body = bcp.thermal_body_for(
        cell,
        heat_capacity=thermal["heat_capacity"],
        ambient_temperature=thermal["ambient_temperature"],
        initial_temperature=load.cell_temperature,
        # `load.duration` IS the step duration, not the horizon: the march
        # multiplies it by `steps` and the total elapsed time is the product.
        # Dividing here would rebuild a different body than the one the march
        # advanced, and the thermal verdict would be about a step that never
        # ran.
        step_duration=load.duration,
    )
    thermal_assessment = lump.assess_lumped_validity(
        lump.build_lumped_thermal_problem(body),
        initial_temperature=load.cell_temperature,
        ambient_temperature=thermal["ambient_temperature"],
        heat_input=final.heat_generation,
    )

    versions = {m.model_id: m.version for m in (*_MODELS, _LUMPED)}
    validity = tuple(
        ModelValidityRecord(
            model_id=model_id, version=versions[model_id], assessment=assessment
        )
        for model_id, assessment in sorted(
            {
                **run.validity_over_the_march,
                _LUMPED.model_id: thermal_assessment,
            }.items()
        )
    )

    report = CredibilityEvidenceReport(
        run_id=identifier,
        values={
            "terminal_voltage": final.terminal_voltage,
            "final_state_of_charge": final.final_state_of_charge,
            "heat_generation": final.heat_generation,
            "final_temperature": final.final_temperature,
        },
        provenance=_provenance(cell, load, thermal, identifier, steps, run),
        validity=validity,
        # BOTH sub-solves' own checks, carried verbatim from the final step.
        # Not re-run and not re-interpreted.
        #
        # The cell's were missing, and not because anyone chose to leave them
        # out: the march called `evaluate_step` directly, so
        # `BatteryCellSolver.validate` never ran and there were no cell checks
        # to carry. A report that named that solver in its provenance and
        # carried none of its checks was describing a solve that had not
        # happened. The march runs the solver now, so they exist and they
        # arrive here.
        #
        # The two sets share no check name -- the cell reports
        # `metric_dimensions`, `coulomb_balance_residual` and
        # `rint_terminal_residual`, the body reports `lumped_balance_residual`
        # and `analytic_reference_agreement` -- so they concatenate without
        # renaming. `CredibilityEvidenceReport` refuses a duplicate name, so a
        # future collision is an error here rather than a silently dropped
        # check.
        validation=tuple(final.cell_validation.checks)
        + tuple(final.thermal_validation.checks),
        # No CouplingEvidence: the march is one-way and never iterates to a
        # fixed point, so every number that record carries -- iterations run,
        # iterate change, tolerance -- would have to be invented. The march's
        # own outcome travels beside the report instead.
        coupling=None,
        contributing_models=tuple(
            sorted((m.model_id, m.version) for m in (*_MODELS, _LUMPED))
        ),
        declarations=(
            AssertedContext(
                source="CellLimits",
                payload=cell.limits.to_dict(),
                description="caller-declared cell limits",
            ),
            AssertedContext(
                source="DischargeLoad",
                payload=load.to_dict(),
                description="caller-declared duty and stopping rule",
            ),
        ),
    )
    return BatteryCaseRun(run=run, report=report)


# =====================================================================
# Describing what this boundary accepts
# =====================================================================

def _probe_limits(**overrides) -> bctx.CellLimits:
    """Every limit declared, so each one's omission can be measured.

    Not a default and never merged into a caller's payload: the numbers are
    irrelevant and only the decidability of each condition with and without a
    field is read from them.
    """
    values = dict(
        continuous_discharge_c_rate=Quantity(3.0, "1/hour"),
        pulse_discharge_c_rate=Quantity(10.0, "1/hour"),
        rated_pulse_duration=Quantity(30.0, "second"),
        usable_soc_minimum=Quantity(0.1, "dimensionless"),
        usable_soc_maximum=Quantity(0.95, "dimensionless"),
        minimum_discharge_temperature=Quantity(253.15, "kelvin"),
        maximum_discharge_temperature=Quantity(333.15, "kelvin"),
        resistance_reference_temperature=Quantity(298.15, "kelvin"),
        resistance_temperature_span=Quantity(25.0, "kelvin"),
        cell_thermal_conductance=Quantity(0.4, "watt/kelvin"),
        self_heating_rise_bound=Quantity(15.0, "kelvin"),
        polarization_time_constant=Quantity(20.0, "second"),
        soc_step_resolution=Quantity(0.05, "dimensionless"),
        capacity_reference_temperature=Quantity(298.15, "kelvin"),
        capacity_temperature_span=Quantity(25.0, "kelvin"),
        peukert_exponent=Quantity(1.05, "dimensionless"),
        peukert_reference_current=Quantity(1.0, "ampere"),
        peukert_fit_decades=Quantity(1.5, "dimensionless"),
        peukert_reference_temperature=Quantity(298.15, "kelvin"),
        peukert_temperature_span=Quantity(25.0, "kelvin"),
    )
    values.update(overrides)
    return bctx.CellLimits(**values)


def _probe_load(**overrides) -> bat.DischargeLoad:
    values = dict(
        load_id="probe",
        current=Quantity(1.5, "ampere"),
        initial_state_of_charge=Quantity(0.9, "dimensionless"),
        cell_temperature=Quantity(298.15, "kelvin"),
        duration=Quantity(600.0, "second"),
        pulse_current=Quantity(4.0, "ampere"),
        pulse_duration=Quantity(10.0, "second"),
        cutoff_voltage=Quantity(3.0, "volt"),
        cutoff_state_of_charge=Quantity(0.15, "dimensionless"),
    )
    values.update(overrides)
    return bat.DischargeLoad(**values)


def _probe_cell(limits: bctx.CellLimits) -> bat.CellSpecification:
    return bat.CellSpecification(
        cell_id="probe",
        nominal_capacity=Quantity(2.5, "ampere_hour"),
        internal_resistance=Quantity(0.03, "ohm"),
        open_circuit_voltage_at_full=Quantity(4.2, "volt"),
        open_circuit_voltage_at_empty=Quantity(3.0, "volt"),
        coulombic_efficiency=Quantity(0.99, "dimensionless"),
        limits=limits,
    )


def _unknown_battery_conditions(
    limits: bctx.CellLimits, load: bat.DischargeLoad
) -> frozenset[str]:
    """Every battery condition still UNKNOWN with this declaration.

    Through the domain's own ``assess_all``, which supplies the derived
    quantities. A bare parameter context would report every derived condition
    UNKNOWN regardless of what was declared, which would make every limit look
    like it unlocks nothing.
    """
    cell = _probe_cell(limits)
    problem = bat.build_battery_problem(cell, load)
    assessments = bat.assess_all(
        problem,
        state_of_charge=load.initial_state_of_charge,
        discharge_current=load.current,
        cell_temperature=load.cell_temperature,
        open_circuit_voltage_curve=cell.open_circuit_voltage_curve,
    )
    return frozenset(
        name
        for assessment in assessments.values()
        for name in assessment.unknown
    )


def describe_battery_case() -> CaseDescription:
    """Every field this boundary accepts, as the battery models declare it.

    Computed, not written. The field list comes from the binding table -- which
    is itself built from ``LIMIT_SPECS`` and audited against the registries at
    import -- and required-ness, dimension, prose and unlocked conditions come
    from the model records.
    """
    limit_bindings = [b for b in _BINDINGS if b.section == LIMITS]
    load_optional = [
        b for b in _BINDINGS if b.section == LOAD and not b.is_required
    ]

    measured = _measure_section_unlocks(
        limit_bindings,
        lambda full, drop: bctx.CellLimits(
            **{
                spec.name: (
                    None if spec.name in drop else getattr(full, spec.name)
                )
                for spec in bctx.LIMIT_SPECS
            }
        ),
        lambda limits: _unknown_battery_conditions(limits, _probe_load()),
        _probe_limits(),
    )
    measured.update(
        _measure_section_unlocks(
            load_optional,
            lambda full, drop: _probe_load(
                **{name: None for name in drop}
            ),
            lambda load: _unknown_battery_conditions(_probe_limits(), load),
            _probe_load(),
        )
    )

    fields = []
    for binding in _BINDINGS:
        unlocks, alternates, group = measured.get(binding.key, ((), (), ()))
        fields.append(
            FieldDescription(
                section=binding.section,
                key=binding.key,
                kind=binding.kind,
                required=binding.is_required,
                dimension=(
                    None
                    if binding.unit_exemplar is None
                    else dimensionality(binding.unit_exemplar)
                ),
                unit_exemplar=binding.unit_exemplar,
                unlocks=unlocks,
                alternative_to=alternates,
                group_unlocks=group,
                model_id=binding.model.model_id if binding.model else None,
                model_input=binding.input_name,
                description=binding.description,
            )
        )
    return CaseDescription(
        fields=tuple(fields),
        coupling_supplied=dict(BATTERY_SUPPLIED_INPUTS),
        models=tuple(sorted(m.model_id for m in (*_MODELS, _LUMPED))),
        example=example_battery_payload(),
    )


def example_battery_payload() -> dict[str, Any]:
    """One complete, runnable payload with every optional field supplied.

    A 2.5 Ah cell discharged at 1.5 A for ten minutes -- ten steps of sixty
    seconds -- heating itself against a 0.4 W/K path to a 298.15 K ambient.
    Every value carries a unit, including the dimensionless ones.
    """
    return {
        "cell": {
            "cell_id": "C1",
            "nominal_capacity": "2.5 ampere_hour",
            "internal_resistance": "0.03 ohm",
            "open_circuit_voltage_at_full": "4.2 volt",
            "open_circuit_voltage_at_empty": "3.0 volt",
            "coulombic_efficiency": "0.99 dimensionless",
            "chemistry": "lithium_ion",
            "limits": {
                "continuous_discharge_c_rate": "3 1/hour",
                "pulse_discharge_c_rate": "10 1/hour",
                "rated_pulse_duration": "30 second",
                "usable_soc_minimum": "0.1 dimensionless",
                "usable_soc_maximum": "0.95 dimensionless",
                "minimum_discharge_temperature": "253.15 kelvin",
                "maximum_discharge_temperature": "333.15 kelvin",
                "resistance_reference_temperature": "298.15 kelvin",
                "resistance_temperature_span": "25 kelvin",
                "cell_thermal_conductance": "0.4 watt/kelvin",
                "self_heating_rise_bound": "15 kelvin",
                "polarization_time_constant": "20 second",
                "soc_step_resolution": "0.05 dimensionless",
                "capacity_reference_temperature": "298.15 kelvin",
                "capacity_temperature_span": "25 kelvin",
                "peukert_exponent": "1.05 dimensionless",
                "peukert_reference_current": "1 ampere",
                "peukert_fit_decades": "1.5 dimensionless",
                "peukert_reference_temperature": "298.15 kelvin",
                "peukert_temperature_span": "25 kelvin",
                "cooling_mode": "passive",
            },
        },
        "load": {
            "load_id": "L1",
            "discharge_current": "1.5 ampere",
            "state_of_charge": "0.9 dimensionless",
            "cell_temperature": "298.15 kelvin",
            "duration": "60 second",
            "pulse_current": "4 ampere",
            "pulse_duration": "10 second",
            "cutoff_voltage": "3.0 volt",
            "cutoff_state_of_charge": "0.15 dimensionless",
            "duty_type": "pulsed",
        },
        "thermal": {
            "heat_capacity": "60 joule/kelvin",
            "ambient_temperature": "298.15 kelvin",
        },
        "march": {"steps": 10},
    }
