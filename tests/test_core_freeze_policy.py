"""Part T: the freeze policy document, made executable.

`docs/CORE_FREEZE_POLICY.md` states what is frozen, how many symbols there are,
what digest they hash to, which guard catches which compatibility event, and
which packages are out of scope. A policy document is worth exactly as much as
its agreement with the code, and prose does not fail a build.

So this file parses the document and checks it. Every number, digest, module
name, file path, classification and guard-test name in the policy is verified
to exist and to match. Editing prose is free; editing a fact is a failure until
the code agrees -- and, more usefully, changing the CODE fails here until the
policy is updated, which is the direction that actually goes stale.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from engcore import api_snapshot

REPO = pathlib.Path(__file__).resolve().parents[1]
POLICY = REPO / "docs" / "CORE_FREEZE_POLICY.md"


@pytest.fixture(scope="module")
def text() -> str:
    assert POLICY.exists(), f"the freeze policy is missing: {POLICY}"
    return POLICY.read_text(encoding="utf-8")


def state_table(text: str) -> dict[str, str]:
    """The FROZEN-STATE table, parsed rather than eyeballed."""
    # Split on the next HEADING, not on '---': the first '---' inside the
    # section is the table's own separator row, which would leave the header
    # and nothing else.
    block = text.split("## FROZEN-STATE", 1)[1].split("\n## ", 1)[0]
    values: dict[str, str] = {}
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] not in ("key", "---"):
            values[cells[0]] = cells[1].strip("`")
    return values


# =====================================================================
# The stated state must be the actual state
# =====================================================================

def test_the_policy_states_the_real_frozen_digest(text):
    """The one number a consumer would quote in a bug report."""
    assert state_table(text)["frozen digest"] == api_snapshot.frozen_digest()


def test_the_policy_states_the_real_symbol_counts(text):
    table = state_table(text)
    snapshot = api_snapshot.build()
    assert int(table["frozen symbols"]) == api_snapshot.frozen_only()["symbol_count"]
    assert int(table["experimental symbols"]) == snapshot["experimental_count"]
    assert int(table["total public symbols"]) == snapshot["symbol_count"]
    assert int(table["deprecated symbols"]) == len(api_snapshot.DEPRECATED_SYMBOLS)


def test_the_policy_states_the_real_schema(text):
    assert state_table(text)["schema"] == api_snapshot.SCHEMA


def test_the_stated_counts_add_up(text):
    """Internal arithmetic, so the table cannot be half-updated.

    A frozen count and an experimental count that do not sum to the total is a
    table somebody edited one line of.
    """
    table = state_table(text)
    assert (
        int(table["frozen symbols"]) + int(table["experimental symbols"])
        == int(table["total public symbols"])
    )


def test_the_pinned_file_the_policy_names_is_the_one_that_is_pinned(text):
    assert "tests/api/frozen_api_snapshot.json" in text
    pinned = json.loads(
        (REPO / "tests" / "api" / "frozen_api_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    assert pinned["symbol_count"] == int(state_table(text)["frozen symbols"])


# =====================================================================
# The surfaces it names must be the surfaces that exist
# =====================================================================

def test_the_policy_names_all_seven_canonical_modules(text):
    for module in api_snapshot.CANONICAL_MODULES:
        assert module in text, f"{module} is a Core module the policy omits"


def test_the_policy_names_no_module_that_is_not_canonical(text):
    """The direction that would quietly promise something.

    A policy listing `engcore.sria` among the frozen modules would extend the
    contract by prose.
    """
    # Dunders excluded: 'engcore.__file__' appears in section 7 inside an
    # explanation of how the wheel probe proves provenance, not as a claim
    # about a module.
    listed = {
        name for name in re.findall(r"\bengcore\.[a-z_]+\b", text)
        if not name.split(".")[1].startswith("_")
    }
    known = set(api_snapshot.CANONICAL_MODULES) | {
        f"engcore.{name}" for name in ("domains", "systems", "sria", "design", "mcp")
    } | {"engcore.api_snapshot", "engcore.execution.run_sweep"}
    assert listed <= known, listed - known


def test_the_policy_names_every_non_core_package(text):
    layering = _load_layering()
    for name in layering.NON_CORE_PACKAGES:
        assert f"`{name}`" in text, (
            f"{name} is an unclassified-by-the-policy package under engcore"
        )


def test_the_policy_states_the_real_round_trip_count(text):
    """Section 6's serialization number, checked against the inventory."""
    match = re.search(r"`(\d+)` frozen records round-trip", text)
    assert match, "the policy no longer states how many records round-trip"
    stated = int(match.group(1))
    actual = sum(
        1 for entry in api_snapshot.frozen_only()["symbols"]
        if _has_round_trip(entry)
    )
    assert stated == actual, f"policy says {stated}, inventory has {actual}"


def _has_round_trip(entry: dict) -> bool:
    import importlib

    module = importlib.import_module(entry["module"])
    value = getattr(module, entry["name"], None)
    return (
        isinstance(value, type)
        and hasattr(value, "to_dict")
        and hasattr(value, "from_dict")
    )


# =====================================================================
# Every guard it cites must exist and be a real test
# =====================================================================

def guard_names(text: str) -> set[str]:
    return set(re.findall(r"`(test_[a-z0-9_]+)`", text))


def collected_test_names() -> set[str]:
    names: set[str] = set()
    for path in (REPO / "tests").glob("test_core_*.py"):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"def (test_[a-z0-9_]+)\(", line)
            if match:
                names.add(match.group(1))
    return names


def test_every_guard_the_policy_cites_exists(text):
    """A policy citing a test that was renamed or deleted is describing a
    guarantee nothing enforces."""
    cited, actual = guard_names(text), collected_test_names()
    missing = cited - actual
    assert not missing, (
        f"the policy cites {sorted(missing)} as guards, and no such test "
        f"exists under tests/test_core_*.py"
    )


def test_the_policy_cites_a_guard_for_every_compatibility_event(text):
    """The event table must not contain a row with an empty guard cell."""
    block = text.split("## 3. What counts as a compatibility event", 1)[1]
    block = block.split("## 4.", 1)[0]
    rows = [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in block.splitlines()
        if line.strip().startswith("|")
    ]
    rows = [r for r in rows if len(r) == 2 and r[0] not in ("event", "---")]
    assert len(rows) >= 10, f"only {len(rows)} compatibility events listed"
    for event, guard in rows:
        assert guard, f"'{event}' has no guard"
        assert guard.startswith("`"), f"'{event}' cites {guard!r}, not a guard"


def test_the_file_paths_the_policy_names_all_exist(text):
    referenced = set(re.findall(r"`((?:tests|benchmarks|src|docs)/[\w./]+)`", text))
    assert referenced, "the policy names no files at all"
    missing = [p for p in referenced if not (REPO / p).exists()]
    assert not missing, missing


# =====================================================================
# Claims the policy makes about itself
# =====================================================================

def test_the_policy_states_the_real_exception_root_count(text):
    """Section 9's "seven roots" is a finding, not a round number."""
    assert "**seven** exception roots" in text
    contracts = _load_contracts()
    assert len(contracts.EXCEPTION_ROOTS) == 7


def test_the_regeneration_command_in_the_policy_is_the_working_one(text):
    """Following step 4 must produce the pinned file, not destroy it.

    This exact instruction was wrong once: it omitted `--frozen`, so following
    it would have written the FULL snapshot over the frozen contract.
    """
    assert (
        "python -X utf8 -m engcore.api_snapshot --frozen "
        "> tests/api/frozen_api_snapshot.json"
    ) in text


def test_the_policy_declares_the_deprecation_fields_it_requires(text):
    for field in api_snapshot.DEPRECATION_FIELDS:
        assert f"`{field}`" in text, f"the policy never mentions {field}"


def test_the_policy_does_not_claim_a_single_exception_base(text):
    """The claim that was FALSE and is the reason section 9 exists."""
    lowered = text.lower()
    assert "single core base" not in lowered
    assert "one exception base" not in lowered


# ---------------------------------------------------------------------

def _load_layering():
    return _load_by_path("layering_guard", REPO / "tests" / "test_core_api_layering.py")


def _load_contracts():
    return _load_by_path("contract_guard", REPO / "tests" / "test_core_api_contracts.py")


def _load_by_path(name: str, path: pathlib.Path):
    """Loaded BY PATH, for the standing reason in this repo.

    Five benchmark rounds ship a `conftest.py` in a directory with no
    `__init__.py`, so they are importable as top-level `conftest` and
    alphabetical collection decides which one wins. Importing a sibling test
    module by name here would be subject to the same accident.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
