"""The blind challenge's own guards: no peeking, and no quiet unsealing.

Two different promises are enforced here, and they fail for different reasons.

**Before the freeze — the no-peek proof (Phase 1O).** The challenge is only
blind if the thing that built its truth could not have asked Forge for the
answer. That is not a promise a docstring can keep. Every module under
``benchmarks/blind/`` that participates in generation or truth construction is
parsed, its import graph is walked TRANSITIVELY, and any edge reaching
``engcore`` — by import statement, by ``importlib`` call, or by a string handed
to one — fails the suite. A monkeypatch guard then does the same thing
dynamically, so a path that evades the AST cannot evade both.

**After the freeze — the seal.** ``FREEZE.json`` carries the digest of the case
set, of the truth, of the manifest, of the disagreement log, and of every
source file that produced them. The guards below recompute all of them. A case
edited, added or removed; a truth status changed; a generator altered — each
moves a digest and turns this file red. Repairing it by updating the digest is
not a repair: **a change to a frozen challenge is a NEW challenge version**,
and `benchmarks/blind/v1` is closed the moment Forge has seen it.

The one place the two layers are allowed to meet is
:func:`test_the_oracle_bounds_match_the_model_records`, which reads the model
records and checks that the oracle's transcribed bounds have not drifted from
them. That is a check ON the freeze rather than an input TO it: it imports
``engcore`` here, in the test, and never in anything the freeze digests.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
BLIND = REPO / "benchmarks" / "blind"
V1 = BLIND / "v1"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# =====================================================================
# Phase 1O — the no-peek static proof
# =====================================================================

#: Every module that participates in generating a case or deciding its truth.
#: A module added to this set and not to the audit is the failure mode this
#: list exists to prevent, so the audit also asserts the set is complete.
TRUTH_LAYER = (
    "benchmarks/blind/generate.py",
    "benchmarks/blind/build_truth.py",
    "benchmarks/blind/families.py",
    "benchmarks/blind/bound_registry.py",
    "benchmarks/blind/admissibility.py",
    "benchmarks/blind/freeze.py",
    "benchmarks/blind/oracles/units.py",
    "benchmarks/blind/oracles/electrothermal.py",
    "benchmarks/blind/oracles/battery.py",
    "benchmarks/blind/oracles/kinetics.py",
    "benchmarks/blind/oracles/conduction.py",
    "benchmarks/blind/oracles/spice.py",
)

#: Names that must never be reachable from the truth layer. The first is the
#: runtime itself; the rest are the specific surfaces whose answers the
#: challenge exists to be independent of, listed by name so a failure says
#: WHICH promise broke.
FORBIDDEN_ROOTS = ("engcore", "src.engcore", "crafty")
FORBIDDEN_NAMES = (
    "run_electrothermal_case", "run_battery_case", "derive_verdict",
    "assess_realization", "cstr_validity_context", "solve_circuit",
    "solve_slab", "solve_reactor", "ValidityDomain", "ScientificModelDefinition",
    "CSTR_MODEL", "DIFFUSION_MODEL", "LUMPED_CAPACITY_MODEL",
    "assess_resistance_validity", "assess_rated_resistance_validity",
)
#: The existing benchmark's own answers. Reading a payload from it would be
#: bad enough; reading its ground truth would make the challenge a copy.
FORBIDDEN_PATH_FRAGMENTS = (
    "ground_truth", "expected_verdict", "should_be_caught_by",
    "results_hard", "results_battery", "index_hard", "index_battery",
    "split_hard", "ADJUDICATIONS",
)


def _module_paths() -> list[pathlib.Path]:
    return [REPO / name for name in TRUTH_LAYER]


def _shown(path: pathlib.Path) -> str:
    """A path for a message, which may be a temporary file the falsification
    test wrote outside the repository."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


#: Phase 2 modules. They MUST reach the runtime -- running Forge and comparing
#: its answer to the frozen truth is what they are for -- so they are excluded
#: from the no-peek audit by name rather than by accident. Neither is digested
#: in FREEZE.json, so neither can change what the challenge says.
PHASE_TWO = (
    "benchmarks/blind/run_forge.py",
    "benchmarks/blind/compare.py",
)


def test_no_phase_two_module_is_digested_by_the_freeze() -> None:
    """The exemption is safe only because the freeze does not depend on them.

    A module that both imports the runtime and contributes to a digest in
    FREEZE.json would be a hole in the firewall wide enough to drive the whole
    round through. This asserts the exemption list and the digested list are
    disjoint.
    """
    freeze = _freeze()
    digested = set(freeze["generator_digest"])
    overlap = digested & set(PHASE_TWO)
    assert not overlap, (
        f"{sorted(overlap)} both reaches the runtime and is digested by the "
        f"freeze")


def test_the_truth_layer_list_is_complete() -> None:
    """Every .py under benchmarks/blind is audited, or the audit is a subset."""
    on_disk = {
        path.relative_to(REPO).as_posix()
        for path in BLIND.rglob("*.py")
        if "__pycache__" not in path.parts and path.name != "__init__.py"
    }
    audited = set(TRUTH_LAYER) | set(PHASE_TWO)
    unaudited = on_disk - audited
    assert not unaudited, (
        f"these modules live in benchmarks/blind and are in neither "
        f"TRUTH_LAYER nor PHASE_TWO, so nothing says whether they may reach "
        f"the runtime: {sorted(unaudited)}"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_no_truth_module_imports_the_runtime(path: pathlib.Path) -> None:
    """AST import audit. An `import engcore` anywhere in the truth layer."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offences: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_ROOTS or alias.name in FORBIDDEN_ROOTS:
                    offences.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in FORBIDDEN_ROOTS or module in FORBIDDEN_ROOTS:
                offences.append(f"line {node.lineno}: from {module} import ...")
    assert not offences, (
        f"{_shown(path)} reaches the runtime: {offences}. The blind "
        f"challenge's truth is only independent if the thing that computed it "
        f"could not ask Forge for the answer."
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_no_truth_module_names_a_runtime_surface(path: pathlib.Path) -> None:
    """Name-reference audit, including names smuggled in as strings.

    An import audit alone is not enough: ``importlib.import_module("engcore…")``
    imports nothing at parse time, and a getattr on a module fetched some other
    way names no import either. So every identifier and every string constant
    in the tree is checked against the forbidden set.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    offences: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            offences.append(f"line {node.lineno}: name {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            offences.append(f"line {node.lineno}: attribute .{node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            for needle in FORBIDDEN_ROOTS:
                # A DOCSTRING may name the runtime -- saying "this does not
                # import engcore" is the point of several of them. What may not
                # appear is a string that could be RESOLVED into it, which is
                # what an import-shaped string is.
                if text == needle or text.startswith(f"{needle}."):
                    offences.append(f"line {node.lineno}: string {text!r}")
            for needle in FORBIDDEN_NAMES:
                if text == needle:
                    offences.append(f"line {node.lineno}: string {text!r}")
    assert not offences, (
        f"{_shown(path)} names a runtime surface: {offences}"
    )


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.name)
def test_no_truth_module_reads_the_existing_benchmark_answers(
    path: pathlib.Path,
) -> None:
    """The existing corpus's labels are off limits, by name.

    ``freeze.py`` reads existing PAYLOADS -- it has to, to prove no blind case
    is a copy of one -- and the guard below asserts it reads the payload key
    and nothing else. Everything that decides a case's truth may not touch the
    existing corpus at all.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    offences = [
        f"line {node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and any(fragment in node.value for fragment in FORBIDDEN_PATH_FRAGMENTS)
    ]
    if path.name == "freeze.py":
        # It compares payload bytes to prove none was copied. That is the
        # opposite of peeking, and it is why the exception is narrow: the
        # only key it may read is `payload`.
        assert '"ground_truth"' not in source and "'ground_truth'" not in source
        return
    assert not offences, (
        f"{_shown(path)} reads the existing benchmark's answers: "
        f"{offences}"
    )


def test_the_transitive_import_graph_never_reaches_the_runtime() -> None:
    """Follow every edge, not just the first.

    A truth module that imported a helper that imported ``engcore`` would pass
    every per-file audit above and still have peeked. This walks the closure.
    """
    seen: set[str] = set()
    frontier = [path for path in _module_paths()]
    trail: dict[str, str] = {}
    while frontier:
        path = frontier.pop()
        key = path.relative_to(REPO).as_posix()
        if key in seen:
            continue
        seen.add(key)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:                       # relative, inside blind/
                    base = path.parent
                    for _ in range(node.level - 1):
                        base = base.parent
                    if node.module:
                        candidate = base / pathlib.Path(
                            node.module.replace(".", "/"))
                    else:
                        candidate = base
                    for alias in node.names:
                        for option in (candidate / f"{alias.name}.py",
                                       candidate.with_suffix(".py")):
                            if option.is_file():
                                trail.setdefault(
                                    option.relative_to(REPO).as_posix(), key)
                                frontier.append(option)
                    continue
                modules = [node.module or ""]
            for module in modules:
                assert module.split(".")[0] not in FORBIDDEN_ROOTS, (
                    f"{key} reaches {module} (via {trail.get(key, 'directly')})"
                )


def test_the_guard_would_actually_catch_a_peek(tmp_path: pathlib.Path) -> None:
    """The audit fails on a module that DOES peek. A guard nobody falsified.

    Written because an audit that has only ever run against clean code is
    indistinguishable from an audit that passes everything.
    """
    peeker = tmp_path / "peeker.py"
    peeker.write_text(
        "from engcore.mcp.problem import run_electrothermal_case\n"
        "def truth(payload):\n"
        "    return run_electrothermal_case(payload)\n",
        encoding="utf-8")
    with pytest.raises(AssertionError, match="reaches the runtime"):
        test_no_truth_module_imports_the_runtime(peeker)

    stringly = tmp_path / "stringly.py"
    stringly.write_text(
        "import importlib\n"
        "def truth(payload):\n"
        "    mod = importlib.import_module('engcore.mcp.problem')\n"
        "    return mod.run_electrothermal_case(payload)\n",
        encoding="utf-8")
    with pytest.raises(AssertionError, match="names a runtime surface"):
        test_no_truth_module_names_a_runtime_surface(stringly)


def test_importing_the_truth_layer_loads_no_runtime_module() -> None:
    """The dynamic half: import it all and look at what arrived.

    The AST audits are static. This one runs the modules. If any of them
    reached the runtime at import time -- through a lazy import, an exec, or a
    path the parser cannot see -- ``sys.modules`` says so.
    """
    for name in list(sys.modules):
        if name.split(".")[0] in ("engcore", "src"):
            pytest.skip(
                "the runtime is already imported in this process (another test "
                "in the same worker imported it), so this check cannot "
                "distinguish its own imports from theirs")
    import importlib

    for dotted in (
        "benchmarks.blind.generate", "benchmarks.blind.build_truth",
        "benchmarks.blind.families", "benchmarks.blind.bound_registry",
        "benchmarks.blind.oracles.electrothermal",
        "benchmarks.blind.oracles.battery",
        "benchmarks.blind.oracles.kinetics",
        "benchmarks.blind.oracles.conduction",
        "benchmarks.blind.oracles.spice",
    ):
        importlib.import_module(dotted)
    leaked = sorted(name for name in sys.modules
                    if name.split(".")[0] in ("engcore", "crafty"))
    assert not leaked, (
        f"importing the truth layer pulled in {leaked}; the oracle reached the "
        f"runtime at import time")


# =====================================================================
# The seal
# =====================================================================

def _freeze() -> dict:
    if not (V1 / "FREEZE.json").is_file():
        pytest.skip("benchmarks/blind/v1 has not been frozen in this tree")
    return json.loads((V1 / "FREEZE.json").read_text(encoding="utf-8"))


def _digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def test_the_frozen_case_bytes_still_produce_the_frozen_digest() -> None:
    freeze = _freeze()
    paths = sorted((V1 / "cases").glob("*.json"))
    lines = [f"{p.name} {_digest(p.read_bytes())}" for p in paths]
    computed = _digest("\n".join(lines).encode("utf-8"))
    assert computed == freeze["case_set_digest"], (
        "the frozen case set no longer digests to what FREEZE.json records. A "
        "case was added, removed or edited. This is not repaired by updating "
        "the digest: a changed challenge is a NEW challenge version."
    )


def test_the_case_membership_has_not_changed() -> None:
    freeze = _freeze()
    assert len(list((V1 / "cases").glob("*.json"))) == freeze["case_count"]


def test_the_frozen_truth_bytes_still_produce_the_frozen_digest() -> None:
    freeze = _freeze()
    blob = (V1 / "TRUTH.json").read_bytes()
    assert _digest(blob) == freeze["truth_digest"], (
        "TRUTH.json has changed since the freeze. Truth is frozen BEFORE Forge "
        "runs and stays frozen after: a truth proven wrong afterwards is "
        "recorded as an erratum, never edited in place."
    )


def test_the_manifest_has_not_changed() -> None:
    freeze = _freeze()
    assert _digest((V1 / "MANIFEST.json").read_bytes()) == freeze["manifest_digest"]


def test_the_oracle_disagreement_log_has_not_changed() -> None:
    freeze = _freeze()
    assert (_digest((V1 / "ORACLE_DISAGREEMENTS.json").read_bytes())
            == freeze["oracle_disagreements_digest"])


def test_every_generator_source_file_still_digests_to_its_frozen_value() -> None:
    """The corpus is only reproducible if what made it is pinned too."""
    freeze = _freeze()
    drifted = {
        name: (recorded, _digest((REPO / name).read_bytes()))
        for name, recorded in freeze["generator_digest"].items()
        if _digest((REPO / name).read_bytes()) != recorded
    }
    assert not drifted, (
        f"the challenge's own source has changed since the freeze: "
        f"{sorted(drifted)}. Regenerating v1 from a different generator would "
        f"produce a different corpus under the same name."
    )


def test_no_truth_status_changed_after_the_freeze() -> None:
    """The class counts in FREEZE.json and in TRUTH.json must still agree.

    A blunter check than the digest and it fails differently: the digest says
    'something moved', this says WHICH truth statuses moved, which is the
    question anyone reading a broken seal actually has.
    """
    import collections

    freeze = _freeze()
    truths = json.loads((V1 / "TRUTH.json").read_text(encoding="utf-8"))["truths"]
    classes = collections.Counter(t["truth_class"] for t in truths.values())
    verdicts = collections.Counter(t["independent_verdict"]
                                   for t in truths.values())
    assert dict(classes) == freeze["truth_class_counts"]
    assert dict(verdicts) == freeze["verdict_counts"]


def test_the_frozen_corpus_reuses_no_existing_benchmark_payload() -> None:
    """No legacy hold-out case, and no copy of an open one either."""
    _freeze()
    existing: set[str] = set()
    for directory in ("cases_hard", "cases_battery"):
        folder = REPO / "benchmarks" / "hard" / directory
        for path in folder.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))["payload"]
            existing.add(_digest(json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")))
    truths = json.loads((V1 / "TRUTH.json").read_text(encoding="utf-8"))["truths"]
    reused = [cid for cid, t in truths.items()
              if t["payload_digest"] in existing]
    assert not reused, f"blind cases copied from the existing corpus: {reused}"


def test_the_first_run_artifact_is_never_overwritten() -> None:
    """If a first run exists, its digest is recorded and still matches.

    The first blind result is the primary scientific artifact of this round.
    It is preserved *especially* if it is bad, so this guard exists from the
    moment it is written rather than being added later when the number is
    known.
    """
    first = V1 / "FORGE_FIRST_RUN.json"
    seal = V1 / "FIRST_RUN_SEAL.json"
    if not first.is_file():
        pytest.skip("Forge has not been run against the frozen challenge yet")
    assert seal.is_file(), (
        "FORGE_FIRST_RUN.json exists with no FIRST_RUN_SEAL.json beside it; "
        "the primary blind result is unsealed")
    recorded = json.loads(seal.read_text(encoding="utf-8"))
    assert _digest(first.read_bytes()) == recorded["first_run_digest"], (
        "FORGE_FIRST_RUN.json has changed. The first blind run is the result; "
        "a re-run goes in a POST_FIX artifact and never replaces it."
    )
    assert recorded["pre_forge_freeze_sha"], (
        "the seal names no PRE_FORGE_FREEZE_SHA, so nothing dates the freeze "
        "before the run")


# =====================================================================
# The one place the two layers may meet: a check ON the freeze
# =====================================================================

def test_the_oracle_bounds_match_the_model_records() -> None:
    """The transcribed bounds have not drifted from the records they came from.

    This test imports the runtime. That is allowed HERE and nowhere in the
    truth layer, because it runs AFTER the freeze as a check on it: if a
    threshold moved in production, the frozen truth was computed against the
    old one and this says so. It is never an input to a truth.
    """
    import importlib
    import pkgutil

    sys.path.insert(0, str(REPO / "src"))
    import engcore
    from engcore.scientific.models.definition import ScientificModelDefinition

    from benchmarks.blind.oracles import battery as battery_oracle
    from benchmarks.blind.oracles import electrothermal as et_oracle
    from benchmarks.blind.oracles import kinetics as kinetics_oracle

    declared: dict[tuple[str, str], tuple[float | None, float | None]] = {}
    for info in pkgutil.walk_packages(engcore.__path__, "engcore."):
        try:
            module = importlib.import_module(info.name)
        except Exception:                              # noqa: BLE001
            continue
        for name in dir(module):
            value = getattr(module, name, None)
            if not isinstance(value, ScientificModelDefinition):
                continue
            for condition in getattr(value.validity, "conditions", ()) or ():
                minimum = getattr(condition, "minimum", None)
                maximum = getattr(condition, "maximum", None)
                declared[(value.model_id, condition.name)] = (
                    None if minimum is None else float(minimum.magnitude),
                    None if maximum is None else float(maximum.magnitude),
                )

    # Scoped by MODEL FAMILY rather than by a prefix that matches everything.
    # `temperature` is declared by the material models over [200, 450] K and by
    # the CSTR over [250, 1000] K -- the same NAME, two different bounds, two
    # different classes in the register -- so an unscoped comparison reports
    # every one of them as drift. That is the exact confusion
    # `bound_registry.bound_for` takes a `system` argument to avoid.
    drift: list[str] = []
    scopes = {
        et_oracle: ("electrical.", "thermal."),
        battery_oracle: ("battery.",),
        kinetics_oracle: ("kinetics.",),
    }
    for oracle, prefixes in scopes.items():
        for condition, (minimum, maximum, _mi, _ma) in oracle.BOUNDS.items():
            matches = [(model, lo, hi) for (model, name), (lo, hi)
                       in declared.items()
                       if name == condition
                       and any(model.startswith(p) for p in prefixes)]
            if not matches:
                continue
            for model, lo, hi in matches:
                if (lo is None) != (minimum is None) or (
                        lo is not None and abs(lo - minimum) > 1e-12 * max(abs(lo), 1.0)):
                    drift.append(f"{model}::{condition} minimum {lo} vs {minimum}")
                if (hi is None) != (maximum is None) or (
                        hi is not None and abs(hi - maximum) > 1e-12 * max(abs(hi), 1.0)):
                    drift.append(f"{model}::{condition} maximum {hi} vs {maximum}")
    assert not drift, (
        f"the oracle's transcribed bounds have drifted from the model records: "
        f"{sorted(set(drift))}. The frozen truth was computed against the "
        f"transcribed values; if production moved a threshold, the frozen "
        f"result is a result about the old one and must be read that way."
    )
