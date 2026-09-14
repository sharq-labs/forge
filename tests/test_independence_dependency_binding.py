"""Identity bindings are part of artifact-evidence identity, not display metadata."""

from engcore.scientific.independence_evidence import ArtifactFingerprint


def test_same_bytes_bound_to_two_dependencies_remain_two_evidence_records():
    payload = b"one binary can implement more than one declared dependency"
    first = ArtifactFingerprint.from_bytes(
        "binary-as-implementation",
        payload,
        dependency_identity="ext:route:implementation",
    )
    second = ArtifactFingerprint.from_bytes(
        "binary-as-backend",
        payload,
        dependency_identity="ext:route:backend",
    )

    assert first.digest == second.digest
    assert first.dependency_identity != second.dependency_identity
    assert len(frozenset({first, second})) == 2


def test_existing_positional_fingerprint_constructor_keeps_its_name_slot():
    fingerprint = ArtifactFingerprint("0" * 64, "legacy-name", kind="source")

    assert fingerprint.name == "legacy-name"
    assert fingerprint.kind == "source"
    assert fingerprint.dependency_identity == ""
