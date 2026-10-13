"""A report cannot hide an undecided challenge behind one surviving route."""

from itertools import permutations

import pytest

from engcore.claims.analysis.challenge import Challenge, ChallengeKind, ChallengeReport, ChallengeResult


def _challenge(result):
    return Challenge(ChallengeKind.ALTERNATIVE_MODEL, "synthetic", result is not ChallengeResult.NOT_ATTEMPTED,
                     result, result is ChallengeResult.WEAKENED, (), "summary fixture, not evidence")


@pytest.mark.parametrize("results, expected", [
    ((), "not_challenged"),
    ((ChallengeResult.NOT_ATTEMPTED,), "not_challenged"),
    ((ChallengeResult.SURVIVED,), "survived_attempted_challenges"),
    ((ChallengeResult.SURVIVED, ChallengeResult.NOT_ATTEMPTED), "survived_attempted_challenges"),
    ((ChallengeResult.INCONCLUSIVE,), "inconclusive_attempted_challenges"),
    ((ChallengeResult.SURVIVED, ChallengeResult.INCONCLUSIVE), "inconclusive_attempted_challenges"),
    ((ChallengeResult.WEAKENED, ChallengeResult.INCONCLUSIVE), "weakened"),
])
def test_summary_preserves_inconclusive_and_weakened_results_independent_of_order(results, expected):
    for order in permutations(results):
        report = ChallengeReport("claim", "supported", tuple(map(_challenge, order)))
        assert report.status == expected
        assert report.to_dict()["status"] == expected
        assert report.nominal_verdict == "supported"


def test_removing_a_surviving_route_cannot_hide_remaining_inconclusive_routes():
    both = ChallengeReport("claim", "supported", (_challenge(ChallengeResult.SURVIVED), _challenge(ChallengeResult.INCONCLUSIVE)))
    remaining = ChallengeReport("claim", "supported", both.challenges[1:])
    assert both.status == remaining.status == "inconclusive_attempted_challenges"
    assert both.digest != remaining.digest
