"""The audit in `docs/domains/evidentiary-levels.md`, made load-bearing.

The audit decides, for every passing validation check under
`src/engcore/domains/**`, whether it can earn a `ValidationLevel`. That
decision is worth exactly as much as the guarantee that the code still matches
it, and until now there was none: somebody could set `establishes=` on any of
the sixteen checks the audit calls unlevellable, and nothing would notice.

These tests read the **source**, not a run, and not the prose. The inventory is
built by walking the AST for `ValidationCheck(...)` constructions, so a check
added in a branch that no test happens to exercise is still counted, and a
docstring claiming a check establishes nothing cannot stand in for the keyword
that decides it.

`domains/thermal/` is excluded: it is byte-frozen, out of the audit's scope,
and a test that read it would fail the moment the freeze was lifted for an
unrelated reason.

Two failure modes are covered, and they are different:

* a check that *gains* a level without the audit being revisited — the one the
  audit exists to prevent, since a level is a claim;
* a check that *loses* one, or a new unlevelled check appearing, which is not
  dishonest but leaves the counts in the document wrong.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOMAINS = REPO_ROOT / "src" / "engcore" / "domains"
AUDIT = REPO_ROOT / "docs" / "domains" / "evidentiary-levels.md"

#: Excluded by the audit's own scope. Byte-frozen by
#: ``experiments/thermal_t1/t1_config.py::THERMAL_FROZEN_FILE_DIGESTS``.
FROZEN_TREE = DOMAINS / "thermal"

#: Every check under `domains/**` (except the frozen tree) that can establish a
#: level, and what it establishes. Read off the audit's own table.
LEVELLED = {
    "dimensional_consistency": "DIMENSIONALLY_VALID",
    "metric_dimensions": "DIMENSIONALLY_VALID",
    "linear_system_residual": "NUMERICALLY_CONVERGED",
    "tolerance_independence": "NUMERICALLY_CONVERGED",
    "analytic_invariant_agreement": "ANALYTICALLY_VERIFIED",
    "analytic_reference_agreement": "ANALYTICALLY_VERIFIED",
    # The consensus decides its own level; the check carries whatever the
    # declaration earned, which is CROSS_SOLVER_VALIDATED or nothing.
    "cross_method_agreement": None,
    # Emitted through CrossSolverConsensus.to_check(); the consensus decides
    # whether route independence is sufficient to award CROSS_SOLVER_VALIDATED.
    "independent_solver_agreement": None,
}

#: The seventeen. Every check that passes today and establishes nothing, with the
#: audit's category for it. Changing this set means the document's counts are
#: wrong, which is the point of asserting it here.
ESTABLISHES_NOTHING = {
    # battery/solver.py
    "coulomb_balance_residual": "never",
    "rint_terminal_residual": "earnable later",
    # electrical/dc/validation.py
    "kirchhoff_current_law": "never",
    "resistor_metric_consistency": "never",
    "voltage_source_relation": "never",
    "power_balance": "never",
    # electrical/material.py
    "resistance_strictly_positive": "never",
    # electrical/ngspice.py
    "realization_precondition_non_singular": "never",
    "provider_element_metric_consistency": "never",
    # kinetics/cstr/validation.py
    "integration_reported_success": "never",
    "trajectory_finite": "never",
    "state_physically_admissible": "never",
    # Levelled (CROSS_SOLVER_VALIDATED) until IND-04: its reference reads the
    # solver's own derived parameters, so it is not independent evidence.
    "independent_steady_state_agreement": "earnable later",
    # thermal_models/conduction1d_schemes.py
    "field_finite": "never",
    "amplitude_decay": "never",
    "boundary_conditions_held": "never",
    # thermal_models/lumped.py
    "lumped_balance_residual": "never",
    # thermal_models/nafems_t3.py — local execution checks. The external
    # benchmark level is issued by the repository-pinned OracleEvidenceSet,
    # not by any of these self-checks.
    "nafems_t3_field_finite": "never",
    "nafems_t3_boundary_conditions_held": "never",
    "nafems_t3_refinement_sensitivity": "never",
    # thermal_models/conduction2d.py — the third pass. The other two checks
    # this model emits reuse `field_finite` and `boundary_conditions_held`
    # above, whose verdicts apply to them unchanged.
    "field_linear_system_residual": "never",
}

#: Emitted only on an unsuccessful path, so it never passes and is not one of
#: the sixteen. Named rather than filtered silently: the difference between
#: "establishes nothing" and "never runs successfully" is the difference the
#: `NOT_RUN` outcome exists to record.
NEVER_PASSES = {
    "cell_step_evaluated",
    "linear_system_solved",
    "time_march_finite",
}

#: Emitted only as `NOT_RUN` in the module the audit reaches, with the level it
#: would carry awarded elsewhere or not at all.
NOT_RUN_ONLY = {"discretization_convergence"}


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` bindings, so a check named through a
    constant is resolved rather than skipped."""
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                constants[target.id] = node.value.value
    return constants


def _inventory() -> dict[str, set[str]]:
    """``{check name: {establishes-expression source, ...}}`` over the domains.

    A name can be constructed in several places with different level
    expressions — ``dimensional_consistency`` is built once per outcome — so
    the value is a set and the tests reason over it rather than over the last
    one seen.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(DOMAINS.rglob("*.py")):
        if FROZEN_TREE in path.parents or path == FROZEN_TREE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(
                func, "id", ""
            )
            kw = {k.arg: k.value for k in node.keywords}

            # CrossSolverConsensus.to_check() is also a ValidationCheck emitter.
            # It carries the consensus's dynamically derived establishes value,
            # so an AST inventory that sees only literal ValidationCheck(...)
            # constructors would silently classify the NOT_RUN fallback while
            # missing the successful level-bearing path.
            if (
                name == "to_check"
                and isinstance(func, ast.Attribute)
                and "consensus" in ast.unparse(func.value)
            ):
                label = kw.get("name")
                if isinstance(label, ast.Constant) and isinstance(label.value, str):
                    found.setdefault(label.value, set()).add(
                        "consensus.establishes"
                    )
                continue

            if name != "ValidationCheck":
                continue
            label = kw.get("name")
            if isinstance(label, ast.Constant):
                key = label.value
            elif isinstance(label, ast.Name) and label.id in constants:
                key = constants[label.id]
            else:  # pragma: no cover - nothing in the tree reaches this today
                pytest.fail(
                    f"{path}: a ValidationCheck is named by an expression this "
                    f"inventory cannot resolve ({ast.unparse(label)}), so the "
                    f"audit cannot see it"
                )
            establishes = kw.get("establishes")
            found.setdefault(key, set()).add(
                "None" if establishes is None else ast.unparse(establishes)
            )
    return found


INVENTORY = _inventory()


def test_the_inventory_is_not_empty_or_the_rest_proves_nothing():
    """A guard on the guard. An AST walk that silently found nothing would
    make every assertion below vacuously true."""
    assert len(INVENTORY) >= 20
    assert "power_balance" in INVENTORY
    assert "lumped_balance_residual" in INVENTORY


def test_every_check_in_the_domains_is_accounted_for_by_the_audit():
    """No check exists that the document has never considered.

    This is the test that catches a *new* check, which is the ordinary way an
    audit goes stale: somebody adds one, it establishes nothing, and the
    document's count of sixteen quietly becomes seventeen without anyone
    having decided anything about it.
    """
    accounted = (
        set(LEVELLED)
        | set(ESTABLISHES_NOTHING)
        | NEVER_PASSES
        | NOT_RUN_ONLY
    )
    unaccounted = sorted(set(INVENTORY) - accounted)
    assert not unaccounted, (
        f"validation checks with no row in {AUDIT.name}: {unaccounted}. Decide "
        f"what each can earn and record it there before adding it here."
    )


def test_the_audited_checks_still_establish_nothing():
    """The claim the audit makes, asserted against the source that makes it.

    Every construction of each of these names passes ``establishes=None``. Not
    "usually" and not "on the passing path": a level awarded on any path is a
    level this document says was not earned.
    """
    offenders = {
        name: sorted(exprs)
        for name, exprs in INVENTORY.items()
        if name in ESTABLISHES_NOTHING and exprs != {"None"}
    }
    assert not offenders, (
        f"{sorted(offenders)} now establish a level. The audit in "
        f"{AUDIT.name} says they cannot; if that is wrong, the argument in the "
        f"document has to change first, and this list with it."
    )
    missing = sorted(set(ESTABLISHES_NOTHING) - set(INVENTORY))
    assert not missing, (
        f"{missing} are audited and no longer exist. The document's counts are "
        f"now wrong."
    )


def test_the_levelled_checks_are_exactly_the_ones_the_audit_names():
    """The other direction: a level cannot appear where none was argued for."""
    levelled = {
        name for name, exprs in INVENTORY.items() if exprs != {"None"}
    }
    assert levelled == set(LEVELLED), (
        f"unexpected: {sorted(levelled - set(LEVELLED))}; "
        f"gone: {sorted(set(LEVELLED) - levelled)}"
    )
    for name, expected in LEVELLED.items():
        if expected is None:
            continue
        joined = " ".join(sorted(INVENTORY[name]))
        assert expected in joined, f"{name} no longer mentions {expected}"


def test_external_validation_levels_are_not_self_issued_by_domain_checks():
    """Strong external levels are never minted by local domain self-checks.

    BENCHMARK_VALIDATED is now earnable through the repository-pinned NAFEMS
    oracle, which lives outside this domain-check inventory. Experimental
    validation remains unoccupied. A domain check quietly claiming either
    would bypass the external-authority boundary.
    """
    joined = " ".join(
        expr for exprs in INVENTORY.values() for expr in sorted(exprs)
    )
    assert "BENCHMARK_VALIDATED" not in joined
    assert "EXPERIMENTALLY_VALIDATED" not in joined


def test_the_document_carries_a_row_for_every_audited_check():
    """The counts in the document are checkable, so they are checked.

    Prose can drift from a dictionary in a test file as easily as from code.
    This asserts the document actually names each of the sixteen and states the
    total, so the two cannot disagree silently.
    """
    text = AUDIT.read_text(encoding="utf-8")
    for name in ESTABLISHES_NOTHING:
        assert f"`{name}`" in text, f"{name} has no row in {AUDIT.name}"
    # 21 after Sprint 2.5 added three local NAFEMS execution checks that
    # deliberately establish no level.
    assert "Checks that pass today while establishing nothing: 21" in text
    assert str(len(ESTABLISHES_NOTHING)) == "21"
