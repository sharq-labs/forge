"""Does the checked-out Core match the Core that was certified?

Sprint 6, Phases 10, 13 and 14. This is the test whose absence let V1 go two
sprints out of date without anything noticing. V1's digest algorithm was never
lost — it is written out inside the certificate and reproduces its stored value
exactly at the commit it names — but nothing ever ran it.

Two halves.

`test_the_certificate_describes_this_tree` is the one that matters in daily
use: it reads `certification/current_core_v2.json` and compares the working
tree against it. Everything else here exists to prove that test can fail.

The drift and fault cases run against a **synthetic repository** built in a
temporary directory, not against the checkout. Adding and deleting certified
source files to see what happens is exactly the sort of thing a test should not
do to the tree it is running in.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from tools.certification.core_certificate import (
    CERTIFICATE_SCHEMA,
    CertificationError,
    ScopeArea,
    aggregate_digest,
    area_digest,
    build_certificate,
    build_manifest,
    enumerate_area,
    file_digest,
    load_certificate,
    repo_root,
    repository_identity,
    v1_compatible_core_digest,
    verify_certificate,
    write_certificate,
)

try:
    ROOT = repo_root(pathlib.Path(__file__))
except CertificationError:  # pragma: no cover - a tree without .git
    # The mutation harness copies `tests/` into a scratch directory that is not
    # a repository. This module is not among the suites it runs there, but a
    # module-level raise would be a collection error for anything that did
    # collect the directory, so it skips instead.
    pytest.skip("not inside a repository checkout", allow_module_level=True)

CERTIFICATE_PATH = ROOT / "certification" / "current_core_v2.json"
V1_PATH = ROOT / "certification" / "current_core_v1.json"


# ---- the test the absence of which let V1 go stale --------------------------------
@pytest.mark.skipif(
    not CERTIFICATE_PATH.exists(), reason="no V2 certificate has been built yet"
)
def test_the_certificate_describes_this_tree():
    """The whole point. If this is red, the certificate does not describe HEAD.

    It is deliberately not skipped when it fails and not softened into a
    warning: a certificate nobody checks is the thing this sprint exists to
    stop shipping.
    """
    result = verify_certificate(
        ROOT, load_certificate(CERTIFICATE_PATH), require_commit=False
    )
    assert result.ok, "\n" + result.render()


@pytest.mark.skipif(not CERTIFICATE_PATH.exists(), reason="no V2 certificate yet")
def test_the_certificate_records_what_it_covers_and_what_it_does_not():
    certificate = load_certificate(CERTIFICATE_PATH)
    assert certificate["schema"] == CERTIFICATE_SCHEMA
    assert certificate["scope"]["in"] and certificate["scope"]["out"]
    for area in certificate["scope"]["in"]:
        assert area["why"].strip(), f"{area['area']} gives no reason for inclusion"
        assert area["classification"] in {
            "CORE_CERTIFIED", "RUNTIME_SUPPORT", "HARNESS", "DOMAIN_ASSURANCE"
        }
    assert not certificate["diagnostic"], "a diagnostic certificate certifies nothing"


@pytest.mark.skipif(not CERTIFICATE_PATH.exists(), reason="no V2 certificate yet")
def test_every_certified_file_is_listed_with_its_own_digest():
    """A manifest, not one opaque number — that is what makes drift diagnosable."""
    manifest = load_certificate(CERTIFICATE_PATH)["manifest"]
    total = 0
    for name, area in manifest["areas"].items():
        assert area["files"], f"area {name} lists no files"
        assert area["file_count"] == len(area["files"])
        for relative, digest in area["files"].items():
            assert len(digest) == 64, f"{relative} has no sha256"
        assert area["digest"] == area_digest(area["files"])
        total += area["file_count"]
    assert manifest["file_count"] == total
    assert manifest["aggregate_digest"] == aggregate_digest(
        {n: a["digest"] for n, a in manifest["areas"].items()}
    )


# ---- V1 continuity -------------------------------------------------------------------
def test_the_v1_recipe_is_still_in_the_v1_certificate():
    """V1's algorithm is recoverable because V1 wrote it down. Keep it that way."""
    v1 = load_certificate(V1_PATH)
    recipe = "\n".join(v1["verification"]["how_to_reproduce_the_certified_tree"])
    for fragment in ("hashlib", "rglob('*.py')", "__pycache__", "sha256"):
        assert fragment in recipe, f"the V1 recipe no longer mentions {fragment}"
    assert v1["core"]["tree_sha256"] == v1["verification"]["expected_core_tree_sha256"]


def test_the_v1_compatible_digest_is_deterministic():
    assert v1_compatible_core_digest(ROOT) == v1_compatible_core_digest(ROOT)
    assert len(v1_compatible_core_digest(ROOT)) == 64


@pytest.mark.skipif(not CERTIFICATE_PATH.exists(), reason="no V2 certificate yet")
def test_the_certificate_records_the_v1_relationship_truthfully():
    continuity = load_certificate(CERTIFICATE_PATH)["v1_continuity"]
    assert continuity["v1_algorithm_recovered"] is True
    assert continuity["v1_compatible_core_digest_now"] == v1_compatible_core_digest(ROOT)
    # The core moved since V1, and the certificate must not pretend otherwise.
    assert (
        continuity["v1_compatible_core_digest_now"]
        != continuity["v1_core_digest_at_its_own_commit"]
    )


# ---- the algorithm -------------------------------------------------------------------
def test_the_digest_is_deterministic_and_sensitive(tmp_path):
    one = tmp_path / "a.py"
    one.write_bytes(b"x = 1\n")
    first = file_digest(one)
    assert first == file_digest(one)

    one.write_bytes(b"x = 2\n")
    assert file_digest(one) != first


def test_line_endings_are_not_normalized(tmp_path):
    """A CRLF copy is a different file, and several trees here are byte-pinned."""
    lf, crlf = tmp_path / "lf.py", tmp_path / "crlf.py"
    lf.write_bytes(b"x = 1\ny = 2\n")
    crlf.write_bytes(b"x = 1\r\ny = 2\r\n")
    assert file_digest(lf) != file_digest(crlf)


def test_ordering_does_not_depend_on_discovery_order(tmp_path):
    entries = {"b.py": "aa" * 32, "a.py": "bb" * 32, "c.py": "cc" * 32}
    shuffled = {k: entries[k] for k in ("c.py", "a.py", "b.py")}
    assert area_digest(entries) == area_digest(shuffled)


def test_a_symlink_in_scope_is_refused(tmp_path):
    (tmp_path / "src" / "engcore" / "scientific").mkdir(parents=True)
    real = tmp_path / "src" / "engcore" / "scientific" / "real.py"
    real.write_bytes(b"x = 1\n")
    link = tmp_path / "src" / "engcore" / "scientific" / "link.py"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not creatable in this environment")
    area = ScopeArea("core", "CORE_CERTIFIED", ("src/engcore/scientific/**/*.py",), "")
    with pytest.raises(CertificationError, match="symlink"):
        enumerate_area(tmp_path, area)


def test_pycache_is_excluded(tmp_path):
    base = tmp_path / "src" / "engcore" / "scientific"
    (base / "__pycache__").mkdir(parents=True)
    (base / "real.py").write_bytes(b"x = 1\n")
    (base / "__pycache__" / "real.py").write_bytes(b"junk\n")
    (base / "real.pyc").write_bytes(b"junk\n")
    area = ScopeArea("core", "CORE_CERTIFIED", ("src/engcore/scientific/**/*.py",), "")
    assert enumerate_area(tmp_path, area) == ["src/engcore/scientific/real.py"]


def test_an_area_matching_nothing_is_refused(tmp_path):
    """A scope hole is worse than a wrong digest: it certifies silence."""
    (tmp_path / "src").mkdir()
    empty = ScopeArea("core", "CORE_CERTIFIED", ("src/nothing/**/*.py",), "")
    with pytest.raises(CertificationError, match="matched no files"):
        build_manifest(tmp_path, scope=(empty,))


# ---- a synthetic repository, for the drift and fault cases ---------------------------
SYNTHETIC_SCOPE = (
    ScopeArea("core", "CORE_CERTIFIED", ("src/engcore/scientific/**/*.py",), "core"),
    ScopeArea("harness", "HARNESS", ("tests/mutation_guards.py",), "harness"),
)


def _git(root: pathlib.Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=root, check=True, capture_output=True, text=True,
    )


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    """A tiny committed repository with the same shape as the real scope."""
    root = tmp_path / "repo"
    (root / "src" / "engcore" / "scientific").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "pyproject.toml").write_bytes(b"[project]\nname='synthetic'\n")
    (root / "src" / "engcore" / "scientific" / "__init__.py").write_bytes(b"")
    (root / "src" / "engcore" / "scientific" / "record.py").write_bytes(b"VALUE = 1\n")
    (root / "src" / "engcore" / "scientific" / "units.py").write_bytes(b"UNIT = 'm'\n")
    (root / "tests" / "mutation_guards.py").write_bytes(b"MUTATIONS = ()\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "synthetic")

    monkeypatch.setattr(
        "tools.certification.core_certificate.SCOPE", SYNTHETIC_SCOPE
    )
    certificate = build_certificate(root, certification_id="SYNTHETIC")
    return root, certificate


def _verify(root, certificate):
    return verify_certificate(root, certificate, require_commit=True)


def test_building_twice_from_one_tree_produces_identical_bytes(synthetic, tmp_path):
    """A certificate carries no timestamp, so a rebuild is a comparison.

    V1 recorded when it was written, with a note that the timestamp was not
    identity. True, and it also meant two engineers certifying the same commit
    produced two different files and had to take on trust that the difference
    was only the clock. Leaving it out makes that checkable: on one machine,
    the same commit gives the same bytes.
    """
    root, _ = synthetic
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    write_certificate(first, build_certificate(root, certification_id="SYNTHETIC"))
    write_certificate(second, build_certificate(root, certification_id="SYNTHETIC"))
    assert first.read_bytes() == second.read_bytes()
    assert b"generated" not in first.read_bytes()


def test_a_synthetic_tree_verifies_against_its_own_certificate(synthetic):
    root, certificate = synthetic
    result = _verify(root, certificate)
    assert result.ok, "\n" + result.render()
    assert "matches the tree" in result.render()


# ---- CERT-1 .. CERT-8 ------------------------------------------------------------------
def test_cert_1_a_modified_certified_byte_is_caught_and_named(synthetic):
    root, certificate = synthetic
    (root / "src" / "engcore" / "scientific" / "record.py").write_bytes(b"VALUE = 2\n")
    result = _verify(root, certificate)
    assert not result.ok
    assert "MODIFIED: src/engcore/scientific/record.py" in result.render()
    assert result.expected_aggregate != result.actual_aggregate


def test_cert_2_an_added_certified_module_is_caught_and_named(synthetic):
    root, certificate = synthetic
    (root / "src" / "engcore" / "scientific" / "extra.py").write_bytes(b"NEW = 1\n")
    result = _verify(root, certificate)
    assert not result.ok
    assert "ADDED: src/engcore/scientific/extra.py" in result.render()


def test_cert_3_a_removed_certified_file_is_caught_and_named(synthetic):
    root, certificate = synthetic
    (root / "src" / "engcore" / "scientific" / "units.py").unlink()
    result = _verify(root, certificate)
    assert not result.ok
    assert "REMOVED: src/engcore/scientific/units.py" in result.render()


def test_cert_4_an_altered_per_file_digest_is_caught(synthetic):
    """Tampering with the record rather than the tree fails the same way."""
    root, certificate = synthetic
    tampered = json.loads(json.dumps(certificate))
    files = tampered["manifest"]["areas"]["core"]["files"]
    files["src/engcore/scientific/record.py"] = "0" * 64
    result = _verify(root, tampered)
    assert not result.ok
    assert "MODIFIED: src/engcore/scientific/record.py" in result.render()


def test_cert_5_an_altered_aggregate_digest_is_caught(synthetic):
    root, certificate = synthetic
    tampered = json.loads(json.dumps(certificate))
    tampered["manifest"]["aggregate_digest"] = "f" * 64
    result = _verify(root, tampered)
    assert not result.ok
    assert result.expected_aggregate == "f" * 64
    assert result.actual_aggregate != result.expected_aggregate


def test_cert_6_changed_harness_bytes_are_caught(synthetic):
    """'79/79 killed' is a claim about these exact bytes."""
    root, certificate = synthetic
    (root / "tests" / "mutation_guards.py").write_bytes(b"MUTATIONS = ()  # weakened\n")
    result = _verify(root, certificate)
    assert not result.ok
    assert "MODIFIED: tests/mutation_guards.py" in result.render()
    assert "AREA harness" in result.render()


def test_cert_7_a_certificate_naming_another_commit_is_caught(synthetic):
    root, certificate = synthetic
    tampered = json.loads(json.dumps(certificate))
    tampered["repository"]["commit"] = "0" * 40
    result = _verify(root, tampered)
    assert not result.ok
    assert any("names commit" in problem for problem in result.problems)


def test_cert_8_a_dirty_tree_is_refused_where_policy_forbids_it(synthetic):
    root, certificate = synthetic
    (root / "src" / "engcore" / "scientific" / "record.py").write_bytes(b"VALUE = 1\n\n")
    result = verify_certificate(root, certificate, require_clean=True)
    assert not result.ok
    assert any("uncommitted" in problem for problem in result.problems)


def test_building_from_a_dirty_tree_is_refused(synthetic):
    root, _ = synthetic
    (root / "src" / "engcore" / "scientific" / "record.py").write_bytes(b"VALUE = 9\n")
    with pytest.raises(CertificationError, match="refusing to certify a dirty tree"):
        build_certificate(root, certification_id="SYNTHETIC")

    diagnostic = build_certificate(
        root, allow_dirty=True, certification_id="SYNTHETIC"
    )
    assert diagnostic["diagnostic"] is True
    result = verify_certificate(root, diagnostic, require_clean=False)
    assert not result.ok, "a diagnostic certificate must never verify as a certificate"
    assert any("diagnostic" in problem for problem in result.problems)


def test_restoring_the_tree_makes_verification_green_again(synthetic):
    root, certificate = synthetic
    target = root / "src" / "engcore" / "scientific" / "record.py"
    original = target.read_bytes()
    target.write_bytes(b"VALUE = 3\n")
    assert not _verify(root, certificate).ok
    target.write_bytes(original)
    assert _verify(root, certificate).ok


# ---- Phase 14: no self-certification loophole -------------------------------------------
def test_verification_compares_against_the_stored_certificate_not_the_tree(synthetic):
    """A verifier that rebuilt its expectations would pass for any tree at all.

    Asserted twice: structurally, that the verifier's source never calls the
    builder; and behaviourally, that a certificate from one tree fails against
    a different tree.
    """
    import inspect

    from tools.certification import core_certificate

    source = inspect.getsource(core_certificate.verify_certificate)
    for forbidden in ("build_certificate(", "build_manifest("):
        assert forbidden not in source, (
            f"verify_certificate calls {forbidden} — verification would be "
            f"comparing the tree to itself"
        )

    root, certificate = synthetic
    (root / "src" / "engcore" / "scientific" / "record.py").write_bytes(b"VALUE = 7\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "moved on")
    # The tree is clean and committed; the certificate is simply of another tree.
    result = verify_certificate(root, certificate, require_commit=False)
    assert not result.ok, "a certificate of another tree must not verify"
    assert "MODIFIED: src/engcore/scientific/record.py" in result.render()


def test_a_certificate_of_an_unknown_schema_is_refused(synthetic):
    root, certificate = synthetic
    tampered = json.loads(json.dumps(certificate))
    tampered["schema"] = "core_certificate/99"
    result = verify_certificate(root, tampered)
    assert not result.ok
    assert any("schema" in problem for problem in result.problems)


def test_a_certificate_that_disagrees_with_itself_is_caught(synthetic):
    root, certificate = synthetic
    tampered = json.loads(json.dumps(certificate))
    tampered["manifest"]["areas"]["core"]["file_count"] = 99
    result = _verify(root, tampered)
    assert not result.ok
    assert any("disagrees with itself" in problem for problem in result.problems)


def test_dirty_paths_are_reported_with_their_first_character(synthetic):
    """A regression guard for a one-character bug in a diagnostic.

    `git status --porcelain` puts the index and worktree states in the first
    two columns and one of them is usually a space, so stripping the output
    removes it from the first line only — and every path parsed from that line
    then loses its first character. The first draft of this tool reported an
    uncommitted `tools/...` as `ools/...`, which is precisely the kind of
    quietly wrong diagnostic the sprint exists to remove.
    """
    from tools.certification.core_certificate import _porcelain_paths

    root, _ = synthetic
    target = root / "src" / "engcore" / "scientific" / "record.py"
    target.write_bytes(b"VALUE = 4\n")
    identity = repository_identity(root)
    assert identity["dirty_paths"] == ["src/engcore/scientific/record.py"]

    # And directly, over each status shape, including a staged one whose first
    # column is not a space.
    assert _porcelain_paths(" M tools/a.py\n") == ["tools/a.py"]
    assert _porcelain_paths("M  tools/a.py\n") == ["tools/a.py"]
    assert _porcelain_paths("?? tools/a.py\n") == ["tools/a.py"]
    assert _porcelain_paths("R  old.py -> tools/a.py\n") == ["tools/a.py"]


def test_a_certificate_round_trips_through_disk(synthetic, tmp_path):
    root, certificate = synthetic
    path = tmp_path / "cert.json"
    write_certificate(path, certificate)
    assert load_certificate(path) == certificate
    assert path.read_bytes().endswith(b"\n")
    assert b"\r\n" not in path.read_bytes(), "certificates are written with LF"
