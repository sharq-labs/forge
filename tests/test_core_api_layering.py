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
    "hybrid_uq",      # 4 -- Core V2: routed grid / local-Gaussian uncertainty
    "adequacy",       # 5 -- held-out scoring, evidence identity
    "execution",      # 6 -- the sweep engine
    "studies",        # 7 -- orchestration
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
    """Core V2 is additive: its canonical modules are the V1 seven plus the V2
    additions, and together they are every Core layer."""
    assert set(api_snapshot.V2_CANONICAL_MODULES) == {
        f"engcore.{name}" for name in LAYERS
    }
    assert api_snapshot.V2_CANONICAL_MODULES[: len(api_snapshot.CANONICAL_MODULES)] == (
        api_snapshot.CANONICAL_MODULES
    )


# =====================================================================
# PART M -- every package under engcore is classified, none by default
# =====================================================================

#: Packages that live under `engcore` and are deliberately NOT part of the
#: frozen Core API, each with the reason it is out of scope. This is the half
#: of the classification that nothing else states: `CANONICAL_MODULES` says
#: what IS the Core, and without this a new directory appearing under
#: `src/engcore/` would be neither frozen nor experimental nor excluded -- it
#: would simply be unclassified, which is how an accidental public surface
#: starts.
NON_CORE_PACKAGES = {
    "domainpacks": (
        "plugin discovery, validation, registration and provenance infrastructure; "
        "above the Scientific Core and deliberately outside the frozen scientific API"
    ),
    "domains": (
        "scientific domains built ON the Core. Read-only for this round by "
        "standing instruction, and above the Core rather than in it"
    ),
    "systems": "cross-domain compositions, built on domains",
    "sria": "the evidence / admission / assurance / campaign layer, above Core",
    "design": "design generation and design memory, above Core",
    "credibility": (
        "scientific credibility/V&V reports and the SRIA evidence bridge; "
        "above the Core and independent of the MCP transport adapter"
    ),
    "mcp": "the tool-server adapter -- an outer consumer, not scientific authority",
    "claims": (
        "the scientific intelligence layer -- claim contract, capability registry, "
        "routing, planning and assessment. EXPERIMENTAL, above credibility/SRIA, "
        "and forbidden from depending on MCP transport"
    ),
    "assembly": "system/multiphysics assembly above the frozen Scientific Core",
    "compositionpacks": "composition plugin manifests and registry infrastructure above Core",
    "executionpacks": "execution-provider pack manifests and registry infrastructure above Core",
    "planning": "production planning and provider selection above the frozen Scientific Core",
    "product": "product-facing scientific gateway/orchestration above Core",
    "materials": (
        "material identity/state and sourced property resolution built on "
        "scientific.knowledge; above the frozen Core"
    ),
    "numerical": (
        "provider-neutral numerical execution (NumPy/SciPy/SymPy/PETSc/SUNDIALS "
        "providers) beneath the Core solver protocol; computes, holds no authority"
    ),
    "spatial": (
        "tagged meshes, framed fields, mappings and material binding on the Core "
        "field/mesh records; Gmsh/meshio are providers"
    ),
    "pde": (
        "provider-neutral PDE/FEM contracts and the FEniCSx provider; the solver "
        "computes, Forge keeps identity/applicability/provenance authority"
    ),
    "coupling": (
        "adapters that turn PDE/numerical providers and BIG 7 fields into participants "
        "of the existing multiphysics runtime; no new coupling authority"
    ),
    "scenarios": (
        "transient/scenario contracts currently outside the frozen Core surface; "
        "promotion requires an explicit version/freeze decision"
    ),
}


def package_directories() -> set[str]:
    """Real packages on disk, which is the only list that cannot go stale."""
    root = SRC / "engcore"
    return {
        path.name
        for path in root.iterdir()
        if path.is_dir()
        and not path.name.startswith(("_", "."))
        and (path / "__init__.py").exists()
    }


def test_every_package_under_engcore_is_classified_core_or_not():
    found = package_directories()
    classified = set(LAYERS) | set(NON_CORE_PACKAGES)
    unclassified = found - classified
    assert not unclassified, (
        f"{sorted(unclassified)} live under src/engcore/ and are neither a "
        f"Core layer nor a recorded non-Core package. A package with no "
        f"classification is a public surface nobody decided to have: add it to "
        f"LAYERS (and to CANONICAL_MODULES, and to the frozen snapshot) or to "
        f"NON_CORE_PACKAGES with the reason it is out of scope"
    )
    missing = classified - found
    assert not missing, f"classified but absent from disk: {sorted(missing)}"


def test_no_non_core_package_is_in_the_frozen_api():
    """The classification has to MEAN something, so this checks it holds."""
    frozen_modules = {e["module"] for e in api_snapshot.frozen_only()["symbols"]}
    for name in NON_CORE_PACKAGES:
        assert f"engcore.{name}" not in frozen_modules, (
            f"engcore.{name} is recorded as non-Core but appears in the frozen "
            f"contract"
        )


#: The only deliberate Core -> non-Core contract edges.
#:
#: `studies -> domains`: orchestration composes domain implementations.
#: `execution -> scenarios`: the transient runtime consumes declarative,
#: domain-independent scenario value objects (schedules, events, stop
#: conditions, QOIs). Scenarios carry no model/solver selection or scientific
#: authority, and remain outside the frozen Core API for now.
#:
#: These are exact package-level allowances, not a general escape hatch.
CORE_NON_CORE_ALLOWANCES = {
    "studies": {"domains"},
    "execution": {"scenarios"},
}


def test_no_core_package_imports_a_non_core_one():
    """The direction that would invert the whole layering.

    `scientific` importing `domains` would make the Core depend on the domains
    built on top of it, and the read-only boundary would become unenforceable.
    """
    offenders = []
    for package, path in core_modules():
        checked = set(NON_CORE_PACKAGES) - CORE_NON_CORE_ALLOWANCES.get(
            package, set()
        )
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            reached = None
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                head = (node.module or '').split('.')
                if len(head) >= 2 and head[0] == 'engcore' and head[1] in checked:
                    reached = node.module
            elif isinstance(node, ast.ImportFrom) and node.level >= 1:
                # `from ..domains.x import y` inside engcore/studies/tcr.py:
                # level 2 at depth 0 leaves engcore/studies and lands on a
                # sibling of it, which is where a non-Core name can appear.
                depth = len(path.relative_to(SRC / 'engcore' / package).parts) - 1
                if node.level - 1 > depth and (node.module or '').split('.')[0] in checked:
                    reached = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    head = alias.name.split('.')
                    if len(head) >= 2 and head[0] == 'engcore' and head[1] in checked:
                        offenders.append(str(path.relative_to(SRC)) + ' -> ' + alias.name)
            if reached is not None:
                offenders.append(str(path.relative_to(SRC)) + ' -> ' + reached)
    assert not offenders, offenders


def test_core_to_non_core_allowances_are_exact_and_narrow():
    """The two deliberate contract edges may not silently widen."""
    assert CORE_NON_CORE_ALLOWANCES == {
        "studies": {"domains"},
        "execution": {"scenarios"},
    }
    reached: dict[str, set[str]] = {
        package: set() for package in CORE_NON_CORE_ALLOWANCES
    }
    for package, path in core_modules():
        if package not in reached:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            head = None
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                parts = (node.module or "").split(".")
                if len(parts) >= 2 and parts[0] == "engcore":
                    head = parts[1]
            elif isinstance(node, ast.ImportFrom) and node.level >= 1:
                depth = len(
                    path.relative_to(SRC / "engcore" / package).parts
                ) - 1
                if node.level - 1 > depth:
                    head = (node.module or "").split(".")[0]
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    if len(parts) >= 2 and parts[0] == "engcore":
                        candidate = parts[1]
                        if candidate in NON_CORE_PACKAGES:
                            reached[package].add(candidate)
            if head in NON_CORE_PACKAGES:
                reached[package].add(head)

    for package, allowed in CORE_NON_CORE_ALLOWANCES.items():
        assert reached[package] <= allowed, (
            f"{package} reaches undeclared non-Core package(s): "
            f"{sorted(reached[package] - allowed)}"
        )
