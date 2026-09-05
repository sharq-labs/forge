"""MODEL0-R DIFFERENTIAL PROOF — executed evidence.

Preregistered in ``docs/milestones/model0r-differential-prereg.md``. Every test here maps
to a lettered test in prereg §7, or to a predeclared prediction in §6.

The question under test is **not** whether Model != Realization != Solver
should exist — that boundary is DESIGN-FROZEN. It is whether
``ModelRealizationDefinition`` carries information that has no correct home on
the model, on the solver, or in runtime settings.

The null hypothesis is allowed to win. ``TEST G`` is the reduction attack and
is written to succeed if the reduction succeeds.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import pathlib

import numpy as np
import pytest

from src.engcore.domains.thermal.conduction1d.problem import (
    DIFFUSION_MODEL,
    ConductionSlab,
    SlabDiscretization,
)
from src.engcore.domains.thermal.conduction1d.reference import (
    REFERENCE_ID,
    exact_midpoint,
)
from src.engcore.domains.thermal.conduction1d.solver import (
    Conduction1DSolver,
    solve_slab,
)
from src.engcore.domains.thermal.conduction1d.problem import (
    build_conduction_problem,
)
from src.engcore.domains.thermal_models.conduction1d_schemes import (
    CORE_LINEAR_SOLVE,
    EXPLICIT_REALIZATION,
    FTCS_STABILITY_LIMIT,
    IMPLICIT_REALIZATION,
    ReducedSchemeSolver,
    SchemeSolver,
    admissible_realizations,
    assess_realization,
    banded_scheme_solver,
    conduction_realizations,
    fourier_number_of,
    realization_applicability,
    solve_with_realization,
    sparse_scheme_solver,
)
from src.engcore.scientific.errors import ScientificCoreError
from src.engcore.scientific.ir.problem import ModelReference
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.realizations.definition import (
    ModelFormulation,
    ModelRealizationDefinition,
    RealizationReference,
)
from src.engcore.scientific.results.provenance import (
    PROVENANCE_SCHEMA,
    PROVENANCE_SCHEMA_V1,
    ExecutionBinding,
    ProvenanceRecord,
)
from src.engcore.scientific.results.result import ScientificResult
from src.engcore.scientific.results.validation import ValidationOutcome
from src.engcore.scientific.solvers.capability import (
    CoreCapabilities,
    SolverCapabilityId,
)
from src.engcore.scientific.solvers.protocol import (
    ConvergenceState,
    SolverIdentity,
)
from src.engcore.scientific.units.quantity import Quantity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

LENGTH = Quantity(0.1, "meter")
ALPHA = Quantity(1.2e-5, "m**2/s")
END_TIME = Quantity(60.0, "second")

#: Preregistered configurations (prereg §6). Same physical slab, different
#: discretization only.
STABLE = (32, 160)      # r = 0.4608
UNSTABLE = (32, 80)     # r = 0.9216


def slab(n_cells: int, n_steps: int, slab_id: str = "m0rd") -> ConductionSlab:
    return ConductionSlab(
        slab_id=slab_id,
        length=LENGTH,
        diffusivity=ALPHA,
        end_time=END_TIME,
        discretization=SlabDiscretization(n_cells, n_steps),
    )


def exact_mid() -> float:
    return exact_midpoint(
        length_m=LENGTH.magnitude_in("meter"),
        alpha_m2_s=ALPHA.magnitude_in("m**2/s"),
        time_s=END_TIME.magnitude_in("second"),
    )


# =====================================================================
# §6 — the predeclared arithmetic, confirmed by execution
# =====================================================================

def test_p3_preregistered_fourier_numbers_are_what_was_predicted():
    """prereg §6: r = 0.4608 at (32,160) and 0.9216 at (32,80)."""
    assert fourier_number_of(slab(*STABLE)) == pytest.approx(0.4608, rel=1e-9)
    assert fourier_number_of(slab(*UNSTABLE)) == pytest.approx(0.9216, rel=1e-9)
    assert fourier_number_of(slab(*STABLE)) <= FTCS_STABILITY_LIMIT
    assert fourier_number_of(slab(*UNSTABLE)) > FTCS_STABILITY_LIMIT


# =====================================================================
# TEST A — same model identity
# =====================================================================

def test_a1_both_realizations_name_the_same_scientific_model():
    expected = (DIFFUSION_MODEL.model_id, DIFFUSION_MODEL.version)
    assert IMPLICIT_REALIZATION.model_key == expected
    assert EXPLICIT_REALIZATION.model_key == expected


def test_a2_no_second_scientific_model_was_created():
    """The distinction under test belongs at realization level.

    A ``Fourier analytical model`` beside a ``Fourier numerical model`` would
    make the proof easy and would prove nothing about realizations.
    """
    import src.engcore.domains.thermal_models.conduction1d_schemes as schemes

    source = pathlib.Path(inspect.getfile(schemes)).read_text(encoding="utf-8")
    assert "ScientificModelDefinition(" not in source
    assert "ScientificModelDefinition" not in dir(schemes)


def test_a3_the_registry_returns_both_for_one_model_key():
    registry = conduction_realizations()
    found = registry.for_model(DIFFUSION_MODEL.model_id, DIFFUSION_MODEL.version)
    assert {r.realization_id for r in found} == {
        IMPLICIT_REALIZATION.realization_id,
        EXPLICIT_REALIZATION.realization_id,
    }
    assert registry.model_keys() == (
        (DIFFUSION_MODEL.model_id, DIFFUSION_MODEL.version),
    )


# =====================================================================
# TEST B — materially different realization
# =====================================================================

def test_b1_the_difference_is_not_the_formulation_enum():
    """``formulation`` is held constant, so it is not carrying the proof."""
    assert IMPLICIT_REALIZATION.formulation is ModelFormulation.PDE
    assert EXPLICIT_REALIZATION.formulation is ModelFormulation.PDE


def test_b2_the_difference_is_not_identifier_or_prose():
    """Strip identity and prose; a real semantic difference must survive."""
    def semantics(r: ModelRealizationDefinition) -> dict:
        return {
            "formulation": r.formulation.value,
            "provided": sorted(c.identifier for c in r.provided_capabilities),
            "required": sorted(c.identifier for c in r.required_capabilities),
            "solver_caps": sorted(
                c.name for c in r.required_solver_capabilities
            ),
        }

    assert semantics(IMPLICIT_REALIZATION) != semantics(EXPLICIT_REALIZATION)


def test_b3_required_solver_capabilities_differ_and_the_difference_is_real():
    """Backward Euler solves a linear system every step. FTCS does not.

    This is arithmetic, not a label: the implicit update is
    ``(I - rT) u_new = u_old`` and the explicit update is a matrix-vector
    product.
    """
    linear = SolverCapabilityId.coerce(CORE_LINEAR_SOLVE)
    assert IMPLICIT_REALIZATION.requires_solver_capability(linear)
    assert not EXPLICIT_REALIZATION.requires_solver_capability(linear)
    assert (
        IMPLICIT_REALIZATION.required_solver_capabilities
        > EXPLICIT_REALIZATION.required_solver_capabilities
    )


def test_b4_the_stability_bound_is_a_theorem_not_an_authored_flag():
    """Von Neumann: the FTCS amplification factor is 1 - 4r sin^2(k dx / 2).

    Measured from the implementation rather than asserted: run one step of the
    explicit scheme on the highest representable mode and read the ratio.
    """
    for n_steps, expect_growth in ((160, False), (80, True)):
        s = slab(32, n_steps)
        r = fourier_number_of(s)
        n = s.discretization.n_cells - 1
        nyquist = np.array([(-1.0) ** i for i in range(n)])
        step = SchemeSolver().backend.explicit_stepper(n, r)
        ratio = float(np.max(np.abs(step(nyquist)))) / float(
            np.max(np.abs(nyquist))
        )
        # 1 - 4r for the alternating mode, exactly.
        assert ratio == pytest.approx(abs(1.0 - 4.0 * r), rel=1e-12)
        assert (ratio > 1.0) is expect_growth


# =====================================================================
# TEST C — validity distinction
# =====================================================================

def test_c1_one_realization_is_inadmissible_where_the_other_is_not():
    unstable = slab(*UNSTABLE)
    assert (
        assess_realization(EXPLICIT_REALIZATION, unstable).status
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    # Backward Euler declares no restriction, so its envelope is empty and the
    # honest answer is UNKNOWN — never IN_DOMAIN. Absence of declared limits is
    # not evidence of unlimited applicability.
    assert (
        assess_realization(IMPLICIT_REALIZATION, unstable).status
        is ValidityStatus.UNKNOWN
    )


def test_c2_both_are_admissible_at_the_stable_configuration():
    stable = slab(*STABLE)
    assessment = assess_realization(EXPLICIT_REALIZATION, stable)
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert assessment.satisfied == ("fourier_number",)


def test_c3_the_model_itself_does_not_distinguish_them():
    """The MODEL is valid at both configurations. Only the realization is not.

    This is the statement the separation exists to make: *the model is valid
    here but this particular realization is not adequate*.
    """
    for n_cells, n_steps in (STABLE, UNSTABLE):
        s = slab(n_cells, n_steps)
        assessment = DIFFUSION_MODEL.validity.assess({"alpha": s.diffusivity})
        assert assessment.status is ValidityStatus.IN_DOMAIN
    # And the model's validity domain has nothing to say about a Fourier
    # number, because the diffusion equation has no Fourier number: it does
    # not exist until the equation is discretized.
    assert {c.name for c in DIFFUSION_MODEL.validity.conditions} == {"alpha"}


def test_c4_the_inadmissible_case_actually_fails_when_executed():
    """prereg §6 prediction 2: catastrophic violation, not mild inaccuracy."""
    result = solve_with_realization(
        slab(*UNSTABLE), EXPLICIT_REALIZATION, run_id="c4-explicit-unstable"
    )
    max_abs = result.values["u:max_abs"].magnitude
    assert (not np.isfinite(max_abs)) or max_abs > 1e6
    decay = next(
        c for c in result.validation.checks if c.name == "amplitude_decay"
    )
    assert decay.outcome is ValidationOutcome.FAIL
    assert result.validation.status is ValidationOutcome.FAIL


def test_c5_the_same_configuration_is_fine_for_the_other_realization():
    result = solve_with_realization(
        slab(*UNSTABLE), IMPLICIT_REALIZATION, run_id="c5-implicit-unstable"
    )
    assert result.convergence is ConvergenceState.CONVERGED
    assert result.validation.status is not ValidationOutcome.FAIL
    assert result.values["u:midpoint"].magnitude == pytest.approx(
        exact_mid(), rel=5e-2
    )


def test_c6_both_agree_with_the_closed_form_where_both_are_admissible():
    """The frozen analytic reference keeps its oracle role and judges both."""
    stable = slab(*STABLE)
    for realization in (IMPLICIT_REALIZATION, EXPLICIT_REALIZATION):
        result = solve_with_realization(
            stable, realization, run_id=f"c6-{realization.realization_id}"
        )
        assert result.convergence is ConvergenceState.CONVERGED
        assert result.validation.status is not ValidationOutcome.FAIL
        assert result.values["u:midpoint"].magnitude == pytest.approx(
            exact_mid(), rel=2e-2
        )
    assert REFERENCE_ID == "thermal.conduction1d.single_mode_analytic"


def test_c7_refusal_is_available_and_is_typed():
    with pytest.raises(ValueError, match="outside its applicability envelope"):
        solve_with_realization(
            slab(*UNSTABLE),
            EXPLICIT_REALIZATION,
            run_id="c7",
            require_admissible=True,
        )


# =====================================================================
# TEST D — planner-relevant distinction, without executing
# =====================================================================

def test_d1_capability_gap_selects_between_them_before_execution():
    """Half one: decidable from the record as it stands today.

    Given only a backend that cannot solve a linear system, the explicit
    realization is runnable and the implicit one is not — read off declared
    facts, with no solve and no magic strings.
    """
    available = (SolverCapabilityId.coerce("thermal:conduction_1d_transient"),)
    assert EXPLICIT_REALIZATION.solver_capability_gap(available) == frozenset()
    assert IMPLICIT_REALIZATION.solver_capability_gap(available) == frozenset(
        {SolverCapabilityId.coerce(CORE_LINEAR_SOLVE)}
    )


def test_d2_stability_rejection_needs_information_not_on_the_record():
    """Half two, and the milestone's central finding.

    The applicability envelope is evaluated per realization and decides the
    selection. It is reached through a side-table keyed by realization
    identity, because ``ModelRealizationDefinition`` has no field to carry it:
    on the record the bound exists only as free text in ``assumptions``.
    """
    verdicts = {
        realization.realization_id: (assessment.status, gap)
        for realization, assessment, gap in admissible_realizations(
            slab(*UNSTABLE),
            available_solver_capabilities=(
                SolverCapabilityId.coerce("thermal:conduction_1d_transient"),
                SolverCapabilityId.coerce(CORE_LINEAR_SOLVE),
            ),
        )
    }
    assert verdicts[EXPLICIT_REALIZATION.realization_id][0] is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert verdicts[IMPLICIT_REALIZATION.realization_id][1] == frozenset()

    # The finding, asserted so it cannot quietly stop being true.
    assert "applicability" not in ModelRealizationDefinition.__dataclass_fields__
    assert "validity" not in ModelRealizationDefinition.__dataclass_fields__
    bound_text = [
        a for a in EXPLICIT_REALIZATION.assumptions if "1/2" in a
    ]
    assert bound_text, "the bound survives only as prose"
    assert isinstance(bound_text[0], str)
    # And the envelope that *is* evaluable is built from core types that
    # already exist — nothing was invented to make this work.
    envelope = realization_applicability(EXPLICIT_REALIZATION)
    assert [c.name for c in envelope.conditions] == ["fourier_number"]


def test_d3_no_ranking_or_selection_was_smuggled_into_the_registry():
    """The registry filters and reports. It does not choose."""
    rows = admissible_realizations(slab(*UNSTABLE))
    assert len(rows) == 2
    assert not hasattr(conduction_realizations(), "best")
    assert not hasattr(conduction_realizations(), "select")


# =====================================================================
# TEST E — solver substitution
# =====================================================================

def test_e1_two_concrete_solvers_run_one_realization_identically():
    stable = slab(*STABLE)
    sparse = solve_with_realization(
        stable, IMPLICIT_REALIZATION, run_id="e1-sparse",
        solver=sparse_scheme_solver(),
    )
    banded = solve_with_realization(
        stable, IMPLICIT_REALIZATION, run_id="e1-banded",
        solver=banded_scheme_solver(),
    )
    assert sparse.solver.key != banded.solver.key
    assert sparse.solver.backend != banded.solver.backend
    # Same realization identity, unchanged by the substitution.
    assert sparse.provenance.realizations == banded.provenance.realizations
    assert sparse.provenance.models == banded.provenance.models
    assert sparse.values["u:midpoint"].magnitude == pytest.approx(
        banded.values["u:midpoint"].magnitude, rel=1e-10
    )


def test_e2_the_realization_record_names_no_solver_backend_or_tolerance():
    """A realization that named one would make swapping a linear solver a
    change of scientific identity."""
    for realization in (IMPLICIT_REALIZATION, EXPLICIT_REALIZATION):
        blob = json.dumps(realization.to_dict(), sort_keys=True).lower()
        for leak in (
            "splu", "solve_banded", "scipy", "numpy", "csc", "tolerance",
            "atol", "rtol", "thread", "device", "gpu",
        ):
            assert leak not in blob, f"{leak!r} leaked into {realization.key}"


def test_e3_the_frozen_solver_agrees_with_the_new_implicit_realization():
    """Cross-check against code this milestone cannot modify.

    ``Conduction1DSolver`` is byte-pinned from an earlier commit and
    implements the same backward-Euler scheme. It is used here only as an
    independent numerical witness, not as a host for the realization: it
    publishes a bundled domain capability and does not declare
    ``core:linear_solve``.
    """
    stable = slab(*STABLE)
    frozen = solve_slab(stable, run_id="e3-frozen")
    mine = solve_with_realization(stable, IMPLICIT_REALIZATION, run_id="e3-new")
    assert mine.values["u:midpoint"].magnitude == pytest.approx(
        frozen.values["u:midpoint"].magnitude, rel=1e-9
    )
    declared = {c.name for c in Conduction1DSolver().capabilities}
    assert declared == {"thermal:conduction_1d_transient"}
    assert CORE_LINEAR_SOLVE.name not in declared


def test_e4_one_solver_identity_covers_both_realizations():
    """Solver identity cannot be what distinguishes the two realizations."""
    stable = slab(*STABLE)
    solver = sparse_scheme_solver()
    a = solve_with_realization(
        stable, IMPLICIT_REALIZATION, run_id="e4-a", solver=solver
    )
    b = solve_with_realization(
        stable, EXPLICIT_REALIZATION, run_id="e4-b", solver=solver
    )
    assert a.solver.key == b.solver.key
    assert a.provenance.solvers == b.provenance.solvers
    assert a.provenance.realizations != b.provenance.realizations


# =====================================================================
# TEST F — provenance
# =====================================================================

def test_f1_provenance_names_model_realization_and_solver_separately():
    result = solve_with_realization(
        slab(*STABLE), EXPLICIT_REALIZATION, run_id="f1"
    )
    prov = result.provenance
    assert prov.models == (("thermal.conduction1d.linear_diffusion", "0.1.0"),)
    assert prov.realizations == (
        ("thermal.conduction1d.explicit_forward_euler", "0.1.0"),
    )
    assert prov.solvers == (("thermal.conduction1d.scheme_solver", "0.1.0"),)
    assert len({prov.models, prov.realizations, prov.solvers}) == 3


def test_f2_realization_identity_is_typed_not_metadata():
    """The untyped escape hatch was available and was not used."""
    result = solve_with_realization(
        slab(*STABLE), EXPLICIT_REALIZATION, run_id="f2"
    )
    meta = json.dumps(result.provenance.metadata, sort_keys=True)
    assert "explicit_forward_euler" not in meta
    assert "realization" not in meta
    assert "bindings" in ProvenanceRecord.__dataclass_fields__
    binding = result.provenance.bindings[0]
    assert isinstance(binding.realization, RealizationReference)
    assert isinstance(binding.model, ModelReference)
    assert isinstance(binding.solver, SolverIdentity)


def test_f3_realization_survives_serialization_round_trip():
    result = solve_with_realization(
        slab(*STABLE), IMPLICIT_REALIZATION, run_id="f3"
    )
    restored = ScientificResult.from_dict(result.to_dict())
    assert restored.provenance.realizations == result.provenance.realizations
    assert json.dumps(restored.to_dict(), sort_keys=True) == json.dumps(
        result.to_dict(), sort_keys=True
    )


def test_f4_old_provenance_payloads_still_load_and_declare_no_relation():
    """Requirement 6: read ``/1``, and fabricate nothing it did not contain.

    The payload below has exactly one model and one solver, so a binding
    *looks* determined. It is not: the record never stated that this solver
    computed that model, and inventing the association here would put a claim
    into the record its author never made.
    """
    payload = ProvenanceRecord(
        run_id="legacy", models=(("m", "1"),), solvers=(("s", "1"),)
    ).to_dict()
    payload["schema"] = PROVENANCE_SCHEMA_V1
    payload.pop("bindings")
    restored = ProvenanceRecord.from_dict(payload)
    assert restored.bindings == ()
    assert restored.realizations == ()
    # The participants it did state are preserved exactly.
    assert restored.models == (("m", "1"),)
    assert restored.solvers == (("s", "1"),)
    assert restored.bindings_for_model("m") == ()
    # Re-serializing writes the current version. One-way upgrade, as intended.
    assert restored.to_dict()["schema"] == PROVENANCE_SCHEMA


def test_f5_an_unknown_provenance_version_fails_loudly():
    payload = ProvenanceRecord(run_id="x").to_dict()
    payload["schema"] = "provenance_record/3"
    with pytest.raises(Exception):
        ProvenanceRecord.from_dict(payload)


def test_f6_two_realizations_are_not_conflated_in_one_record():
    stable = slab(*STABLE)
    solver = sparse_scheme_solver()
    ids = {
        solve_with_realization(
            stable, r, run_id=f"f6-{r.realization_id}", solver=solver
        ).provenance.realizations
        for r in (IMPLICIT_REALIZATION, EXPLICIT_REALIZATION)
    }
    assert len(ids) == 2


# =====================================================================
# TEST G — the reduction attack (prereg §5)
# =====================================================================

def test_g1_model_plus_solver_alone_cannot_distinguish_the_two_computations():
    """The strongest reduction, executed.

    One solver identity, one model identity, two materially different
    computations — one of which is catastrophically wrong at this
    configuration. Under (model, solver) alone the two records are identical.
    """
    unstable = slab(*UNSTABLE)
    solver = sparse_scheme_solver()
    good = solve_with_realization(
        unstable, IMPLICIT_REALIZATION, run_id="g1-good", solver=solver
    )
    bad = solve_with_realization(
        unstable, EXPLICIT_REALIZATION, run_id="g1-bad", solver=solver
    )

    reduced = lambda res: (res.provenance.models, res.provenance.solvers)
    assert reduced(good) == reduced(bad)          # indistinguishable
    assert good.provenance.realizations != bad.provenance.realizations

    # And they are not the same science: one is right, one is not.
    assert good.validation.status is not ValidationOutcome.FAIL
    assert bad.validation.status is ValidationOutcome.FAIL


def test_g2_the_preregistered_reduction_is_built_and_it_works():
    """prereg §5: the H0 steel-man, constructed and executed — not argued.

    ``ReducedSchemeSolver`` carries the scheme as a string in
    ``SolverSettings.options``, exactly as the frozen production solver
    already does. It computes the same numbers. H0 is not refuted by the
    reduction failing to run; it runs.
    """
    stable = slab(*STABLE)
    for time_integration, realization in (
        ("backward_euler", IMPLICIT_REALIZATION),
        ("forward_euler", EXPLICIT_REALIZATION),
    ):
        reduced = ReducedSchemeSolver(time_integration=time_integration)
        reduced.bind_reduced("reduced-p", stable)
        problem = build_conduction_problem(stable, problem_id="reduced-p")
        raw = reduced.solve(reduced.prepare(problem))
        typed = solve_with_realization(
            stable, realization, run_id=f"g2-{time_integration}"
        )
        assert raw.values["u:midpoint"] == pytest.approx(
            typed.values["u:midpoint"].magnitude, rel=1e-12
        )
        assert reduced.solver_settings.options["time_integration"] == (
            time_integration
        )


def test_g2b_what_the_built_reduction_actually_costs():
    """Measured on the reduction that exists, not on one imagined.

    Three costs, each asserted:
      1. the channel is unvalidated — a nonsense scheme is accepted silently;
      2. running it at all needs a scheme-string -> realization branch;
      3. the string is unreachable until a solver instance exists.
    """
    from src.engcore.scientific.errors import InvalidModelRealization
    from src.engcore.scientific.solvers.protocol import SolverSettings

    # 1. Nothing validates the option. Compare with realization identity,
    #    which is validated on construction.
    assert SolverSettings(options={"time_integration": "not_a_scheme"}).options[
        "time_integration"
    ] == "not_a_scheme"
    with pytest.raises(InvalidModelRealization):
        ModelRealizationDefinition(
            realization_id="  ",
            version="0.1.0",
            model=IMPLICIT_REALIZATION.model,
            formulation=ModelFormulation.PDE,
            provided_capabilities=IMPLICIT_REALIZATION.provided_capabilities,
        )

    # 2. The magic-string branch the reduction needs in order to run.
    source = inspect.getsource(ReducedSchemeSolver.bind_reduced)
    assert '"backward_euler"' in source

    # 3. The scheme is a property of an instantiated solver, so "which
    #    approaches exist for this model?" cannot be asked of the reduction
    #    at all — only "what is this particular solver configured to do?".
    assert "time_integration" not in dir(SolverSettings)
    registry = conduction_realizations()
    assert len(registry.for_model(*IMPLICIT_REALIZATION.model_key)) == 2


def test_g3_what_the_reduction_loses_is_enumerated_and_asserted():
    """prereg §5 requires naming exactly what becomes lost/duplicated/
    ambiguous/misplaced. Each entry below is asserted, not narrated."""
    # LOST: which approaches exist for a model, before any solve.
    registry = conduction_realizations()
    assert len(registry.for_model(*IMPLICIT_REALIZATION.model_key)) == 2
    # There is no equivalent question answerable from a SolverRegistry: a
    # solver publishes what it can execute, never how many ways a model may
    # be posed.
    solver = sparse_scheme_solver()
    assert len(solver.capabilities) == 2  # capabilities, not realizations

    # LOST: pre-execution admissibility. Settings are only reachable through
    # an instantiated solver, and carry no envelope at all.
    assert not hasattr(solver.solver_settings, "assess")

    # MISPLACED: solver-capability requirements would have to be inferred from
    # the scheme string, i.e. a magic-string branch in whatever does the
    # inferring.
    assert IMPLICIT_REALIZATION.required_solver_capabilities != (
        EXPLICIT_REALIZATION.required_solver_capabilities
    )

    # DUPLICATED: the stability bound would have to be restated by every
    # solver implementing the scheme. Two solvers already implement it here.
    assert sparse_scheme_solver().identity.key != (
        banded_scheme_solver().identity.key
    )
    for s in (sparse_scheme_solver(), banded_scheme_solver()):
        assert not hasattr(s, "stability_limit")

    # AMBIGUOUS: model assumptions and realization assumptions are different
    # claims and the reduction has one field for both.
    assert set(DIFFUSION_MODEL.assumptions).isdisjoint(
        EXPLICIT_REALIZATION.assumptions
    )


def test_g4_the_reduction_does_not_fully_succeed_field_by_field():
    """The preregistered stopping condition, evaluated by search not by claim.

    Every non-empty field of the realization record is searched for in the
    serialized reduction. A field whose declared value appears there is
    counted as reconstructible. If ALL of them were, the null hypothesis would
    win and the milestone would have to report a negative result.
    """
    realization = IMPLICIT_REALIZATION
    result = solve_with_realization(slab(*STABLE), realization, run_id="g4")
    reduction = {
        "model": result.provenance.models,
        "solver": result.provenance.solvers,
        "solver_backend": result.solver.backend,
        "settings": sparse_scheme_solver().solver_settings.to_dict(),
        "provenance_metadata": result.provenance.metadata,
        "provenance_assumptions": result.provenance.assumptions,
        # The frozen production solver's channel too, since it is the richest
        # untyped carrier that exists today.
        "frozen_solver_options": dict(
            Conduction1DSolver().solver_settings.options
        ),
    }
    blob = json.dumps(reduction, sort_keys=True, default=str).lower()

    payload = realization.to_dict()
    present, lost = set(), set()
    for name in ModelRealizationDefinition.__dataclass_fields__:
        value = payload[name]
        if not value:                       # nothing declared, nothing to lose
            continue
        text = json.dumps(value, default=str).lower().strip('"')
        (present if text in blob else lost).add(name)

    assert lost, "the reduction reconstructed everything; H0 wins"

    # --- The accounting, stated conservatively --------------------------
    # An earlier draft of this test counted eight fields as lost. That was
    # wrong four times over and is corrected here rather than defended:
    #
    #   * ``assumptions`` is NOT lost. ``solve_with_realization`` writes
    #     model + realization assumptions into provenance, so every
    #     realization assumption string — including the stability bound — is
    #     verbatim inside the reduction. It registered as lost only because
    #     the whole JSON list, brackets included, is not a substring.
    #   * ``realization_id``, ``name`` and ``description`` are identity and
    #     prose, which prereg §4 disqualifies in advance.
    #   * ``formulation`` is held constant across the pair, so it
    #     differentiates nothing in this proof whether or not it survives.
    #   * ``version`` is present, but only because the model and solver
    #     happen to carry the same string and nothing says whose it is.
    #
    # What is left is the honest result: two differentiating, machine-usable
    # fields with no home in the reduction.
    differentiating = {"provided_capabilities", "required_solver_capabilities"}
    assert differentiating <= lost

    # The corrections above, asserted rather than narrated.
    bound = "conditionally stable: requires alpha dt / dx^2 <= 1/2"
    assert bound in EXPLICIT_REALIZATION.assumptions
    explicit = solve_with_realization(
        slab(*STABLE), EXPLICIT_REALIZATION, run_id="g4-explicit"
    )
    assert bound in explicit.provenance.assumptions, (
        "the stability bound IS carried by the reduction, as prose"
    )
    assert present == {"version"}
    assert {realization.version} | {
        v for _, v in result.provenance.models + result.provenance.solvers
    } == {"0.1.0"}
    assert "realization" not in blob


def test_g5_a_wrong_answer_can_still_report_convergence():
    """Observed, not predicted: the failing scheme did not go non-finite.

    At r = 0.9216 the explicit march ends at |u| ~ 1e17 — finite, so the
    solver honestly reports CONVERGED while validation FAILS. That is the
    project's own invariant (`26.1 numerical convergence != scientific
    validity`) appearing unprompted, and it is the reason admissibility has to
    be decidable *before* execution rather than inferred from the outcome.
    """
    result = solve_with_realization(
        slab(*UNSTABLE), EXPLICIT_REALIZATION, run_id="g5"
    )
    assert result.convergence is ConvergenceState.CONVERGED
    assert result.validation.status is ValidationOutcome.FAIL
    assert np.isfinite(result.values["u:max_abs"].magnitude)


# =====================================================================
# Architecture fitness (prereg §8, master context §59)
# =====================================================================

def test_x1_the_frozen_thermal_tree_was_not_edited_or_extended():
    from experiments.thermal_t1.t1_config import THERMAL_FROZEN_FILE_DIGESTS

    for relative, expected in THERMAL_FROZEN_FILE_DIGESTS.items():
        path = REPO_ROOT / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"{relative} changed"
    on_disk = {
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in (REPO_ROOT / "src/engcore/domains/thermal").rglob("*.py")
    }
    pinned = {k.replace("\\", "/") for k in THERMAL_FROZEN_FILE_DIGESTS}
    assert on_disk == pinned


def test_x2_no_domain_conditional_was_added_to_universal_core():
    core = REPO_ROOT / "src/engcore/scientific"
    for path in core.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for leaked in (
            "conduction1d", "forward_euler", "backward_euler", "fourier_number",
            "conduction1d_schemes",
        ):
            assert leaked not in text, f"{leaked!r} leaked into {path.name}"


def test_x3_the_realization_contract_was_not_modified():
    """prereg §8.3: this milestone produces the evidence and stops."""
    assert set(ModelRealizationDefinition.__dataclass_fields__) == {
        "realization_id", "version", "model", "formulation", "name",
        "description", "provided_capabilities", "required_capabilities",
        "required_solver_capabilities", "assumptions", "implementation",
    }
    assert set(IMPLICIT_REALIZATION.to_dict()) == {
        "schema", "realization_id", "version", "model", "formulation",
        "name", "description", "provided_capabilities",
        "required_capabilities", "required_solver_capabilities",
        "assumptions", "implementation",
    }


def test_x4_no_untyped_escape_hatch_was_used_by_the_new_module():
    import src.engcore.domains.thermal_models.conduction1d_schemes as schemes

    source = pathlib.Path(inspect.getfile(schemes)).read_text(encoding="utf-8")
    assert "artifacts=" not in source

    # The scheme arrives as a typed realization record, never as a settings
    # string: ``bind`` is annotated for it and refuses a foreign model.
    signature = inspect.signature(SchemeSolver.bind)
    assert signature.parameters["realization"].annotation == (
        "ModelRealizationDefinition"
    )
    with pytest.raises(ValueError, match="implements"):
        sparse_scheme_solver().bind(
            "p",
            slab(*STABLE),
            ModelRealizationDefinition(
                realization_id="other.model.realization",
                version="0.1.0",
                model=ModelReference("other.model", "1.0"),
                formulation=ModelFormulation.ALGEBRAIC,
                provided_capabilities=IMPLICIT_REALIZATION.provided_capabilities,
            ),
        )

    # And the solver's own options carry no scheme identity at all.
    assert set(sparse_scheme_solver().solver_settings.options) == {"backend"}


def test_x5_bulk_field_did_not_re_enter_the_scientific_record():
    """prereg §11: arrays stay out of values, metadata and diagnostics."""
    result = solve_with_realization(
        slab(*STABLE), IMPLICIT_REALIZATION, run_id="x5"
    )
    blob = json.dumps(result.to_dict(), sort_keys=True)
    assert len(blob) < 20_000
    assert "field" not in result.metadata["numerics"]
    for value in result.values.values():
        assert isinstance(value.magnitude, float)


def test_x7_no_second_name_was_minted_for_a_core_owned_capability():
    """Falsifier D1. Capability identity is exact-string with no registry, so
    a domain-minted ``core:linear_solve`` beside the core's
    ``core:linear_system`` would be two names for one operation and a silent
    capability gap."""
    assert CORE_LINEAR_SOLVE is CoreCapabilities.LINEAR_SYSTEM
    assert CORE_LINEAR_SOLVE.name == "core:linear_system"
    core_names = {c.name for c in CoreCapabilities.all()}
    for realization in (IMPLICIT_REALIZATION, EXPLICIT_REALIZATION):
        for required in realization.required_solver_capabilities:
            if required.name.startswith("core:"):
                assert required.name in core_names, (
                    f"{required.name} invents a name in the core namespace"
                )


def test_x8_rebinding_models_cannot_strand_an_inherited_binding():
    """Falsifier D3, under the binding contract."""
    base = ProvenanceRecord(run_id="p", bindings=(_binding("a", "ra", "s"),))
    with pytest.raises(ScientificCoreError, match="inheriting 1 execution"):
        base.derived("child", models=(("b", "1"),))
    # Explicit is fine, in either direction.
    assert base.derived("c1", models=(("b", "1"),), bindings=()).bindings == ()
    assert base.derived("c2").bindings == base.bindings
    # And a record with no bindings is unaffected.
    plain = ProvenanceRecord(run_id="p2", models=(("a", "1"),))
    assert plain.derived("c3", models=(("b", "1"),)).bindings == ()


def test_x9_the_capability_gap_is_over_declarations_not_behaviour():
    """Falsifier D5, recorded as a known limit rather than papered over.

    ``Conduction1DSolver`` factorizes and back-substitutes every step, and
    declares no linear-system capability. It is byte-pinned, so that gap can
    never be closed by editing it. A capability gap is a necessary condition
    computed over *declarations*; it is not a statement about behaviour.
    """
    declared = {c.name for c in Conduction1DSolver().capabilities}
    gap = IMPLICIT_REALIZATION.solver_capability_gap(declared)
    assert gap == frozenset({SolverCapabilityId.coerce(CORE_LINEAR_SOLVE)})
    frozen_source = pathlib.Path(
        REPO_ROOT / "src/engcore/domains/thermal/conduction1d/solver.py"
    ).read_text(encoding="utf-8")
    assert "spla.splu" in frozen_source  # it does perform the operation


# =====================================================================
# D2 resolution — the typed ternary provenance relation
# =====================================================================

def _binding(model_id: str, realization_id: str | None, solver_id: str):
    return ExecutionBinding(
        model=ModelReference(model_id, "1.0"),
        realization=(
            RealizationReference(realization_id, "1.0") if realization_id else None
        ),
        solver=SolverIdentity(solver_id, "1.0"),
    )


def test_r1_one_model_one_realization_one_solver():
    """The arity-one case, stated structurally rather than by coincidence."""
    result = solve_with_realization(
        slab(*STABLE), EXPLICIT_REALIZATION, run_id="r1"
    )
    prov = result.provenance
    assert len(prov.bindings) == 1
    binding = prov.bindings[0]
    assert binding.model.key == (DIFFUSION_MODEL.model_id, DIFFUSION_MODEL.version)
    assert binding.realization.key == EXPLICIT_REALIZATION.key
    assert binding.solver.key == ("thermal.conduction1d.scheme_solver", "0.1.0")
    # Participant sets are derived from it, not authored beside it.
    assert prov.models == (binding.model.key,)
    assert prov.solvers == (binding.solver.key,)
    assert prov.realizations == (binding.realization.key,)


def test_r2_two_independent_bindings_stay_separable():
    """The case three participant tuples cannot represent.

    Two models, two realizations, two solvers — and crucially the pairing is
    *crossed*, so any positional reading of the sorted participant sets gets
    it wrong.
    """
    prov = ProvenanceRecord(
        run_id="r2",
        bindings=(
            _binding("model.alpha", "real.zulu", "solver.two"),
            _binding("model.beta", "real.alpha", "solver.one"),
        ),
    )
    assert len(prov.bindings) == 2
    alpha = prov.bindings_for_model("model.alpha")
    beta = prov.bindings_for_model("model.beta")
    assert len(alpha) == 1 and len(beta) == 1
    assert alpha[0].realization.realization_id == "real.zulu"
    assert alpha[0].solver.solver_id == "solver.two"
    assert beta[0].realization.realization_id == "real.alpha"
    assert beta[0].solver.solver_id == "solver.one"


def test_r3_positional_pairing_would_get_it_wrong():
    """Requirement 1, demonstrated rather than asserted.

    Zipping the derived participant sets produces the *opposite* of the truth
    for the crossed case, which is why association must be structural.
    """
    prov = ProvenanceRecord(
        run_id="r3",
        bindings=(
            _binding("model.alpha", "real.zulu", "solver.two"),
            _binding("model.beta", "real.alpha", "solver.one"),
        ),
    )
    positional = dict(zip(prov.models, prov.realizations))
    truth = {b.model.key: b.realization.key for b in prov.bindings}
    assert positional != truth
    # And order of construction carries no information either.
    reversed_order = ProvenanceRecord(
        run_id="r3b", bindings=tuple(reversed(prov.bindings))
    )
    assert reversed_order.bindings == prov.bindings


def test_r4_one_realization_executed_by_two_compatible_solvers():
    """Requirement 7, and the question participant sets cannot answer.

    The same realization on two backends is one realization. The record has
    to say so without duplicating it or inventing a second identity.
    """
    stable = slab(*STABLE)
    runs = [
        solve_with_realization(
            stable, IMPLICIT_REALIZATION, run_id=f"r4-{n}", solver=make()
        )
        for n, make in (("sparse", sparse_scheme_solver), ("banded", banded_scheme_solver))
    ]
    merged = ProvenanceRecord(
        run_id="r4-merged",
        bindings=tuple(b for r in runs for b in r.provenance.bindings),
    )
    solvers = merged.solvers_for_realization(IMPLICIT_REALIZATION.realization_id)
    assert len(solvers) == 2
    assert {s.solver_id for s in solvers} == {
        "thermal.conduction1d.scheme_solver",
        "thermal.conduction1d.scheme_solver_banded",
    }
    # One realization, one model, two solvers — and the realization's own
    # identity is unchanged by which backend ran it.
    assert merged.realizations == (IMPLICIT_REALIZATION.key,)
    assert len(merged.models) == 1
    assert len(merged.solvers) == 2


def test_r5_bindings_round_trip_including_a_missing_realization():
    prov = ProvenanceRecord(
        run_id="r5",
        bindings=(
            _binding("model.alpha", "real.zulu", "solver.two"),
            # A pre-MODEL0-R computation: model and solver, no realization.
            _binding("model.beta", None, "solver.one"),
        ),
        inputs={"x": Quantity(1.0, "meter")},
    )
    restored = ProvenanceRecord.from_dict(prov.to_dict())
    assert restored.bindings == prov.bindings
    assert restored.realizations == (("real.zulu", "1.0"),)
    assert restored.bindings_for_model("model.beta")[0].realization is None
    assert json.dumps(restored.to_dict(), sort_keys=True) == json.dumps(
        prov.to_dict(), sort_keys=True
    )


def test_r6_realizations_is_derived_and_has_no_second_source_of_truth():
    """Requirement 4. One canonical representation, one place to write it."""
    assert "realizations" not in ProvenanceRecord.__dataclass_fields__
    assert isinstance(
        inspect.getattr_static(ProvenanceRecord, "realizations"), property
    )
    prov = ProvenanceRecord(run_id="r6", bindings=(_binding("m", "r", "s"),))
    assert "realizations" not in prov.to_dict()
    assert "bindings" in prov.to_dict()
    with pytest.raises(TypeError):
        ProvenanceRecord(run_id="x", realizations=(("r", "1"),))


def test_r7_participant_sets_may_not_contradict_the_bindings():
    """Requirement 4: the derived view cannot become a second place to edit."""
    with pytest.raises(ScientificCoreError, match="contradicts the bindings"):
        ProvenanceRecord(
            run_id="r7",
            models=(("other.model", "1.0"),),
            bindings=(_binding("model.alpha", "real.zulu", "solver.two"),),
        )
    # Declaring an extra participant that no binding covers is allowed:
    # partial knowledge is honest, contradiction is not.
    ok = ProvenanceRecord(
        run_id="r7b",
        models=(("model.alpha", "1.0"), ("uncovered.model", "1.0")),
        bindings=(_binding("model.alpha", "real.zulu", "solver.two"),),
    )
    assert len(ok.models) == 2
    assert ok.bindings_for_model("uncovered.model") == ()


def test_r8_the_realization_record_still_names_no_solver():
    """Requirement 2. The concrete solver lives on the binding, not on the
    realization: a realization is not one execution of itself."""
    assert set(ModelRealizationDefinition.__dataclass_fields__) == {
        "realization_id", "version", "model", "formulation", "name",
        "description", "provided_capabilities", "required_capabilities",
        "required_solver_capabilities", "assumptions", "implementation",
    }
    blob = json.dumps(IMPLICIT_REALIZATION.to_dict(), sort_keys=True)
    assert "solver_identity" not in blob
    assert "scheme_solver" not in blob
    assert set(ExecutionBinding.__dataclass_fields__) == {
        "model", "realization", "solver",
    }


def test_r9_a_binding_refuses_untyped_participants():
    with pytest.raises(ScientificCoreError, match="ModelReference"):
        ExecutionBinding(model=("m", "1"), solver=SolverIdentity("s", "1"))
    with pytest.raises(ScientificCoreError, match="SolverIdentity"):
        ExecutionBinding(model=ModelReference("m", "1"), solver=("s", "1"))
    with pytest.raises(ScientificCoreError, match="RealizationReference"):
        ExecutionBinding(
            model=ModelReference("m", "1"),
            solver=SolverIdentity("s", "1"),
            realization=("r", "1"),
        )


def test_x11_provenance_records_what_executed_not_what_was_requested():
    """Falsifier C9. The realization is read back from the prepared solve."""
    source = inspect.getsource(solve_with_realization)
    assert "prepared.payload.realization" in source
    # Rebinding different PHYSICS to one problem id is refused, exactly as
    # the frozen ``bind_slab`` refuses it. Rebinding a different REALIZATION
    # is allowed: one problem computed two ways is the point of the milestone.
    solver = sparse_scheme_solver()
    solver.bind("p", slab(*STABLE), IMPLICIT_REALIZATION)
    solver.bind("p", slab(*STABLE), EXPLICIT_REALIZATION)
    with pytest.raises(ValueError, match="different physics"):
        solver.bind("p", slab(*STABLE, slab_id="other"), IMPLICIT_REALIZATION)


def test_x6_deferred_formulation_members_gained_no_consumer():
    """prereg §12: DISCRETE and DAE remain unexercised and provisional."""
    for realization in (IMPLICIT_REALIZATION, EXPLICIT_REALIZATION):
        assert realization.formulation is not ModelFormulation.DISCRETE
        assert realization.formulation is not ModelFormulation.DAE
