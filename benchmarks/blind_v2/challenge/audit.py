"""Prove the challenge cannot see the system it is challenging.

Five checks, each catching something the others do not:

1. **AST imports** -- every ``import`` statement in every challenge module,
   read from the syntax tree rather than by pattern, so a name split across
   lines or hidden in a function body is still seen.
2. **Transitive graph** -- the same check followed through every first-party
   module the package imports, so a clean module importing a dirty one fails.
3. **Name and string scan** -- catches ``importlib.import_module("engcore...")``
   and any other route that puts a forbidden name in a literal.
4. **Runtime sys.modules** -- imports the package in a *fresh interpreter* and
   asks what actually loaded. This is the check that cannot be argued with.
5. **Path audit** -- every string literal that looks like a path is checked
   against the corpora this round is forbidden to open.

The audit is only worth what its own falsification test says it is: 
``prove_audit_catches_a_peeker`` writes a module that deliberately peeks and
requires every applicable check to fail on it.
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import textwrap

PACKAGE = pathlib.Path(__file__).resolve().parent
BLIND_V2 = PACKAGE.parent
REPO = BLIND_V2.parent.parent

#: What the challenge may not import, at any depth.
FORBIDDEN_MODULES = (
    "engcore",
    "src.engcore",
    "benchmarks.hard",
    "benchmarks.blind",
    "benchmarks.oracles",
    "tests.oracles",
    "tests.mutation_guards",
)

#: What the challenge may not open. The legacy holdouts and every existing
#: answer key; this round opens none of them.
FORBIDDEN_PATHS = (
    "benchmarks/hard",
    "benchmarks/blind",
    "benchmarks/oracles",
    "benchmarks/ai_designs",
    "tests/oracles",
    "cases_hard",
    "cases_battery",
    "split_battery",
    "holdout",
)

#: The challenge's own directory is not a peek; nor is the contract capture,
#: which runs once, before generation, and is not imported by any module here.
ALLOWED_LOCAL_PREFIXES = ("challenge", "benchmarks.blind_v2.challenge", ".")


def _modules() -> list[pathlib.Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue  # a relative import stays inside this package
            if node.module:
                names.append(node.module)
    return names


def _violates(name: str) -> bool:
    return any(
        name == bad or name.startswith(bad + ".") for bad in FORBIDDEN_MODULES
    )


def audit_imports(paths: list[pathlib.Path] | None = None) -> list[str]:
    findings: list[str] = []
    for path in paths or _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imported_names(tree):
            if _violates(name):
                findings.append(f"{path.name}: imports {name!r}")
    return findings


def audit_strings(paths: list[pathlib.Path] | None = None) -> list[str]:
    findings: list[str] = []
    for path in paths or _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            text = node.value
            # This module is the one place the forbidden names must appear as
            # literals -- they are the audit's own subject. Exempting it from
            # the *string* scan does not exempt it from anything else: its
            # imports are still read from the syntax tree, it is still walked
            # by the transitive check, and the runtime check would still see
            # anything it actually loaded.
            if path.name == "audit.py":
                continue
            if _violates(text):
                findings.append(f"{path.name}: names {text!r} in a string")
            for forbidden in FORBIDDEN_PATHS:
                if forbidden in text:
                    findings.append(f"{path.name}: names path {forbidden!r}")
    return findings


def audit_attribute_chains(paths: list[pathlib.Path] | None = None) -> list[str]:
    """``engcore.scientific...`` reached as an attribute of an aliased module."""
    findings: list[str] = []
    for path in paths or _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and _violates(node.id):
                findings.append(f"{path.name}: references {node.id!r}")
    return findings


def audit_runtime(module: str = "challenge") -> list[str]:
    """Import the package in a fresh interpreter and see what loaded."""
    script = textwrap.dedent(
        f"""
        import json, sys
        sys.path.insert(0, {str(BLIND_V2)!r})
        import importlib, pkgutil
        package = importlib.import_module({module!r})
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            importlib.import_module(info.name)
        loaded = sorted(
            name for name in sys.modules
            if any(name == bad or name.startswith(bad + ".")
                   for bad in {list(FORBIDDEN_MODULES)!r})
        )
        print(json.dumps(loaded))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=300
    )
    if proc.returncode != 0:
        return [f"runtime audit could not import the package: {proc.stderr.strip()[:400]}"]
    loaded = json.loads(proc.stdout.strip().splitlines()[-1])
    return [f"runtime: {name} was loaded" for name in loaded]


def audit_transitive() -> list[str]:
    """Follow first-party imports out of the package and audit those too."""
    findings: list[str] = []
    seen: set[pathlib.Path] = set()
    queue = list(_modules())
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imported_names(tree):
            if _violates(name):
                findings.append(f"{path.name}: transitively imports {name!r}")
                continue
            candidate = REPO / (name.replace(".", "/") + ".py")
            if candidate.exists() and candidate not in seen:
                queue.append(candidate)
    return findings


def run_all() -> dict:
    checks = {
        "ast_imports": audit_imports(),
        "transitive_imports": audit_transitive(),
        "name_and_string_scan": audit_strings() + audit_attribute_chains(),
        "runtime_sys_modules": audit_runtime(),
    }
    return {
        "clean": not any(checks.values()),
        "checks": checks,
        "modules_audited": [p.name for p in _modules()],
        "forbidden_modules": list(FORBIDDEN_MODULES),
        "forbidden_paths": list(FORBIDDEN_PATHS),
    }


PEEKER = '''"""A module that peeks, written only so the audit can catch it."""
import engcore.scientific.models.definition as peeked
from engcore.scientific.units.quantity import Quantity
import importlib
def cheat():
    return importlib.import_module("engcore.domains.battery.cell"), peeked, Quantity
'''


def prove_audit_catches_a_peeker() -> dict:
    """Write a deliberately peeking module and require the audit to fail.

    An audit that has never been shown to fail is a decoration. This writes a
    real one into the package, runs every check against it, removes it, and
    reports what each check saw. A check that stayed silent is a check that
    would have stayed silent for a real leak.
    """
    decoy = PACKAGE / "_falsification_peeker.py"
    decoy.write_text(PEEKER, encoding="utf-8")
    try:
        caught = {
            "ast_imports": audit_imports([decoy]),
            "name_and_string_scan": audit_strings([decoy]) + audit_attribute_chains([decoy]),
            "transitive_imports": audit_transitive(),
            "runtime_sys_modules": audit_runtime(),
        }
    finally:
        decoy.unlink(missing_ok=True)
        for cached in (PACKAGE / "__pycache__").glob("_falsification_peeker*"):
            cached.unlink(missing_ok=True)
    return {
        "caught_by": {name: bool(found) for name, found in caught.items()},
        "detail": caught,
        "audit_is_effective": all(bool(found) for found in caught.values()),
    }
