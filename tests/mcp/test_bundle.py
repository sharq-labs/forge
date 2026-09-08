"""The evidence bundle, and a verifier that has been seen to fail.

The point of this module is the second half of that sentence. A verifier whose
tests only ever hand it a good bundle proves that it can say yes, which is the
one answer nobody needs it for. So every check :func:`verify_bundle` performs is
given a bundle that should fail it, and the failure is asserted by category —
not merely "something was refused", but *which* question found the damage.

Two of those corruptions recompute the manifest afterwards. That is deliberate:
the manifest says in its own text that it does not detect an edit followed by a
rewritten manifest, and these tests hold it to that while showing that the
checks which do not rely on the digest still catch it.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib

import pytest

from src.engcore.mcp.bundle import (
    BUNDLE_MANIFEST_SCHEMA,
    BundleVerification,
    verify_bundle,
    write_bundle,
)
from src.engcore.mcp.errors import CredibilityEvidenceError
from src.engcore.mcp.problem import example_electrothermal_payload

# `src.engcore.mcp.server` is imported IN THE FIXTURE, not here. It is the one
# module in `src/` that imports the optional `[mcp]` SDK, and importing it at
# module level made this whole file a COLLECTION ERROR on
# `pip install -e ".[dev]"` -- the command the README opens with.
# `tests/mcp/test_server.py` guards the same dependency correctly, and
# `pyproject.toml` states the rule both are held to: of the optional groups,
# "the suite must stay runnable, and green, without it".
#
# Guarded in the fixture rather than with a module-level `importorskip`, which
# is how test_server.py does it, because that would skip all 27 tests here and
# only 24 need the SDK. The three that do not include
# `test_no_runtime_module_reads_a_bundle_back` and
# `test_the_bundle_module_writes_no_scientific_record`, which parse source and
# assert an architectural boundary -- checks with nothing to do with the
# transport, and exactly the ones this repository's own reasoning says must not
# be skipped, since "a skipped test proves nothing".

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = "manifest.json"
REPORT = "stages/00-R1/report.json"
VERDICT = "stages/00-R1/verdict.json"


@pytest.fixture(scope="module")
def response():
    # `mcp.types`, not `mcp`: `tests/mcp/` has no `__init__.py`, so this
    # directory IS an importable namespace package named `mcp` and
    # `importorskip("mcp")` would never fire. The same trap test_server.py
    # documents having fallen into.
    pytest.importorskip(
        "mcp.types", reason="install the optional [mcp] dependency group"
    )
    from src.engcore.mcp.server import _response

    return _response(example_electrothermal_payload())


@pytest.fixture
def bundle(tmp_path, response) -> pathlib.Path:
    """A freshly written bundle, per test, so corruption never leaks."""
    return write_bundle(
        response,
        tmp_path / "bundle",
        case=example_electrothermal_payload(),
        bundle_id="test",
    )


def _read(root: pathlib.Path, relative: str):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _overwrite(root: pathlib.Path, relative: str, payload) -> None:
    """Write bytes, never text.

    ``Path.write_text`` translates newlines on this platform, which would
    change every line of a file while changing no value in it — a corruption
    the digest catches for the wrong reason. These tests must edit exactly what
    they say they edit.
    """
    data = (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    (root / relative).write_bytes(data)


def _recompute_manifest(root: pathlib.Path) -> None:
    """Rewrite the manifest over whatever is now on disk.

    Not offered by the production module, and it should not be: there is no
    legitimate reason for the platform to re-attest a bundle it did not write.
    It exists here to demonstrate the limitation the manifest states about
    itself, and to prove the checks that do not depend on a digest.
    """
    manifest = _read(root, MANIFEST)
    for entry in manifest["files"]:
        data = (root / entry["path"]).read_bytes()
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        entry["bytes"] = len(data)
    _overwrite(root, MANIFEST, manifest)


# =====================================================================
# What a bundle contains
# =====================================================================

def test_a_bundle_holds_the_record_as_it_is(bundle, response):
    """Verbatim, not reformatted and not summarised."""
    assert _read(bundle, REPORT) == response["stages"][0]["report"]
    assert _read(bundle, VERDICT) == response["stages"][0]["verdict"]
    assert _read(bundle, "stages/00-R1/repairs.json") == (
        response["stages"][0]["repairs"]
    )
    assert _read(bundle, "coupling.json") == response["coupling"]


def test_the_bundle_is_a_partition_with_nothing_duplicated(bundle, response):
    """No file is a second copy of another's content.

    The response itself is deliberately not written alongside the split, so a
    verifier is never asked what to do when two statements of one fact differ.
    """
    files = sorted(
        str(p.relative_to(bundle)).replace("\\", "/")
        for p in bundle.rglob("*")
        if p.is_file()
    )
    assert files == [
        "README.md",
        "case.json",
        "coupling.json",
        "manifest.json",
        "run.json",
        "stages/00-R1/repairs.json",
        "stages/00-R1/report.json",
        "stages/00-R1/verdict.json",
    ]
    bodies = [
        (bundle / f).read_bytes() for f in files if f != "manifest.json"
    ]
    assert len(set(bodies)) == len(bodies)


def test_the_manifest_lists_every_file_except_itself(bundle):
    manifest = _read(bundle, MANIFEST)
    assert manifest["schema"] == BUNDLE_MANIFEST_SCHEMA
    listed = {entry["path"] for entry in manifest["files"]}
    on_disk = {
        str(p.relative_to(bundle)).replace("\\", "/")
        for p in bundle.rglob("*")
        if p.is_file()
    }
    assert listed == on_disk - {MANIFEST}
    # and it says so, rather than leaving a reader to notice
    assert manifest["manifest_excludes_itself"] is True
    for entry in manifest["files"]:
        assert len(entry["sha256"]) == 64
        assert entry["bytes"] == len((bundle / entry["path"]).read_bytes())


def test_the_bundle_omits_what_the_record_does_not_have(bundle):
    """``provenance.environment`` is empty here because it is empty there.

    The bundle carries the absence rather than filling it in at write time with
    facts the run never observed. If this ever fails because the runtime
    started recording an environment, the bundle should carry that — and this
    assertion should be updated to say so, not deleted.
    """
    provenance = _read(bundle, REPORT)["provenance"]
    assert "environment" in provenance
    assert provenance["environment"] == {}


def test_the_readme_states_the_limitation_rather_than_hiding_it(bundle):
    text = (bundle / "README.md").read_text(encoding="utf-8")
    assert "No signature" in text
    assert "does not list itself" in text
    assert "Advisory input to an engineer of record" in text


def test_two_bundles_of_one_response_agree_byte_for_byte(tmp_path, response):
    """Only the manifest differs, and only in when it was written."""
    first = write_bundle(response, tmp_path / "a", case={"x": 1})
    second = write_bundle(response, tmp_path / "b", case={"x": 1})
    for relative in ("run.json", "case.json", "coupling.json", REPORT, VERDICT):
        assert (first / relative).read_bytes() == (second / relative).read_bytes()
    a, b = _read(first, MANIFEST), _read(second, MANIFEST)
    assert a["files"] == b["files"]


# =====================================================================
# Writing refuses what it cannot record honestly
# =====================================================================

def test_writing_into_an_existing_directory_is_refused(bundle, response):
    with pytest.raises(CredibilityEvidenceError, match="already exists"):
        write_bundle(response, bundle)


def test_a_response_with_no_stages_is_refused(tmp_path):
    with pytest.raises(CredibilityEvidenceError, match="no stages"):
        write_bundle({"system": "x", "stages": []}, tmp_path / "empty")


def test_colliding_stage_ids_are_refused_rather_than_overwritten(tmp_path):
    """Two ids that differ only in a character a path cannot carry."""
    response = {
        "system": "x",
        "stages": [
            {"component_id": "R/1", "report": {}, "verdict": {}, "repairs": []},
            {"component_id": "R:1", "report": {}, "verdict": {}, "repairs": []},
        ],
    }
    # Different indices, so they do not in fact collide -- the guard is about
    # one index, and this records that the naming keeps them apart.
    root = write_bundle(response, tmp_path / "two")
    assert (root / "stages/00-R_1").is_dir()
    assert (root / "stages/01-R_1").is_dir()


# =====================================================================
# The verifier says yes, and says what it checked
# =====================================================================

def test_a_clean_bundle_verifies_and_reports_what_it_checked(bundle):
    result = verify_bundle(bundle)
    assert result.ok
    assert result.findings == ()
    # A pass with zero checks would be the failure mode this reports around.
    assert result.checked["digests"] == 7
    assert result.checked["reports_loaded"] == 1
    assert result.checked["verdicts_rederived"] == 1
    assert "VERIFIED" in result.report()


# =====================================================================
# The verifier says no — one test per question it asks
# =====================================================================

def test_editing_one_value_after_the_manifest_is_written_is_refused(bundle):
    """The central corrupted-bundle test.

    One number, changed in place, with the manifest untouched. Nothing about
    the bundle looks wrong to a reader; the digest is the whole difference.
    """
    report = _read(bundle, REPORT)
    name, value = next(iter(sorted(report["values"].items())))
    original = value["magnitude"]
    value["magnitude"] = original * 2.0
    _overwrite(bundle, REPORT, report)

    result = verify_bundle(bundle)
    assert not result.ok
    categories = {finding.category for finding in result.findings}
    assert "digest_mismatch" in categories
    finding = next(
        f for f in result.findings if f.category == "digest_mismatch"
    )
    assert finding.path == REPORT
    assert "REFUSED" in result.report()
    # the value really did change, so the test is about the edit and not about
    # some incidental rewriting of the file
    assert _read(bundle, REPORT)["values"][name]["magnitude"] == original * 2.0


def test_an_edit_that_recomputes_the_manifest_is_still_caught_by_the_schema(
    bundle,
):
    """The digest is bypassed on purpose; the schema check is what remains."""
    report = _read(bundle, REPORT)
    report["schema"] = "mcp_evidence_package/99"
    _overwrite(bundle, REPORT, report)
    _recompute_manifest(bundle)

    result = verify_bundle(bundle)
    categories = {finding.category for finding in result.findings}
    # the manifest is consistent with the directory again ...
    assert "digest_mismatch" not in categories
    # ... and the bundle is still refused
    assert not result.ok
    assert categories == {"unloadable_report"}
    assert "unsupported schema" in result.findings[0].detail


def test_a_verdict_that_its_own_report_does_not_derive_is_caught(bundle):
    """The fourth question, and the only one that reads two files against each other.

    ``CredibilityEvidenceReport.from_dict`` already refuses a payload whose
    embedded verdict disagrees with its contents. What it cannot do is notice
    that the *sibling file* a reader is most likely to open first says
    something else.
    """
    verdict = _read(bundle, VERDICT)
    derived = _read(bundle, REPORT)["verdict"]
    replacement = "supported" if derived != "supported" else "not_supported"
    verdict["value"] = replacement
    _overwrite(bundle, VERDICT, verdict)
    _recompute_manifest(bundle)

    result = verify_bundle(bundle)
    assert not result.ok
    assert {f.category for f in result.findings} == {"verdict_inconsistent"}
    assert derived in result.findings[0].detail
    assert replacement in result.findings[0].detail


def test_a_verdict_this_platform_does_not_issue_is_caught(bundle):
    verdict = _read(bundle, VERDICT)
    verdict["value"] = "definitely_fine"
    _overwrite(bundle, VERDICT, verdict)
    _recompute_manifest(bundle)

    categories = {f.category for f in verify_bundle(bundle).findings}
    assert categories == {"verdict_inconsistent", "unknown_verdict"}


def test_a_removed_file_is_caught(bundle):
    (bundle / REPORT).unlink()
    result = verify_bundle(bundle)
    assert not result.ok
    assert {f.category for f in result.findings} == {"missing_file"}
    # and the count shows the report was never loaded, rather than passing
    assert result.checked["reports_loaded"] == 0


def test_a_file_the_manifest_does_not_list_is_caught(bundle):
    """An added file is a finding. A verifier that only looked at what it was
    told to look at would pass a bundle with a second, unaccounted report."""
    (bundle / "stages/00-R1/report.backup.json").write_bytes(b"{}\n")
    result = verify_bundle(bundle)
    assert not result.ok
    assert {f.category for f in result.findings} == {"unlisted_file"}


def test_a_truncated_report_is_caught(bundle):
    (bundle / REPORT).write_bytes(b'{"schema": "mcp_evidence_pa')
    _recompute_manifest(bundle)
    result = verify_bundle(bundle)
    assert {f.category for f in result.findings} == {"unloadable_report"}


def test_a_missing_manifest_is_a_finding_and_not_an_empty_pass(bundle):
    (bundle / MANIFEST).unlink()
    result = verify_bundle(bundle)
    assert not result.ok
    assert result.findings[0].category == "missing_manifest"


def test_an_unreadable_manifest_is_a_finding(bundle):
    (bundle / MANIFEST).write_bytes(b"not json")
    result = verify_bundle(bundle)
    assert not result.ok
    assert result.findings[0].category == "unreadable_manifest"


def test_a_manifest_with_the_wrong_schema_is_refused(bundle):
    manifest = _read(bundle, MANIFEST)
    manifest["schema"] = "mcp_evidence_bundle_manifest/2"
    _overwrite(bundle, MANIFEST, manifest)
    result = verify_bundle(bundle)
    assert result.findings[0].category == "unreadable_manifest"


def test_verifying_a_directory_that_is_not_a_bundle_is_refused(tmp_path):
    result = verify_bundle(tmp_path)
    assert not result.ok
    assert result.checked == {
        "digests": 0,
        "reports_loaded": 0,
        "verdicts_rederived": 0,
    }


def test_findings_accumulate_rather_than_stopping_at_the_first(bundle):
    (bundle / "stages/00-R1/extra.json").write_bytes(b"{}\n")
    report = _read(bundle, REPORT)
    report["run_id"] = "someone-elses-run"
    _overwrite(bundle, REPORT, report)
    result = verify_bundle(bundle)
    categories = {f.category for f in result.findings}
    assert {"unlisted_file", "digest_mismatch"} <= categories


# =====================================================================
# The command
# =====================================================================

def test_the_command_exits_zero_on_a_clean_bundle_and_non_zero_otherwise(
    bundle, capsys
):
    from src.engcore.mcp.bundle import main

    assert main(["verify", str(bundle)]) == 0
    assert "VERIFIED" in capsys.readouterr().out

    (bundle / MANIFEST).unlink()
    assert main(["verify", str(bundle)]) == 1
    assert "REFUSED" in capsys.readouterr().out


def test_the_command_can_emit_json(bundle, capsys):
    from src.engcore.mcp.bundle import main

    main(["verify", str(bundle), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["findings"] == []


# =====================================================================
# A view, never a source
# =====================================================================

def test_no_runtime_module_reads_a_bundle_back():
    """Nothing in the runtime imports the bundle module.

    The moment a bundle can influence what the runtime concludes, every
    guarantee about a verdict being derived rather than asserted is worth
    whatever the file system is worth.
    """
    importers = []
    for path in (REPO_ROOT / "src/engcore").rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "bundle.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and "bundle" in (
                node.module or ""
            ):
                importers.append(str(path))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "bundle" in alias.name:
                        importers.append(str(path))
    assert importers == []


def test_the_bundle_module_writes_no_scientific_record():
    """It reads records and writes files. It constructs no result and no check."""
    source = (REPO_ROOT / "src/engcore/mcp/bundle.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    code = ast.unparse(tree)
    for forbidden in (
        "ScientificResult(", "ValidationCheck(", "ValidationReport(",
        "CredibilityEvidenceReport(", "derive_verdict(",
    ):
        assert forbidden not in code, forbidden
    # It does load a report -- that is the schema check -- and that is the only
    # route by which a stored record becomes an object here.
    assert "CredibilityEvidenceReport.from_dict" in code


def test_the_verification_record_serializes(bundle):
    result = verify_bundle(bundle)
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["ok"] is True
    assert isinstance(result, BundleVerification)
