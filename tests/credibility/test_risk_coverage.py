"""P20 #12: the false-trust and over-refusal metrics are provider-independent.

The requirement is that these numbers mean the same thing whether the
prediction came from a native Forge model, from PyBaMM, or from a provider that
does not exist yet. The enforcement is structural: :class:`PredictionOutcome`
has no field that could name an engine, so the metric cannot be sliced by one
and two engines cannot end up scored on different scales.

The rest of this file is the arithmetic, including the three cases that are
easy to get wrong and expensive to get wrong silently: an empty denominator
must not read as zero, unknown truth must enter no rate, and NOT_SUPPORTED must
not be counted as a refusal.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from engcore.credibility.risk_coverage import (
    GroundTruth,
    PredictionOutcome,
    RiskCoverageReport,
    TrustDecision,
    risk_coverage_curve,
    summarise,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "src" / "engcore" / "credibility" / "risk_coverage.py"


def _outcome(case_id, decision, truth, margin=None):
    return PredictionOutcome(case_id, decision, truth, margin)


def test_the_metric_record_cannot_name_a_provider():
    """The enforcement, asserted over the dataclass rather than over a run."""
    fields = set(PredictionOutcome.__dataclass_fields__)
    assert fields == {"case_id", "decision", "truth", "margin"}
    for banned in ("provider", "solver", "model", "backend", "engine", "source"):
        assert banned not in fields, (
            f"PredictionOutcome gained a {banned!r} field; the metric can now "
            f"be sliced by which engine produced a number, which is how two "
            f"providers stop being comparable"
        )
    with pytest.raises(TypeError):
        PredictionOutcome(  # type: ignore[call-arg]
            "c", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE, provider="pybamm"
        )


def test_the_module_names_no_provider_in_code():
    """Prose may explain the rule; code may not implement an exception to it."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    banned = {"pybamm", "pybop", "salib", "ngspice", "provider"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.lower() in banned:
            pytest.fail(f"line {node.lineno}: names {node.id}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            lowered = node.value.lower()
            for word in banned:
                assert word not in lowered, f"line {node.lineno}: {word!r} in a literal"


def test_identical_outcomes_score_identically_whatever_produced_them():
    """Two 'runs' with the same decisions and truths give the same report.

    This is the property in its operational form: nothing about a case except
    its decision and its truth can move a number, so the same evidence from a
    native solve and from PyBaMM produces the same risk profile.
    """
    native = [
        _outcome("n1", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE),
        _outcome("n2", TrustDecision.SUPPORTED, GroundTruth.OUTSIDE_TOLERANCE),
        _outcome("n3", TrustDecision.REFUSED, GroundTruth.OUTSIDE_TOLERANCE),
    ]
    external = [
        _outcome("p1", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE),
        _outcome("p2", TrustDecision.SUPPORTED, GroundTruth.OUTSIDE_TOLERANCE),
        _outcome("p3", TrustDecision.REFUSED, GroundTruth.OUTSIDE_TOLERANCE),
    ]
    first, second = summarise(native), summarise(external)
    assert first.to_dict() == second.to_dict()
    assert first.coverage == pytest.approx(2 / 3)
    assert first.false_trust_rate == pytest.approx(0.5)
    assert first.over_refusal_rate == pytest.approx(0.0)


def test_the_two_by_two_is_counted_in_the_four_cells():
    report = summarise(
        [
            _outcome("a", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE),
            _outcome("b", TrustDecision.SUPPORTED, GroundTruth.OUTSIDE_TOLERANCE),
            _outcome("c", TrustDecision.REFUSED, GroundTruth.WITHIN_TOLERANCE),
            _outcome("d", TrustDecision.REFUSED, GroundTruth.OUTSIDE_TOLERANCE),
        ]
    )
    assert (
        report.correct_support,
        report.false_trust,
        report.over_refusal,
        report.correct_refusal,
    ) == (1, 1, 1, 1)
    assert report.false_trust_rate == pytest.approx(0.5)
    assert report.over_refusal_rate == pytest.approx(0.5)
    assert report.coverage == pytest.approx(0.5)


def test_an_empty_denominator_is_null_and_never_zero():
    """A system that refused nothing has an UNMEASURED over-refusal rate.

    Reporting ``0.0`` there would read as "we checked and it never happens",
    which is the single most flattering thing an assurance metric can say
    without evidence.
    """
    report = summarise(
        [_outcome("a", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE)]
    )
    assert report.refused == 0
    assert report.over_refusal_rate is None
    assert report.to_dict()["over_refusal_rate"] is None
    assert summarise([]).coverage is None


def test_unknown_truth_is_counted_and_enters_no_rate():
    report = summarise(
        [
            _outcome("a", TrustDecision.SUPPORTED, GroundTruth.UNKNOWN),
            _outcome("b", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE),
            _outcome("c", TrustDecision.REFUSED, GroundTruth.UNKNOWN),
        ]
    )
    assert report.truth_unknown == 2
    assert report.supported == 2
    # One supported case has known truth and it was right.
    assert report.false_trust_rate == pytest.approx(0.0)
    assert report.correct_support + report.false_trust == 1
    # The refusal had unknown truth, so nothing can be said about refusals.
    assert report.over_refusal_rate is None


def test_not_supported_is_not_a_refusal():
    """A contradicted claim and a declined one are different products.

    Folding them together would count a working guardrail as a failed claim
    and would make the over-refusal rate unreadable.
    """
    report = summarise(
        [
            _outcome("a", TrustDecision.NOT_SUPPORTED, GroundTruth.OUTSIDE_TOLERANCE),
            _outcome("b", TrustDecision.REFUSED, GroundTruth.OUTSIDE_TOLERANCE),
        ]
    )
    assert report.not_supported == 1
    assert report.refused == 1
    assert report.correct_refusal == 1
    assert report.coverage == pytest.approx(0.0)


def test_a_case_counted_twice_is_refused():
    with pytest.raises(ValueError, match="twice"):
        summarise(
            [
                _outcome("a", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE),
                _outcome("a", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE),
            ]
        )


def test_refusing_everything_buys_a_perfect_false_trust_rate_and_no_coverage():
    """The degenerate strategy, made visible rather than rewarded."""
    report = summarise(
        [
            _outcome(f"c{i}", TrustDecision.REFUSED, GroundTruth.WITHIN_TOLERANCE)
            for i in range(10)
        ]
    )
    assert report.coverage == pytest.approx(0.0)
    assert report.false_trust_rate is None, "no supported cases means no measured risk"
    assert report.over_refusal_rate == pytest.approx(1.0)


def test_the_curve_trades_coverage_against_risk():
    outcomes = [
        _outcome("a", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE, margin=0.9),
        _outcome("b", TrustDecision.SUPPORTED, GroundTruth.WITHIN_TOLERANCE, margin=0.6),
        _outcome("c", TrustDecision.SUPPORTED, GroundTruth.OUTSIDE_TOLERANCE, margin=0.2),
        _outcome("d", TrustDecision.REFUSED, GroundTruth.OUTSIDE_TOLERANCE),
    ]
    curve = risk_coverage_curve(outcomes, [0.0, 0.5, 0.8])
    assert [p.supported for p in curve] == [3, 2, 1]
    assert curve[0].false_trust_rate == pytest.approx(1 / 3)
    assert curve[1].false_trust_rate == pytest.approx(0.0)
    assert curve[0].coverage == pytest.approx(0.75)


def test_a_case_with_no_margin_is_never_accepted_by_a_threshold():
    """An absent margin is not a large one."""
    outcomes = [
        _outcome("a", TrustDecision.SUPPORTED, GroundTruth.OUTSIDE_TOLERANCE, margin=None)
    ]
    curve = risk_coverage_curve(outcomes, [0.0, 1.0])
    assert [p.supported for p in curve] == [0, 0]
    assert all(p.false_trust_rate is None for p in curve)


def test_the_report_states_that_a_null_rate_is_not_zero():
    payload = RiskCoverageReport(
        total=0, supported=0, not_supported=0, refused=0,
        correct_support=0, false_trust=0, correct_refusal=0, over_refusal=0,
        truth_unknown=0,
    ).to_dict()
    assert "is not zero" in payload["rate_note"]
