"""Parts D and E: the frozen public API, pinned and guarded.

`tests/api/frozen_api_snapshot.json` is the contract. This file is what makes
it one: it fails on a removed or renamed frozen symbol, a required argument
added or removed, a default changed, a keyword-only argument becoming
positional, an enum member or value changed, a public dataclass field removed
or reordered, and an exception base changed.

The file is pretty-printed for review, but the COMPARISON is over
`canonical_bytes`, so reformatting it cannot drift the check and cannot fake a
pass either.

What is NOT frozen is recorded too. Eight symbols under `engcore.studies` are
classified EXPERIMENTAL: they are one flagship study's scaffolding, and
freezing them would commit the Core to a demonstration's API. They are still
snapshotted, so a change to them is visible; they are simply not a promise.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from engcore import api_snapshot

PINNED = pathlib.Path(__file__).resolve().parent / "api" / "frozen_api_snapshot.json"
FULL = pathlib.Path(__file__).resolve().parent / "api" / "full_api_snapshot.json"


def pinned() -> dict:
    """The FROZEN contract. Experimental symbols are not in this file."""
    return json.loads(PINNED.read_text(encoding="utf-8"))


def pinned_full() -> dict:
    """Frozen AND experimental, so a change to either is visible."""
    return json.loads(FULL.read_text(encoding="utf-8"))


def by_key(snapshot: dict) -> dict[tuple[str, str], dict]:
    return {(e["module"], e["name"]): e for e in snapshot["symbols"]}


# =====================================================================
# The whole-surface comparison
# =====================================================================

def test_the_public_api_matches_the_pinned_snapshot():
    """One assertion covering every frozen shape at once.

    When this fails, the diff below names what moved. If the change was
    deliberate, regenerate with
    `python -X utf8 -m engcore.api_snapshot > tests/api/frozen_api_snapshot.json`
    AND record it as a compatibility event -- that is what the freeze policy
    makes it.
    """
    current, expected = api_snapshot.frozen_only(), pinned()
    if api_snapshot.canonical_bytes(current) == api_snapshot.canonical_bytes(expected):
        return

    now, before = by_key(current), by_key(expected)
    removed = sorted(before.keys() - now.keys())
    added = sorted(now.keys() - before.keys())
    changed = sorted(k for k in before.keys() & now.keys() if before[k] != now[k])
    pytest.fail(
        "the public API no longer matches the pinned snapshot\n"
        f"  removed : {removed}\n"
        f"  added   : {added}\n"
        f"  changed : {changed[:20]}"
    )


def test_the_pinned_snapshot_is_internally_consistent():
    snapshot = pinned()
    assert snapshot["schema"] == api_snapshot.SCHEMA
    assert snapshot["symbol_count"] == len(snapshot["symbols"])
    assert snapshot["symbol_count"] > 190, "the surface shrank unexpectedly"


# =====================================================================
# The specific failures the snapshot must catch
# =====================================================================

def test_every_frozen_symbol_still_imports_from_its_canonical_module():
    import importlib

    for entry in pinned()["symbols"]:
        module = importlib.import_module(entry["module"])
        assert hasattr(module, entry["name"]), (
            f"{entry['module']}.{entry['name']} is gone from its canonical module"
        )


def test_no_frozen_symbol_lost_its_kind():
    now = by_key(api_snapshot.frozen_only())
    for key, entry in by_key(pinned()).items():
        assert now[key]["kind"] == entry["kind"], key


def test_required_arguments_are_unchanged():
    """Adding a required argument breaks every existing call; removing one is
    a silent behaviour change for callers that were passing it."""
    now = by_key(api_snapshot.frozen_only())
    for key, entry in by_key(pinned()).items():
        if "signature" not in entry:
            continue
        assert now[key]["signature"]["required"] == entry["signature"]["required"], key


def test_parameter_kinds_and_defaults_are_unchanged():
    """Keyword-only becoming positional-or-keyword still compiles every call,
    and is still a compatibility event: it freezes argument ORDER that was
    never part of the contract."""
    now = by_key(api_snapshot.frozen_only())
    for key, entry in by_key(pinned()).items():
        if "signature" not in entry:
            continue
        before = {p["name"]: p for p in entry["signature"]["parameters"]}
        after = {p["name"]: p for p in now[key]["signature"]["parameters"]}
        assert set(before) == set(after), f"{key}: parameter set changed"
        for name, parameter in before.items():
            assert after[name]["kind"] == parameter["kind"], f"{key}.{name}: kind"
            assert after[name]["has_default"] == parameter["has_default"], f"{key}.{name}"
            assert after[name]["default"] == parameter["default"], f"{key}.{name}: default"


def test_enum_members_and_values_are_unchanged():
    now = by_key(api_snapshot.frozen_only())
    for key, entry in by_key(pinned()).items():
        if "enum_members" not in entry:
            continue
        assert now[key]["enum_members"] == entry["enum_members"], key


def test_public_dataclass_fields_keep_their_order():
    """Order is the positional-construction contract, so a reorder is a break
    even when every field survives."""
    now = by_key(api_snapshot.frozen_only())
    for key, entry in by_key(pinned()).items():
        if "dataclass_fields" not in entry:
            continue
        assert now[key]["dataclass_fields"] == entry["dataclass_fields"], key


def test_exception_inheritance_is_unchanged():
    """`except SomeBase` is a contract callers write against."""
    now = by_key(api_snapshot.frozen_only())
    for key, entry in by_key(pinned()).items():
        if "exception_mro" not in entry:
            continue
        assert now[key]["exception_mro"] == entry["exception_mro"], key


def test_union_aliases_keep_their_members():
    now = by_key(api_snapshot.frozen_only())
    for key, entry in by_key(pinned()).items():
        if "union_members" not in entry:
            continue
        assert now[key]["union_members"] == entry["union_members"], key


# =====================================================================
# PART O -- defaults
# =====================================================================

def test_no_frozen_public_default_is_mutable():
    """A mutable default is shared across calls; freezing one freezes the bug."""
    offenders = [
        f"{e['module']}.{e['name']}({p['name']}=)"
        for e in api_snapshot.build()["symbols"]
        for p in e.get("signature", {}).get("parameters", [])
        if p["default"]["kind"] == "MUTABLE_DEFAULT"
    ]
    assert not offenders, offenders


def test_experimental_surface_is_explicitly_marked():
    """Nothing is EXPERIMENTAL by accident, and nothing frozen is unmarked."""
    snapshot = api_snapshot.build()
    experimental = [e for e in snapshot["symbols"] if e["classification"] == "EXPERIMENTAL"]
    assert {e["module"] for e in experimental} == {"engcore.studies"}
    for entry in experimental:
        assert entry["experimental_because"], entry["name"]

    workers = [
        p for e in snapshot["symbols"]
        for p in e.get("signature", {}).get("parameters", [])
        if p.get("classification") == "EXPERIMENTAL"
    ]
    assert len(workers) == 2, "the two `workers` parameters must stay marked"


# =====================================================================
# PART E -- determinism, in fresh processes
# =====================================================================

def _digest_in_fresh_process(hashseed: str, cwd: pathlib.Path) -> str:
    import os

    environment = dict(os.environ, PYTHONHASHSEED=hashseed)
    out = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "engcore.api_snapshot", "--digest"],
        capture_output=True, text=True, env=environment, cwd=str(cwd), check=True,
    )
    return out.stdout.strip()


def test_the_snapshot_is_byte_identical_across_fresh_processes():
    """Different hash seeds, different working directories, same bytes."""
    repo = pathlib.Path(__file__).resolve().parents[1]
    digests = {
        _digest_in_fresh_process("0", repo),
        _digest_in_fresh_process("1", repo),
        _digest_in_fresh_process("random", repo),
        _digest_in_fresh_process("random", repo.parent),
    }
    assert len(digests) == 1, f"the snapshot is not deterministic: {digests}"
    assert digests.pop() == api_snapshot.digest()


def test_the_snapshot_carries_nothing_machine_specific():
    """A path, an address or a timestamp in the bytes would break the wheel
    comparison in a way that looked like an API change."""
    blob = api_snapshot.canonical_bytes().decode("utf-8")
    for forbidden in ("0x", "C:\\", "/home/", "Users", "site-packages",
                      ".venv", "Temp", "tmp"):
        assert forbidden not in blob, f"snapshot contains {forbidden!r}"
