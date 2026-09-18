"""Core V2 is additive-only: the proof obligations of docs/CORE_V2_API_DESIGN.md section 9.

Written before the V2 implementation. Every test here must hold on every V2 commit: a V2 that moved one V1
byte would not be an addition to Core V1 but a replacement of it.
"""

from __future__ import annotations

import importlib
import inspect
import json
import pathlib

from engcore import api_snapshot

REPO = pathlib.Path(__file__).resolve().parents[1]
V1_FROZEN_DIGEST = "c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929"
V1_FROZEN_COUNT = 194
V1_TOTAL_COUNT = 205


def _canonical(entry) -> bytes:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def test_the_v1_surface_is_the_v1_contract_plus_only_additive_changes():
    """AMENDED at Core Freeze V4 (I-29, R-65). Was: the live frozen digest IS `V1_FROZEN_DIGEST`.

    The 2026-09-16 re-audit moved it from `c80e6418` to `f18aa806` and moved nothing else: the same
    194 frozen symbols, the same 205 public ones, the same seven modules. `V1_FROZEN_DIGEST` stays
    where it is -- it is Core Freeze V1's record of its own commit -- and the digest equality is
    replaced by the claim V4 makes and proves: every difference from the V1 surface as V1 committed
    it is one of the additive kinds the owner allowed.
    """
    from tools.certification import core_freeze_v4

    stored = core_freeze_v4.stored_v1_frozen_snapshot(REPO)
    assert stored["digest"] == V1_FROZEN_DIGEST
    assert core_freeze_v4.additive_only_problems(stored["snapshot"], api_snapshot.frozen_only()) == []
    assert api_snapshot.frozen_only()["symbol_count"] == V1_FROZEN_COUNT
    assert api_snapshot.build()["symbol_count"] == V1_TOTAL_COUNT
    assert api_snapshot.build()["modules"] == list(api_snapshot.CANONICAL_MODULES)


def test_v2_adds_modules_and_changes_none_of_the_v1_seven():
    assert len(api_snapshot.CANONICAL_MODULES) == 7
    assert api_snapshot.V2_CANONICAL_MODULES[:7] == api_snapshot.CANONICAL_MODULES
    assert set(api_snapshot.V2_ADDED_MODULES).isdisjoint(api_snapshot.CANONICAL_MODULES)


def test_every_v1_frozen_entry_is_byte_identical_inside_the_v2_surface():
    pinned = json.loads((REPO / "tests" / "api" / "frozen_api_snapshot.json").read_text(encoding="utf-8"))
    v2 = {(e["module"], e["name"]): e for e in api_snapshot.frozen_only(api_snapshot.build(modules=api_snapshot.V2_CANONICAL_MODULES))["symbols"]}
    for entry in pinned["symbols"]:
        key = (entry["module"], entry["name"])
        assert key in v2, f"V1 frozen symbol {key} is missing from the V2 surface"
        assert _canonical(v2[key]) == _canonical(entry), f"V1 frozen symbol {key} changed shape in V2"


def test_the_v2_surface_minus_v1_is_only_the_added_modules():
    v1 = {(e["module"], e["name"]) for e in api_snapshot.build()["symbols"]}
    v2 = {(e["module"], e["name"]) for e in api_snapshot.build(modules=api_snapshot.V2_CANONICAL_MODULES)["symbols"]}
    assert v1 <= v2
    assert {module for module, _ in v2 - v1} <= set(api_snapshot.V2_ADDED_MODULES)


def test_no_v1_canonical_module_export_list_changed():
    """By module, against the pinned full V1 snapshot, including experimental names."""
    pinned = json.loads((REPO / "tests" / "api" / "full_api_snapshot.json").read_text(encoding="utf-8"))
    expected: dict[str, set[str]] = {}
    for entry in pinned["symbols"]:
        expected.setdefault(entry["module"], set()).add(entry["name"])
    for module_name in api_snapshot.CANONICAL_MODULES:
        exported = set(getattr(importlib.import_module(module_name), "__all__", ()))
        assert exported == expected[module_name], f"{module_name}.__all__ changed: {sorted(exported ^ expected[module_name])}"


def test_the_v2_additions_add_no_exception_root():
    from engcore.uq import UQProblemError

    for module_name in api_snapshot.V2_ADDED_MODULES:
        module = importlib.import_module(module_name)
        for name in getattr(module, "__all__", ()):
            value = getattr(module, name)
            if inspect.isclass(value) and issubclass(value, BaseException):
                assert issubclass(value, UQProblemError), f"{module_name}.{name} is a new exception root"


def test_the_v2_additions_import_nothing_above_their_layer():
    """hybrid_uq may reach scientific, inference and uq; never adequacy, execution, studies or non-Core packages."""
    import ast

    forbidden = {"adequacy", "execution", "studies", "domains", "systems", "sria", "design", "mcp"}
    root = REPO / "src" / "engcore" / "hybrid_uq"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    parts = node.module.split(".")
                    if parts[0] == "engcore" and len(parts) > 1:
                        names.append(parts[1])
                elif node.level >= 2 and node.module:
                    names.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                names += [a.name.split(".")[1] for a in node.names if a.name.startswith("engcore.") and "." in a.name]
            offenders += [f"{path.name} -> {n}" for n in names if n in forbidden]
    assert not offenders, offenders
