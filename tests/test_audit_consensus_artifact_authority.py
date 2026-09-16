"""IND-03: artifact independence evidence is bytes Forge resolves or the domain pins.

The audit (probe ``agentD/ind1.py``, part C) presented, for every dependency
identity of two declared routes, the bytes ``f"junk-{route}-{identity}"`` with a
fingerprint computed from those same bytes. Every check the evidence gate made
passed -- the fingerprint re-hashed, each identity had its own artifact, no
digest was shared -- and ``TrustedConsensusGate`` kept ``CROSS_SOLVER_VALIDATED``.
The gate verified that the caller's bytes matched the caller's fingerprint, and
nothing tied either to the dependency they were presented for.

The rule these tests pin:

* a ``py:`` identity is evidenced only by the bytes of the source file Forge
  itself resolves for it (the defining module of the object the identity names);
* an ``ext:`` identity -- something outside the interpreter, which Forge cannot
  read for itself -- is evidenced only by bytes whose digest the domain layer
  pins for that identity on that route (``artifact_digests`` in the route pin).

Anything else covers nothing and says why.
"""

from __future__ import annotations

import importlib
import pathlib

from engcore.domains.electrical import dc_consensus as dcc
from engcore.execution.consensus import TrustedConsensusGate
from engcore.scientific.consensus import SOLVER_INDEPENDENCE_DIMENSIONS
from engcore.scientific.independence_evidence import (
    ArtifactFingerprint,
    RouteIndependenceEvidence,
    assess_independence_evidence,
)
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.solvers.protocol import SolverIdentity
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    PINS,
    earned_consensus,
    route,
    route_declarations_for_tests,
)

#: Eight real, distinct standard-library sources: one per solver-independence
#: dimension per route, so no two identities resolve to one file.
REAL = {
    "a": {
        "preprocessing": "py:json.decoder:JSONDecoder",
        "numerical_method": "py:csv:DictReader",
        "implementation": "py:textwrap:TextWrapper",
        "backend": "py:fractions:Fraction",
    },
    "b": {
        "preprocessing": "py:statistics:median",
        "numerical_method": "py:difflib:SequenceMatcher",
        "implementation": "py:shlex:shlex",
        "backend": "py:string:Template",
    },
}


def _source(identity: str) -> bytes:
    module_name = identity.split(":")[1]
    return pathlib.Path(importlib.import_module(module_name).__file__).read_bytes()


def _evidence(route_record, payload_for):
    canonical = route_record.dependencies.canonical()
    artifacts, blobs = {}, {}
    for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
        rows = [
            (f"{route_record.route_id}-{dimension.value}-{i}", payload_for(route_record, identity), identity)
            for i, identity in enumerate(sorted(canonical[dimension]))
        ]
        artifacts[dimension] = frozenset(
            ArtifactFingerprint.from_bytes(name, payload, dependency_identity=identity)
            for name, payload, identity in rows
        )
        blobs[dimension] = {name: payload for name, payload, _ in rows}
    return RouteIndependenceEvidence(route_record.route_id, route_record.dependencies.digest, artifacts), blobs


def _junk(route_record, identity):
    return f"junk-{route_record.route_id}-{identity}".encode()


def _gate(consensus, payload_for):
    records = [_evidence(item, payload_for) for item in consensus.routes]
    return TrustedConsensusGate().assess(
        consensus,
        [record for record, _ in records],
        artifact_bytes={item.route_id: blobs for item, (_, blobs) in zip(consensus.routes, records)},
    )


def _agreeing(a, b):
    return earned_consensus(
        (a, b), {a.route_id: {"v": 1.0}, b.route_id: {"v": 1.0}},
        thresholds=dcc.DC_CONSENSUS_THRESHOLDS, tolerance_key="agreement_rel_tol", required=("v",),
    )


# ---- the probe ---------------------------------------------------------------------------------
def test_probe_junk_bytes_for_external_identities_nobody_pinned_keep_no_level():
    consensus = _agreeing(route("a"), route("b"))  # ext:test:* identities, no artifact pins
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    decision = _gate(consensus, _junk)
    assert not decision.validated
    assert not decision.independence.strongly_independent
    assert "pinned" in decision.check.detail


def test_probe_junk_bytes_for_python_identities_keep_no_level():
    a = route("a", **REAL["a"])
    b = route("b", **REAL["b"])
    decision = _gate(_agreeing(a, b), _junk)
    assert not decision.validated
    assert "source" in decision.check.detail


def test_probe_production_dc_routes_with_junk_bytes_are_not_trusted():
    routes = (
        dcc.native_route(SolverIdentity("electrical.dc.mna", "0.1.0", backend="scipy.linalg.solve")),
        dcc.external_route(SolverIdentity("engcore.electrical.dc.ngspice", "0", backend="ngspice")),
    )
    records = [_evidence(item, _junk) for item in routes]
    report = assess_independence_evidence(
        routes, [r for r, _ in records],
        artifact_bytes={item.route_id: blobs for item, (_, blobs) in zip(routes, records)},
    )
    assert not report.strongly_independent


# ---- what does count -----------------------------------------------------------------------------
def test_real_python_sources_are_evidence_and_keep_the_level():
    a = route("a", **REAL["a"])
    b = route("b", **REAL["b"])
    decision = _gate(_agreeing(a, b), lambda _route, identity: _source(identity))
    assert decision.independence.strongly_independent, decision.independence.reason
    assert decision.validated
    assert decision.check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


def test_bytes_for_a_python_identity_that_are_another_modules_source_cover_nothing():
    a = route("a", **REAL["a"])
    b = route("b", **REAL["b"])
    swapped = {"py:textwrap:TextWrapper": "py:shlex:shlex"}

    def payload(_route, identity):
        return _source(swapped.get(identity, identity))

    evidence, blobs = _evidence(a, payload)
    assessment = evidence.assess(a, blobs)
    assert not assessment.verified
    assert "py:textwrap:TextWrapper" not in assessment.covered[
        next(d for d in SOLVER_INDEPENDENCE_DIMENSIONS if d.value == "implementation")
    ]


def test_external_bytes_count_only_when_the_domain_pins_their_digest(route_declarations_for_tests):
    a, b = route("a"), route("b")
    consensus = _agreeing(a, b)

    def honest(route_record, identity):
        return f"the real artifact behind {identity}".encode()

    for item in (a, b):
        canonical = item.dependencies.canonical()
        PINS[item.route_id]["artifact_digests"] = {
            identity: [ArtifactFingerprint.from_bytes("pin", honest(item, identity)).digest]
            for dimension in SOLVER_INDEPENDENCE_DIMENSIONS
            for identity in canonical[dimension]
        }
    assert _gate(consensus, honest).validated
    refused = _gate(consensus, _junk)
    assert not refused.validated
    assert "pinned" in refused.check.detail
