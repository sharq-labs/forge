from datetime import datetime, timezone
import pytest

from engcore.scientific.knowledge import KnowledgeFreshness
from tests.scientific.knowledge.helpers import freshness, source


def test_freshness_is_derived_from_published_time_and_policy():
    policy=freshness(limit=365)
    now=datetime(2026,9,19,tzinfo=timezone.utc)
    assert policy.assess(source(published="2026-01-01T00:00:00+00:00"),now=now) is KnowledgeFreshness.CURRENT
    assert policy.assess(source(published="2020-01-01T00:00:00+00:00"),now=now) is KnowledgeFreshness.STALE
    assert policy.digest==policy.digest


def test_future_or_missing_publication_time_is_not_current():
    policy=freshness(limit=365)
    now=datetime(2026,9,19,tzinfo=timezone.utc)
    assert policy.assess(source(published="2027-01-01T00:00:00+00:00"),now=now) is KnowledgeFreshness.UNKNOWN
    assert policy.assess(source(published=""),now=now) is KnowledgeFreshness.UNKNOWN


def test_naive_assessment_time_is_refused_for_reproducibility():
    with pytest.raises(ValueError,match="timezone-aware"):
        freshness().assess(source(),now=datetime(2026,9,19))
