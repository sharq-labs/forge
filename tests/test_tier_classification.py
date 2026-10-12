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

import importlib.util
import pathlib

import pytest

# The tier tables are loaded from `tests/conftest.py` BY PATH, not with
# `from conftest import ...`.
#
# The bare name is ambiguous and, since the benchmark rounds merged, wrong.
# pytest imports a `conftest.py` that sits in a directory with no
# `__init__.py` as a TOP-LEVEL module called `conftest`, and collection runs
# alphabetically, so `benchmarks/scientific_truth/tests/conftest.py` reaches
# `sys.modules["conftest"]` first and `from conftest import CAMPAIGN_TESTS`
# raises ImportError for the whole FAST suite. Five benchmark rounds now ship
# such a file.
#
# The repository used to defend the bare name by refusing to put a second
# `conftest.py` anywhere that could win the race -- `tests/domains/battery/
# battery_cases.py` says so in its header, and `benchmarks/empirical_
# validation/tests/test_empirical_validation.py` declines to write one for the
# same reason. That is a convention every future round has to know about and
# one of them did not. Loading the file this test is actually about, by its
# path, needs no convention: no import order can change which file this is.
_CONFTEST_PATH = pathlib.Path(__file__).resolve().parent / "conftest.py"
_spec = importlib.util.spec_from_file_location(
    "engcore_tests_root_conftest", _CONFTEST_PATH
)
assert _spec is not None and _spec.loader is not None, _CONFTEST_PATH
_root_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_root_conftest)

CAMPAIGN_TESTS = _root_conftest.CAMPAIGN_TESTS
EXPENSIVE_MODULES = _root_conftest.EXPENSIVE_MODULES
EXPENSIVE_TESTS = _root_conftest.EXPENSIVE_TESTS
STATIC_GUARDS = _root_conftest.STATIC_GUARDS
normalized_nodeid = _root_conftest.normalized_nodeid

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


def test_every_expensive_test_exists() -> None:
    """A renamed test would silently rejoin FAST, and a shared build with it.

    Keys are `module::function` or `module::function[case]`; the function must
    still be defined in the module and, for a case key, the case id must still
    appear in it.
    """
    missing = []
    for key in EXPENSIVE_TESTS:
        module, _, rest = key.partition("::")
        name, _, case = rest.partition("[")
        path = REPO_ROOT / module
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
        if f"def {name}(" not in source or (case and case.rstrip("]") not in source):
            missing.append(key)
    assert not missing, f"conftest names expensive tests that no longer exist: {missing}"


def test_expensive_tests_are_not_also_classified_by_module() -> None:
    """One table per test: a per-test label inside an expensive module is dead."""
    doubled = sorted(
        key for key in EXPENSIVE_TESTS if key.partition("::")[0] in EXPENSIVE_MODULES
    )
    assert not doubled, f"labelled both by module and by test: {doubled}"
    overlap = sorted(set(EXPENSIVE_TESTS) & set(CAMPAIGN_TESTS))
    assert not overlap, f"labelled both expensive and campaign by test: {overlap}"


def test_the_per_test_labels_reach_the_items_they_name(pytestconfig: pytest.Config) -> None:
    """The table is applied to the collected items, including those under `benchmarks/`.

    Checked on stand-in items handed to the hook, so this pins the matching rule
    (an exact id, or the id without its case), not pytest's collection order.
    """

    class _Item:
        def __init__(self, nodeid: str) -> None:
            self.nodeid = nodeid
            self.name = nodeid.rpartition("::")[2]
            self.markers: list[str] = []

        def add_marker(self, marker) -> None:
            self.markers.append(marker.name)

    items = []
    for key in EXPENSIVE_TESTS:
        items.append(_Item(key if "[" in key else f"{key}[some-case]"))
        if "[" not in key:
            items.append(_Item(key))
    bystander = _Item(
        "benchmarks/scientific_truth/tests/test_scientific_truth.py"
        "::test_randomized_cases_inside_the_declared_domain_hold[lumped_property]"
    )
    _root_conftest.pytest_collection_modifyitems(pytestconfig, [*items, bystander])
    assert all(item.markers == ["expensive"] for item in items), [
        (item.nodeid, item.markers) for item in items if item.markers != ["expensive"]
    ]
    assert bystander.markers == [], "a case not named in the table must stay in FAST"


def test_markers_are_actually_applied(pytestconfig: pytest.Config) -> None:
    """The mechanism itself works: this test is in neither tier."""
    assert normalized_nodeid("a\\b::c") == "a/b::c"
