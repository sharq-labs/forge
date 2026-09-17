"""Core re-audit 2026-09-16, batch 45: an admitted table carries the records the gate wrote and the units it used.

Problem R-71 (the audit's finding 102), improvement I-28 part B of three, under
benchmarks/core_v4_false_confidence/BATCH45_THRESHOLD_PROTOCOL.json.

`AdmittedForwardRow`'s constructor is its admission gate. `AdmittedForwardTable`'s own constructor takes
finished arrays and checks only that each admitted row carries one non-empty string per observation, and
nothing parses those strings -- so a table of fabricated values with refs ('forged', 'x') produces a
posterior. And a table's numbers are in the units of the set that built it while it records none of them, so
reusing it with a set whose keys match in other units compared 1500 milliohm against a table in ohm.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.inference import grid as G
from engcore.inference.grid import (
    AdmittedForwardTable,
    InferenceProblemError,
    gaussian_grid_posterior,
)

GOOD_REF = "numerical|pred-1|ver-1|bind-1"
ANALYTIC_REF = "analytic|pred-2|ver-2|bind-2"


def _symbol(name):
    assert hasattr(G, name), (
        f"engcore.inference.grid has no {name!r}; it is preregistered in BATCH45_THRESHOLD_PROTOCOL.json"
    )
    return getattr(G, name)


def _table(refs=(GOOD_REF,), *, units=None, values=((10.0,), (20.0,), (30.0,))):
    kwargs = {}
    if units is not None:
        import dataclasses

        assert any(f.name == "observation_units" for f in dataclasses.fields(AdmittedForwardTable)), (
            "AdmittedForwardTable has no `observation_units`; it is preregistered in "
            "BATCH45_THRESHOLD_PROTOCOL.json")
        kwargs["observation_units"] = units
    return AdmittedForwardTable(
        parameter_names=("x",),
        observation_keys=("H:y",),
        points=np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64),
        values=np.asarray(values, dtype=np.float64),
        admissible_mask=np.asarray([True, True, False], dtype=bool),
        admission_refs=(tuple(refs), tuple(refs), ()),
        rejection_reasons=("", "", "numerical convergence failed"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# an_admission_record_has_the_form_the_gate_writes
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-71 as audited: refs ('forged', 'x') produce a posterior -- the table checks only that each admitted row carries one non-empty string per observation")
def test_r71_a_table_whose_admission_records_are_free_strings_is_refused():
    """The audited forgery: refs ('forged', 'x') produced a posterior."""
    with pytest.raises(InferenceProblemError, match="admission record"):
        _table(refs=("forged",))


@pytest.mark.xfail(strict=True, reason="R-71: nothing parses the records, so the route the audit calls the difference between two kinds of evidence is unreadable")
def test_r71_a_record_naming_no_declared_route_is_refused():
    with pytest.raises(InferenceProblemError, match="route|admission record"):
        _table(refs=("guessed|pred-1|ver-1|bind-1",))


@pytest.mark.xfail(strict=True, reason="R-71: any non-empty string is an admission record")
def test_r71_a_record_with_an_empty_part_is_refused():
    with pytest.raises(InferenceProblemError, match="admission record"):
        _table(refs=("numerical|pred-1||bind-1",))


def test_r71_the_records_the_gate_writes_are_accepted():
    """The control: the form is read off the writer, so what it writes must pass."""
    assert _table(refs=(GOOD_REF,)) is not None
    assert _table(refs=(ANALYTIC_REF,)) is not None


@pytest.mark.xfail(strict=True, reason="R-71: admission_route survives only as a prefix of a string nothing reads")
def test_r71_a_table_says_which_routes_its_admitted_rows_crossed():
    table = _table(refs=(GOOD_REF,))
    assert hasattr(table, "admitted_routes"), (
        "AdmittedForwardTable has no `admitted_routes`; it is preregistered")
    assert table.admitted_routes == ("numerical",), (
        "the route is recorded only as a prefix of a string nothing parses")


def test_r71_a_rejected_row_still_needs_no_admission_record():
    """The control: a rejected row claims nothing, so it carries nothing."""
    table = _table(refs=(GOOD_REF,))
    assert table.admission_refs[2] == ()


# ---------------------------------------------------------------------------
# a_table_declares_the_units_its_numbers_are_in
# ---------------------------------------------------------------------------
def _observations(unit="ohm", magnitude=1.5):
    from engcore.inference.grid import GaussianObservation, ObservationSet
    from engcore.scientific.units import Quantity

    return ObservationSet(
        observations=(
            GaussianObservation(
                condition_id="c1", observable_name="y", value=Quantity(magnitude, unit),
                sigma=Quantity(0.1, unit), source_ref="b45-fixture",
            ),
        ),
        dataset_id="d1",
    )


@pytest.mark.xfail(strict=True, reason="R-71 as audited: 1500 milliohm against a table in ohm gives a MAP of 1.5 -- keys match, units are never checked")
def test_r71_reusing_a_table_with_another_units_set_is_refused():
    """As audited: 1500 milliohm against a table in ohm gave a MAP of 1.5."""
    table = _table(refs=(GOOD_REF,), units=("ohm",))
    with pytest.raises(InferenceProblemError, match="unit"):
        table.select_observations(_observations(unit="milliohm", magnitude=1500.0))
    with pytest.raises(InferenceProblemError, match="unit"):
        gaussian_grid_posterior(table, _observations(unit="milliohm", magnitude=1500.0))


@pytest.mark.xfail(strict=True, reason="R-71: the field the control needs does not exist yet")
def test_r71_the_set_it_was_built_against_still_works():
    table = _table(refs=(GOOD_REF,), units=("ohm",))
    values, columns = table.select_observations(_observations())
    assert columns == (0,) and values.shape == (3, 1)


@pytest.mark.xfail(strict=True, reason="R-71: the field does not exist yet")
def test_r71_a_table_that_declares_no_units_still_computes_a_posterior():
    """The control: refusing every undeclared table would delete legitimate cached tables."""
    table = _table(refs=(GOOD_REF,))
    assert getattr(table, "observation_units", ()) == ()
    posterior = gaussian_grid_posterior(table, _observations(magnitude=20.0))
    assert posterior.weights.shape == (3,)


# ---------------------------------------------------------------------------
# the_admission_path_requires_a_bound_table
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-71: there is no bound-table requirement at all")
def test_r71_the_admission_path_refuses_an_unbound_table():
    require_bound = _symbol("require_bound_forward_table")
    with pytest.raises(InferenceProblemError, match="unit|bound"):
        require_bound(_table(refs=(GOOD_REF,)), _observations())
    require_bound(_table(refs=(GOOD_REF,), units=("ohm",)), _observations())


@pytest.mark.xfail(strict=True, reason="R-71: the predictive-admission route accepts a table bound to nothing")
def test_r71_predictive_admission_refuses_an_unbound_table():
    from engcore.uq import UQProblemError, condition_posterior_on_predictive_admission
    import tests.test_k31_predictive_admission as K

    with pytest.raises((UQProblemError, InferenceProblemError), match="unit|bound"):
        condition_posterior_on_predictive_admission(
            K._posterior((0.7, 0.3, 0.0)), _table(refs=(GOOD_REF,)),
            maximum_unsupported_mass=1.0e-12)
