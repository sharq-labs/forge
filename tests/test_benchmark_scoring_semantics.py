"""The scorer must not be able to call a coincidence a caught defect.

WHY THIS MODULE EXISTS
----------------------
The old scorer compared one enum per case. That made a case where Forge
returned the right verdict for a reason the truth does not name indistinguishable
from one where the declared mechanism actually fired -- and the benchmark had
110 of the former in its development split without any figure saying so.

A richer scorer is only worth having if its metrics move for the reasons they
claim to. So this module does two things:

* pins the *semantics* -- what FIRED, COINCIDENTAL and UNSPECIFIED mean, on
  hand-built cases small enough to read;
* **mutation-tests the metrics themselves**: change one input, and assert that
  the metric it is about moves while the others hold still. A scorecard whose
  verdict accuracy moved when only a catcher changed would be a new way of
  saying the same misleading thing.

Nothing here runs Forge. These are tests of the measuring instrument.
"""

from __future__ import annotations

import importlib.util
import sys
import pathlib

import pytest

BENCH = pathlib.Path(__file__).resolve().parent.parent / "benchmarks" / "hard"


def _scoring():
    """Load the scorer's classification module by path.

    Registered in ``sys.modules`` before it is executed because ``dataclass``
    resolves annotations through the defining module, and a module that is not
    there yet resolves to None.
    """
    name = "_scoring_under_test"
    spec = importlib.util.spec_from_file_location(name, BENCH / "scoring.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scoring = _scoring()


def truth(**overrides):
    base = {
        "label": "model_inapplicable",
        "expected_verdict": "NOT_SUPPORTED",
        "reason": "prose a scorer cannot check",
        "should_be_caught_by": "biot_number",
        "defect": "biot_out",
        "needs_review": False,
    }
    base.update(overrides)
    return base


def facts(verdict="NOT_SUPPORTED", violated=(), unknown=(), satisfied=(), refused=False):
    return scoring.ReportFacts(
        verdict=verdict,
        violated=frozenset(violated),
        unknown=frozenset(unknown),
        satisfied=frozenset(satisfied),
        coupling_refused=refused,
    )


def score(ground_truth, report_facts, case_id="T0001"):
    return scoring.score_case(ground_truth, case_id, "electrothermal", report_facts)


# =====================================================================
# The grammar of a declared catcher
# =====================================================================

@pytest.mark.parametrize(
    "raw,form,name",
    [
        ("", "not_declared", None),
        ("biot_number", "deciding_condition", "biot_number"),
        ("biot_number -> UNKNOWN", "expect_unknown", "biot_number"),
        ("biot_number (alt route remains)", "expect_held", "biot_number"),
        ("thermal runaway", "mechanism", "coupling_refusal"),
    ],
)
def test_every_catcher_shape_in_the_corpus_parses_to_what_it_means(raw, form, name):
    parsed = scoring.parse_catcher(raw)
    assert parsed.form.value == form
    assert parsed.name == name


def test_the_corpus_contains_no_catcher_shape_this_grammar_cannot_read():
    """If the benchmark grows a sixth shape, it must not parse as a condition.

    A new shape falling through to DECIDING_CONDITION would be scored against a
    condition name that does not exist, and would read as a permanent miss.
    """
    import json

    shapes = set()
    for path in sorted((BENCH / "cases_hard").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))["ground_truth"].get(
            "should_be_caught_by", ""
        )
        shapes.add(scoring.parse_catcher(raw).form.value)
    assert shapes == {
        "not_declared",
        "deciding_condition",
        "expect_unknown",
        "expect_held",
        "mechanism",
    }, shapes


# =====================================================================
# Phase K -- the five behaviours the round asked to be proven
# =====================================================================

def test_a_coincidental_catch_does_not_count_as_declared_catcher_success():
    """THE case this module exists for: right verdict, wrong mechanism."""
    result = score(
        truth(should_be_caught_by="operating_temperature_utilization"),
        facts(violated=["radiation_to_convection_ratio"],
              satisfied=["operating_temperature_utilization"]),
    )
    assert result.verdict_match is True          # the verdict is right
    assert result.declared_catcher_status == "NOT_FIRED"
    assert result.catch_type == "COINCIDENTAL"   # and it was not the mechanism
    assert result.false_accept is False

    card = scoring.scorecard([result])
    assert card["declared_catcher_rate"] == "0/1 (0.0%)"
    assert card["coincidental_catches"] == 1
    # The verdict figure is untouched by the mechanism being wrong.
    assert card["exact_verdict_match"] == "1/1 (100.0%)"


def test_a_correct_verdict_with_a_wrong_reason_is_not_a_fully_correct_case():
    declared = score(truth(), facts(violated=["biot_number"]))
    coincidental = score(
        truth(), facts(violated=["radiation_to_convection_ratio"])
    )
    assert declared.verdict_match == coincidental.verdict_match is True
    assert declared.catch_type == "DECLARED"
    assert coincidental.catch_type == "COINCIDENTAL"
    assert declared != coincidental, (
        "two cases that differ only in whether the declared mechanism fired "
        "must not score identically"
    )


def test_a_wrong_verdict_with_the_right_catcher_is_still_a_wrong_verdict():
    """Firing the declared condition does not buy a verdict."""
    result = score(
        truth(expected_verdict="INSUFFICIENT_EVIDENCE"),
        facts(verdict="NOT_SUPPORTED", violated=["biot_number"]),
    )
    assert result.declared_catcher_status == "FIRED"
    assert result.verdict_match is False
    card = scoring.scorecard([result])
    assert card["exact_verdict_match"] == "0/1 (0.0%)"
    assert card["declared_catcher_rate"] == "1/1 (100.0%)"


def test_a_missing_expected_reason_is_unspecified_and_not_a_failure():
    """The benchmark never defined a machine-checkable reason; say so."""
    result = score(truth(), facts(violated=["biot_number"]))
    assert result.reason_match == "UNSPECIFIED"
    card = scoring.scorecard([result])
    assert card["reason_specified_cases"] == 0
    assert card["reason_accuracy"] == "0/0 (n/a)"
    assert "not machine-comparable" in card["reason_note"]


def test_an_alternate_catcher_counts_only_when_the_truth_declares_it():
    """ALTERNATE_VALID is read from truth, never inferred from a failure."""
    without = score(
        truth(), facts(violated=["geometry_route_ratio"])
    )
    assert without.catch_type == "COINCIDENTAL"

    with_declaration = score(
        truth(acceptable_catchers=["geometry_route_ratio"]),
        facts(violated=["geometry_route_ratio"]),
    )
    assert with_declaration.catch_type == "ALTERNATE_VALID"
    card = scoring.scorecard([with_declaration])
    assert card["alternate_valid_catches"] == 1
    assert card["coincidental_catches"] == 0


def test_no_case_in_the_corpus_declares_an_alternate_today():
    """So every ALTERNATE_VALID in a real run would be a truth revision."""
    import json

    for path in sorted((BENCH / "cases_hard").glob("*.json")):
        truth_fields = json.loads(path.read_text(encoding="utf-8"))["ground_truth"]
        assert "acceptable_catchers" not in truth_fields


# =====================================================================
# The other statuses
# =====================================================================

def test_an_undeclared_mechanism_is_reported_as_undeclared_not_as_a_coincidence():
    """122 unsound cases name no mechanism. Guessing about them is the sin."""
    result = score(
        truth(should_be_caught_by=""), facts(violated=["biot_number"])
    )
    assert result.declared_catcher_status == "NOT_DECLARED"
    assert result.catch_type == "UNDECLARED"
    card = scoring.scorecard([result])
    assert card["declared_catcher_cases"] == 0
    assert card["declared_catcher_not_declared"] == 1
    assert card["coincidental_catches"] == 0


def test_a_sound_case_asserts_its_near_miss_condition_is_SATISFIED():
    """A SUPPORTED case names the condition that must NOT refuse."""
    held = score(
        truth(label="valid", expected_verdict="SUPPORTED",
              should_be_caught_by="linearization_excursion_ratio"),
        facts(verdict="SUPPORTED", satisfied=["linearization_excursion_ratio"]),
    )
    assert held.declared_catcher_status == "HELD"
    assert held.catch_type == "NOT_APPLICABLE"
    assert held.false_reject is False


def test_a_screened_condition_counts_as_deciding_an_insufficient_evidence_case():
    """The screen adjudication moved verdicts and left the catcher alone."""
    result = score(
        truth(expected_verdict="INSUFFICIENT_EVIDENCE",
              should_be_caught_by="internal_fourier_number"),
        facts(verdict="INSUFFICIENT_EVIDENCE", unknown=["internal_fourier_number"]),
    )
    assert result.declared_catcher_status == "FIRED"
    assert result.verdict_match is True


def test_a_mechanism_catcher_reads_the_coupling_and_not_a_condition():
    fired = score(
        truth(should_be_caught_by="thermal runaway"),
        facts(refused=True),
    )
    assert fired.declared_catcher_status == "FIRED"
    not_fired = score(
        truth(should_be_caught_by="thermal runaway"),
        facts(violated=["biot_number"], refused=False),
    )
    assert not_fired.declared_catcher_status == "NOT_FIRED"


def test_a_false_accept_is_an_unsound_case_forge_called_supported():
    result = score(truth(), facts(verdict="SUPPORTED"))
    assert result.false_accept is True
    assert result.catch_type == "NONE"
    card = scoring.scorecard([result])
    assert card["false_accept"] == "1/1 (100.00%)"


# =====================================================================
# Phase Q -- mutation testing the METRICS
# =====================================================================
#
# One input changes at a time. The metric it is about must move; the others
# must not. This is what stops the scorecard from being a new way of saying
# one number.

BASELINE = [
    ("A", truth(), facts(violated=["biot_number"])),
    ("B", truth(should_be_caught_by="melting_temperature_utilization"),
     facts(violated=["melting_temperature_utilization"])),
    ("C", truth(label="valid", expected_verdict="SUPPORTED",
                should_be_caught_by="biot_number"),
     facts(verdict="SUPPORTED", satisfied=["biot_number"])),
]


def _card(cases):
    return scoring.scorecard([score(t, f, case_id=i) for i, t, f in cases])


def test_the_baseline_this_section_perturbs_is_perfect():
    card = _card(BASELINE)
    assert card["exact_verdict_match"] == "3/3 (100.0%)"
    assert card["declared_catcher_rate"] == "3/3 (100.0%)"
    assert card["coincidental_catches"] == 0
    assert card["false_accept"] == "0/2 (0.00%)"


def test_changing_only_the_actual_mechanism_moves_the_catcher_rate_alone():
    mutated = list(BASELINE)
    mutated[0] = ("A", truth(), facts(violated=["radiation_to_convection_ratio"]))
    card = _card(mutated)
    base = _card(BASELINE)
    assert card["declared_catcher_rate"] != base["declared_catcher_rate"]
    assert card["coincidental_catches"] == 1
    # ...and the verdict metrics do not move, because the verdict did not.
    assert card["exact_verdict_match"] == base["exact_verdict_match"]
    assert card["false_accept"] == base["false_accept"]
    assert card["false_reject"] == base["false_reject"]


def test_changing_only_the_declared_catcher_moves_the_catcher_rate_alone():
    mutated = list(BASELINE)
    mutated[0] = ("A", truth(should_be_caught_by="some_other_condition"),
                  facts(violated=["biot_number"]))
    card = _card(mutated)
    base = _card(BASELINE)
    assert card["declared_catcher_rate"] == "2/3 (66.7%)"
    assert card["exact_verdict_match"] == base["exact_verdict_match"]
    assert card["false_accept"] == base["false_accept"]


def test_changing_only_the_verdict_moves_the_verdict_metrics_alone():
    mutated = list(BASELINE)
    # The declared condition still fires; only the final verdict is wrong.
    mutated[0] = ("A", truth(expected_verdict="INSUFFICIENT_EVIDENCE"),
                  facts(verdict="NOT_SUPPORTED", violated=["biot_number"]))
    card = _card(mutated)
    base = _card(BASELINE)
    assert card["exact_verdict_match"] == "2/3 (66.7%)"
    assert card["declared_catcher_rate"] == base["declared_catcher_rate"]
    assert card["coincidental_catches"] == base["coincidental_catches"]


def test_adding_an_acceptable_catcher_moves_a_coincidence_to_an_alternate():
    coincidental = ("A", truth(), facts(violated=["geometry_route_ratio"]))
    alternate = ("A", truth(acceptable_catchers=["geometry_route_ratio"]),
                 facts(violated=["geometry_route_ratio"]))
    before = _card([coincidental] + BASELINE[1:])
    after = _card([alternate] + BASELINE[1:])
    assert before["coincidental_catches"] == 1
    assert after["coincidental_catches"] == 0
    assert after["alternate_valid_catches"] == 1
    # It is still a declared-catcher miss: the DECLARED mechanism did not fire.
    assert after["declared_catcher_rate"] == before["declared_catcher_rate"]
    assert after["exact_verdict_match"] == before["exact_verdict_match"]


def test_declaring_an_expected_unknown_reason_opens_the_reason_denominator():
    without = _card(BASELINE)
    assert without["reason_specified_cases"] == 0

    with_reason = list(BASELINE)
    with_reason[0] = (
        "A",
        truth(expected_verdict="INSUFFICIENT_EVIDENCE",
              expected_unknown_reason="internal_fourier_number"),
        facts(verdict="INSUFFICIENT_EVIDENCE",
              unknown=["internal_fourier_number"]),
    )
    card = _card(with_reason)
    assert card["reason_specified_cases"] == 1
    assert card["reason_accuracy"] == "1/1 (100.0%)"


def test_every_rate_states_its_own_denominator():
    """No figure here may be a fraction of a population it is not about."""
    card = _card(BASELINE)
    for key in (
        "exact_verdict_match", "catch_rate", "false_accept", "false_reject",
        "declared_catcher_rate", "reason_accuracy",
    ):
        assert "/" in card[key], f"{key} does not carry a denominator"


def test_per_family_keeps_the_same_three_questions_apart():
    families = scoring.per_family(
        [score(t, f, case_id=i) for i, t, f in BASELINE]
    )
    assert set(families) == {"biot_out"}
    row = families["biot_out"]
    assert row["total"] == 3
    assert row["verdict_match"] == 3
    assert row["declared_catcher_fired"] == 3
    assert row["coincidental"] == 0
