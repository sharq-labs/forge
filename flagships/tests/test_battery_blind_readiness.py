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


#: sha256 (LF-normalized) of the Kirkaldy artifacts as merged before this campaign (base 4634eba2): untouched
KIRKALDY_PINS = {
    "flagships/forge_flagships/data/big14_a_kirkaldy_fade_preregistration.json":
        "da6ac0da6c1ee88285a85f575f7ab0046b1d37563ac68d9658c3d10b19ca1c19",
    "docs/flagships/big14/kirkaldy_fade_study.json": "2b62d63a3907206a5a442cd77838626ba9d100bac198e9801eaae3dd7621266e",
    "flagships/forge_flagships/kirkaldy_fade.py": "5400f9c6cf5e4e0322079a17e0ff0b7c3a0f5a0e004fd95041ac51dea52b382b",
}


def test_kirkaldy_stays_not_met_and_its_artifacts_are_untouched():
    for rel, pin in KIRKALDY_PINS.items():
        data = (REPO / rel).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == pin, f"{rel} changed: the NOT MET record is not edited"
    study = json.loads((REPO / "docs" / "flagships" / "big14" / "kirkaldy_fade_study.json").read_text())
    assert "NOT MET" in json.dumps(study)
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
    # exp(f + C) is C' exp(f): the Arrhenius law WITHOUT the T_ref offset is the same family (review C M-9)
    from engcore.blindfold.expression import c, mul, pw, v
    bare = mul(c(2e-4), v("q"), {"exp": mul(c(-3000.0), pw(v("T"), -1.0))})
    kirkaldy = bb.PRIOR_ART_FAMILIES[0][1]
    assert bb.fade_family_digest(bare) == bb.fade_family_digest(kirkaldy)
    assert all(e.expression is not None for e in bb.prior_art_snapshot().entries)


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


def test_readiness_is_not_ready_with_every_blocker_derived(monkeypatch):
    r = bb.readiness()
    assert r["CONFIRMATORY_DATA_EXPOSED"] == "NO"
    assert r["BATTERY_READINESS"].startswith("NOT_READY(")
    for b in bb.readiness_blockers():
        assert b.split(":")[0] in r["BATTERY_READINESS"]
    # a blocker disappears only when its FACT changes, never by editing a list
    monkeypatch.setattr(bb, "DATA_AUTHORITY_ROUTE", "escrow-hosted data authority (deployed)")
    assert "DATA_AUTHORITY_ROUTE_NOT_WIRED" not in bb.readiness()["BATTERY_READINESS"]
    monkeypatch.setattr(bb, "PRODUCTION_TRUST_ANCHOR", {"profile": "test"})
    assert "PRODUCTION_AUTHORITY_NOT_PROVISIONED" in bb.readiness()["BATTERY_READINESS"]


def test_the_dry_run_records_every_abstention_with_its_rule_inputs(dry):
    for u in dry["discipline"]["untestable"]:
        assert u["reason"]
    sealed_or_abstained = {u["hypothesis_id"] for u in dry["discipline"]["untestable"]} | {
        h for h, n in dry["falsifiers_sealed"].items() if n}
    assert sealed_or_abstained == set(dry["statuses"])
    assert dry["discipline"]["issues"] == []


def test_the_readiness_document_matches_the_code():
    text = DOC.read_text()
    r = bb.readiness()
    for key in ("PREREGISTRATION_DIGEST", "HYPOTHESIS_REGISTRY_DIGEST", "PRIOR_ART_SNAPSHOT_DIGEST", "RED_TEAM_PLAN_DIGEST",
                "BATTERY_READINESS"):
        assert f"{key}: {r[key]}" in text, key
    assert "CONFIRMATORY_DATA_EXPOSED: NO" in text
    assert hashlib.sha256(json.dumps(r["MULTIPLICITY_BUDGET"], sort_keys=True).encode()).hexdigest()[:16] in text
