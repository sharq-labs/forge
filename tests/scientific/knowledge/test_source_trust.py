from engcore.scientific.knowledge import SourceStanding
from tests.scientific.knowledge.helpers import registry, source


def test_exact_source_pin_is_trusted_and_registry_identity_is_stable():
    src=source()
    reg=registry(src)
    assert reg.assess(src).standing is SourceStanding.PINNED
    assert reg.pin_for(src.source_id) is not None
    assert len(reg.digest)==64


def test_same_source_id_with_changed_document_digest_is_not_trusted():
    reg=registry(source())
    changed=source(digest="b"*64)
    assert reg.assess(changed).standing is SourceStanding.DIGEST_MISMATCH


def test_same_source_id_with_changed_version_is_not_trusted():
    reg=registry(source())
    changed=source(version="2027.1")
    assert reg.assess(changed).standing is SourceStanding.VERSION_MISMATCH
