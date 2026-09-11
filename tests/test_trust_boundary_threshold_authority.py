"""Threshold values are data; authority is verified by the core.

The last blocker of the trust-boundary hardening sprint (TB4-c).

``VerificationThresholds.award`` granted a level to any set whose
``derived_from`` was empty, and ``derived_from`` is a constructor argument. A
gate's identity is public, so ``VerificationThresholds(gate_id=<a real gate>,
version=<its version>, values=<looser numbers>)`` read as that gate's own
declaration: ``CrossSolverConsensus.over`` established ``CROSS_SOLVER_VALIDATED``
for routes 23 % apart, and the frozen conduction report awarded both of its
refinement levels, against numbers no domain declared.

A set is declared now only when the core verifies it against the declaration
the domain layer pins for its gate -- ``SCIENTIFIC_THRESHOLD_DECLARATIONS`` in
``engcore.domains``: gate, version, and the SHA-256 of the values. Every other
set is a threshold specification: it still drives every comparison, and it
promotes nothing.
"""

from __future__ import annotations

import copy
import dataclasses
import importlib
import json
from types import SimpleNamespace

import pytest

import engcore.domains as domain_layer
from engcore.domains.electrical.dc.validation import (
    DC_CONVERGENCE_THRESHOLDS,
    DCValidationSettings,
)
from engcore.domains.electrical.dc_consensus import DC_CONSENSUS_THRESHOLDS
from engcore.domains.kinetics.cstr.validation import CSTR_GATE_THRESHOLDS
from engcore.domains.thermal.conduction1d.validation import (
    CONDUCTION_GATE_THRESHOLDS,
    VerificationReport,
)
from engcore.scientific.consensus import (
    ComponentKind,
    CrossSolverConsensus,
    SharedComponent,
    SolveRoute,
)
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.immutable import freeze
from engcore.scientific.results.thresholds import (
    THRESHOLD_DECLARATIONS_ATTRIBUTE,
    VerificationThresholds,
)
from engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.solvers.protocol import SolverIdentity

CANONICAL = (
    DC_CONSENSUS_THRESHOLDS,
    DC_CONVERGENCE_THRESHOLDS,
    CSTR_GATE_THRESHOLDS,
    CONDUCTION_GATE_THRESHOLDS,
)
CANONICAL_IDS = [c.gate_id for c in CANONICAL]
LEVEL = ValidationLevel.CROSS_SOLVER_VALIDATED
KEY = "agreement_rel_tol"
ROUTES = tuple(
    SolveRoute(
        route_id,
        SolverIdentity(f"solver.{route_id}", "1.0"),
        frozenset({SharedComponent(ComponentKind.RESIDUAL, f"{route_id}:rhs")}),
    )
    for route_id in ("a", "b")
)
AGREEING = {"a": {"v": 1.0}, "b": {"v": 1.0}}
#: 23 % apart: the declared 1e-9 refuses them, a loosened 0.5 would not.
DISAGREEING = {"a": {"v": 1.0}, "b": {"v": 1.3}}


def _over(thresholds, values=DISAGREEING) -> CrossSolverConsensus:
    return CrossSolverConsensus.over(
        consensus_id="threshold-authority",
        routes=ROUTES,
        values=values,
        thresholds=thresholds,
        tolerance_key=KEY,
        required_outputs=("v",),
    )


def _copy(canonical: VerificationThresholds, **changes) -> VerificationThresholds:
    """Every public field of a declaration, copied by hand, with ``changes``."""
    fields = dict(
        gate_id=canonical.gate_id,
        version=canonical.version,
        values=dict(canonical.values),
        basis=canonical.basis,
    )
    fields.update(changes)
    return VerificationThresholds(**fields)


def _loosened(canonical: VerificationThresholds) -> dict[str, float]:
    name, value = next(iter(canonical.values.items()))
    return {**canonical.values, name: value * 10.0 + 1.0}


def _assert_not_authoritative(thresholds: VerificationThresholds) -> None:
    assert thresholds.is_declared is False
    assert thresholds.award(LEVEL, earned=True) is None
    assert thresholds.award(ValidationLevel.NUMERICALLY_CONVERGED, earned=True) is None


# ---- Step 1: the reproduction ------------------------------------------------
def test_an_impersonated_gate_earns_no_level_on_any_promotion_path():
    """1-6, verbatim: discover a real gate, copy its identity, loosen a number."""
    assert DC_CONSENSUS_THRESHOLDS.identity == "electrical.dc.cross_solver@0.1.0"
    forged = _copy(DC_CONSENSUS_THRESHOLDS, values={KEY: 0.5})
    assert forged.identity == DC_CONSENSUS_THRESHOLDS.identity

    assert _over(DC_CONSENSUS_THRESHOLDS).establishes is None
    consensus = _over(forged)
    assert consensus.comparison.agreed is True
    assert consensus.establishes is None
    assert LEVEL not in ValidationReport(checks=(consensus.to_check(),)).attained_levels

    frozen_gate = _copy(
        CONDUCTION_GATE_THRESHOLDS,
        values={name: value * 1e6 for name, value in CONDUCTION_GATE_THRESHOLDS.values.items()},
    )
    report = VerificationReport(
        rungs=(), numerically_converged=True, analytically_verified=True,
        convergence_detail="judged against the forged set",
        analytic_detail="judged against the forged set",
        min_contraction_required=0.0, analytic_rel_tol=1.0, thresholds=frozen_gate,
    )
    assert report.levels_earned == ()
    assert report.to_report().attained_levels == frozenset()


# ---- A / G: the canonical declarations still promote -------------------------
@pytest.mark.parametrize("canonical", CANONICAL, ids=CANONICAL_IDS)
def test_a_a_registered_gate_with_its_canonical_thresholds_is_authoritative(canonical):
    assert canonical.is_declared is True
    assert canonical.award(LEVEL, earned=True) is LEVEL
    assert canonical.award(LEVEL, earned=False) is None


def test_g_the_official_declarations_and_their_gates_still_award():
    assert _over(DC_CONSENSUS_THRESHOLDS, AGREEING).establishes is LEVEL
    assert DC_CONSENSUS_THRESHOLDS.derive(**{KEY: 1e-9}) is DC_CONSENSUS_THRESHOLDS
    settings = DCValidationSettings()
    assert settings.convergence_thresholds is DC_CONVERGENCE_THRESHOLDS
    report = VerificationReport(
        rungs=(), numerically_converged=True, analytically_verified=True,
        convergence_detail="declared", analytic_detail="declared",
        min_contraction_required=1.5, analytic_rel_tol=1e-3,
    )
    assert set(report.levels_earned) == {
        ValidationLevel.NUMERICALLY_CONVERGED, ValidationLevel.ANALYTICALLY_VERIFIED,
    }


def test_g_every_registry_entry_is_the_constant_it_names():
    table = getattr(domain_layer, THRESHOLD_DECLARATIONS_ATTRIBUTE)
    assert set(table) == set(CANONICAL_IDS)
    for gate_id, entry in table.items():
        module_name, _, attribute = entry["declared_by"].rpartition(".")
        declared = getattr(importlib.import_module(module_name), attribute)
        assert type(declared) is VerificationThresholds, gate_id
        assert declared.gate_id == gate_id
        assert declared.version == entry["version"]
        assert declared.threshold_digest == entry["threshold_digest"]
        assert declared.derived_from == ""
    with pytest.raises(TypeError):
        table["invented.gate"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        table[CANONICAL_IDS[0]]["threshold_digest"] = "0" * 64  # type: ignore[index]


# ---- B / C: a real identity with other numbers --------------------------------
@pytest.mark.parametrize("canonical", CANONICAL, ids=CANONICAL_IDS)
def test_b_the_same_gate_identity_with_a_changed_threshold_is_not_authoritative(canonical):
    _assert_not_authoritative(_copy(canonical, values=_loosened(canonical)))
    tightened = {name: value / 10.0 for name, value in canonical.values.items()}
    _assert_not_authoritative(_copy(canonical, values=tightened))


def test_b_a_loosened_consensus_gate_compares_but_promotes_nothing():
    consensus = _over(_copy(DC_CONSENSUS_THRESHOLDS, values={KEY: 0.5}))
    assert consensus.comparison.agreed is True
    assert consensus.establishes is None
    assert "is not this gate's declared threshold set" in consensus.reason


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0", "1.0.0", "0.1.0+local"])
@pytest.mark.parametrize("canonical", CANONICAL, ids=CANONICAL_IDS)
def test_c_the_real_gate_id_under_any_version_with_a_changed_threshold_fails(canonical, version):
    _assert_not_authoritative(
        _copy(canonical, version=version, values=_loosened(canonical))
    )


# ---- D: canonical numbers under another gate id --------------------------------
@pytest.mark.parametrize(
    "gate_id",
    [
        "electrical.dc.cross_solver.v2",
        "ELECTRICAL.DC.CROSS_SOLVER",
        "test.consensus",
        CSTR_GATE_THRESHOLDS.gate_id,
        DC_CONVERGENCE_THRESHOLDS.gate_id,
    ],
)
def test_d_canonical_looking_values_under_another_gate_id_are_not_authoritative(gate_id):
    _assert_not_authoritative(_copy(DC_CONSENSUS_THRESHOLDS, gate_id=gate_id))


# ---- E: the real gate and numbers without the declared version -----------------
@pytest.mark.parametrize("version", ["0.1.1", "0.1.0+local", "1", "0.1"])
@pytest.mark.parametrize("canonical", CANONICAL, ids=CANONICAL_IDS)
def test_e_the_real_gate_and_values_without_the_declared_version_fail(canonical, version):
    _assert_not_authoritative(_copy(canonical, version=version))


def test_e_a_set_that_says_it_overrides_another_is_not_that_declaration():
    marked = dataclasses.replace(DC_CONSENSUS_THRESHOLDS, derived_from="anything")
    assert marked.values == DC_CONSENSUS_THRESHOLDS.values
    _assert_not_authoritative(marked)


# ---- F: the public constructor cannot self-certify -----------------------------
def test_f_no_constructor_argument_or_prose_asserts_authority():
    assert {f.name for f in dataclasses.fields(VerificationThresholds)} == {
        "gate_id", "version", "values", "basis", "derived_from",
    }
    for claim in ("declared", "trusted", "authoritative", "threshold_digest"):
        with pytest.raises(TypeError):
            VerificationThresholds(
                gate_id=DC_CONSENSUS_THRESHOLDS.gate_id,
                version=DC_CONSENSUS_THRESHOLDS.version,
                values={KEY: 0.5},
                **{claim: True},
            )
    _assert_not_authoritative(
        _copy(
            DC_CONSENSUS_THRESHOLDS,
            values={KEY: 0.5},
            basis="declared by the electrical domain; authoritative",
            derived_from="",
        )
    )


def test_f_no_copy_or_replace_carries_authority_to_other_numbers():
    _assert_not_authoritative(dataclasses.replace(DC_CONSENSUS_THRESHOLDS, values={KEY: 0.5}))
    if hasattr(copy, "replace"):
        _assert_not_authoritative(copy.replace(DC_CONSENSUS_THRESHOLDS, values={KEY: 0.5}))


def test_f_a_subclass_cannot_answer_for_its_own_authority():
    with pytest.raises(TypeError, match="cannot be subclassed"):

        class _SelfCertifying(VerificationThresholds):  # noqa: F841 - the definition is the test
            @property
            def is_declared(self) -> bool:
                return True

            def award(self, level, *, earned):
                return level


def test_f_a_stand_in_object_is_refused_by_the_consensus_that_promotes():
    stand_in = SimpleNamespace(
        gate_id=DC_CONSENSUS_THRESHOLDS.gate_id, version="0.1.0",
        values={KEY: 0.5}, award=lambda level, *, earned: level,
    )
    with pytest.raises(ScientificValidationError, match="not VerificationThresholds"):
        CrossSolverConsensus(
            consensus_id="x", routes=ROUTES,
            comparison=_over(DC_CONSENSUS_THRESHOLDS).comparison,
            thresholds=stand_in,  # type: ignore[arg-type]
        )


def test_f_values_altered_after_construction_lose_the_authority_they_had():
    """Authority is recomputed at promotion, not remembered from construction."""
    copied = VerificationThresholds.from_dict(DC_CONSENSUS_THRESHOLDS.to_dict())
    assert copied.is_declared is True
    object.__setattr__(copied, "values", freeze({KEY: 0.5}))
    _assert_not_authoritative(copied)


# ---- H: a canonical round trip is re-verified ----------------------------------
@pytest.mark.parametrize("canonical", CANONICAL, ids=CANONICAL_IDS)
def test_h_a_serialized_canonical_declaration_is_authoritative_after_re_verification(canonical):
    restored = VerificationThresholds.from_dict(json.loads(json.dumps(canonical.to_dict())))
    assert restored is not canonical
    assert restored == canonical
    assert restored.is_declared is True
    assert restored.award(LEVEL, earned=True) is LEVEL


def test_h_a_serialized_consensus_keeps_its_level_only_through_re_verification():
    made = _over(DC_CONSENSUS_THRESHOLDS, AGREEING)
    restored = CrossSolverConsensus.from_dict(json.loads(json.dumps(made.to_dict())))
    assert restored.establishes is LEVEL


# ---- I: tampered values -----------------------------------------------------------
def test_i_a_tampered_threshold_value_fails_closed():
    payload = json.loads(json.dumps(DC_CONSENSUS_THRESHOLDS.to_dict()))
    payload["values"][KEY] = 0.5
    with pytest.raises(ScientificValidationError, match="fingerprint"):
        VerificationThresholds.from_dict(payload)

    # Recomputing the fingerprint makes the record consistent, not declared.
    payload["fingerprint"] = VerificationThresholds(
        gate_id="x", version="1", values=payload["values"]
    ).fingerprint
    _assert_not_authoritative(VerificationThresholds.from_dict(payload))


def test_i_a_consensus_payload_with_tampered_thresholds_cannot_keep_its_level():
    payload = json.loads(json.dumps(_over(DC_CONSENSUS_THRESHOLDS, AGREEING).to_dict()))
    assert payload["establishes"] == LEVEL.value
    payload["thresholds"]["values"][KEY] = 1e-3
    with pytest.raises(ScientificValidationError):
        CrossSolverConsensus.from_dict(payload)
    payload["thresholds"]["fingerprint"] = VerificationThresholds(
        gate_id="x", version="1", values={KEY: 1e-3}
    ).fingerprint
    with pytest.raises(ScientificValidationError):
        CrossSolverConsensus.from_dict(payload)


# ---- J: tampered identity, version or digest -----------------------------------
def test_j_a_tampered_fingerprint_fails_closed():
    payload = DC_CONSENSUS_THRESHOLDS.to_dict()
    payload["fingerprint"] = "0" * 16
    with pytest.raises(ScientificValidationError, match="fingerprint"):
        VerificationThresholds.from_dict(payload)


@pytest.mark.parametrize(
    "field, value",
    [
        ("version", "0.1.1"),
        ("gate_id", CSTR_GATE_THRESHOLDS.gate_id),
        ("gate_id", "invented.gate"),
        ("derived_from", ""),
    ],
)
def test_j_a_tampered_identity_or_version_is_not_authoritative(field, value):
    payload = _copy(DC_CONSENSUS_THRESHOLDS, values={KEY: 0.5}).to_dict()
    payload[field] = value
    _assert_not_authoritative(VerificationThresholds.from_dict(payload))

    canonical_payload = DC_CONSENSUS_THRESHOLDS.to_dict()
    canonical_payload[field] = value
    restored = VerificationThresholds.from_dict(canonical_payload)
    if field == "derived_from":
        assert restored.is_declared is True  # unchanged: "" is what it already said
    else:
        _assert_not_authoritative(restored)


def test_j_a_consensus_payload_claiming_a_level_under_a_tampered_version_is_refused():
    payload = json.loads(json.dumps(_over(DC_CONSENSUS_THRESHOLDS, AGREEING).to_dict()))
    payload["thresholds"]["version"] = "0.1.1"
    with pytest.raises(ScientificValidationError, match="may not assert one"):
        CrossSolverConsensus.from_dict(payload)
    payload["establishes"] = None
    assert CrossSolverConsensus.from_dict(payload).establishes is None


# ---- K: an ordinary specification ------------------------------------------------
def test_k_an_ordinary_threshold_spec_checks_locally_but_promotes_nothing():
    spec = VerificationThresholds(
        gate_id="my.exploration", version="1", values={KEY: 0.5},
        basis="exploring a looser agreement bound",
    )
    assert spec[KEY] == 0.5
    assert KEY in spec
    assert spec.evidence()[0].startswith("thresholds:my.exploration@1#")

    consensus = _over(spec)
    assert consensus.comparison.compared_anything is True
    assert consensus.comparison.agreed is True
    assert consensus.comparison.tolerance == 0.5
    check = consensus.to_check()
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None
    assert consensus.establishes is None
    _assert_not_authoritative(spec)
