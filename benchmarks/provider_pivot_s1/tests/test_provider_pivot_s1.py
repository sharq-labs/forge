"""The seven regressions this round's claims rest on.

Deliberately few, for the reason the Sprint 3 recovery's own benchmark tests
give: a hundred micro-tests around this machinery would say less than these do.
Each pins a property that, if it broke, would let a later round reach a
flattering answer without anybody noticing.

The freeze record is what makes most of them checkable. It is not a Gate A and
not a certification — this round produced neither — it is the state the evidence
came from, pinned by digest, so that "has this moved?" is a question with an
answer.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
HARNESS = os.path.join(BENCH, "harness")
REPO = os.path.dirname(os.path.dirname(BENCH))

#: The harness modules have short names -- `common`, `compare`, `freeze` -- and
#: a bare `import common` would be two bad things at once: a name that shadows
#: nothing today but could, and a statement the repository's undeclared-
#: dependency guard reads as a missing PyPI package, because a static scanner
#: cannot tell a sibling file from a distribution. This borrows the loader the
#: recovery's benchmark tests already use: load by path, keep the module, and
#: leave `sys.path` as it was found.
_LOADED: dict[str, object] = {}


def harness(name: str):
    if name in _LOADED:
        return _LOADED[name]
    added = HARNESS not in sys.path
    if added:
        sys.path.insert(0, HARNESS)
    try:
        spec = importlib.util.spec_from_file_location(
            f"_provider_pivot_s1_{name}", os.path.join(HARNESS, f"{name}.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if added and HARNESS in sys.path:
            sys.path.remove(HARNESS)
    _LOADED[name] = module
    return module


def load(name: str) -> dict:
    path = os.path.join(EVIDENCE, name)
    if not os.path.exists(path):
        pytest.skip(f"{name} has not been produced; run this round's harness")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


@pytest.fixture(scope="module")
def frozen() -> dict:
    return load("FREEZE.json")


# =====================================================================

def test_f1_every_frozen_source_still_hashes_to_what_the_freeze_recorded(frozen):
    """R1. The evidence is only meaningful beside the code that produced it.

    A provider adapter edited after the freeze makes every number in
    ``COMPARISON.json`` a statement about code that no longer exists.
    """
    moved = {
        relative: (recorded, sha256_file(os.path.join(REPO, relative)))
        for relative, recorded in frozen["sources"].items()
        if sha256_file(os.path.join(REPO, relative)) != recorded
    }
    assert not moved, (
        f"these sources have changed since the freeze: {sorted(moved)}. "
        f"Re-run the harness and re-freeze, or the evidence describes a tree "
        f"that is gone"
    )


def test_f2_every_frozen_evidence_file_still_hashes_to_what_the_freeze_recorded(frozen):
    """R2. And the evidence itself, so a hand-edited number is visible."""
    moved = {
        name: (recorded, sha256_file(os.path.join(EVIDENCE, name)))
        for name, recorded in frozen["evidence"].items()
        if sha256_file(os.path.join(EVIDENCE, name)) != recorded
    }
    assert not moved, f"evidence changed since the freeze: {sorted(moved)}"


def test_f3_no_holdout_split_appears_anywhere_in_the_evidence(frozen):
    """R3. The round's central abstention, checked rather than promised.

    Every cell in this archive has had its residuals read, so no pristine
    holdout remains. This round scored calibration and validation only. A
    holdout trajectory id appearing in any evidence file would mean it did not.
    """
    common = harness("common")
    assert set(common.DEVELOPMENT_SPLITS) == {"calibration", "validation"}

    selection = common.selection()
    withheld = {
        row["trajectory_id"]
        for row in selection["selected"]
        if row["split"] in ("locked_holdout", "observed_holdout")
    }
    assert withheld, "the selection names no withheld trajectories; the guard is vacuous"

    for name in frozen["evidence"]:
        text = open(os.path.join(EVIDENCE, name), encoding="utf-8").read()
        trespass = sorted(t for t in withheld if t in text)
        assert not trespass, f"{name} names withheld trajectories: {trespass[:5]}"

    # And the loader itself still refuses them, so the abstention is structural
    # rather than a property of what this round happened to ask for.
    with pytest.raises(SystemExit, match="development split"):
        common.development_trajectories(("locked_holdout",))


def test_f4_every_fitted_authority_is_derived_and_names_its_parent(frozen):
    """R4. P4's rule, checked against the record the fit actually wrote.

    A fitted authority whose source were ``pybamm_named_set`` would be citing
    the publisher for numbers Forge fitted.
    """
    assert frozen["parameter_authorities"], "the freeze pinned no authorities"
    for unit, entry in frozen["parameter_authorities"].items():
        assert entry["source"] == "forge_derived", unit
        assert entry["parent_authority_digest"], unit
        assert entry["authority_digest"] != entry["parent_authority_digest"], unit

    # The digests are reproducible from the payloads, not just recorded beside
    # them: a digest nobody can recompute is a number, not an identity.
    from engcore.providers import pybamm_provider as pp

    fit = load("FIT.json")
    for unit, block in fit["blocks"].items():
        if not block.get("fits"):
            continue
        fields = dict(block["authority"])
        band = fields.pop("temperature_validity_k")
        fields["temperature_validity_k"] = None if band is None else tuple(band)
        assert (
            pp.ParameterAuthority(**fields).digest() == block["authority_digest"]
        ), unit


def test_f5_the_fit_saw_calibration_and_nothing_else():
    """R5. P5's rule, checked against what the fit recorded about itself."""
    fit = load("FIT.json")
    assert fit["split_fitted"] == "calibration"
    assert set(fit["what_was_not_seen"]) == {
        "validation",
        "observed_holdout",
        "locked_holdout",
    }
    for row in fit["per_trajectory"]:
        assert row["split"] == "calibration", row["trajectory_id"]
        if row["outcome"] == "ok":
            assert row["evidence"]["dataset_role"] == "calibration"
            assert row["evidence"]["is_validation_evidence"] is False


def test_f6_the_comparison_carries_both_populations():
    """R6. The correction this round had to make, pinned so it cannot recur.

    The per-route table scores each route over the trajectories it offered,
    which is the right population for a refusal rate and the wrong one for a
    model comparison. Read as a comparison it said the provider route had the
    lower calibration RMSE; over the trajectories both offered, it does not.
    """
    comparison = load("COMPARISON.json")
    assert "like_for_like" in comparison, (
        "the comparison no longer states the common population, so its first "
        "table can be mistaken for a model comparison again"
    )
    calibration = comparison["like_for_like"]["calibration"]["routes"]
    native = calibration["native"]
    provider = calibration["pybamm_thevenin_1rc"]
    assert native["n"] > 0 and provider["n"] > 0
    assert native["rmse"] < provider["rmse"], (
        "over the common calibration population the native model was better; "
        "if that has changed, the report's section 3 is now wrong"
    )


def test_f7_a_successful_provider_run_still_reaches_no_support():
    """R7. The claim the whole sprint turns on, read off the evidence.

    Coverage through the full credibility verdict is zero for every provider
    route, because a PyBaMM run attains no ``ValidationLevel``. A future change
    that made it non-zero without validation evidence arriving would be the
    failure this round exists to prevent.
    """
    comparison = load("COMPARISON.json")
    trust = comparison["risk_trust_path"]
    for route, block in trust.items():
        if not route.startswith("pybamm"):
            continue
        assert "coverage" in block, route
        assert block["coverage"] == 0.0, (
            f"{route} reached non-zero coverage through the trust path. That "
            f"is only correct if validation evidence has been bound to a "
            f"provider run -- check that it has"
        )
