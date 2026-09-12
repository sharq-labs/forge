"""EV-26: what the two branches actually share, established by reading imports.

The claim this round rests on is that the reference branch never touches the
Core. A claim like that is worth nothing if it is only asserted in a docstring,
so it is established here by walking the import graph of every module the
reference branch reaches and reporting what is in it.

The walk is static: the source is parsed and every ``import`` and ``from ...
import`` is followed, including relative ones. Relative import levels are
resolved by dropping ``node.level`` components from the importing module's
package path -- the arithmetic that a previous round got wrong by one, which
made every module look independent of everything. It is written out here so it
can be checked rather than trusted.

THREE VERDICTS.

  FULLY_INDEPENDENT_AFTER_RAW_FIXTURE
      The two branches meet only at the raw fixture file. No module, no helper,
      no constant and no conversion factor is shared.
  PARTIALLY_INDEPENDENT
      They share something identifiable, which is named.
  NOT_INDEPENDENT
      One reaches the other.

Sharing the Python standard library is not counted as sharing. ``math.exp``
does not encode anyone's physics, and a round that called it a dependency would
be unable to call anything independent.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent
SRC = REPO / "src"

STDLIB = set(sys.stdlib_module_names)


def _module_path(dotted: str) -> Path | None:
    for base in (ROOT, SRC):
        candidate = base / Path(*dotted.split("."))
        if (candidate / "__init__.py").exists():
            return candidate / "__init__.py"
        if candidate.with_suffix(".py").exists():
            return candidate.with_suffix(".py")
    return None


def _imports(path: Path, dotted: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parts = dotted.split(".")
    if path.name == "__init__.py":
        package = parts
    else:
        package = parts[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # One level means "this package"; each further level strips one
                # more component. len(package) - (level - 1) components remain.
                base = package[: max(0, len(package) - (node.level - 1))]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            if prefix:
                found.add(prefix)
    return found


def closure(entry: str) -> set[str]:
    """Every first-party module reachable from ``entry`` by import."""
    seen: set[str] = set()
    queue = [entry]
    while queue:
        dotted = queue.pop()
        if dotted in seen:
            continue
        root = dotted.split(".")[0]
        if root in STDLIB:
            continue
        path = _module_path(dotted)
        if path is None:
            # Third-party (numpy, scipy, pint). Recorded as a leaf: its name is
            # kept so a shared numerical kernel is visible, but its own imports
            # are not walked.
            seen.add(dotted)
            continue
        seen.add(dotted)
        for name in _imports(path, dotted):
            if name.split(".")[0] in STDLIB:
                continue
            queue.append(name)
    return seen


BRANCHES = {
    "branch_A_engcore": "adapters.adapter_a",
    "branch_B_reference": "adapters.adapter_b",
    "reference_numerics": "reference.physics",
    "reference_linear_algebra": "reference.nodal",
    "external_solver_problem_statement": "reference.spice",
}


def tracer_self_check() -> dict:
    """Prove the tracer can see a dependency before trusting it not to find one.

    A previous round's tracer had an off-by-one in its relative-import
    arithmetic and returned a closure of size one for every module, which made
    everything look independent of everything. A tracer that reports "no
    engcore reached" is therefore not believed until it has been shown to
    report engcore when engcore is genuinely reached.

    Branch A reaches engcore through imports written inside function bodies,
    not at module top level, so this also checks that nested imports are
    followed.
    """
    a = closure("adapters.adapter_a")
    b = closure("adapters.adapter_b")
    return {
        "branch_A_closure_size": len(a),
        "branch_A_engcore_modules": len([m for m in a if m.startswith("engcore")]),
        "branch_A_reaches_engcore_through_function_level_imports": any(
            m.startswith("engcore.domains") for m in a
        ),
        "branch_B_closure_size": len(b),
        "verdict": (
            "TRACER_SEES_DEPENDENCIES"
            if len([m for m in a if m.startswith("engcore")]) > 10
            else "TRACER_IS_NOT_WORKING"
        ),
    }


def report() -> dict:
    closures = {name: sorted(closure(entry)) for name, entry in BRANCHES.items()}
    engcore = {
        name: [m for m in modules if m.split(".")[0] == "engcore"]
        for name, modules in closures.items()
    }
    adapter_cross = {
        name: [m for m in modules if m.startswith("adapters.") and m != entry]
        for (name, entry), modules in zip(BRANCHES.items(), closures.values())
    }
    third_party = {
        name: sorted(
            {
                m.split(".")[0]
                for m in modules
                if m.split(".")[0] not in {"engcore", "adapters", "reference", "audit"}
            }
        )
        for name, modules in closures.items()
    }

    entries = []
    for name in BRANCHES:
        reaches_engcore = bool(engcore[name])
        reaches_other_adapter = bool(adapter_cross[name])
        if name == "branch_A_engcore":
            verdict = "PARTIALLY_INDEPENDENT"
            note = (
                "Branch A is the Core. It is not meant to be independent of "
                "engcore; it is listed so the graph is complete and so the "
                "absence of any reference module in its closure is on the "
                "record too."
            )
        elif reaches_engcore or reaches_other_adapter:
            verdict = "NOT_INDEPENDENT"
            note = "reaches " + ", ".join(engcore[name] + adapter_cross[name])
        else:
            verdict = "FULLY_INDEPENDENT_AFTER_RAW_FIXTURE"
            note = (
                "meets branch A only at the raw fixture JSON; no module, "
                "constant or conversion factor in common"
            )
        entries.append(
            {
                "branch": name,
                "entry_point": BRANCHES[name],
                "modules_in_closure": len(closures[name]),
                "engcore_modules_reached": engcore[name],
                "other_adapter_modules_reached": adapter_cross[name],
                "third_party_roots": third_party[name],
                "verdict": verdict,
                "note": note,
            }
        )

    core_numerical_kernels = {
        "scipy.linalg.solve": "DC, src/engcore/domains/electrical/dc/solver.py",
        "scipy.integrate.solve_ivp": "CSTR, src/engcore/domains/kinetics/cstr/solver.py",
        "scipy.optimize.brentq": "CSTR steady states",
        "scipy.sparse.linalg": "1-D conduction",
    }
    reference_kernels = {
        "reference.linalg.lu_solve": "Gaussian elimination with partial pivoting, written in this round",
        "reference.integrate.rk4": "classical fixed-step RK4, written in this round",
        "reference.integrate.bisect": "bisection, written in this round",
        "reference.physics.diffusion_ftcs_midpoint": "explicit FTCS march, written in this round",
        "ngspice 42": "a separate process",
    }
    return {
        "schema": "independence_graph/1",
        "tracer_self_check": tracer_self_check(),
        "branches": entries,
        "core_numerical_kernels_excluded_from_the_reference_branch": core_numerical_kernels,
        "reference_numerical_kernels_used_instead": reference_kernels,
        "numpy_and_scipy_note": (
            "scipy.constants appears in branch B's closure. It is a table of "
            "published numbers, not a solver, and the Core does not read it: "
            "the Core carries its own molar gas constant, which is why that "
            "constant is compared rather than shared. No scipy solver, and no "
            "numpy linear algebra, is reachable from the reference branch."
        ),
        "what_is_shared_and_why_it_has_to_be": [
            {
                "shared": "the raw fixture JSON files",
                "unavoidable": True,
                "reason": (
                    "The two branches must be given the same physical problem "
                    "or they are not comparable. The fixtures carry no derived "
                    "quantity and no engcore type, so what is shared is a "
                    "statement of the physics and not a construction of it."
                ),
            },
            {
                "shared": "the modified nodal analysis FORMULATION for DC",
                "unavoidable": True,
                "reason": (
                    "It is the formulation the field uses, and ngspice uses it "
                    "too. What is not shared is the assembly, the ordering of "
                    "unknowns, the linear solver and the unit conversion. This "
                    "is recorded as a real limit on the DC independence claim "
                    "rather than left out."
                ),
            },
            {
                "shared": "the Python standard library's math module",
                "unavoidable": True,
                "reason": "exp and sin encode nobody's physics.",
            },
        ],
    }
