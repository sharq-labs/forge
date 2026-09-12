"""What is actually importable from each Core package, and what leaks.

PART A and PART B. The instruction was not to assume `__all__` is correct, so
this reads the NAMESPACE rather than the declaration and reports the difference
between them.

Three populations per package:

``declared``
    what ``__all__`` says.
``reachable``
    every public (non-underscore) name actually bound in the package
    namespace after import -- which is what a caller can write
    ``from engcore.x import y`` for, whatever ``__all__`` says.
``leaked``
    reachable minus declared. Every one of these is accidental public surface
    unless somebody decided otherwise, and the decision has to be recorded.

Leaks are further split by WHY they are there, because the remedy differs:

``submodule``
    a module object bound by ``from .x import y`` as a side effect. Harmless to
    read, but it means ``engcore.pkg.x`` is reachable without importing it, and
    a caller can then reach anything inside it.
``stdlib/third-party``
    an imported module or symbol from outside the package, bound at module
    scope. This is how ``json``, ``math`` and friends become "public API".
``local``
    a helper defined in the package that nobody meant to export.

    python -X utf8 benchmarks/core_api_stability/audit/inventory.py
"""

from __future__ import annotations

import importlib
import inspect
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

#: The Core packages this sprint governs. `domains` is READ-ONLY and excluded
#: from classification -- it is not Core API. `mcp`, `sria`, `design`,
#: `systems` are product/application layers above the Core and are reported but
#: not frozen by this round.
CORE_PACKAGES = (
    "engcore.scientific",
    "engcore.data",
    "engcore.inference",
    "engcore.uq",
    "engcore.adequacy",
    "engcore.execution",
    "engcore.studies",
)

ABOVE_THE_CORE = ("engcore.mcp", "engcore.sria", "engcore.design", "engcore.systems")


def classify_leak(package, name, value):
    """Why is this name in the namespace when `__all__` does not claim it."""
    if isinstance(value, types.ModuleType):
        if value.__name__.startswith(package.__name__ + "."):
            return "submodule"
        return "imported-module"
    origin = getattr(value, "__module__", None)
    if origin is None:
        return "value"
    if origin.startswith(package.__name__.split(".")[0]):
        return "local"
    return "third-party-symbol"


def kind_of(value):
    if inspect.isclass(value):
        import enum

        if issubclass(value, BaseException):
            return "exception"
        if issubclass(value, enum.Enum):
            return "enum"
        return "class"
    if inspect.isfunction(value) or inspect.isbuiltin(value):
        return "function"
    if isinstance(value, types.ModuleType):
        return "module"
    return type(value).__name__


def survey(name):
    package = importlib.import_module(name)
    declared = tuple(getattr(package, "__all__", ()) or ())
    reachable = tuple(sorted(n for n in vars(package) if not n.startswith("_")))
    leaked = tuple(n for n in reachable if n not in set(declared))

    missing = tuple(n for n in declared if not hasattr(package, n))

    leaks = []
    for n in leaked:
        value = getattr(package, n)
        leaks.append({
            "name": n,
            "why": classify_leak(package, n, value),
            "kind": kind_of(value),
            "origin": getattr(value, "__module__", None) or getattr(value, "__name__", None),
        })

    return {
        "package": name,
        "declared_count": len(declared),
        "reachable_count": len(reachable),
        "declared": list(declared),
        "leaked": leaks,
        "declared_but_absent": list(missing),
    }


def main() -> int:
    report = {"core": [], "above_the_core": []}

    print("=" * 78)
    print("CORE PACKAGES -- governed by this sprint")
    print("=" * 78)
    print(f"{'package':<26} {'__all__':>8} {'reachable':>10} {'leaked':>7}")
    print("-" * 78)
    total_declared = total_leaked = 0
    for name in CORE_PACKAGES:
        row = survey(name)
        report["core"].append(row)
        total_declared += row["declared_count"]
        total_leaked += len(row["leaked"])
        print(f"{name:<26} {row['declared_count']:>8} {row['reachable_count']:>10} "
              f"{len(row['leaked']):>7}")
        if row["declared_but_absent"]:
            print(f"    !! __all__ names that do not exist: {row['declared_but_absent']}")

    print(f"\n  totals: {total_declared} declared, {total_leaked} leaked\n")

    print("=" * 78)
    print("LEAKED NAMES -- accidental public surface, by package")
    print("=" * 78)
    for row in report["core"]:
        if not row["leaked"]:
            continue
        print(f"\n{row['package']}  ({len(row['leaked'])})")
        by_why = {}
        for leak in row["leaked"]:
            by_why.setdefault(leak["why"], []).append(leak)
        for why in sorted(by_why):
            names = ", ".join(f"{v['name']}({v['kind']})" for v in by_why[why])
            print(f"    {why:<20} {names}")

    print("\n" + "=" * 78)
    print("ABOVE THE CORE -- reported, not frozen by this round")
    print("=" * 78)
    for name in ABOVE_THE_CORE:
        try:
            row = survey(name)
        except Exception as exc:  # noqa: BLE001 - reported
            print(f"{name:<26} import failed: {type(exc).__name__}: {exc}")
            continue
        report["above_the_core"].append(row)
        print(f"{name:<26} {row['declared_count']:>8} declared, "
              f"{len(row['leaked']):>3} leaked")

    out = ROOT / "benchmarks" / "core_api_stability" / "INVENTORY.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(json.dumps(report, indent=2, sort_keys=True).encode("utf-8"))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
