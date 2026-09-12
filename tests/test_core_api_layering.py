"""Parts C and L: canonical import paths, package identity, and layer direction.

Two properties that are easy to lose and hard to notice afterwards:

**One object, one identity.** ``src.engcore.x`` and ``engcore.x`` are both
importable in this checkout -- ``pythonpath = ["src", "."]`` in pyproject makes
``src`` a package too, and eleven SHA-256-pinned experiment files still spell
it that way. If the same class is loaded under both names, Python creates TWO
classes: ``isinstance`` fails across them, and a record built by one fails a
type check in the other. The repository already holds both halves of that rule
in ``test_trust_boundary_package_identity.py``; this file states the API-facing
half -- every frozen symbol resolves to exactly one class object.

**The layer direction.** Derived from the actual import graph, not from a
diagram, because a re-export in an ``__init__`` creates a real edge that no
diagram shows.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import sys

import pytest

from engcore import api_snapshot

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

#: The permitted direction. A package may import anything BELOW it and nothing
#: above. Index in this tuple is the layer number.
LAYERS = (
    "scientific",     # 0 -- primitives: units, results, validation, twins, fields
    "data",           # 1 -- the data boundary
    "inference",      # 2 -- admission, observations, split, grid, calibration
    "uq",             # 3 -- posterior-predictive uncertainty
    "adequacy",       # 4 -- held-out scoring, evidence identity
    "execution",      # 5 -- the sweep engine
    "studies",        # 6 -- orchestration
)
LAYER_OF = {name: index for index, name in enumerate(LAYERS)}

#: `execution` is deliberately OFF the inference ladder rather than on it. Its
#: own `__init__` says so: "Not part of the Scientific Core: this layer runs the
#: core's operations, it declares none of its own contracts." So it may import
#: the primitives and must not import `inference`, `uq` or `adequacy` -- a sweep
#: engine that knew what a posterior was would be a scientific layer.
EXECUTION_MAY_IMPORT = {"scientific", "data"}

#: Who may import `execution`. Only the top: orchestration composes the sweep
#: with the inference layers, which is exactly the arrangement Sprint 9 chose
#: when it kept `inference.calibration` free of an execution dependency by
#: having it take a caller-supplied forward evaluator. `studies` supplying one
#: backed by `run_sweep` is the correct direction; `inference` importing
#: `run_sweep` would have been the inversion.
MAY_IMPORT_EXECUTION = {"studies"}


def core_modules():
    for package in LAYERS:
        root = SRC / "engcore" / package
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" not in path.parts:
                yield package, path


def imported_core_packages(path: pathlib.Path, package: str) -> set[str]:
    """Which sibling Core packages this module imports, absolute or relative."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    depth = len(path.relative_to(SRC / "engcore" / package).parts) - 1
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                parts = node.module.split(".")
                if parts[0] == "engcore" and len(parts) > 1 and parts[1] in LAYER_OF:
                    found.add(parts[1])
            elif node.level > 0:
                # `from ..x import y` at depth d reaches up (level - 1) packages
                # from this module's own package.
                if node.level - 1 > depth and node.module:
                    found.add(node.module.split(".")[0])
                elif node.level - 1 == depth + 1 and node.module:
                    found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "engcore" and len(parts) > 1 and parts[1] in LAYER_OF:
                    found.add(parts[1])
    return {f for f in found if f in LAYER_OF and f != package}


# =====================================================================
# PART L -- layering
# =====================================================================

def test_no_core_package_imports_one_above_it():
    """The rule, checked against every module rather than the package __init__."""
    violations = []
    for package, path in core_modules():
        for imported in imported_core_packages(path, package):
            if package == "execution":
                if imported not in EXECUTION_MAY_IMPORT:
                    violations.append(
                        f"{path.relative_to(SRC)} : execution -> {imported}"
                    )
                continue
            if imported == "execution":
                if package not in MAY_IMPORT_EXECUTION:
                    violations.append(
                        f"{path.relative_to(SRC)} : {package} -> execution"
                    )
                continue
            if LAYER_OF[imported] >= LAYER_OF[package]:
                violations.append(
                    f"{path.relative_to(SRC)} : {package}(L{LAYER_OF[package]}) "
                    f"-> {imported}(L{LAYER_OF[imported]})"
                )
    assert not violations, "forbidden upward dependencies:\n  " + "\n  ".join(violations)


def test_scientific_imports_no_other_core_package():
    """The bottom layer must stay the bottom layer."""
    reached = set()
    for package, path in core_modules():
        if package == "scientific":
            reached |= imported_core_packages(path, package)
    assert not reached, f"scientific reaches upward into {sorted(reached)}"


def test_inference_does_not_import_orchestration():
    """Sprint 9's rule, kept: the calibration layer takes a forward evaluator
    rather than importing the sweep, and knows nothing about studies."""
    reached = set()
    for package, path in core_modules():
        if package == "inference":
            reached |= imported_core_packages(path, package)
    assert "studies" not in reached
    assert "execution" not in reached
    assert "uq" not in reached and "adequacy" not in reached


def test_the_import_graph_has_no_cycles():
    edges = {}
    for package, path in core_modules():
        edges.setdefault(package, set()).update(imported_core_packages(path, package))

    visiting, done = set(), set()

    def walk(node, trail):
        if node in visiting:
            pytest.fail(f"import cycle: {' -> '.join(trail + [node])}")
        if node in done:
            return
        visiting.add(node)
        for nxt in sorted(edges.get(node, ())):
            walk(nxt, trail + [node])
        visiting.discard(node)
        done.add(node)

    for package in LAYERS:
        walk(package, [])


# =====================================================================
# PART C -- canonical imports and package identity
# =====================================================================

def test_every_frozen_symbol_imports_from_its_canonical_module():
    for entry in api_snapshot.build()["symbols"]:
        module = importlib.import_module(entry["module"])
        assert hasattr(module, entry["name"]), f"{entry['module']}.{entry['name']}"


def test_a_symbol_reached_two_ways_is_the_same_object():
    """`engcore.x.Y` and `engcore.x.sub.Y` must be one object, not two.

    A re-export that rebuilt the class would give two types that fail
    `isinstance` against each other while looking identical in every log line.
    """
    checked = 0
    for entry in api_snapshot.build()["symbols"]:
        defined_in = entry.get("defined_in")
        if not defined_in or not defined_in.startswith("engcore."):
            continue
        exported = getattr(importlib.import_module(entry["module"]), entry["name"])
        deep = getattr(importlib.import_module(defined_in), entry["name"], None)
        if deep is None:
            continue
        assert exported is deep, (
            f"{entry['module']}.{entry['name']} is not the same object as "
            f"{defined_in}.{entry['name']}"
        )
        checked += 1
    assert checked > 100, f"only {checked} symbols were cross-checked"


def test_the_src_spelling_is_not_a_second_package_identity():
    """`src.engcore.x` must resolve to the SAME module object as `engcore.x`.

    `src/__init__.py` exists to make that true -- the repository's own note
    calls it "an alias for the canonical engcore modules, never a second copy".
    If it ever became a second copy, every frozen class would have a twin.
    """
    import engcore.scientific.units.quantity as canonical

    try:
        import src.engcore.scientific.units.quantity as aliased
    except ImportError:
        pytest.skip("the `src.` spelling is not importable in this environment")

    assert aliased is canonical, "src.engcore is a SECOND package identity"
    assert aliased.Quantity is canonical.Quantity
    value = canonical.Quantity(1.0, "ohm")
    assert isinstance(value, aliased.Quantity)


def test_no_frozen_class_is_defined_under_a_src_prefixed_module():
    """A frozen symbol whose `__module__` starts with `src.` would serialize
    and repr under a path that does not exist in the wheel."""
    offenders = [
        f"{e['module']}.{e['name']} defined in {e['defined_in']}"
        for e in api_snapshot.build()["symbols"]
        if str(e.get("defined_in", "")).startswith("src.")
    ]
    assert not offenders, offenders


def test_the_canonical_modules_are_exactly_the_core_packages():
    assert set(api_snapshot.CANONICAL_MODULES) == {
        f"engcore.{name}" for name in LAYERS
    }
