"""IND-05 and NUM-03: what reading a consensus may import, and near-zero agreement.

IND-05 (probe ``agentD/ind3.py``). ``CrossSolverConsensus.from_dict`` verified
each route against its pin by hashing the route's dependencies, and hashing
canonicalises every ``py:`` identity by IMPORTING the module it names. So a
payload whose backend read ``["py:this:s"]`` imported ``this`` (and printed the
Zen of Python) before the digest could disagree with anything. A record chose
code to run on the reader. The declared identities are now compared against the
identities the pin lists first, and only identities the pin lists are resolved.

NUM-03. ``relative_difference(1.2e-17, 0.0)`` is 1.0, so two routes that agree
on a bridge current to round-off FAILED. The fix is a declared absolute floor
per quantity kind, read from the threshold set -- never an undeclared number.
"""

from __future__ import annotations

import json
import sys

import pytest

from engcore.domains import SCIENTIFIC_ROUTE_DECLARATIONS
from engcore.domains.electrical import dc_consensus as dcc
from engcore.domains.kinetics.cstr.validation import INTEGRATION_ROUTE_DEPENDENCIES
from engcore.scientific.consensus import CrossSolverConsensus, IndependenceVerdict
from engcore.scientific.results.thresholds import VerificationThresholds
from engcore.scientific.results.validation import ValidationOutcome
from engcore.scientific.solvers.protocol import SolverIdentity
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    route,
    route_declarations_for_tests,
)

NATIVE = SolverIdentity("electrical.dc.mna", "0.1.0", backend="scipy.linalg.solve")
EXTERNAL = SolverIdentity("engcore.electrical.dc.ngspice", "0", backend="ngspice")
SENTINEL_MODULE = "tests._audit_consensus_import_sentinel"


def _dc(values, required):
    return CrossSolverConsensus.over(
        consensus_id="x",
        routes=(dcc.native_route(NATIVE), dcc.external_route(EXTERNAL)),
        values=values,
        thresholds=dcc.DC_CONSENSUS_THRESHOLDS,
        tolerance_key="agreement_rel_tol",
        required_outputs=required,
    )


# ---- IND-05 ----------------------------------------------------------------------------
@pytest.mark.parametrize("dimension", ["backend", "implementation", "preprocessing"])
def test_reading_a_consensus_never_imports_a_module_the_payload_names(dimension):
    payload = _dc(
        {dcc.NATIVE_ROUTE_ID: {"v": 1.0}, dcc.EXTERNAL_ROUTE_ID: {"v": 2.0}}, ("v",)
    ).to_dict()
    payload["routes"][1]["dependencies"]["identities"][dimension] = [
        f"py:{SENTINEL_MODULE}:anything"
    ]
    sys.modules.pop(SENTINEL_MODULE, None)
    record = CrossSolverConsensus.from_dict(json.loads(json.dumps(payload)))
    assert SENTINEL_MODULE not in sys.modules, "from_dict imported a module a payload named"
    assert record.independence is IndependenceVerdict.UNVERIFIED
    assert "pin" in dict(record.unverified_routes)[dcc.EXTERNAL_ROUTE_ID]


def test_the_probe_payload_does_not_import_this():
    payload = _dc(
        {dcc.NATIVE_ROUTE_ID: {"v": 1.0}, dcc.EXTERNAL_ROUTE_ID: {"v": 2.0}}, ("v",)
    ).to_dict()
    payload["routes"][1]["dependencies"]["identities"]["backend"] = ["py:this:s"]
    already = "this" in sys.modules
    CrossSolverConsensus.from_dict(json.loads(json.dumps(payload)))
    assert already or "this" not in sys.modules


def test_production_pins_list_exactly_the_identities_their_constants_declare():
    declared = {
        dcc.NATIVE_ROUTE_ID: dcc.NATIVE_ROUTE_DEPENDENCIES,
        dcc.EXTERNAL_ROUTE_ID: dcc.EXTERNAL_ROUTE_DEPENDENCIES,
        **{
            f"kinetics.cstr.integration:{m}": deps
            for m, deps in INTEGRATION_ROUTE_DEPENDENCIES.items()
        },
    }
    for route_id, dependencies in declared.items():
        pin = SCIENTIFIC_ROUTE_DECLARATIONS[route_id]
        assert {
            dimension: sorted(names) for dimension, names in pin["identities"].items()
        } == {d.value: sorted(n) for d, n in dependencies.identities.items()}, route_id
        assert dependencies.digest == pin["dependency_digest"], route_id


def test_verified_production_routes_still_verify():
    record = _dc(
        {dcc.NATIVE_ROUTE_ID: {"v": 1.0}, dcc.EXTERNAL_ROUTE_ID: {"v": 1.0}}, ("v",)
    )
    assert record.unverified_routes == ()
    assert record.routes_are_independent


# ---- NUM-03 ----------------------------------------------------------------------------
def test_round_off_on_a_near_zero_quantity_is_not_a_disagreement():
    consensus = _dc(
        {
            dcc.NATIVE_ROUTE_ID: {"resistor_current:Rbridge": 1.2e-17, "node_voltage:n1": 0.5},
            dcc.EXTERNAL_ROUTE_ID: {"resistor_current:Rbridge": 0.0, "node_voltage:n1": 0.5},
        },
        ("resistor_current:Rbridge", "node_voltage:n1"),
    )
    assert consensus.comparison.agreed, consensus.comparison.detail
    assert consensus.to_check().outcome is ValidationOutcome.PASS


def test_a_disagreement_above_the_declared_floor_still_fails():
    consensus = _dc(
        {
            dcc.NATIVE_ROUTE_ID: {"resistor_current:Rbridge": 1.0e-9},
            dcc.EXTERNAL_ROUTE_ID: {"resistor_current:Rbridge": 0.0},
        },
        ("resistor_current:Rbridge",),
    )
    assert not consensus.comparison.agreed
    assert consensus.to_check().outcome is ValidationOutcome.FAIL


def test_the_floor_is_declared_in_the_threshold_set_and_absent_means_none():
    floors = {
        key: value
        for key, value in dcc.DC_CONSENSUS_THRESHOLDS.values.items()
        if key.startswith("agreement_rel_tol.floor.")
    }
    assert floors, "the DC consensus threshold set declares no absolute floors"
    assert dcc.DC_CONSENSUS_THRESHOLDS.is_declared
    a, b = route("a"), route("b")
    undeclared = VerificationThresholds(
        gate_id="test.no.floor", version="1", values={"agreement_rel_tol": 1e-9}
    )
    consensus = CrossSolverConsensus.over(
        consensus_id="nofloor", routes=(a, b),
        values={"a": {"i:x": 1.2e-17}, "b": {"i:x": 0.0}},
        thresholds=undeclared, tolerance_key="agreement_rel_tol", required_outputs=("i:x",),
    )
    # No declared floor, no invented one: the strict relative rule applies.
    assert consensus.comparison.worst_relative_difference == pytest.approx(1.0)


def test_a_floored_record_round_trips_and_its_comparison_is_recomputed():
    consensus = _dc(
        {
            dcc.NATIVE_ROUTE_ID: {"resistor_current:Rbridge": 1.2e-17},
            dcc.EXTERNAL_ROUTE_ID: {"resistor_current:Rbridge": 0.0},
        },
        ("resistor_current:Rbridge",),
    )
    again = CrossSolverConsensus.from_dict(json.loads(json.dumps(consensus.to_dict())))
    assert again.comparison == consensus.comparison
