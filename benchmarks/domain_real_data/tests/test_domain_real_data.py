"""Domain real-data round: raw bytes pinned, provenance complete, licences respected, inventory current.

These tests hold the round's evidence claims, not any scientific result: the
round calibrated nothing and issued no verdict.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "domain_real_data"

REQUIRED_FIELDS = (
    "id", "domains", "title", "authors", "institution", "persistent_identifier", "source", "publication",
    "licence", "classification", "status", "system", "equipment", "protocol", "temperature", "pressure",
    "sampling", "channels", "uncertainty", "raw_or_processed", "quality", "claim_mapping",
    "held_out_possible", "missing_information",
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def registry():
    return json.loads((ROUND / "DATASETS.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def datasets(registry):
    return {d["id"]: d for d in registry["datasets"]}


def test_every_file_the_registry_pins_has_its_bytes(registry):
    pinned = [(d["id"], f) for d in registry["datasets"] for f in d.get("files_in_repository", [])]
    assert pinned
    for dataset_id, entry in pinned:
        assert sha(ROOT / entry["path"]) == entry["sha256"], (dataset_id, entry["path"])


def test_vendored_lg_files_agree_between_registry_and_provenance(datasets):
    provenance = json.loads((ROUND / "battery" / "lg_hg2_mcmaster" / "PROVENANCE.json").read_text(encoding="utf-8"))
    from_provenance = {f["vendored_path"]: f["sha256"] for f in provenance["files"]}
    from_registry = {f["path"]: f["sha256"] for f in datasets["DS-BAT-LGHG2"]["files_in_repository"]}
    assert from_provenance == from_registry
    for path, digest in from_provenance.items():
        assert (ROOT / path).stat().st_size == next(f["bytes"] for f in provenance["files"] if f["vendored_path"] == path)
        assert sha(ROOT / path) == digest


def test_vendored_lg_files_are_the_bytes_mendeley_publishes():
    manifest = json.loads((ROUND / "battery" / "lg_hg2_mcmaster" / "MENDELEY_MANIFEST.json").read_text(encoding="utf-8"))
    published = {f["filename"]: f["sha256_published_by_mendeley"] for f in manifest["files"]}
    raw = ROUND / "battery" / "lg_hg2_mcmaster" / "raw"
    files = [p for p in raw.iterdir() if p.name != ".gitattributes"]
    assert len(files) == 6
    for path in files:
        assert sha(path) == published[path.name], path.name


def test_raw_directory_forbids_line_ending_normalisation():
    attributes = (ROUND / "battery" / "lg_hg2_mcmaster" / "raw" / ".gitattributes").read_text(encoding="utf-8")
    assert "* -text" in attributes.splitlines()
    # The cycler exports really are CRLF with a NUL byte; a normalised checkout would change that.
    body = (ROUND / "battery" / "lg_hg2_mcmaster" / "raw" / "549_Dis_2C.csv").read_bytes()
    assert b"\r\n" in body and body.count(b"\x00") == 1


def test_every_dataset_records_every_provenance_field(registry):
    vocab = registry["vocabulary"]
    for d in registry["datasets"]:
        for field in REQUIRED_FIELDS:
            assert field in d, (d["id"], field)
            value = d[field]
            assert value not in ("", None, [], {}) or field == "missing_information", (d["id"], field)
        assert d["classification"] in vocab["classification"], d["id"]
        assert d["status"] in vocab["status"], d["id"]
        assert d["quality"]["grade"][0] in vocab["quality"], d["id"]
        for claim in d["claim_mapping"]:
            assert claim["testable"] in vocab["testable"], (d["id"], claim)


def test_nothing_is_vendored_without_a_licence_that_permits_it(registry):
    for d in registry["datasets"]:
        redistribution = d["licence"]["redistribution"]
        if d["status"] == "VENDORED":
            assert redistribution == "PERMITTED", d["id"]
            assert d["files_in_repository"], d["id"]
        if d["status"] == "EXTERNAL_FETCH_REQUIRED":
            assert redistribution != "PERMITTED", d["id"]
            assert not d.get("files_in_repository"), d["id"]
            assert d.get("acquisition") and d.get("manifest"), d["id"]


def test_external_fetch_datasets_left_no_raw_bytes_in_the_round():
    vendored_raw = ROUND / "battery" / "lg_hg2_mcmaster" / "raw"
    for path in ROUND.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or vendored_raw in path.parents:
            continue
        assert path.suffix in {".json", ".md", ".py"}, path


def test_synthetic_data_is_never_called_measured():
    scan = json.loads((ROUND / "REPOSITORY_SCAN.json").read_text(encoding="utf-8"))
    measured = [p for g in scan["groups"] if g["class"] == "REAL_MEASURED" for p in g["files"]]
    for path in measured:
        assert not re.search(r"cases_|/truth|oracle|synthetic|experiments/", path), path
    assert scan["unknown_provenance_files"] == 0


def test_every_measured_file_in_the_repository_is_in_the_registry(registry):
    scan = json.loads((ROUND / "REPOSITORY_SCAN.json").read_text(encoding="utf-8"))
    registered = {f["path"] for d in registry["datasets"] for f in d.get("files_in_repository", [])}
    for group in scan["groups"]:
        if group["class"] in ("REAL_MEASURED", "REFERENCE_ONLY"):
            for path in group["files"]:
                assert path in registered, path


def test_repository_scan_is_current():
    scan = _load("_drd_scan", ROUND / "audit" / "inventory_scan.py")
    assert scan.render(scan.scan()) == scan.OUT.read_bytes()


def test_quality_screen_is_current_and_hashes_match():
    screen = _load("_drd_quality", ROUND / "audit" / "quality_screen.py")
    doc = screen.screen()
    assert doc["all_hashes_match_registry"]
    assert screen.render(doc) == screen.OUT.read_bytes()


def test_claim_map_names_only_models_that_exist(registry):
    source = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "engcore").rglob("*.py"))
    pattern = re.compile(r"\b(?:battery|electrical|thermal|kinetics)\.[a-z0-9_]+\.[a-z0-9_]+\b|\b(?:ideal-actuator-disk-hover|mvr0-multirotor-mass-endurance-reference)\b")
    named = {m for d in registry["datasets"] for c in d["claim_mapping"] for m in pattern.findall(c["model"])}
    assert named
    for model_id in named:
        assert f'"{model_id}"' in source, model_id


def test_the_round_is_evidence_only():
    for path in (ROUND / "audit").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+engcore", text, re.MULTILINE), path
