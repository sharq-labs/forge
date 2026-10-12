"""Static change impact for the developer gate: which test modules a change can reach.

``tools/forge_check.py --changed`` uses this to add, beyond its fixed scientific
sentinels, the tests a change can actually affect. It is a developer aid. It
never replaces FAST, SCIENTIFIC, FULL or hardened recertification, and it never
decides a scientific result.

How a test module is reached
----------------------------
A test module is *affected* by a changed path when any of these holds:

``imports``  it imports, directly or through any chain of first-party modules,
             the changed Python file. Imports are read from the whole file (a
             function-level import counts), importing ``a.b.c`` also executes
             ``a/__init__`` and ``a/b/__init__``, and a dotted first-party module
             name inside a string (``importlib.import_module("engcore.x")``, a
             ``py:engcore.x`` identity) counts as an import. Module names are
             resolved against the pytest ``pythonpath`` roots in pyproject.toml,
             so the graph imports exactly what the suite can import.
``mentions`` its source names the changed file's repository path or, for a
             distinctive file name, the bare name: a test that opens a data
             file, a document or a workflow by path.
``scans``    the change is under ``src/`` and the test walks a source tree
             (``rglob``, ``glob``, ``os.walk``, ``walk_packages``, ``git
             ls-files``) and names a source root. An import graph never reaches
             such guards, so they are added for every source change. A test
             that reads ONE source file by a constructed path is reached by
             ``mentions`` (its distinctive file name).

What it cannot see, and what happens then
-----------------------------------------
Reflection the text does not show (a module name assembled at run time), a
data file read under a computed path, or a change the rules above do not reach
at all. A changed path that is not Python source and that no test mentions is
reported as *unresolved*; the gate then selects the whole regression pack and
says so. The graph over-approximates: an extra test costs seconds, a missed
one costs false confidence.
"""

from __future__ import annotations

import ast
import pathlib
import re
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

_SKIP_DIRS = frozenset({".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache",
                        ".mypy_cache", ".ruff_cache", "build", "dist"})
_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_SCAN_CALL = re.compile(r"\brglob\(|\.glob\(|\bos\.walk\(|\bwalk_packages\(|\biter_modules\(|ls-files")
_SOURCE_WORD = re.compile(r"[\"'/]src[\"'/]|src/engcore|\bengcore\b")
#: File names too common to identify one file when a test mentions them.
_COMMON_NAMES = frozenset({"__init__.py", "conftest.py", "README.md", "setup.py", "manifest.json",
                           "config.py", "utils.py", "common.py", "data.json", "__main__.py"})


class ChangeClass(str, Enum):
    """What a changed path is, by repository ownership. Earlier members take precedence."""

    TEST_INFRASTRUCTURE = "test_infrastructure"  # decides how every test runs or which cases exist
    CERTIFICATION_PINNED = "certification_pinned"  # a hardened-recertification trigger
    TRUST_OR_AUTHORITY = "trust_or_authority"  # evidence admission, authority, escrow, trust registries
    SCIENTIFIC_SHARED = "scientific_shared"  # generic scientific runtime under src/engcore
    DOMAIN_LOCAL = "domain_local"  # one domain, system, product, provider or flagship
    TEST_ONLY = "test_only"  # a test module or test helper
    LOCAL_NONSCIENTIFIC = "local_nonscientific"  # repository tooling outside the runtime
    DOC_ONLY = "doc_only"  # prose
    UNCLASSIFIED = "unclassified"


#: The minimum gate each class calls for, beyond this developer gate. Advisory text only.
MINIMUM_GATE: Mapping[ChangeClass, str] = {
    ChangeClass.TEST_INFRASTRUCTURE: "selection or tiering changed: whole regression pack here, then FAST",
    ChangeClass.CERTIFICATION_PINNED: "hardened recertification is required (owner-run); this gate does not replace it",
    ChangeClass.TRUST_OR_AUTHORITY: "FAST, SCIENTIFIC and a forge-scientific-review before merge",
    ChangeClass.SCIENTIFIC_SHARED: "FAST, then SCIENTIFIC before merge",
    ChangeClass.DOMAIN_LOCAL: "FAST before merge; SCIENTIFIC when expensive affected tests were left out",
    ChangeClass.TEST_ONLY: "FAST before merge",
    ChangeClass.LOCAL_NONSCIENTIFIC: "FAST before merge",
    ChangeClass.DOC_ONLY: "this gate",
    ChangeClass.UNCLASSIFIED: "reach unknown: whole regression pack here, then FAST",
}

#: Files that change how every test runs or which cases exist: the gate's own list.
from tools.forge_check import CONSERVATIVE_FILES as INFRASTRUCTURE_FILES  # noqa: E402

_TRUST_PREFIXES = (
    "src/engcore/authority/",
    "src/engcore/blindfold/",
    "src/engcore/sria/assurance/",
    "src/engcore/credibility/evidence_graph/",
)
_TRUST_FILES = frozenset({
    "src/engcore/sria/admission.py",
    "src/engcore/sria/charter.py",
    "src/engcore/sria/evidence.py",
    "src/engcore/sria/gateway.py",
    "src/engcore/credibility/assurance_bundle.py",
    "src/engcore/credibility/assurance_manifest.py",
    "src/engcore/credibility/assurance_replay_bundle.py",
    "src/engcore/credibility/replay_binding.py",
    "src/engcore/credibility/knowledge_evidence.py",
    "src/engcore/claims/external_evidence.py",
})
_DOMAIN_PREFIXES = (
    "src/engcore/domains/",
    "src/engcore/domainpacks/",
    "src/engcore/compositionpacks/",
    "src/engcore/executionpacks/",
    "src/engcore/systems/",
    "src/engcore/product/",
    "src/engcore/providers/",
    "providers/",
    "flagships/",
)


def norm(path: str) -> str:
    out = str(path).replace("\\", "/")
    return out[2:] if out.startswith("./") else out


def is_test_module(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.startswith("test_") and name.endswith(".py") and ("/tests/" in f"/{rel}")


def recertification_reasons(rel: str) -> tuple[str, ...]:
    """The hardened-recertification triggers ``rel`` hits -- the CI classifier's own answer."""
    from tools.certification.recertification_scope import recertification_reasons as reasons

    return reasons(norm(rel))


def classify(path: str) -> ChangeClass:
    rel = norm(path)
    name = rel.rsplit("/", 1)[-1]
    if rel in INFRASTRUCTURE_FILES or name == "conftest.py":
        return ChangeClass.TEST_INFRASTRUCTURE
    if recertification_reasons(rel):
        return ChangeClass.CERTIFICATION_PINNED
    if rel.startswith(_TRUST_PREFIXES) or rel in _TRUST_FILES or (
        rel.startswith("src/engcore/claims/") and name.endswith("_trust.py")
    ):
        return ChangeClass.TRUST_OR_AUTHORITY
    if rel.endswith(".py") and "/tests/" in f"/{rel}":
        return ChangeClass.TEST_ONLY
    if rel.startswith(_DOMAIN_PREFIXES):
        return ChangeClass.DOMAIN_LOCAL
    if rel.startswith("src/"):
        return ChangeClass.SCIENTIFIC_SHARED
    if rel.endswith(".md") or rel.startswith("docs/") or name in ("LICENSE", "CITATION.cff"):
        return ChangeClass.DOC_ONLY
    if rel.startswith(("tools/", ".github/", ".claude/")) and (rel.endswith(".py") or rel.endswith((".yml", ".yaml", ".json", ".md"))):
        return ChangeClass.LOCAL_NONSCIENTIFIC
    return ChangeClass.UNCLASSIFIED


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------


@dataclass
class ImpactGraph:
    root: pathlib.Path
    deps: dict[str, set[str]]
    texts: dict[str, str]
    unparseable: tuple[str, ...]
    roots: tuple[pathlib.Path, ...] = ()
    reverse: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for a, bs in self.deps.items():
            for b in bs:
                self.reverse.setdefault(b, set()).add(a)

    @property
    def test_modules(self) -> tuple[str, ...]:
        return tuple(sorted(r for r in self.deps if is_test_module(r)))

    def module_names(self, rel: str) -> tuple[str, ...]:
        """Every dotted name ``rel`` is importable as under the pytest roots (whether or not it exists now)."""
        path = (self.root / rel).resolve()
        names = []
        for r in self.roots:
            try:
                parts = list(path.relative_to(r).with_suffix("").parts)
            except ValueError:
                continue
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            if parts and all(x.isidentifier() for x in parts):
                names.append(".".join(parts))
        return tuple(names)

    def importers(self, rel: str) -> set[str]:
        """Every file that imports ``rel`` through any chain (``rel`` excluded).

        A path absent from the tree (deleted, or renamed away) has no graph
        node; its importers are found by its dotted module names in the text.
        """
        if rel not in self.deps:
            names = [n for n in self.module_names(rel) if "." in n]
            pattern = re.compile("|".join(rf"\b{re.escape(n)}\b" for n in names)) if names else None
            direct = {f for f, text in self.texts.items() if pattern is not None and pattern.search(text)}
            out = set(direct)
            for f in direct:
                out |= self.importers(f)
            return out
        seen, frontier = {rel}, [rel]
        while frontier:
            nxt = []
            for x in frontier:
                for y in self.reverse.get(x, ()):
                    if y not in seen:
                        seen.add(y)
                        nxt.append(y)
            frontier = nxt
        seen.discard(rel)
        return seen


def _python_files(root: pathlib.Path) -> list[pathlib.Path]:
    out = []
    for p in root.rglob("*.py"):
        parts = p.relative_to(root).parts
        if any(part in _SKIP_DIRS or part.endswith(".egg-info") for part in parts):
            continue
        out.append(p)
    return sorted(out)


def build_graph(root: pathlib.Path) -> ImpactGraph:
    root = root.resolve()
    pythonpath = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]["pythonpath"]
    roots = [(root / r).resolve() for r in pythonpath]
    files = _python_files(root)

    mod_to_file: dict[str, str] = {}
    file_mods: dict[str, list[str]] = {}
    for f in files:
        rel = f.relative_to(root).as_posix()
        for r in roots:
            try:
                parts = list(f.relative_to(r).with_suffix("").parts)
            except ValueError:
                continue
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            if parts and all(x.isidentifier() for x in parts):
                name = ".".join(parts)
                mod_to_file.setdefault(name, rel)
                file_mods.setdefault(rel, []).append(name)

    def executed_by(name: str) -> list[str]:
        """Files run by importing ``name``: the module itself and every parent package's __init__."""
        bits = name.split(".")
        return [f for i in range(1, len(bits) + 1) if (f := mod_to_file.get(".".join(bits[:i])))]

    deps: dict[str, set[str]] = {}
    texts: dict[str, str] = {}
    unparseable: list[str] = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        try:
            text = f.read_bytes().decode("utf-8-sig")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError, ValueError):
            unparseable.append(rel)
            deps[rel] = set()
            continue
        texts[rel] = text
        own = (file_mods.get(rel) or [""])[0]
        package = own if f.name == "__init__.py" else own.rpartition(".")[0]
        out: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    out.update(executed_by(alias.name))
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    anchor = package.split(".") if package else []
                    if node.level > 1:
                        anchor = anchor[: len(anchor) - (node.level - 1)]
                    base = ".".join(anchor + ([node.module] if node.module else []))
                out.update(executed_by(base))
                for alias in node.names:
                    out.update(executed_by(f"{base}.{alias.name}" if base else alias.name))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 400:
                for dotted in _DOTTED.findall(node.value):
                    if dotted in mod_to_file or dotted.split(".", 1)[0] in ("engcore", "src", "tools", "benchmarks",
                                                                            "experiments", "forge_flagships"):
                        out.update(executed_by(dotted))
        out.discard(rel)
        deps[rel] = out
    return ImpactGraph(root, deps, texts, tuple(unparseable), tuple(roots))


# ---------------------------------------------------------------------------
# Impact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Impact:
    classes: Mapping[str, ChangeClass]
    affected: Mapping[str, tuple[str, ...]]  # test module -> why (sorted reasons)
    unresolved: tuple[str, ...]  # changed paths whose reach could not be established

    @property
    def affected_modules(self) -> tuple[str, ...]:
        return tuple(sorted(self.affected))


def _mentions(text: str, rel: str) -> bool:
    if rel in text:
        return True
    name = rel.rsplit("/", 1)[-1]
    return name not in _COMMON_NAMES and len(name) > 6 and "." in name and name in text


def impact_of(paths: Iterable[str], graph: ImpactGraph) -> Impact:
    changed = sorted({norm(p) for p in paths})
    classes = {p: classify(p) for p in changed}
    why: dict[str, set[str]] = {}
    unresolved: list[str] = []
    tests = graph.test_modules
    scanners: tuple[str, ...] | None = None
    for rel in changed:
        reached = False
        if rel.endswith(".py"):
            for t in graph.importers(rel):
                if is_test_module(t):
                    why.setdefault(t, set()).add(f"imports {rel}")
                    reached = True
        for t in tests:
            if t != rel and _mentions(graph.texts.get(t, ""), rel):
                why.setdefault(t, set()).add(f"mentions {rel}")
                reached = True
        if rel.rsplit("/", 1)[-1] == "conftest.py":
            directory = rel.rpartition("/")[0]
            for t in tests:
                if not directory or t.startswith(directory + "/"):
                    why.setdefault(t, set()).add(f"governed by {rel}")
                    reached = True
        if rel.startswith("src/"):
            if scanners is None:
                scanners = tuple(t for t in tests if _SCAN_CALL.search(graph.texts.get(t, ""))
                                 and _SOURCE_WORD.search(graph.texts.get(t, "")))
            for t in scanners:
                why.setdefault(t, set()).add("reads source files by path")
            reached = reached or bool(scanners)
        if rel.endswith(".py") and rel in graph.unparseable:
            reached = False
        if not reached and not is_test_module(rel) and classes[rel] is not ChangeClass.DOC_ONLY:
            unresolved.append(rel)
    return Impact(classes, {t: tuple(sorted(r)) for t, r in why.items()}, tuple(unresolved))


# ---------------------------------------------------------------------------
# Execution tiers, read from tests/conftest.py (the only place they are assigned)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tiers:
    campaign_tests: frozenset[str]
    expensive_tests: frozenset[str]  # exact node ids or module::function keys
    expensive_modules: frozenset[str]
    static_guards: Mapping[str, frozenset[str]]


def load_tiers(root: pathlib.Path) -> Tiers:
    """The tier tables, read as literals from tests/conftest.py (never executed)."""
    tree = ast.parse((root / "tests" / "conftest.py").read_text(encoding="utf-8"))
    found: dict[str, object] = {}
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id in ("CAMPAIGN_TESTS", "EXPENSIVE_TESTS", "EXPENSIVE_MODULES", "STATIC_GUARDS"):
            value = node.value
            if target.id == "STATIC_GUARDS":
                guards = {}
                for k, v in zip(value.keys, value.values):  # frozenset({...}) calls
                    guards[ast.literal_eval(k)] = frozenset(ast.literal_eval(v.args[0]))
                found[target.id] = guards
            else:
                found[target.id] = ast.literal_eval(value)
    return Tiers(
        frozenset(found["CAMPAIGN_TESTS"]),
        frozenset(found["EXPENSIVE_TESTS"]),
        frozenset(found["EXPENSIVE_MODULES"]),
        dict(found["STATIC_GUARDS"]),
    )


def _test_functions(text: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")}


def split_by_tier(modules: Iterable[str], tiers: Tiers, texts: Mapping[str, str]) -> tuple[list[str], list[str], list[str]]:
    """``(fast_targets, deselect_prefixes, expensive_left_out)`` for affected modules.

    An expensive module is replaced by its static guards (named node ids); an
    expensive or campaign test inside an ordinary module is deselected by its
    key. ``--deselect`` matches node-id PREFIXES, so a key that is also the
    prefix of another test function in that module (``test_a`` / ``test_ab``)
    is not deselected: that expensive test runs rather than risk dropping a
    fast one. Everything left out is returned so the caller can print it.
    """
    targets, deselect, left_out = [], [], []
    keys = sorted(tiers.expensive_tests | tiers.campaign_tests)
    for module in sorted(set(modules)):
        if module in tiers.expensive_modules:
            left_out.append(module)
            targets.extend(f"{module}::{name}" for name in sorted(tiers.static_guards.get(module, ())))
            continue
        targets.append(module)
        functions = _test_functions(texts.get(module, ""))
        for key in keys:
            mod, _, rest = key.partition("::")
            if mod != module:
                continue
            function = rest.split("[", 1)[0]
            if "[" not in rest and any(f != function and f.startswith(function) for f in functions):
                continue
            deselect.append(key)
            left_out.append(key)
    return targets, deselect, left_out


__all__ = [
    "ChangeClass",
    "Impact",
    "ImpactGraph",
    "INFRASTRUCTURE_FILES",
    "MINIMUM_GATE",
    "Tiers",
    "build_graph",
    "classify",
    "impact_of",
    "is_test_module",
    "load_tiers",
    "norm",
    "recertification_reasons",
    "split_by_tier",
]
