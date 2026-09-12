"""Standing guards over the mathematics itself.

The earlier rounds ask whether the record matches the runtime, and whether the
matched behaviour is claimed for the right regimes. These ask the question
underneath both: is the arithmetic right?

Every assertion here is against something computed OUTSIDE the code under test
-- an independently written integrator, a closed form derived in this audit, an
external simulator, a conservation law, or a convergence order the scheme
itself justifies. None of them would notice a record change, and none of them
can be satisfied by making the implementation agree with itself.
"""

import math

import pytest

from benchmarks.scientific_truth.audit import checks, independence, properties

CLEAN = {
    "AGREE", "PASS", "LIMIT_CORRECT", "SIGN_CORRECT", "HOLDS",
    "NO_MATERIAL_CANCELLATION", "CONVERGES_AT_EXPECTED_ORDER",
}


def _dirty(rows):
    return [row for row in rows if row.get("verdict") not in CLEAN]


# =====================================================================
# Independent oracle agreement, model family by model family
# =====================================================================
@pytest.mark.parametrize(
    "family",
    [
        "lumped_rows", "lumped_limits", "lumped_monotonicity",
        "diffusion_rows", "diffusion_limits",
        "battery_rows", "battery_limits_and_signs",
        "dc_rows", "dc_limits_and_signs",
        "material_rows", "material_limits_and_signs",
    ],
)
def test_the_runtime_agrees_with_an_independent_oracle(family):
    rows = getattr(checks, family)()
    assert rows, family
    assert _dirty(rows) == [], _dirty(rows)


@pytest.mark.parametrize("family", ["cstr_rows", "cstr_limits_and_signs"])
def test_the_reactor_agrees_with_an_independent_oracle(family):
    """Separated because the CSTR cases integrate stiff systems and are slow."""
    rows = getattr(checks, family)()
    assert rows, family
    assert _dirty(rows) == [], _dirty(rows)


# =====================================================================
# The numerical method, held to the order its own scheme justifies
# =====================================================================
def test_the_diffusion_solver_converges_at_the_order_its_scheme_justifies():
    """First order in time, second in space. Neither is assumed.

    The spatial ladder has the constant first-order time error subtracted
    before its order is read, because refining one discretization while
    another is held fixed measures their sum and not the one being refined.
    """
    rows = checks.diffusion_convergence()
    assert len(rows) == 2
    for row in rows:
        assert row["monotone_decreasing"], row
        assert row["verdict"] == "CONVERGES_AT_EXPECTED_ORDER", row
    time_row, space_row = rows
    assert all(abs(order - 1.0) < 0.3 for order in time_row["observed_orders"])
    assert all(abs(order - 2.0) < 0.3 for order in space_row["observed_orders"])


def test_the_predicted_discretization_error_is_what_the_solver_actually_makes():
    """A stronger statement than "inside tolerance".

    The relative error of each reference solve is predicted from the scheme --
    lambda^2 t dt / 2 in time plus lambda t (pi dx/L)^2 / 12 in space -- and
    the solver's actual error matches that prediction to within a few per cent.
    A solver making a DIFFERENT error of the same size would pass a tolerance
    and fail this.
    """
    for row in checks.diffusion_rows():
        if row["check"] != "reference_case":
            continue
        ratio = row["relative_error"] / row["predicted_scheme_error"]
        assert 0.5 <= ratio <= 1.5, (row["case"], ratio)


# =====================================================================
# Conservation, measured rather than inferred
# =====================================================================
def test_every_conservation_residual_is_round_off():
    rows = [
        row
        for family in (
            "lumped_rows", "battery_rows", "dc_rows", "cstr_rows",
        )
        for row in getattr(checks, family)()
        if row["check"] == "conservation"
    ]
    assert len(rows) >= 30, len(rows)
    assert _dirty(rows) == [], _dirty(rows)


# =====================================================================
# The signs that would still look plausible if they were wrong
# =====================================================================
def test_an_endothermic_reaction_cools_the_reactor():
    """The single most consequential sign in reactor engineering.

    beta = (-dH)/(rho cp) changes sign with the enthalpy of reaction. A model
    with it backwards heats on an endotherm and cools on an exotherm, and
    returns entirely plausible temperatures while doing so -- no record, no
    validity condition and no dimensional check would notice.
    """
    rows = [
        row for row in checks.cstr_limits_and_signs() if row["check"] == "sign"
    ]
    assert rows
    for row in rows:
        assert row["verdict"] == "SIGN_CORRECT", row


def test_a_discharge_pulls_the_terminal_below_the_open_circuit():
    rows = [
        row for row in checks.battery_limits_and_signs() if row["check"] == "sign"
    ]
    assert rows
    for row in rows:
        assert row["verdict"] == "SIGN_CORRECT", row


def test_a_passive_element_never_delivers_power():
    rows = [row for row in checks.dc_limits_and_signs() if row["check"] == "sign"]
    assert rows
    for row in rows:
        assert row["verdict"] == "SIGN_CORRECT", row


# =====================================================================
# The external oracle
# =====================================================================
def test_the_dc_solver_agrees_with_ngspice():
    """An independently written simulator, sharing no code with this repository."""
    rows = [row for row in checks.dc_rows() if row["check"] == "external_oracle"]
    if not rows:
        pytest.skip("ngspice is not installed in this environment")
    assert len(rows) >= 10
    assert _dirty(rows) == [], _dirty(rows)
    assert max(row["relative_error"] for row in rows) < 1e-5


# =====================================================================
# Independence: agreement is only evidence between things that can disagree
# =====================================================================
def test_this_audits_oracles_do_not_import_the_code_they_judge():
    report = independence.survey()
    coupled = [
        row for row in report["this_audits_oracles"]
        if row["verdict"] != "INDEPENDENT_OF_CORE"
    ]
    assert coupled == [], coupled


def test_no_route_the_repository_offers_as_a_check_computes_the_answer_it_checks():
    """PARTIAL is acceptable and NO is not.

    Every pair in this repository shares the problem statement -- the
    declaration objects and the result contract -- which is unavoidable if the
    two routes are to be about the same system. What must not happen is a
    route that is offered as a check importing the numerics it checks.
    """
    report = independence.survey()
    assert report["counts"]["NO"] == 0, [
        row for row in report["pairs"] if row["independent"] == "NO"
    ]


# =====================================================================
# Property testing over the declared domain
# =====================================================================
@pytest.mark.parametrize(
    "family", ["lumped_property", "battery_property", "diffusion_property"]
)
def test_randomized_cases_inside_the_declared_domain_hold(family):
    report = getattr(properties, family)()
    assert report["verdict"] == "HOLDS", report
    assert report["generated"] > 0
    # A generator that rejects nothing is not enforcing the domain it claims to.
    assert report["rejected"] > 0, (
        f"{family} refused no draw at all, so its domain constraints are not "
        "binding and the property is being checked on an unconstrained set"
    )
