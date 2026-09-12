"""The eight points closed explicitly, plus Parts F, H, I, M, N.

Each section states the rule it enforces and why that rule rather than a
neighbouring one.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import subprocess
import sys

import pytest

from engcore import api_snapshot

REPO = pathlib.Path(__file__).resolve().parents[1]


# =====================================================================
# 1. CANONICAL PACKAGE IDENTITY
# =====================================================================
#
# `engcore.*` is the only supported public identity. `src.engcore.*` is
# importable in a CHECKOUT because pyproject puts "." on pythonpath, and eleven
# SHA-256-pinned experiment files still spell it that way -- so it cannot simply
# be removed. It is classified, not frozen.

UNSUPPORTED_CHECKOUT_ALIAS = "src.engcore"


def test_the_src_alias_is_classified_not_frozen():
    """Object identity matching is NOT a reason to freeze an alias.

    `src.engcore.x is engcore.x` happens to hold today, and that is a useful
    property -- it is what stops a second package identity existing. It is not
    a promise about `src.engcore` being importable, and this test says so
    rather than letting the identity check be read as support.
    """
    assert UNSUPPORTED_CHECKOUT_ALIAS not in api_snapshot.CANONICAL_MODULES
    for module in api_snapshot.CANONICAL_MODULES:
        assert module.startswith("engcore."), module
        assert not module.startswith("src."), module

    for entry in api_snapshot.frozen_only()["symbols"]:
        assert not entry["module"].startswith("src.")
        assert not str(entry.get("defined_in", "")).startswith("src.")


def test_the_alias_when_importable_is_the_same_object_not_a_second_identity():
    """While it exists, it must not create twin classes.

    Two module identities for one class means `isinstance` fails across them
    and a record built by one is rejected by the other -- with both spelling
    the same name in every log line.
    """
    import engcore.scientific.units.quantity as canonical

    try:
        aliased = importlib.import_module("src.engcore.scientific.units.quantity")
    except ImportError:
        pytest.skip("the checkout alias is not importable here, which is fine")
    assert aliased is canonical
    assert aliased.Quantity is canonical.Quantity


def test_the_wheel_must_not_expose_the_alias():
    """The packaging half: `src` must not be a distributed package.

    Read from the build configuration rather than from a built wheel, so this
    fails at the moment somebody changes the configuration rather than at the
    moment somebody builds.
    """
    import tomllib

    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    packages = config["tool"]["setuptools"]["packages"]
    assert set(packages) == {"find"}, (
        "packages are DISCOVERED, not listed. An explicit list is where `src` "
        f"would be reintroduced as a distributed name; found {sorted(packages)}"
    )
    assert packages["find"]["where"] == ["src"], (
        "discovery is rooted at src/, so the distributed top-level names are "
        "src/'s CHILDREN -- `engcore` -- and never `src` itself"
    )


# =====================================================================
# 2. EXPERIMENTAL STUDIES API
# =====================================================================

EXPECTED_EXPERIMENTAL = {
    ("engcore.studies", "TCR_MODEL_REF"),
    ("engcore.studies", "TcrTruth"),
    ("engcore.studies", "build_tcr_parameter_set"),
    ("engcore.studies", "ols_reference_estimate"),
    ("engcore.studies", "synthesize_tcr_observations"),
    ("engcore.studies", "tcr_forward_evaluator"),
    ("engcore.studies", "tcr_forward_table"),
    ("engcore.studies", "tcr_prediction"),
}


def test_the_experimental_manifest_is_exactly_these_eight():
    snapshot = api_snapshot.build()
    actual = {
        (e["module"], e["name"])
        for e in snapshot["symbols"] if e["classification"] == "EXPERIMENTAL"
    }
    assert actual == EXPECTED_EXPERIMENTAL


def test_no_experimental_symbol_is_in_the_frozen_contract():
    frozen = {(e["module"], e["name"]) for e in api_snapshot.frozen_only()["symbols"]}
    assert not (frozen & EXPECTED_EXPERIMENTAL)
    assert api_snapshot.frozen_only()["symbol_count"] == 197


def test_an_experimental_symbol_cannot_move_the_frozen_digest():
    """The separation, demonstrated rather than asserted.

    Drop an experimental entry from a copy of the full snapshot and the frozen
    digest must not move. If the two shared a digest, every edit to the
    `engcore.studies` example would read as a compatibility event -- and the
    day somebody stops believing the alarm is the day a real one is missed.
    """
    full = api_snapshot.build()
    before = api_snapshot.frozen_digest(full)

    mutated = json.loads(json.dumps(full))
    mutated["symbols"] = [
        e for e in mutated["symbols"] if e["classification"] != "EXPERIMENTAL"
    ]
    assert api_snapshot.frozen_digest(mutated) == before

    # ... and a FROZEN change must move it, so the digest is not simply inert.
    mutated2 = json.loads(json.dumps(full))
    for entry in mutated2["symbols"]:
        if entry["classification"] == "FREEZE":
            entry["name"] += "_renamed"
            break
    assert api_snapshot.frozen_digest(mutated2) != before


# =====================================================================
# 3. DEPENDENCY HYGIENE -- the runtime probe
# =====================================================================

def declared_groups() -> dict[str, list[str]]:
    import tomllib

    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return config["project"].get("optional-dependencies", {})


def test_the_three_named_packages_are_in_the_right_groups():
    """`psutil`, `jsonschema`, `mpmath` -- each in its group, none in runtime."""
    import tomllib

    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = " ".join(config["project"]["dependencies"])
    groups = declared_groups()

    for name in ("psutil", "jsonschema", "mpmath"):
        assert name not in runtime, (
            f"{name} is a benchmark/oracle dependency and must not be promoted "
            f"into runtime dependencies -- a bare install would then pay for it"
        )
    assert any("mpmath" in r for r in groups["oracles"])
    assert any("jsonschema" in r for r in groups["benchmarks"])
    assert any("psutil" in r for r in groups["benchmarks"])


@pytest.mark.parametrize("group,module", [
    ("oracles", "mpmath"),
    ("benchmarks", "jsonschema"),
    ("benchmarks", "psutil"),
])
def test_a_declared_extra_can_actually_import(group, module):
    """The probe static analysis cannot do.

    A name can be spelled correctly in pyproject and still not install, or
    install under a different import name. `psutil` was DECLARED and ABSENT
    when the group was written, which is exactly the state a static check
    reports as healthy. Skipped rather than failed when the extra is not
    installed: the suite must stay green on a bare install, which is the rule
    every optional group here is written to.
    """
    pytest.importorskip(
        module,
        reason=f"the [{group}] extra is not installed in this environment",
    )
    imported = importlib.import_module(module)
    assert imported.__name__ == module


# =====================================================================
# 4. API SNAPSHOT -- strict JSON, fresh-process identity
# =====================================================================

def test_the_snapshot_is_strict_json():
    for payload in (api_snapshot.canonical_bytes(),
                    api_snapshot.canonical_bytes(api_snapshot.frozen_only())):
        text = payload.decode("utf-8")
        assert "NaN" not in text and "Infinity" not in text
        json.loads(text)  # a conforming parser must accept it


def test_the_frozen_digest_is_identical_in_fresh_processes():
    digests = set()
    for seed in ("0", "1", "random"):
        import os

        out = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "engcore.api_snapshot",
             "--frozen-digest"],
            capture_output=True, text=True, check=True,
            env=dict(os.environ, PYTHONHASHSEED=seed), cwd=str(REPO),
        )
        digests.add(out.stdout.strip())
    assert len(digests) == 1, digests
    assert digests.pop() == api_snapshot.frozen_digest()


# =====================================================================
# 7. EXCEPTIONS -- Part N
# =====================================================================

def public_exceptions():
    for entry in api_snapshot.frozen_only()["symbols"]:
        if entry["kind"] == "exception":
            module = importlib.import_module(entry["module"])
            yield entry, getattr(module, entry["name"])


#: The exception contract as it IS, recorded rather than wished into one tree.
#:
#: There are SEVEN roots, not one, and the Sprint 10 audit found that rather
#: than assuming it. `except ScientificCoreError` does NOT catch everything the
#: Core raises -- inference, data, uq and adequacy each raise from their own
#: root.
#:
#: Deliberately NOT unified in this round. Reparenting twelve exception classes
#: onto `ScientificCoreError` would widen what every existing
#: `except ScientificCoreError` catches, which is a real behaviour change to
#: certified modules, made immediately before a freeze, to buy a naming
#: nicety. Part N asks for the stable boundary to be identified, not for one
#: tree; the boundary is identified here, and unifying it is a compatibility
#: event a later round can schedule deliberately.
EXCEPTION_ROOTS = {
    "engcore.scientific.errors.ScientificCoreError": 13,
    "engcore.inference.grid.InferenceProblemError": 5,
    "engcore.data.errors.BulkDataError": 3,
    "engcore.inference.admissibility.InferenceAdmissibilityError": 1,
    "engcore.inference.parameters.ParameterIdentityError": 1,
    "engcore.adequacy.predictive.ModelAdequacyError": 1,
    "engcore.uq.predictive.UQProblemError": 1,
}


def test_the_exception_roots_are_exactly_the_seven_recorded():
    """A new root appearing is a decision, and this is where it gets made.

    Adding an eighth family means a caller who wanted "everything the Core
    raises" has to learn about it, so it must not happen silently.
    """
    counted: dict[str, int] = {}
    for entry, klass in public_exceptions():
        ancestors = [
            f"{k.__module__}.{k.__qualname__}"
            for k in klass.__mro__
            if k.__module__.startswith("engcore.")
        ]
        counted[ancestors[-1]] = counted.get(ancestors[-1], 0) + 1
    assert counted == EXCEPTION_ROOTS, counted


def test_every_public_exception_descends_from_one_of_those_roots():
    """Each family is catchable by its own base, even though there is no single
    Core base. That is the property a caller can actually rely on."""
    roots = []
    for name in EXCEPTION_ROOTS:
        module_name, _, klass_name = name.rpartition(".")
        roots.append(getattr(importlib.import_module(module_name), klass_name))

    for entry, klass in public_exceptions():
        assert any(issubclass(klass, root) for root in roots), (
            f"{entry['module']}.{entry['name']} belongs to no recorded family"
        )


def test_every_public_exception_is_an_exception():
    for entry, klass in public_exceptions():
        assert issubclass(klass, Exception), f"{entry['module']}.{entry['name']}"
        assert not issubclass(klass, BaseException) or issubclass(klass, Exception), (
            f"{entry['module']}.{entry['name']} sits outside Exception, so a "
            f"bare `except Exception` would not catch it"
        )


def test_no_public_exception_is_a_bare_builtin_alias():
    """`SomeError = ValueError` would make `except SomeError` catch every
    ValueError in the program, including ones the Core never raised."""
    import builtins

    for entry, klass in public_exceptions():
        assert getattr(builtins, klass.__name__, None) is not klass, (
            f"{entry['module']}.{entry['name']} IS a builtin"
        )


def test_the_exception_count_is_what_the_snapshot_says():
    assert len(list(public_exceptions())) == 25
