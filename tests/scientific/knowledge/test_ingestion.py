import hashlib
import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.knowledge import (
    KnowledgeIngestionReceipt, KnowledgeSnapshot, verify_ingestion_receipt,
)
from tests.scientific.knowledge.helpers import claim, source


def test_ingestion_receipt_binds_source_payload_parser_and_exact_claim_set():
    raw=b"pinned scientific source bytes"
    digest=hashlib.sha256(raw).hexdigest()
    src=source(digest=digest)
    clm=claim(source_digest=digest)
    snap=KnowledgeSnapshot("s",(src,),(clm,))
    receipt=KnowledgeIngestionReceipt.from_payload(
        src,raw,"parser.reference","1",(clm.digest,)
    )
    verify_ingestion_receipt(snap,receipt)


def test_ingestion_receipt_refuses_missing_or_extra_claim_digest():
    raw=b"pinned scientific source bytes"
    digest=hashlib.sha256(raw).hexdigest()
    src=source(digest=digest)
    clm=claim(source_digest=digest)
    snap=KnowledgeSnapshot("s",(src,),(clm,))
    receipt=KnowledgeIngestionReceipt.from_payload(
        src,raw,"parser.reference","1",()
    )
    with pytest.raises(InvalidScientificProblem,match="exactly"):
        verify_ingestion_receipt(snap,receipt)
