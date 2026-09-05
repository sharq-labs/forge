"""SRIA V0.1 M2A — outcome bridge gate tests.

Runs under pytest, and standalone via ``python -m tests.test_sria_m2a_bridge``.

M2A is a hard gate: no learned failure model may consume data until the two
failure vocabularies are reconciled. These tests prove the reconciliation is
honest — specifically that ambiguity is preserved as ambiguity rather than
resolved into plausible-looking labels.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from src.engcore.scientific import EvaluationStatus
from src.engcore.sria import AttributedCause, CensoringType, Disposition
from src.engcore.sria.calibration import (
    BridgedOutcome,
    LEGACY_MAPPING_TABLE,
    MappingConfidence,
    bridge_evaluation,
    bridge_evaluation_status,
    mapping_table_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_DIR = REPO_ROOT / "src" / "engcore" / "sria" / "calibration"
BRIDGE_MODULE = CALIBRATION_DIR / "outcome_bridge.py"


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


# =====================================================================
# Coverage and shape of the mapping
# =====================================================================

def test_every_legacy_status_is_mapped():
    """No legacy status may fall through unmapped."""
    assert set(LEGACY_MAPPING_TABLE) == set(EvaluationStatus)
    for status in EvaluationStatus:
        bridged = bridge_evaluation_status(status)
        assert isinstance(bridged, BridgedOutcome)
        assert bridged.legacy_status == status.value

    rows = mapping_table_rows()
    assert len(rows) == len(EvaluationStatus)


def test_unambiguous_statuses_map_exactly():
    ok = bridge_evaluation_status(EvaluationStatus.OK)
    assert ok.outcome.disposition is Disposition.SUCCESS
    assert ok.outcome.attributed_cause is AttributedCause.NONE
    assert ok.mapping_confidence is MappingConfidence.EXACT
    assert ok.pf_eligible is True

    not_run = bridge_evaluation_status(EvaluationStatus.NOT_RUN)
    assert not_run.outcome.disposition is Disposition.INDETERMINATE
    assert not_run.pf_eligible is False
    assert not_run.mapping_confidence is MappingConfidence.EXACT


def test_not_converged_is_partial_not_censored():
    """A completed-but-untrusted run finished; it is not a truncation."""
    bridged = bridge_evaluation_status(EvaluationStatus.NOT_CONVERGED)
    assert bridged.outcome.disposition is Disposition.PARTIAL
    assert bridged.outcome.attributed_cause is AttributedCause.NUMERICAL
    assert bridged.outcome.censoring_type is CensoringType.NONE
    assert bridged.outcome.is_censored is False
    assert bridged.mapping_confidence is MappingConfidence.PARTIAL


# =====================================================================
# The core honesty requirement
# =====================================================================

def test_bare_failed_is_ambiguous_and_ineligible():
    """Legacy FAILED conflates causes; it must not be guessed."""
    bridged = bridge_evaluation_status(EvaluationStatus.FAILED)

    assert bridged.outcome.disposition is Disposition.FAILED
    assert bridged.outcome.attributed_cause is AttributedCause.UNATTRIBUTED
    assert bridged.mapping_confidence is MappingConfidence.AMBIGUOUS
    assert bridged.pf_eligible is False
    assert bridged.outcome.informative_for_pf is False

    # It was not silently turned into any specific cause.
    for guessed in (
        AttributedCause.NUMERICAL,
        AttributedCause.INFRASTRUCTURE,
        AttributedCause.INFEASIBLE,
        AttributedCause.SCIENTIFIC,
    ):
        assert bridged.outcome.attributed_cause is not guessed


def test_unattributed_can_never_be_pf_eligible():
    """The invariant is structural, not a convention downstream code follows."""
    from src.engcore.sria import RunOutcome

    forged = RunOutcome(
        disposition=Disposition.FAILED,
        attributed_cause=AttributedCause.UNATTRIBUTED,
        informative_for_pf=True,   # deliberately inconsistent
    )
    _raises(
        ValueError,
        BridgedOutcome,
        outcome=forged,
        mapping_confidence=MappingConfidence.AMBIGUOUS,
        pf_eligible=True,
        legacy_status="failed",
    )


def test_eligibility_flags_cannot_disagree():
    from src.engcore.sria import RunOutcome

    outcome = RunOutcome(
        disposition=Disposition.SUCCESS,
        attributed_cause=AttributedCause.NONE,
        informative_for_pf=True,
    )
    _raises(
        ValueError,
        BridgedOutcome,
        outcome=outcome,
        mapping_confidence=MappingConfidence.EXACT,
        pf_eligible=False,   # disagrees with informative_for_pf
        legacy_status="ok",
    )


# =====================================================================
# Upgrade only by declared evidence
# =====================================================================

def test_declared_evidence_upgrades_ambiguous_failure():
    numerical = bridge_evaluation_status(
        EvaluationStatus.FAILED, evidence={"failure_kind": "numerical"}
    )
    assert numerical.outcome.attributed_cause is AttributedCause.NUMERICAL
    assert numerical.pf_eligible is True
    assert numerical.mapping_confidence is MappingConfidence.PARTIAL
    assert "failure_kind=numerical" in numerical.evidence_used


def test_infrastructure_failure_cannot_train_failure_model():
    infra = bridge_evaluation_status(
        EvaluationStatus.FAILED, evidence={"failure_kind": "infrastructure"}
    )
    assert infra.outcome.attributed_cause is AttributedCause.INFRASTRUCTURE
    assert infra.pf_eligible is False
    assert infra.outcome.informative_for_pf is False

    timeout = bridge_evaluation_status(
        EvaluationStatus.FAILED, evidence={"failure_kind": "timeout"}
    )
    assert timeout.pf_eligible is False


def test_unrecognised_evidence_is_ignored_not_interpreted():
    """An unknown value must not become a silent classification."""
    for junk in ("weird", "FAILED_SOMEHOW", "probably numerical", "1", "none"):
        bridged = bridge_evaluation_status(
            EvaluationStatus.FAILED, evidence={"failure_kind": junk}
        )
        assert bridged.outcome.attributed_cause is AttributedCause.UNATTRIBUTED
        assert bridged.pf_eligible is False
        assert bridged.mapping_confidence is MappingConfidence.AMBIGUOUS
        assert "ignored" in bridged.notes


def test_censored_failure_is_not_an_observed_failure():
    censored = bridge_evaluation_status(
        EvaluationStatus.FAILED,
        evidence={"censoring": "wallclock", "completion_fraction": 0.6},
    )
    assert censored.outcome.disposition is Disposition.KILLED_CENSORED
    assert censored.outcome.censoring_type is CensoringType.RIGHT_CENSORED_WALLCLOCK
    assert censored.outcome.is_censored is True
    assert censored.outcome.completion_fraction == 0.6
    assert censored.pf_eligible is False
    assert "not an observed failure" in censored.notes


def test_bridged_outcome_round_trips():
    for status in EvaluationStatus:
        bridged = bridge_evaluation_status(status)
        reloaded = BridgedOutcome.from_dict(
            json.loads(json.dumps(bridged.to_dict()))
        )
        assert reloaded.outcome.disposition is bridged.outcome.disposition
        assert reloaded.outcome.attributed_cause is bridged.outcome.attributed_cause
        assert reloaded.pf_eligible == bridged.pf_eligible
        assert reloaded.mapping_confidence is bridged.mapping_confidence


def test_bridge_accepts_a_scientific_evaluation():
    from src.engcore.scientific import Quantity, ScientificEvaluation

    evaluation = ScientificEvaluation(
        evaluation_id="ev-1",
        candidate={"x": Quantity(1.0, "meter")},
        status=EvaluationStatus.FAILED,
    )
    bridged = bridge_evaluation(evaluation)
    assert bridged.outcome.attributed_cause is AttributedCause.UNATTRIBUTED
    assert bridged.pf_eligible is False


# =====================================================================
# THE GATE: learners never touch the legacy vocabulary
# =====================================================================

def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def _code_references(path: Path, symbol: str) -> bool:
    """Whether a module *uses* a symbol in code.

    AST-based on purpose: a grep over raw text also matches docstrings, and a
    module is allowed to *describe* the legacy vocabulary in prose while never
    touching it. Failing on documentation would train us to stop documenting.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == symbol:
            return True
        if isinstance(node, ast.Attribute) and node.attr == symbol:
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == symbol or alias.asname == symbol:
                    return True
    return False


def test_only_the_bridge_may_reference_evaluation_status():
    """Exactly one module in the calibration package knows the legacy enum."""
    assert CALIBRATION_DIR.is_dir(), f"missing {CALIBRATION_DIR}"

    offenders = [
        path.name
        for path in sorted(CALIBRATION_DIR.rglob("*.py"))
        if path.name != "outcome_bridge.py"
        and _code_references(path, "EvaluationStatus")
    ]
    assert offenders == [], (
        f"these learning modules reference the legacy vocabulary in code: "
        f"{offenders}; all legacy outcomes must enter through outcome_bridge"
    )

    # And the bridge really is the module that uses it.
    assert _code_references(BRIDGE_MODULE, "EvaluationStatus")

    # The detector must actually detect: a module that does use it is caught.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "leaky_learner.py"
        bad.write_text(
            "from engcore.scientific import EvaluationStatus\n"
            "def train(rows):\n"
            "    return [r for r in rows if r.status is EvaluationStatus.OK]\n",
            encoding="utf-8",
        )
        assert _code_references(bad, "EvaluationStatus") is True


def test_learning_modules_do_not_import_the_legacy_enum():
    for path in sorted(CALIBRATION_DIR.rglob("*.py")):
        if path.name == "outcome_bridge.py":
            continue
        imported = _module_imports(path)
        for name in imported:
            assert "experiments.evaluation" not in name, (
                f"{path.name} imports {name}"
            )


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M2A — outcome bridge gate tests")
    print("=" * 72)
    failures = 0
    tests = _all_tests()
    for name, test in tests:
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print("=" * 72)
    if failures:
        print(f"M2A bridge tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M2A bridge tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
