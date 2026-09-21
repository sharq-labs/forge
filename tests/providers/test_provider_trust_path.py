"""P9's central proof: one trust path, two solvers, no branch on which.

Three of P20's twelve:

5.  A successful PyBaMM execution does not imply SUPPORTED.
6.  A result outside applicability is refused.
11. Native and PyBaMM results enter the same trust assembly.

The mechanism under test is a single function --
:meth:`CredibilityEvidenceReport.from_result` -- which is the entry to the
credibility/claim path and which was written before any provider existed. It is
not adapted here, not subclassed, and not passed a provider flag. It takes a
``ScientificResult``, and a ``ScientificResult`` is what both the native
battery solver and the PyBaMM adapter produce.

The asymmetry these tests end on is earned, not built in. Given identical
applicability evidence, the native result reaches SUPPORTED and the PyBaMM
result does not -- because the native solver's ``metric_dimensions`` check
establishes ``DIMENSIONALLY_VALID`` and the provider adapter's checks establish
nothing. That is the correct answer and it is reached by the ordinary rule: an
external solver's reputation is not evidence for a specific prediction, so its
run attains no level until somebody produces one.
"""

from __future__ import annotations

import ast
from dataclasses import replace
import pathlib

import pytest

from engcore.credibility.evidence import (
    CredibilityEvidenceReport,
    CredibilityVerdict,
    ModelValidityRecord,
)
from engcore.domains.battery import cell as bcell
from engcore.domains.battery import context as bctx
from engcore.domains.battery import models as bmodels
from engcore.domains.battery import solver as bsolver
from engcore.providers import ExecutionOutcome
from engcore.providers import pybamm_provider as pp
from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
from engcore.scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.units.quantity import Quantity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

NASA_CELL = pp.CellUnderTest(
    cell_id="B0005",
    chemistry="LiCoO2/graphite",
    nominal_capacity_ah=1.86,
    ambient_temperature_k=297.0,
)
PROTOCOL = pp.CurrentProtocol(duration_s=1200.0, constant_current_a=2.0)

FORGE_AUTHORITY = pp.ParameterAuthority(
    authority_id="test.nasa_18650_ecm",
    source="forge_declared",
    parameter_set_name="ECM_Example",
    defining_provider_version="pybamm",
    chemistry="LiCoO2/graphite",
    nominal_capacity_ah=1.86,
    temperature_validity_k=(293.15, 313.15),
    notes="declared for this test; the numbers come from the factory below",
)


def _values_factory():
    import numpy as np
    import pybamm

    values = pybamm.ParameterValues("ECM_Example").copy()
    knots = np.linspace(0.0, 1.0, 11)
    volts = 3.0 + 1.2 * knots

    def ocv(soc):
        return pybamm.Interpolant(knots, volts, soc, interpolator="linear", extrapolate=True)

    values.update(
        {
            "Cell capacity [A.h]": 1.86,
            "Nominal cell capacity [A.h]": 1.86,
            "Open-circuit voltage [V]": ocv,
            "R0 [Ohm]": 0.12,
            "R1 [Ohm]": 0.05,
            "C1 [F]": 1500.0,
            "Lower voltage cut-off [V]": 2.0,
            "Upper voltage cut-off [V]": 4.4,
            "Element-1 initial overpotential [V]": 0.0,
            "Entropic change [V/K]": 0.0,
            "Ambient temperature [K]": 297.0,
            "Initial temperature [K]": 297.0,
        },
        check_already_exists=False,
    )
    return values


def _provider(authority=FORGE_AUTHORITY, factory=_values_factory):
    return pp.PyBaMMProvider(
        authority=authority,
        cell=NASA_CELL,
        protocol=PROTOCOL,
        parameter_values_factory=factory,
    )


def _request(model_key="thevenin_1rc", authority=FORGE_AUTHORITY):
    return pp.build_request(
        model_key=model_key,
        authority=authority,
        cell=NASA_CELL,
        protocol=PROTOCOL,
        qois=("terminal_voltage", "time"),
        initial_state_of_charge=0.95,
    )


def _native_cell_and_load():
    """A declared cell and load at a benign operating point.

    Written out here rather than imported from `tests/domains/battery/
    battery_cases.py`. That module is reachable only by appending its directory
    to `sys.path`, and after such an append `import battery_cases` looks to
    `tests/test_core_guards.py`'s dependency sweep exactly like a third-party
    package it cannot resolve -- which is what it reported when this helper did
    that. The values below are that module's own defaults.
    """
    limits = bctx.CellLimits(
        **{
            bctx.CONTINUOUS_DISCHARGE_C_RATE: Quantity(2.0, "1/hour"),
            bctx.PULSE_DISCHARGE_C_RATE: Quantity(10.0, "1/hour"),
            bctx.RATED_PULSE_DURATION: Quantity(10.0, "second"),
            bctx.USABLE_SOC_MINIMUM: Quantity(0.10, "dimensionless"),
            bctx.USABLE_SOC_MAXIMUM: Quantity(0.95, "dimensionless"),
            bctx.MINIMUM_DISCHARGE_TEMPERATURE: Quantity(253.15, "kelvin"),
            bctx.MAXIMUM_DISCHARGE_TEMPERATURE: Quantity(333.15, "kelvin"),
            bctx.RESISTANCE_REFERENCE_TEMPERATURE: Quantity(298.15, "kelvin"),
            bctx.RESISTANCE_TEMPERATURE_SPAN: Quantity(50.0, "kelvin"),
            bctx.CELL_THERMAL_CONDUCTANCE: Quantity(0.15, "watt/kelvin"),
            bctx.SELF_HEATING_RISE_BOUND: Quantity(15.0, "kelvin"),
            bctx.POLARIZATION_TIME_CONSTANT: Quantity(30.0, "second"),
            bctx.SOC_STEP_RESOLUTION: Quantity(0.10, "dimensionless"),
            bctx.CAPACITY_REFERENCE_TEMPERATURE: Quantity(293.15, "kelvin"),
            bctx.CAPACITY_TEMPERATURE_SPAN: Quantity(20.0, "kelvin"),
            bctx.PEUKERT_EXPONENT: Quantity(1.05, "dimensionless"),
            bctx.PEUKERT_REFERENCE_CURRENT: Quantity(0.5, "ampere"),
            bctx.PEUKERT_FIT_DECADES: Quantity(1.0, "dimensionless"),
        }
    )
    cell = bcell.CellSpecification(
        cell_id="CELL-1",
        limits=limits,
        **{
            bctx.NOMINAL_CAPACITY: Quantity(2.5, "ampere_hour"),
            bctx.INTERNAL_RESISTANCE: Quantity(0.030, "ohm"),
            bctx.OCV_AT_FULL: Quantity(4.2, "volt"),
            bctx.OCV_AT_EMPTY: Quantity(3.0, "volt"),
            bctx.COULOMBIC_EFFICIENCY: Quantity(0.99, "dimensionless"),
        },
    )
    load = bcell.DischargeLoad(
        load_id="LOAD-1",
        current=Quantity(2.5, "ampere"),
        initial_state_of_charge=Quantity(0.90, "dimensionless"),
        **{
            bctx.CELL_TEMPERATURE: Quantity(298.15, "kelvin"),
            bctx.DURATION: Quantity(120.0, "second"),
            bctx.PULSE_CURRENT: Quantity(5.0, "ampere"),
            bctx.PULSE_DURATION: Quantity(1.0, "second"),
            bctx.CUTOFF_VOLTAGE: Quantity(3.0, "volt"),
            bctx.CUTOFF_STATE_OF_CHARGE: Quantity(0.15, "dimensionless"),
        },
    )
    return cell, load


def _native_result() -> tuple[ScientificResult, str, str]:
    """A real native battery solve, wrapped as the ScientificResult it produces."""
    cell, load = _native_cell_and_load()
    problem = bcell.build_battery_problem(cell, load)
    solver = bsolver.BatteryCellSolver()
    solver.bind_cell(cell, load, problem.problem_id)
    prepared = solver.prepare(problem, realization=bmodels.RINT_OCV_REALIZATION)
    raw = solver.solve(prepared)
    model = bmodels.RINT_OCV_MODEL
    metrics = solver.metrics_for(model.model_id, prepared, raw)
    report = solver.validate(prepared, raw)
    from engcore.scientific.ir.problem import ModelReference as Ref

    provenance = ProvenanceRecord(
        run_id="native-battery-run",
        bindings=(
            ExecutionBinding(
                model=Ref(model.model_id, model.version),
                realization=bmodels.RINT_OCV_REALIZATION.reference(),
                solver=solver.identity,
            ),
        ),
    )
    result = ScientificResult(
        result_id="native-battery-run",
        problem_id=problem.problem_id,
        values=metrics,
        models=((model.model_id, model.version),),
        solver=solver.identity,
        convergence=raw.convergence,
        validation=report,
        # The Core refuses a result that says nothing about whether its model
        # applied, which is how this helper was written on the first attempt.
        # Stating it is the point: the native path and the provider path are
        # held to the same rule, and neither gets a default.
        validity_not_assessed={
            model.model_id: (
                "not assessed by this fixture: applicability is the subject of "
                "the test below, which supplies the record explicitly so that "
                "the native and provider results carry the same evidence"
            )
        },
        provenance=provenance,
    )
    return result, model.model_id, model.version


def _in_domain_record(model_id: str, version: str, conditions) -> ModelValidityRecord:
    return ModelValidityRecord(
        model_id=model_id,
        version=version,
        assessment=ValidityAssessment(
            status=ValidityStatus.IN_DOMAIN, satisfied=tuple(conditions)
        ),
    )


# =====================================================================
# 6. Outside applicability is refused -- and PyBaMM is never called
# =====================================================================

def test_a_result_outside_applicability_is_refused():
    """``Chen2020`` describes a 5 A.h NMC811 pouch. The cell is a 2 A.h 18650.

    No PyBaMM import is needed to run this test, which is the point being
    made: the refusal happens before the provider is reached. Applicability
    precedes evidence-bearing execution, and a solve that has already happened
    is a number somebody can read.
    """
    chen = pp.NAMED_AUTHORITIES["Chen2020"]
    outcome = pp.PyBaMMProvider(
        authority=chen, cell=NASA_CELL, protocol=PROTOCOL
    ).execute(_request(model_key="spme", authority=chen))

    assert outcome.outcome is ExecutionOutcome.MODEL_NOT_APPLICABLE
    assert outcome.result is None
    assert outcome.outcome.is_forge_side
    assert not outcome.outcome.is_provider_side
    detail = outcome.receipt.detail
    assert "chemistry mismatch" in detail
    assert "capacity mismatch" in detail


def test_an_authority_declaring_no_temperature_band_is_unknown_and_refused():
    """UNKNOWN is not 'any temperature'. PyBaMM's own ECM example proves it."""
    example = pp.NAMED_AUTHORITIES["ECM_Example"]
    applicable, reasons = example.screen(NASA_CELL)
    assert not applicable
    assert any("declares no temperature validity" in r for r in reasons)
    assert any("UNKNOWN is not" in r for r in reasons)


def test_a_band_stated_against_cell_temperature_is_not_screened_on_ambient():
    """The defect the comparison benchmark's counterfactual probe found.

    The recovery's open-circuit voltage authority states its bands against the
    *median measured cell temperature* and says so: "Ambient is not the
    condition." The first version of this screen compared the ambient against
    those bands, and refused five low-ambient 4 A trajectories on a quantity
    the band was never about -- a 4 A discharge at 4 degC ambient self-heats
    past 40 degC and belongs to the warm band by the authority's own rule.

    Two halves, because the fix has to refuse as well as accept: an authority
    whose basis the cell cannot supply is refused rather than falling back to
    the other temperature.
    """
    cold_ambient_hot_cell = pp.CellUnderTest(
        cell_id="B0042",
        chemistry="LiCoO2/graphite",
        nominal_capacity_ah=1.86,
        ambient_temperature_k=277.15,
        cell_temperature_k=305.0,
    )
    on_cell = replace(FORGE_AUTHORITY, temperature_basis="cell")
    applicable, reasons = on_cell.screen(cold_ambient_hot_cell)
    assert applicable, reasons

    on_ambient = replace(FORGE_AUTHORITY, temperature_basis="ambient")
    applicable, reasons = on_ambient.screen(cold_ambient_hot_cell)
    assert not applicable
    assert any("ambient temperature outside" in r for r in reasons)

    no_cell_temperature = replace(cold_ambient_hot_cell, cell_temperature_k=None)
    applicable, reasons = on_cell.screen(no_cell_temperature)
    assert not applicable
    assert any("declares none" in r and "not a substitute" in r for r in reasons)


def test_a_basis_that_is_not_named_is_refused():
    with pytest.raises(ValueError, match="neither"):
        replace(FORGE_AUTHORITY, temperature_basis="surface")


def test_every_failing_screen_condition_is_reported_not_short_circuited():
    hot = pp.CellUnderTest(
        cell_id="hot", chemistry="LiFePO4", nominal_capacity_ah=20.0,
        ambient_temperature_k=350.0,
    )
    applicable, reasons = FORGE_AUTHORITY.screen(hot)
    assert not applicable
    assert len(reasons) == 3, reasons


# =====================================================================
# 5 and 11. Execution, and the trust path both results travel
# =====================================================================

def test_a_successful_pybamm_run_does_not_imply_supported():
    """The provider delivered. That is the beginning of the trust path."""
    pytest.importorskip("pybamm")
    outcome = _provider().execute(_request())
    assert outcome.outcome is ExecutionOutcome.OK, outcome.receipt.detail
    assert outcome.result is not None

    report = CredibilityEvidenceReport.from_result(outcome.result)
    assert report.verdict is not CredibilityVerdict.SUPPORTED
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_native_and_pybamm_results_enter_the_same_trust_assembly():
    """One function, two solvers, and the same rule applied to both.

    Part one: with no applicability evidence, both are INSUFFICIENT_EVIDENCE.
    The provider gets no head start.

    Part two: given an IN_DOMAIN record for the model each names, the native
    result reaches SUPPORTED and the provider result does not. That difference
    is produced entirely by what the two runs *attained* -- the native solver's
    dimensional check establishes a level and the adapter's checks establish
    none -- and not by anything the path knows about providers.
    """
    pytest.importorskip("pybamm")
    native, native_model, native_version = _native_result()
    outcome = _provider().execute(_request())
    assert outcome.outcome is ExecutionOutcome.OK, outcome.receipt.detail
    external = outcome.result

    bare_native = CredibilityEvidenceReport.from_result(native)
    bare_external = CredibilityEvidenceReport.from_result(external)
    assert bare_native.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert bare_external.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE

    # Part two: the native result, given the applicability record its model's
    # own declared conditions support, reaches SUPPORTED.
    native_conditions = tuple(
        c.name for c in bmodels.RINT_OCV_MODEL.validity.conditions
    )
    supported_native = CredibilityEvidenceReport.from_result(
        native,
        validity=(_in_domain_record(native_model, native_version, native_conditions),),
    )
    assert supported_native.verdict is CredibilityVerdict.SUPPORTED

    # Part three: the provider result, given the honest assessment -- UNKNOWN,
    # because Forge has not translated PyBaMM's own validity conditions -- does
    # not reach SUPPORTED. UNKNOWN never improves an answer.
    external_model, external_version = external.models[0]
    honest_external = CredibilityEvidenceReport.from_result(
        external,
        validity=(
            ModelValidityRecord(
                model_id=external_model,
                version=external_version,
                assessment=ValidityAssessment(status=ValidityStatus.UNKNOWN),
            ),
        ),
    )
    assert honest_external.verdict is not CredibilityVerdict.SUPPORTED, (
        "a provider run whose applicability is UNKNOWN reached SUPPORTED, "
        "which would mean external solver reputation had become evidence"
    )

    # Part four: and the shortcut is closed on both sides by the same Core
    # rule. An IN_DOMAIN assessment that evaluated nothing is refused
    # identically for the provider result and for the native one, so a caller
    # cannot buy support for either by declaring applicability it did not
    # establish. This is the rule that would otherwise be the provider's way in.
    from engcore.scientific.errors import ModelValidityError

    for model_id, version in ((external_model, external_version), (native_model, native_version)):
        with pytest.raises(ModelValidityError, match="established nothing"):
            _in_domain_record(model_id, version, ())

    # The shapes match: both are the same record type, carrying the same kinds
    # of field, so anything downstream reads them identically.
    assert type(bare_native) is type(bare_external)
    assert set(external.values) and set(native.values)
    assert external.provenance.bindings and native.provenance.bindings


def test_the_trust_path_contains_no_branch_on_provider_identity():
    """P9 stated as a property of the source, not of one execution.

    ``if provider == "pybamm": trust = True`` is the failure mode named in the
    sprint brief. This walks the three layers that decide trust and asserts
    that none of them *names* a provider in code.

    CODE, not prose, and for the reason ``tests/core_vocabulary.py`` gives for
    drawing the same line: a provider name in an identifier, an attribute or a
    non-docstring string literal is the trust path branching on who computed
    the number, while the same word in a docstring is usually the layer
    documenting its own ignorance. ``credibility/risk_coverage.py`` is exactly
    that case -- its docstring explains why its record cannot name a provider,
    which is the opposite of naming one -- and a text-only guard reported it as
    a violation on the first run.
    """
    from tests import core_vocabulary

    layers = ("credibility", "claims", "sria")
    needles = {"pybamm", "pybop", "salib", "providers"}
    offenders = []
    for layer in layers:
        root = REPO_ROOT / "src" / "engcore" / layer
        for path in sorted(root.rglob("*.py")):
            for parts in core_vocabulary.code_words(path):
                hit = needles & {p.lower() for p in parts}
                if hit:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)} names {sorted(hit)} in code"
                    )
    assert not offenders, offenders


def test_the_credibility_layer_cannot_import_the_provider_package():
    """The direction that would let a judged thing reach into its judge."""
    root = REPO_ROOT / "src" / "engcore" / "credibility"
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "engcore.providers"
            ):
                pytest.fail(f"{path.name} imports engcore.providers")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("engcore.providers"), path.name
