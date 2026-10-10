"""Big Rocks Rock 3: battery blind confirmatory READINESS.  No confirmatory datum exists here; nothing is run for real.

* Kirkaldy 2024 stays NOT MET and its pre-registration is untouched.
* The real pre-registration names its confirmatory data by requirements only.
* The synthetic dry run walks the whole chain and nothing in it counts as a discovery.
* The readiness record in docs matches the code (no drift) and states NOT_READY with reasons.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest
from forge_flagships import battery_blind as bb

REPO = pathlib.Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "flagships" / "BATTERY_CONFIRMATORY_READINESS.md"


@pytest.fixture(scope="module")
def dry(tmp_path_factory):
    return bb.dry_run(str(tmp_path_factory.mktemp("battery-dry-run")))


def test_kirkaldy_stays_not_met_and_its_preregistration_is_untouched():
    prereg = REPO / "flagships" / "forge_flagships" / "data" / "big14_a_kirkaldy_fade_preregistration.json"
    study = json.loads((REPO / "docs" / "flagships" / "big14" / "kirkaldy_fade_study.json").read_text())
    assert "NOT MET" in json.dumps(study)
    assert prereg.exists()
    assert bb.readiness()["KIRKALDY_2024"].startswith("NOT MET")


def test_the_real_preregistration_holds_no_confirmatory_value():
    p = bb.real_preregistration()
    conf = p.sections["confirmatory_dataset"]
    assert conf["status"] == "TO_BE_DESIGNATED_BY_OWNER" and conf["identity"] is None
    assert p.hypothesis_ids == tuple(h[0] for h in bb.HYPOTHESES)
    assert p.sections["exploratory_data"]["status"].startswith("EXPLORATORY ONLY")


def test_the_family_canonicalizer_abstracts_exponents_and_constants():
    a = bb.HYPOTHESES[2][2]([1e-3, 4000.0, 0.5])
    b = bb.HYPOTHESES[2][2]([7e-2, 100.0, 1.3])
    assert bb.fade_family_digest(a) == bb.fade_family_digest(b)
    assert bb.fade_family_digest(a) == bb.fade_family_digest(bb.HYPOTHESES[0][2]([1e-3, 4000.0]))   # linear = the z=1 member
    assert bb.fade_family_digest(a) != bb.fade_family_digest(bb.HYPOTHESES[1][2]([1e-4, 6000.0, 2e-6, 9000.0]))


def test_the_dry_run_walks_the_whole_chain_without_claiming_anything(dry):
    assert dry["run_kind"] == "dry_run_synthetic"
    assert dry["discipline"]["status"] == "CONFIRMATORY", dry["discipline"]["issues"]
    assert dry["fidelity_link_admitted"], dry["fidelity_admission_refusal"]
    assert not any(dry["counts_as_discovery"].values())
    untestable = {u["hypothesis_id"] for u in dry["discipline"]["untestable"]}
    for hid, n in dry["falsifiers_sealed"].items():
        assert n > 0 or hid in untestable                       # every hypothesis is sealed or abstained from, never dropped
        if n == 0:
            assert dry["statuses"][hid] == "proposed"           # an untestable hypothesis is not scored
    for hid, p in dry["passports"].items():
        assert p["run_kind"] == "dry_run_synthetic" and p["counts_as_discovery"] is False
        assert p["credibility"]["test_mode"] is True
        assert any("DRY RUN" in lim for lim in p["verdict_limits"])
        assert all(f["verdicts"] for f in p["falsifiers"])      # every sealed falsifier was judged
    assert dry["multiplicity"]["family_size"] >= len(dry["statuses"])


def test_readiness_is_not_ready_with_every_blocker_stated():
    r = bb.readiness()
    assert r["CONFIRMATORY_DATA_EXPOSED"] == "NO"
    assert r["BATTERY_READINESS"].startswith("NOT_READY(")
    for b in bb.READINESS_BLOCKERS:
        assert b.split(":")[0] in r["BATTERY_READINESS"]


def test_the_readiness_document_matches_the_code():
    text = DOC.read_text()
    r = bb.readiness()
    for key in ("PREREGISTRATION_DIGEST", "HYPOTHESIS_REGISTRY_DIGEST", "PRIOR_ART_SNAPSHOT_DIGEST", "RED_TEAM_PLAN_DIGEST",
                "BATTERY_READINESS"):
        assert f"{key}: {r[key]}" in text, key
    assert "CONFIRMATORY_DATA_EXPOSED: NO" in text
    assert hashlib.sha256(json.dumps(r["MULTIPLICITY_BUDGET"], sort_keys=True).encode()).hexdigest()[:16] in text
