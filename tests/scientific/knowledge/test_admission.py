from datetime import datetime, timezone
import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.knowledge import (
    KnowledgeAdmissionStatus, SourcePin, TrustedSourceRegistry, admit_claim,
)
from tests.scientific.knowledge.helpers import CONTEXT, freshness, registry, snapshot, source


def test_admission_requires_trust_freshness_and_exact_context():
    snap=snapshot()
    result=admit_claim(
        snap,"claim-1",registry(),freshness(),
        now=datetime(2026,9,19,tzinfo=timezone.utc),
        target_context_digest=CONTEXT,
    )
    assert result.status is KnowledgeAdmissionStatus.ADMISSIBLE


def test_changed_context_is_refused_even_for_pinned_current_source():
    result=admit_claim(
        snapshot(),"claim-1",registry(),freshness(),
        now=datetime(2026,9,19,tzinfo=timezone.utc),
        target_context_digest="d"*64,
    )
    assert result.status is KnowledgeAdmissionStatus.CONTEXT_MISMATCH


def test_untrusted_or_stale_source_is_never_admissible():
    snap=snapshot()
    no_pins=TrustedSourceRegistry(())
    assert admit_claim(
        snap,"claim-1",no_pins,freshness(),
        now=datetime(2026,9,19,tzinfo=timezone.utc),
        target_context_digest=CONTEXT,
    ).status is KnowledgeAdmissionStatus.UNTRUSTED_SOURCE
    assert admit_claim(
        snap,"claim-1",registry(),freshness(limit=1),
        now=datetime(2026,9,19,tzinfo=timezone.utc),
        target_context_digest=CONTEXT,
    ).status is KnowledgeAdmissionStatus.STALE_SOURCE


def test_missing_claim_and_non_digest_target_context_fail_closed():
    with pytest.raises(InvalidScientificProblem,match="no claim"):
        admit_claim(
            snapshot(),"missing",registry(),freshness(),
            now=datetime(2026,9,19,tzinfo=timezone.utc),
            target_context_digest=CONTEXT,
        )
    with pytest.raises(InvalidScientificProblem,match="context"):
        admit_claim(
            snapshot(),"claim-1",registry(),freshness(),
            now=datetime(2026,9,19,tzinfo=timezone.utc),
            target_context_digest="not-a-digest",
        )
