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
import hashlib
import json
import os
import pathlib
import re
import sys
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
    return scope_class(rel)


def scope_class(path: str) -> ChangeClass:
    """What a path IS, setting aside whether it is certification-pinned (which only ever adds a gate)."""
    rel = norm(path)
    name = rel.rsplit("/", 1)[-1]
    if rel in INFRASTRUCTURE_FILES or name == "conftest.py":
        return ChangeClass.TEST_INFRASTRUCTURE
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


_FIRST_PARTY_HEADS = frozenset({"engcore", "src", "tools", "benchmarks", "experiments", "forge_flagships"})


def _python_files(root: pathlib.Path) -> list[pathlib.Path]:
    out = []
    for p in root.rglob("*.py"):
        parts = p.relative_to(root).parts
        if any(part in _SKIP_DIRS or part.endswith(".egg-info") for part in parts):
            continue
        out.append(p)
    return sorted(out)


def _file_facts(text: str) -> list | None:
    """What one file's own text says about what it reaches: ``None`` when it does not parse.

    A pure function of the text: ``("i", name)`` per ``import``, ``("f", level,
    module, names)`` per ``from ... import``, ``("c", dotted)`` per first-party-looking
    dotted name in a short string constant. Resolving them needs the whole tree
    (module names, packages), which :func:`build_graph` does on every run.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    facts: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            facts.extend(("i", alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            facts.append(("f", node.level, node.module or "", [alias.name for alias in node.names]))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 400:
            # A short string naming a first-party module: an importlib target, a
            # ``py:`` identity. Long strings are prose (docstrings) and are not read:
            # measured, reading them too took one domain edit from ~45 affected
            # modules to 557 through package docstrings that merely name a module.
            facts.extend(("c", dotted) for dotted in _DOTTED.findall(node.value))
    return facts


#: Bumped by hand only for a change the identity below cannot see (none so far).
_FACTS_SCHEMA = "forge.test_impact.facts/1"


def _facts_identity() -> str:
    """Everything a cached fact depends on besides the file's own bytes.

    This module's whole source (any edit to the extraction, the regex or the
    400-character rule invalidates every entry) and the interpreter version
    (what parses can change between versions).
    """
    own = pathlib.Path(__file__).read_bytes()
    return hashlib.sha256(_FACTS_SCHEMA.encode() + b"\0" + sys.version.encode() + b"\0" + own).hexdigest()


def _load_facts_cache(path: pathlib.Path | None, identity: str) -> dict:
    """Cached facts by content digest; empty on any doubt (absent, unreadable, other identity, malformed)."""
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("identity") != identity or not isinstance(payload.get("facts"), dict):
            return {}
        return payload["facts"]
    except (OSError, ValueError, AttributeError):
        return {}


def _valid_facts(facts) -> bool:
    if facts is None:
        return True
    if not isinstance(facts, list):
        return False
    for fact in facts:
        if not isinstance(fact, list) or not fact:
            return False
        if fact[0] in ("i", "c"):
            if len(fact) != 2 or not isinstance(fact[1], str):
                return False
        elif fact[0] == "f":
            if (len(fact) != 4 or not isinstance(fact[1], int) or isinstance(fact[1], bool) or not isinstance(fact[2], str)
                    or not isinstance(fact[3], list) or not all(isinstance(n, str) for n in fact[3])):
                return False
        else:
            return False
    return True


def _store_facts_cache(path: pathlib.Path | None, identity: str, facts: dict) -> None:
    """Write atomically; a cache that cannot be written is simply not kept."""
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"identity": identity, "facts": facts}, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def build_graph(root: pathlib.Path, *, cache: pathlib.Path | None = None) -> ImpactGraph:
    """The import graph of every first-party Python file under ``root``.

    ``cache`` (optional) keeps each file's :func:`_file_facts` keyed by the
    sha256 of its bytes. Every file is still listed, read and hashed on every
    call, and everything that depends on more than one file -- the pytest
    roots from ``pyproject.toml``, module names, packages, resolution, the
    reverse graph -- is recomputed, so an added, deleted or renamed file, a
    changed ``pyproject`` or ``conftest`` can never be answered from the cache.
    A cache entry can only ever stand for the exact bytes it was computed from;
    anything doubtful is recomputed.
    """
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

    identity = _facts_identity() if cache is not None else ""
    cached = _load_facts_cache(cache, identity)
    kept: dict = {}
    deps: dict[str, set[str]] = {}
    texts: dict[str, str] = {}
    unparseable: list[str] = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        data = f.read_bytes()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            unparseable.append(rel)
            deps[rel] = set()
            continue
        key = hashlib.sha256(data).hexdigest() if cache is not None else ""
        if key and key in cached and _valid_facts(cached[key]):
            facts = cached[key]
        else:
            facts = _file_facts(text)
        if key:
            kept[key] = facts
        if facts is None:
            unparseable.append(rel)
            deps[rel] = set()
            continue
        texts[rel] = text
        own = (file_mods.get(rel) or [""])[0]
        package = own if f.name == "__init__.py" else own.rpartition(".")[0]
        out: set[str] = set()
        for fact in facts:
            if fact[0] == "i":
                out.update(executed_by(fact[1]))
            elif fact[0] == "f":
                _, level, module, names = fact
                base = module
                if level:
                    anchor = package.split(".") if package else []
                    if level > 1:
                        anchor = anchor[: len(anchor) - (level - 1)]
                    base = ".".join(anchor + ([module] if module else []))
                out.update(executed_by(base))
                for name in names:
                    out.update(executed_by(f"{base}.{name}" if base else name))
            else:
                dotted = fact[1]
                if dotted in mod_to_file or dotted.split(".", 1)[0] in _FIRST_PARTY_HEADS:
                    out.update(executed_by(dotted))
        out.discard(rel)
        deps[rel] = out
    if cache is not None and kept != cached:
        _store_facts_cache(cache, identity, kept)
    return ImpactGraph(root, deps, texts, tuple(unparseable), tuple(roots))


def default_cache_path(root: pathlib.Path) -> pathlib.Path | None:
    """The developer cache for ``root``: outside the repository, one file per checkout.

    ``FORGE_IMPACT_CACHE`` overrides the location; ``off`` (or ``0``, empty) disables it.
    """
    override = os.environ.get("FORGE_IMPACT_CACHE")
    if override is not None:
        return None if override.strip().lower() in ("", "0", "off", "no", "false") else pathlib.Path(override)
    tag = hashlib.sha256(str(pathlib.Path(root).resolve()).encode()).hexdigest()[:16]
    return pathlib.Path.home() / ".cache" / "forge" / "test_impact" / f"facts-{tag}.json"


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
# Execution tiers: the tables in tests/conftest.py, plus the markers a module
# applies itself (``@pytest.mark.expensive`` on a test or class, ``pytestmark``)
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


_TIER_MARKS = frozenset({"expensive", "campaign"})


def _is_tier_mark(node: ast.AST) -> bool:
    """``pytest.mark.expensive`` / ``mark.campaign``, bare or called (``...expensive(reason=...)``)."""
    if isinstance(node, ast.Call):
        node = node.func
    return isinstance(node, ast.Attribute) and node.attr in _TIER_MARKS and (
        isinstance(node.value, ast.Attribute) and node.value.attr == "mark"
    )


def _self_marked(text: str) -> tuple[bool, set[str], set[str]]:
    """``(whole module marked, marked top-level test functions and classes, every collectable name)``."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False, set(), set()
    whole, marked, names = False, set(), set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
            whole = whole or any(_is_tier_mark(v) for v in values)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name.startswith(("test", "Test")):
            names.add(node.name)
            if any(_is_tier_mark(d) for d in node.decorator_list):
                marked.add(node.name)
    return whole, marked, names


def split_by_tier(modules: Iterable[str], tiers: Tiers, texts: Mapping[str, str]) -> tuple[list[str], list[str], list[str]]:
    """``(fast_targets, deselect_prefixes, expensive_left_out)`` for affected modules.

    An expensive module (a conftest table entry, or a module-level
    ``pytestmark``) is replaced by its static guards (named node ids); an
    expensive or campaign test inside an ordinary module (a conftest key, or a
    test function or class decorated with the marker) is deselected by its key.
    ``--deselect`` matches node-id PREFIXES, so a key that is also the prefix of
    another test in that module (``test_a`` / ``test_ab``) is not deselected:
    that expensive test runs rather than risk dropping a fast one. Everything
    left out is returned so the caller can print it.
    """
    targets, deselect, left_out = [], [], []
    keys = sorted(tiers.expensive_tests | tiers.campaign_tests)
    for module in sorted(set(modules)):
        whole, marked, names = _self_marked(texts.get(module, ""))
        if module in tiers.expensive_modules or whole:
            left_out.append(module)
            targets.extend(f"{module}::{name}" for name in sorted(tiers.static_guards.get(module, ())))
            continue
        targets.append(module)
        module_keys = [k for k in keys if k.partition("::")[0] == module] + [f"{module}::{n}" for n in sorted(marked)]
        for key in dict.fromkeys(module_keys):
            rest = key.partition("::")[2]
            name = rest.split("[", 1)[0].split("::", 1)[0]
            if "[" not in rest and any(other != name and other.startswith(name) for other in names):
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
    "NO_NARROW_SCIENTIFIC",
    "Tiers",
    "build_graph",
    "classify",
    "impact_of",
    "next_required",
    "scientific_narrowing",
    "scope_class",
    "is_test_module",
    "load_tiers",
    "norm",
    "recertification_reasons",
    "split_by_tier",
]


# ---------------------------------------------------------------------------
# What the developer must run next, and whether a narrow SCIENTIFIC run is sound
# ---------------------------------------------------------------------------

#: Changes whose reach a narrow SCIENTIFIC selection cannot be trusted to cover:
#: the developer is sent to the whole SCIENTIFIC tier instead.
NO_NARROW_SCIENTIFIC: Mapping[ChangeClass, str] = {
    ChangeClass.TRUST_OR_AUTHORITY: "trust/authority change: its reach is every assessment",
    ChangeClass.SCIENTIFIC_SHARED: "shared scientific code: its reach is wider than its importers' tiers",
    ChangeClass.TEST_INFRASTRUCTURE: "selection, tiering or test configuration changed: the selection itself is in question",
    ChangeClass.UNCLASSIFIED: "unclassified path: reach unknown",
}


def scientific_narrowing(paths: Iterable[str], impact: Impact) -> tuple[str, ...]:
    """Why a narrow (affected-only) SCIENTIFIC run would NOT be sound; empty when it may be offered.

    Developer aid only: even when it may run, the full SCIENTIFIC tier stays the gate
    before review, merge or freeze. Doubt always broadens.
    """
    reasons = []
    for rel in sorted({norm(p) for p in paths}):
        cls = scope_class(rel)
        if cls in NO_NARROW_SCIENTIFIC:
            reasons.append(f"{rel}: {NO_NARROW_SCIENTIFIC[cls]}")
    reasons.extend(f"{rel}: reach could not be established" for rel in impact.unresolved)
    return tuple(reasons)


def next_required(paths: Iterable[str], *, expensive_affected: int) -> tuple[str, ...]:
    """The gates still owed after this developer check, strongest last.

    Follows :data:`MINIMUM_GATE`: FAST for anything but documentation; SCIENTIFIC for
    shared, trust, configuration or unknown reach, and whenever an affected test is
    expensive (a selective run here never replaces the tier); a scientific review for
    trust/authority; recertification for any certification-pinned path.
    """
    rels = sorted({norm(p) for p in paths})
    scopes = {scope_class(r) for r in rels}
    gates = []
    if scopes - {ChangeClass.DOC_ONLY}:
        gates.append("FAST")
    if expensive_affected or scopes & {ChangeClass.SCIENTIFIC_SHARED, ChangeClass.TRUST_OR_AUTHORITY,
                                       ChangeClass.TEST_INFRASTRUCTURE, ChangeClass.UNCLASSIFIED}:
        gates.append("SCIENTIFIC")
    if ChangeClass.TRUST_OR_AUTHORITY in scopes:
        gates.append("forge-scientific-review")
    if any(recertification_reasons(r) for r in rels):
        gates.append("RECERTIFICATION (owner-run)")
    return tuple(gates)
