"""Audit CAP-06: omissions that were assumed but never screened are stated as such.

Three records made claims no condition checks and said so nowhere a reader of
the record would look:

* ``battery.cell.rint_ocv`` - the affine OCV chord ignores the declared
  chemistry, and the omitted reversible (entropic) heat is excluded but its
  size is screened by nothing;
* ``battery.cell.peukert_capacity_derating`` - the exponent ignores chemistry;
* ``thermal.conduction2d`` - one constant conductivity, with no check of the
  temperature span the solution reaches.

None of these is cheaply checkable with what the domains can be told
(dU/dT, a chemistry-specific curve or exponent range, a k(T) span), so the
honest fix is to state them in the record's own exclusions/applicability.
"""

from __future__ import annotations

from engcore.domains.battery.models import PEUKERT_DERATING_MODEL, RINT_OCV_MODEL
from engcore.domains.thermal_models import conduction2d


def _joined(lines) -> str:
    return " ".join(lines).lower()


def test_rint_states_that_chemistry_does_not_shape_its_ocv() -> None:
    text = _joined(RINT_OCV_MODEL.exclusions)
    assert "chemistry" in text and "affine chord" in text


def test_rint_states_that_the_reversible_heat_is_unscreened() -> None:
    text = _joined(RINT_OCV_MODEL.exclusions)
    assert "no condition bounds -i t du/dt" in text


def test_peukert_states_that_chemistry_does_not_shape_its_exponent() -> None:
    text = _joined(PEUKERT_DERATING_MODEL.exclusions)
    assert "chemistry" in text and "exponent" in text


def test_conduction2d_states_that_its_conductivity_span_is_unassessed() -> None:
    text = _joined(conduction2d.APPLICABILITY)
    assert "no k(t) span is declarable" in text


def test_the_lumped_record_states_that_its_heat_capacity_is_unchecked() -> None:
    from engcore.domains.thermal_models.lumped import LUMPED_CAPACITY_MODEL

    assert "not compared with rho c_p v" in _joined(LUMPED_CAPACITY_MODEL.exclusions)


def test_the_held_resistance_limitation_is_stated_where_a_caller_reads() -> None:
    from engcore.domains.electrical import dc_applicability as dc_app
    from engcore.mcp import server

    condition = next(
        c for c in dc_app.SELF_HEATED_RESISTOR_MODEL.validity.conditions
        if c.name == dc_app.RESISTANCE_VARIATION_UTILIZATION
    )
    assert "known limitation" in condition.description.lower()
    assert "KNOWN LIMITATION" in server._RUN_DESCRIPTION
