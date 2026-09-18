"""Sprint 2 probes for the first repository-reviewed external oracle."""

from engcore.domains.thermal_models.nafems_t3_oracle import (
    EVIDENCE_DIGEST,
    nafems_t3_evidence,
)


def test_nafems_t3_digest_probe() -> None:
    evidence = nafems_t3_evidence()
    assert evidence.content_digest == EVIDENCE_DIGEST, (
        f"canonical digest is {evidence.content_digest}"
    )
