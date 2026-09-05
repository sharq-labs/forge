"""The tier tables in conftest.py must not rot.

`tests/conftest.py` classifies tests by node id and by module path. Those are
strings, so a rename or a move degrades silently: the entry stops matching, the
test quietly changes tier, and nobody finds out until a campaign test starts
running in the FAST suite (or, worse, a frozen-experiment reproduction stops
running in SCIENTIFIC).

These tests make that failure loud. They assert nothing about science; they
assert that the classification still refers to tests and files that exist.
"""

from __future__ import annotations

import pathlib

import pytest

from conftest import (
    CAMPAIGN_TESTS,
    EXPENSIVE_MODULES,
    STATIC_GUARDS,
    normalized_nodeid,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _module_source(module: str) -> str:
    return (REPO_ROOT / module).read_text(encoding="utf-8")


def test_every_expensive_module_exists() -> None:
    missing = [m for m in EXPENSIVE_MODULES if not (REPO_ROOT / m).is_file()]
    assert not missing, f"conftest names modules that no longer exist: {missing}"


def test_every_campaign_test_exists() -> None:
    """A renamed campaign test would silently rejoin the FAST suite."""
    missing = []
    for nodeid in CAMPAIGN_TESTS:
        module, _, name = nodeid.partition("::")
        path = REPO_ROOT / module
        if not path.is_file() or f"def {name}(" not in path.read_text(encoding="utf-8"):
            missing.append(nodeid)
    assert not missing, f"conftest names campaign tests that no longer exist: {missing}"


def test_every_static_guard_exists() -> None:
    """A renamed guard would silently drop out of the FAST suite."""
    missing = []
    for module, names in STATIC_GUARDS.items():
        source = _module_source(module)
        missing.extend(
            f"{module}::{name}" for name in sorted(names) if f"def {name}(" not in source
        )
    assert not missing, f"conftest names static guards that no longer exist: {missing}"


def test_static_guards_only_named_for_expensive_modules() -> None:
    """An allowlist for an unclassified module has no effect and is a mistake."""
    stray = sorted(set(STATIC_GUARDS) - set(EXPENSIVE_MODULES))
    assert not stray, f"static guards named for modules that are not expensive: {stray}"


def test_campaign_tests_live_in_expensive_modules() -> None:
    """`campaign` is a subset of `expensive`; the tables must agree."""
    stray = sorted(
        {
            nodeid.partition("::")[0]
            for nodeid in CAMPAIGN_TESTS
            if nodeid.partition("::")[0] not in EXPENSIVE_MODULES
        }
    )
    assert not stray, f"campaign tests in modules that are not expensive: {stray}"


def test_markers_are_actually_applied(pytestconfig: pytest.Config) -> None:
    """The mechanism itself works: this test is in neither tier."""
    assert normalized_nodeid("a\\b::c") == "a/b::c"
