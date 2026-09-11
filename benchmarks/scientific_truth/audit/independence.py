"""ST-12: are the routes claimed independent actually independent?

Two implementations that share a helper, a constant, a discretization or a
preprocessing step do not provide independent evidence: if the shared part is
wrong they agree, confidently, and their agreement is worth nothing. This
module traces what each route actually imports and reports the overlap.

The trace is done on the MODULE IMPORT GRAPH rather than on docstrings,
because a claim of independence written in a comment is exactly the sort of
thing this round exists to disbelieve.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
SRC = REPO / "src"


def _module_path(dotted: str) -> pathlib.Path | None:
    candidate = SRC / (dotted.replace(".", "/") + ".py")
    if candidate.exists():
        return candidate
    package = SRC / dotted.replace(".", "/") / "__init__.py"
    return package if package.exists() else None


def _imports_of(path: pathlib.Path, module: str) -> set[str]:
    """Every module ``module`` imports, with relative imports resolved.

    RELATIVE IMPORT ARITHMETIC, because getting it wrong silently reports
    everything as independent. For a module of n dotted parts, ``from ....x
    import y`` at level L resolves against the first (n - L) parts: level 1 is
    the module's own package, level 2 its parent, and so on. A first pass of
    this audit used (n - L + 1) and found no first-party imports anywhere,
    which made all five route pairs look trivially independent.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = module.split(".")
                base = parts[: max(0, len(parts) - node.level)]
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            if target:
                found.add(target)
    return found


def closure(dotted: str, *, limit: int = 400) -> set[str]:
    """Every first-party module reachable from ``dotted`` by import."""
    seen: set[str] = set()
    stack = [dotted]
    while stack and len(seen) < limit:
        current = stack.pop()
        if current in seen:
            continue
        path = _module_path(current)
        if path is None:
            continue
        seen.add(current)
        for target in _imports_of(path, current):
            if target.startswith("engcore") and target not in seen:
                stack.append(target)
    return seen


#: What a shared module actually CARRIES. Sharing is not one thing: two routes
#: that share an exception class share nothing scientific, two that share a
#: declaration object share the problem statement but not its solution, and two
#: that share a discretization share the answer. Classified explicitly here so
#: a reader can disagree with the classification rather than with a verdict.
MODULE_ROLE = {
    "errors": ("EXCEPTION_TYPES", "raises the same exception classes; carries no equation"),
    "derived_context": ("NAMESPACE_MACHINERY", "reserved-name bookkeeping; carries no equation"),
    "repair": ("HINT_MACHINERY", "repair-hint inversion tables; carries no equation"),
    "problem": ("PROBLEM_STATEMENT", "the declaration and the model record: the same question, not the same answer"),
    "circuit": ("PROBLEM_STATEMENT", "the circuit declaration and its structural validation"),
    "components": ("PROBLEM_STATEMENT", "element declarations and their admissibility rules"),
    "models": ("PROBLEM_STATEMENT", "published model records"),
    "validation": ("POST_SOLVE_CHECKS", "checks run on a result; does not produce the result"),
    "context": ("DERIVED_QUANTITIES", "derived validity quantities -- CARRIES EQUATIONS"),
    "mna": ("NUMERICAL_KERNEL", "the modified-nodal-analysis stamp -- CARRIES THE ANSWER"),
    "solver": ("NUMERICAL_KERNEL", "the solve itself -- CARRIES THE ANSWER"),
    "reference": ("ORACLE", "the closed-form reference an implementation is judged against"),
    "conduction1d_schemes": ("NUMERICAL_KERNEL", "an alternative discretization -- CARRIES THE ANSWER"),
}

#: Roles whose sharing materially weakens an independence claim.
MATERIAL_ROLES = {"NUMERICAL_KERNEL", "DERIVED_QUANTITIES"}


def _role(module: str) -> tuple[str, str]:
    leaf = module.rsplit(".", 1)[-1]
    return MODULE_ROLE.get(leaf, ("UNCLASSIFIED", "not classified by this audit"))


def imported_names_from(module: str, target: str) -> list[str]:
    """Exactly which names ``module`` takes from ``target``.

    "Imports the module under test" and "computes with the module under test"
    are different facts, and only the second destroys an independence claim. A
    bridge that takes two metric-name strings from a solver is not running that
    solver. This reads the names off the AST so the distinction is checkable
    rather than asserted.
    """
    path = _module_path(module)
    if path is None:
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            parts = module.split(".")
            base = parts[: max(0, len(parts) - node.level)]
            resolved = ".".join(base + ([node.module] if node.module else []))
        else:
            resolved = node.module or ""
        if resolved == target:
            names.extend(alias.name for alias in node.names)
    return sorted(set(names))


def names_are_constants(module: str, names: list[str]) -> dict:
    """Is every imported name a module-level constant rather than a callable?"""
    path = _module_path(module)
    if path is None or not names:
        return {"all_constants": not names, "detail": {}}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    callables = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    detail = {
        name: ("callable_or_class" if name in callables else "value")
        for name in names
    }
    return {
        "all_constants": all(kind == "value" for kind in detail.values()),
        "detail": detail,
    }


PAIRS = [
    {
        "pair": "conduction1d solver vs its closed-form reference",
        "a": "engcore.domains.thermal.conduction1d.solver",
        "b": "engcore.domains.thermal.conduction1d.reference",
        "claim": (
            "the module docstring says the reference 'never imports solver, "
            "and a test asserts that'"
        ),
        "matters_because": (
            "this closed form is what the repository verifies its PDE solve "
            "against; a shared discretization would make that verification "
            "circular"
        ),
        "direction_that_matters": "the ORACLE must not depend on the code it judges",
    },
    {
        "pair": "conduction1d solver vs the explicit-scheme realization",
        "a": "engcore.domains.thermal.conduction1d.solver",
        "b": "engcore.domains.thermal_models.conduction1d_schemes",
        "claim": "two schemes over the same physics, offered as a fidelity ladder",
        "matters_because": (
            "agreement between two discretizations is evidence only insofar as "
            "the discretizations differ"
        ),
        "direction_that_matters": "neither may compute the other's answer",
    },
    {
        "pair": "electrical DC solver vs the repository's ngspice bridge",
        "a": "engcore.domains.electrical.dc.solver",
        "b": "engcore.domains.electrical.ngspice",
        "claim": "ngspice is an external simulator used as an independent check",
        "matters_because": (
            "the external tool is genuinely independent, but the BRIDGE that "
            "builds its netlist may share the circuit preprocessing under test"
        ),
        "direction_that_matters": "the NUMBERS must come from ngspice, not from the MNA stamp",
    },
    {
        "pair": "lumped thermal vs the material TCR evaluator",
        "a": "engcore.domains.thermal_models.lumped",
        "b": "engcore.domains.electrical.material",
        "claim": "two domains coupled in the electro-thermal system",
        "matters_because": (
            "a coupled run's two halves must not be resting on one shared "
            "temperature derivation"
        ),
        "direction_that_matters": "neither domain may compute the other's state",
    },
    {
        "pair": "CSTR solver vs the CSTR validity context",
        "a": "engcore.domains.kinetics.cstr.solver",
        "b": "engcore.domains.kinetics.cstr.context",
        "claim": (
            "the validity envelope is decided before a solve, from the "
            "declaration alone"
        ),
        "matters_because": (
            "if the envelope were computed by the same kernel it bounds, a "
            "kernel error would move the bound with it"
        ),
        "direction_that_matters": "the envelope must not be computed by the kernel it bounds",
    },
]

#: Routes this AUDIT uses as oracles, and what they share with the Core.
AUDIT_ORACLES = [
    ("benchmarks.scientific_truth.oracles.lumped", "RK4 written in this audit"),
    ("benchmarks.scientific_truth.oracles.diffusion", "closed form + explicit FTCS written in this audit"),
    ("benchmarks.scientific_truth.oracles.battery", "charge conservation and KVL written in this audit"),
    ("benchmarks.scientific_truth.oracles.cstr", "RK4 + root finding written in this audit"),
    ("benchmarks.scientific_truth.oracles.dc", "incidence-matrix nodal solve + ngspice"),
    ("benchmarks.scientific_truth.oracles.material", "mpmath at 50 digits"),
]


def survey() -> dict:
    rows = []
    for entry in PAIRS:
        a_closure = closure(entry["a"])
        b_closure = closure(entry["b"])
        shared = sorted(a_closure & b_closure)
        classified = [
            {"module": module, "role": _role(module)[0], "carries": _role(module)[1]}
            for module in shared
            if module not in (entry["a"], entry["b"])
        ]
        material = [
            row for row in classified if row["role"] in MATERIAL_ROLES
        ]
        b_depends_on_a = entry["a"] in b_closure
        a_depends_on_b = entry["b"] in a_closure

        taken = imported_names_from(entry["b"], entry["a"])
        taken_kind = names_are_constants(entry["a"], taken)

        if b_depends_on_a and a_depends_on_b:
            verdict = "NO"
            reading = "mutually dependent; neither can be evidence about the other"
        elif b_depends_on_a and taken and taken_kind["all_constants"]:
            verdict = "PARTIAL"
            reading = (
                "the check route imports the route under test, but takes only "
                + ", ".join(taken)
                + " -- module-level values, not callables. It borrows names, "
                "not numbers, so its answers still come from elsewhere"
            )
        elif b_depends_on_a:
            verdict = "NO"
            reading = (
                "the route offered as the check imports the route under test "
                "and takes "
                + ", ".join(f"{k} ({v})" for k, v in taken_kind["detail"].items())
                + ", so it can inherit whatever that route gets wrong"
            )
        elif material:
            verdict = "PARTIAL"
            reading = (
                "shares "
                + ", ".join(row["module"] for row in material)
                + ", which carry equations: agreement is weaker than it looks"
            )
        elif classified:
            verdict = "PARTIAL"
            reading = (
                "shares only the problem statement and platform machinery "
                "(declarations, exception types, result contract). The numbers "
                "are produced independently, but both routes would agree about "
                "a mis-declared problem"
            )
        else:
            verdict = "YES"
            reading = "no shared first-party module at all"

        rows.append({
            **entry,
            "a_reaches": len(a_closure),
            "b_reaches": len(b_closure),
            "shared_modules": classified,
            "shared_modules_carrying_equations": material,
            "check_route_imports_route_under_test": b_depends_on_a,
            "names_taken_from_route_under_test": taken,
            "those_names_are_all_plain_values": taken_kind["all_constants"],
            "name_kinds": taken_kind["detail"],
            "route_under_test_imports_check_route": a_depends_on_b,
            "independent": verdict,
            "reading": reading,
        })

    audit_rows = []
    for module, description in AUDIT_ORACLES:
        path = REPO / (module.replace(".", "/") + ".py")
        text = path.read_text(encoding="utf-8")
        audit_rows.append({
            "oracle_module": module,
            "what_it_is": description,
            "imports_engcore": "engcore" in text.replace("engcore.scientific.units", ""),
            "verdict": (
                "INDEPENDENT_OF_CORE"
                if "import engcore" not in text and "from engcore" not in text
                else "IMPORTS_CORE"
            ),
        })

    return {
        "schema": "scientific_truth_solver_independence/1",
        "method": (
            "the module import closure of each route, parsed from the AST. A "
            "claim of independence in a comment is not evidence; what a module "
            "can reach is."
        ),
        "pairs": rows,
        "this_audits_oracles": audit_rows,
        "counts": {
            "YES": sum(1 for row in rows if row["independent"] == "YES"),
            "PARTIAL": sum(1 for row in rows if row["independent"] == "PARTIAL"),
            "NO": sum(1 for row in rows if row["independent"] == "NO"),
        },
    }
