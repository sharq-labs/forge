"""v0.4 campaign driver (P-4, P-5, G16): sealed root file, commitment before the run, manifest, formal-tier refusal."""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import sys

import pytest

from benchmarks.genesis_lite import pilot_v3, pilot_v4

from .test_v04_isolation import _can_isolate

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _root_file(directory: pathlib.Path, data: bytes | None = None, mode: int = 0o600) -> pathlib.Path:
    f = directory / "root.bin"
    f.write_bytes(secrets.token_bytes(32) if data is None else data)
    os.chmod(f, mode)
    return f


def test_the_roster_holds_every_registered_baseline_and_the_v04_arms():
    roster = pilot_v4.roles()
    assert {"random_grammar", "pysr_units", "grammar_enumeration", "careful", "space_filling", "pysr_symbolic"} <= set(roster)
    assert roster["historical_answer"] == "adversarial"
    assert not [n for n in roster if n.startswith("mind")]                  # D1: Step 1 is baselines only
    assert pilot_v4.ROSTER["grammar_enumeration"][0] == "benchmarks.genesis_lite.arms_grammar_v3:grammar_enumeration"


def test_the_master_seed_domain_differs_from_v03():
    root = b"\x07" * 32
    assert pilot_v4.master_seed(root, 0, "anonymous", 0) != pilot_v3.master_seed(root, 0, "anonymous", 0)


def test_a_root_file_inside_the_tree_refuses():
    with pytest.raises(ValueError, match="inside the code tree"):
        pilot_v4.read_root(ROOT / "pyproject.toml")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_a_readable_root_file_refuses(tmp_path):
    with pytest.raises(ValueError, match="0600"):
        pilot_v4.read_root(_root_file(tmp_path, mode=0o644))


def test_a_root_of_the_wrong_length_refuses(tmp_path):
    f = _root_file(tmp_path, data=b"short")
    if sys.platform == "win32":
        pytest.skip("POSIX permission bits decide first")
    with pytest.raises(ValueError, match="32 bytes"):
        pilot_v4.read_root(f)


@pytest.mark.parametrize("kwargs", [{"campaigns": 0}, {"presentations": ["nope"]}, {"seeds": []}])
def test_a_bad_grid_refuses(kwargs):
    base = {"campaigns": 1, "presentations": ["anonymous"], "seeds": [0]}
    with pytest.raises(ValueError):
        pilot_v4.plan(["careful"], **{**base, **kwargs})


def test_unknown_or_repeated_arms_refuse():
    for arms in (["careful", "careful"], ["mind_full"], ["no_such_arm"]):
        with pytest.raises(ValueError):
            pilot_v4.plan(arms, campaigns=1, presentations=["anonymous"], seeds=[0])


def test_the_formal_tier_refuses_without_a_frozen_preregistration():
    if pilot_v4.PREREG.exists():
        pytest.skip("a v0.4 preregistration exists")
    assert "no frozen v0.4 preregistration" in pilot_v4.formal_identity_check("x")


@pytest.mark.skipif(not _can_isolate(), reason="needs Linux, root and a tree readable by uid 65534")
def test_a_development_run_commits_before_running_and_never_writes_the_root(tmp_path):
    secret = pathlib.Path("/root") / f"gl-v04-root-{secrets.token_hex(4)}"
    secret.mkdir(mode=0o700)
    try:
        f = _root_file(secret)
        root = f.read_bytes()
        out = pathlib.Path("/root") / f"gl-v04-out-{secrets.token_hex(4)}"
        summary = pilot_v4.run(["careful", "always_refuse"], root_file=str(f), out=str(out), campaigns=1,
                               presentations=["anonymous"], seeds=[0], workers=2, deadline_seconds=600)
        assert summary["completed"] == 2
        recs = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]
        assert {r["status"] for r in recs} == {"VALID"}, [r.get("reasons") for r in recs]
        assert all(len(r["isolation_checks"]) == 6 for r in recs)
        commitment = json.loads((out / "commitment.json").read_text())
        import hashlib
        assert commitment["root_commitment_sha256"] == hashlib.sha256(root).hexdigest()
        assert (out / "commitment.json").stat().st_mtime <= (out / "runs.jsonl").stat().st_mtime
        for p in out.iterdir():
            assert root.hex() not in p.read_text() and root not in p.read_bytes()
        manifest = json.loads((out / "environment.json").read_text())
        assert manifest["distributions"] and manifest["isolation_support"][0] is True
        assert str(secret) in manifest["hidden"] or "/root" in manifest["hidden"]
    finally:
        for p in sorted(secret.rglob("*"), reverse=True):
            p.unlink()
        secret.rmdir()
