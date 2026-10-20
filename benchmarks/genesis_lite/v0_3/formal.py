"""Genesis-lite v0.3 DRAFT, P-4: the formal-tier driver over ``analysis.FORMAL_GRID``.

No formal driver existed (readiness row 11, deep audit D-09 / OBS-04). The pilot driver is not one: its master label
carries no tier, its root is revealed with its results, it runs arm by arm (so the records of world sets that later arms
have not yet seen sit in its output file), and it takes the root's path on the command line (the B-LEAK channel).

This driver:

* refuses unless the preregistration it is given is the COMMITTED v0.3 document that the code rebuilds, is FROZEN,
  contains no ``OWNER_DECISION_REQUIRED``, names exactly the v0.3 arm registry and states its candidate (one named
  candidate with its code digests, or ``NONE`` for a baseline-only attempt), commits the root and the environment
  manifest, and the current environment matches it;
* refuses a RETIRED root: one that any other committed preregistration names (pilot roots were revealed with their
  results);
* ADMITS the attempt to the operator's attempt registry and PUBLISHES the admission to the external evaluator (OD-8)
  BEFORE the first world is derived. One attempt per root, whatever the output directory, label or identity; the
  external evaluator refuses a second admission of the same root commitment;
* derives every master from the root, the preregistration digest and the attempt's nonce
  (``forge.genesis_lite.v0_3/formal/<prereg>/<nonce>/...``). A formal master never equals a pilot or development master,
  and two attempts never share a world;
* runs the candidate INSIDE the same attempt, world-set-major, next to every registered arm: every arm runs a world set
  before any of that world set's records leaves the driver (OBS-04), so no record reveals a kind to an arm that has not
  run that world set yet;
* reads the root from STDIN, never from the command line;
* never relabels a record. A record produced under another identity becomes INVALID_BENCHMARK with the reason. The
  driver adds ``tier``, ``root_commitment_sha256``, ``world_set_index`` and ``attempt_sha256``;
* writes an append-only, hash-chained run log that refuses to open an existing file. Its head goes to the evaluator.

After the reveal, :func:`verify_attempt` is the evaluator's check. It checks that the admission is the FIRST one the
evaluator received for that root (:class:`.registry.EvaluatorInbox`), recomputes every master from the revealed root and
that admission, re-derives every answer key, and re-derives every card the arm was shown (the pseudonyms depend on the
arm's name). A record from another world, another attempt, or with another arm's label does not survive. Credits are
re-derived by the evaluator from the sealed proposals and the key (OD-8), not by this check.

NOT done here: the OD-20 deployment itself. The driver cannot verify that the operator, escrow and secrets run under
another OS account or container. That is a preregistered start condition, checked by the deployment attack suite
(:mod:`.deployment_attacks`), the secret-inventory scan (:mod:`.secret_scan`) and the independent probe rerun.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import pathlib
import sys
from typing import Any, Callable, Mapping, Sequence

from .. import analysis as v02_analysis
from . import environment
from .registry import AttemptRefused, AttemptRegistry, campaign_set_sha256

TIER = "formal"
LABEL = "forge.genesis_lite.v0_3/formal"
OWNER_DECISION_REQUIRED = "OWNER_DECISION_REQUIRED"
NO_CANDIDATE = "NONE"
PREREG_DIR = pathlib.Path(__file__).resolve().parents[1] / "preregistration"

Runner = Callable[..., Mapping[str, Any]]


class FormalRefused(RuntimeError):
    """The formal tier cannot run (or its log cannot be trusted) as preregistered."""


def registered_arms() -> list[str]:
    from .arms import ARMS  # noqa: PLC0415

    return sorted(ARMS)


def identity(doc: Mapping[str, Any]) -> str:
    """The sha256 of the canonical preregistration bytes (the same canonical form as v0.2)."""
    return hashlib.sha256(json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=True).encode() + b"\n").hexdigest()


def retired_root_commitments(exclude_identity: str | None = None) -> frozenset[str]:
    """Every root commitment (pilot or formal) of every committed preregistration other than ``exclude_identity``: those
    roots are retired. Pilot roots were revealed with their results; a formal root belongs to its own identity only.
    A root revealed anywhere else is outside this list (the operator generates a fresh root at freeze)."""
    out = set()
    for path in sorted(PREREG_DIR.glob("genesis_lite_v0*.json")):
        raw = path.read_bytes()
        if exclude_identity is not None and hashlib.sha256(raw).hexdigest() == exclude_identity:
            continue
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(doc, Mapping):
            continue
        formal_part = doc.get("formal") if isinstance(doc.get("formal"), Mapping) else {}
        for commitment in (doc.get("pilot_root_commitment_sha256"), formal_part.get("root_commitment_sha256")):
            if isinstance(commitment, str) and len(commitment) == 64:
                out.add(commitment)
    return frozenset(out)


def committed_identity_problems(doc: Mapping[str, Any]) -> list[str]:
    """The document must BE the committed v0.3 preregistration (bytes, digest file) and the code must rebuild it: a
    dict that merely says FROZEN is not a frozen identity."""
    from .preregistration import canonical, committed_doc_problems  # noqa: PLC0415 - it imports this module

    return committed_doc_problems(canonical(dict(doc)))


def master_for(root: bytes, prereg_sha256: str, nonce: str, presentation: str, campaign_id: str, seed: int) -> bytes:
    """One master per world set of one admitted attempt of one identity."""
    return hmac.new(root, f"{LABEL}/{prereg_sha256}/{nonce}/{presentation}/{seed}/{campaign_id}".encode(),
                    hashlib.sha256).digest()


def plan(grid: frozenset[v02_analysis.WorldSet] = v02_analysis.FORMAL_GRID) -> list[v02_analysis.WorldSet]:
    """The world sets in a fixed order (campaign, seed, presentation)."""
    return sorted(grid, key=lambda ws: (int(ws[1].rsplit("-", 1)[1]), ws[2], ws[0]))


def _mentions_owner_decision(node: Any) -> bool:
    if isinstance(node, str):
        return OWNER_DECISION_REQUIRED in node
    if isinstance(node, Mapping):
        return any(_mentions_owner_decision(k) or _mentions_owner_decision(v) for k, v in node.items())
    if isinstance(node, (list, tuple)):
        return any(_mentions_owner_decision(v) for v in node)
    return False


def candidate_of(doc: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The candidate the identity names, or None for a baseline-only attempt. Refuses anything else."""
    cand = doc.get("formal", {}).get("candidate") if isinstance(doc.get("formal"), Mapping) else None
    if cand == NO_CANDIDATE:
        return None
    if not (isinstance(cand, Mapping) and isinstance(cand.get("name"), str) and isinstance(cand.get("spec"), str)
            and ":" in cand["spec"] and isinstance(cand.get("code_sha256"), Mapping) and cand["code_sha256"]):
        raise FormalRefused("the identity names its candidate {name, spec module:function, code_sha256 {path: sha}} or "
                            f"{NO_CANDIDATE!r}")
    if cand["name"] in registered_arms():
        raise FormalRefused(f"the candidate takes a registered arm's name {cand['name']!r}")
    return cand


_ROOT = pathlib.Path(__file__).resolve().parents[3]
#: modules and calls that would load or run code the static pin cannot see (a static screen, not a proof: behaviour is
#: the external evaluator's source review, D6)
_DYNAMIC_CALLS = frozenset({"exec", "eval", "compile", "__import__", "import_module"})
#: modules whose import, or whose attribute call to a dynamic name, loads or runs unseen code
_DYNAMIC_MODULES = frozenset({"importlib", "runpy", "imp", "builtins"})


def _identity_pinned_files() -> frozenset[str]:
    """Files the committed v0.3 identity pins by digest (its own files and the v0.2 files it reuses)."""
    from .preregistration import PREREG_PATH  # noqa: PLC0415

    doc = json.loads(PREREG_PATH.read_bytes())
    out = {f"benchmarks/genesis_lite/v0_3/{n}" for n in doc.get("v0_3_files", {})}
    reused = doc.get("reused_unchanged_from_v0_2", {})
    out |= {f"benchmarks/genesis_lite/{n}" for n in reused.get("harness", {})}
    out |= {f"benchmarks/genesis_lite/{n}" for n in reused.get("evaluator", {})}
    out |= {f"src/engcore/blindfold/{n}" for n in reused.get("substrate", {})}
    out |= set(doc.get("package_markers", {}))
    return frozenset(out)


def _git_lines(*args: str) -> list[str] | None:
    import subprocess  # noqa: PLC0415

    run = subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True, check=False)
    return run.stdout.splitlines() if run.returncode == 0 else None


def _tracked_engcore() -> frozenset[str]:
    """src/engcore files in the HEAD commit (covered by the core certificate, OD-3), and only while src/engcore has no
    staged, modified or untracked change: a file that differs from HEAD is never admitted on the strength of HEAD."""
    dirty = _git_lines("status", "--porcelain", "--untracked-files=all", "--", "src/engcore")
    tracked = _git_lines("ls-tree", "-r", "--name-only", "HEAD", "--", "src/engcore")
    if dirty is None or tracked is None or dirty:
        return frozenset()
    return frozenset(tracked)


class _Ambiguous(Exception):
    pass


def _module_file(module: str) -> str | None:
    """The file CPython would load for a first-party module: a package's __init__.py before a module's .py. Refuses
    (``_Ambiguous``) when an extension module, a sourceless .pyc or a .pyw shares the stem, because then the scanned
    source may not be what runs."""
    for base in (_ROOT, _ROOT / "src"):
        stem = base.joinpath(*module.split("."))
        shadows = [p for p in stem.parent.glob(stem.name + ".*") if p.suffix in (".pyd", ".so", ".pyc", ".pyw")] \
            if stem.parent.is_dir() else []
        package, source = stem / "__init__.py", stem.with_suffix(".py")
        if stem.is_dir():                                    # __init__.<tag>.pyd / __init__.pyc load before __init__.py
            shadows += [p for p in stem.glob("__init__.*") if p.suffix in (".pyd", ".so", ".pyc", ".pyw")]
        if shadows and (package.is_file() or source.is_file() or stem.is_dir()):
            raise _Ambiguous(f"{module}: {sorted(p.name for p in shadows)} share its name")
        if shadows:
            raise _Ambiguous(f"{module}: only a compiled form exists ({sorted(p.name for p in shadows)})")
        if package.is_file():
            return package.relative_to(_ROOT).as_posix()
        if source.is_file():
            return source.relative_to(_ROOT).as_posix()
    return None


def _with_parents(module: str) -> list[str]:
    """The files of a module AND of every parent package (all of them run on import)."""
    parts = module.split(".")
    out = []
    for i in range(1, len(parts) + 1):
        found = _module_file(".".join(parts[:i]))
        if found is not None:
            out.append(found)
    return out


def _static_imports(rel: str) -> tuple[set[str], set[str]]:
    """(first-party files a candidate file imports, dynamic-code names it uses), by reading its source only."""
    import ast  # noqa: PLC0415

    tree = ast.parse((_ROOT / rel).read_bytes())
    package = rel.rsplit("/", 1)[0].replace("/", ".")
    files, dynamic = set(), set()
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join(parts + ([base] if base else []))
            modules = [base] + [f"{base}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _DYNAMIC_CALLS:
                dynamic.add(func.id)                              # exec(...), eval(...), compile(...), __import__(...)
            elif isinstance(func, ast.Attribute) and func.attr in _DYNAMIC_CALLS and (
                    func.attr in ("__import__", "import_module")
                    or (isinstance(func.value, ast.Name) and func.value.id in _DYNAMIC_MODULES)):
                dynamic.add(func.attr)                            # builtins.exec(...), importlib.import_module(...)
            # re.compile(...), model.eval(), torch.compile(...) are ordinary method calls, not dynamic loading
        for module in modules:
            if module.endswith(".*"):
                continue
            top = module.split(".")[0]
            if top in _DYNAMIC_MODULES and module != "builtins":
                dynamic.add(top)                                  # importlib / runpy / imp imported at all
            if module.startswith("builtins.") and module.split(".", 1)[1] in _DYNAMIC_CALLS:
                dynamic.add(module.split(".", 1)[1])              # from builtins import exec
            files.update(_with_parents(module))
    return files, dynamic


def candidate_code_problems(cand: Mapping[str, Any] | None) -> list[str]:
    """The candidate's code is pinned WITHOUT running it on the operator's side (review round 3, N1): its spec module,
    its parent packages and every first-party file it imports, read statically, must be pinned by digest in
    ``code_sha256``, by this identity, or (for src/engcore) be in HEAD with src/engcore clean. Calls and imports of known
    dynamic-loading names are refused as a static SCREEN; this proves which bytes run, not what they do (code reached
    through attribute tricks or through pinned helpers is the external evaluator's source review, D6). Data files the
    candidate reads are listed in ``code_sha256`` by its author; the harness re-measures every listed file before every
    card."""
    if cand is None:
        return []
    problems = []
    pinned = dict(cand.get("code_sha256", {}))
    for rel, sha in sorted(pinned.items()):
        path = (_ROOT / rel).resolve()
        if not path.is_relative_to(_ROOT) or not path.is_file():
            problems.append(f"the candidate's file {rel} is not in this tree")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            problems.append(f"the candidate's file {rel} is not the preregistered code")
    module = str(cand["spec"]).split(":", 1)[0]
    try:
        own_chain = _with_parents(module)
        own = _module_file(module)
        if own is None or own not in pinned:
            problems.append(f"the candidate's module {module} is not one of its pinned files")
        if problems:
            return problems
        allowed = set(pinned) | _identity_pinned_files() | _tracked_engcore()
        for dep in sorted(set(own_chain) - allowed):
            problems.append(f"the candidate's package file {dep} runs on import and is not pinned")
        for rel in sorted(r for r in pinned if r.endswith(".py")):
            files, dynamic = _static_imports(rel)
            if dynamic:
                problems.append(f"{rel} uses {sorted(dynamic)}: dynamic loading is not admissible in a pinned candidate")
            for dep in sorted(files - allowed):
                problems.append(f"the candidate imports {dep}, which is not pinned")
    except _Ambiguous as exc:
        problems.append(f"ambiguous module file: {exc}")
    except SyntaxError as exc:
        problems.append(f"a pinned candidate file does not parse: {exc.filename}")
    return problems


def budget_hours(doc: Mapping[str, Any]) -> float | None:
    """D7: the approved wall-clock cap of the whole formal attempt (baselines + candidate), or None if not set."""
    formal = doc.get("formal", {}) if isinstance(doc.get("formal"), Mapping) else {}
    budget = formal.get("budget", {}) if isinstance(formal.get("budget"), Mapping) else {}
    hours = budget.get("total_hours")
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not hours > 0 or hours != hours:
        return None
    return float(hours)


def preflight(doc: Mapping[str, Any], root: bytes, manifest: Mapping[str, Any]) -> list[str]:
    """Every reason the formal tier may not start under ``doc`` with ``root`` in the environment ``manifest``."""
    problems = []
    if doc.get("status") != "FROZEN":
        problems.append(f"the preregistration is {doc.get('status')!r}, not FROZEN (a DRAFT never drives a formal run)")
    if _mentions_owner_decision(doc):
        problems.append("the preregistration still contains OWNER_DECISION_REQUIRED")
    if set(doc.get("arms", {})) != set(registered_arms()):
        problems.append("the preregistration does not name exactly the registered v0.3 arms")
    try:
        problems += candidate_code_problems(candidate_of(doc))
    except FormalRefused as exc:
        problems.append(str(exc))
    formal = doc.get("formal", {}) if isinstance(doc.get("formal"), Mapping) else {}
    commitment = hashlib.sha256(root).hexdigest()
    if len(root) < 32:
        problems.append("the root is shorter than 32 bytes")
    if formal.get("root_commitment_sha256") != commitment:
        problems.append("the root does not match the preregistered root commitment")
    listed = set(formal.get("retired_root_commitments", ()) or ())
    if commitment in listed | retired_root_commitments(exclude_identity=identity(doc)):
        problems.append("the root is retired: an earlier preregistration committed it (and its pilot revealed it)")
    if formal.get("environment_manifest_sha256") != environment.manifest_digest(manifest):
        problems.append("the environment manifest differs from the preregistered one")
    if budget_hours(doc) is None:
        problems.append("the formal budget (D7: total_hours, baselines + candidate) is not a positive number")
    return problems


def harness_runner(doc: Mapping[str, Any]) -> Runner:
    """The only production runner: the v0.3 harness bound to the committed identity in the formal tier (it measures
    the environment itself)."""
    from . import harness  # noqa: PLC0415 - harness imports preregistration, which imports this module
    from .preregistration import canonical  # noqa: PLC0415

    try:
        binding = harness.bind(canonical(dict(doc)), tier=TIER)
    except harness.HarnessRefused as exc:
        raise FormalRefused(f"the v0.3 harness refuses to bind: {exc}") from exc

    def runner(arm: str, *, master_seed: bytes, campaign_id: str, presentation: str, seed: int) -> Mapping[str, Any]:
        return harness.run_one(arm, binding=binding, master_seed=master_seed, campaign_id=campaign_id,
                               presentation=presentation, seed=seed).to_dict()

    return runner


def run_formal(root: bytes, doc: Mapping[str, Any], *, manifest: Mapping[str, Any], registry: AttemptRegistry,
               publish: Callable[[Mapping[str, Any]], None], sink: Callable[[dict[str, Any]], None],
               runner: Runner | None = None, clock: Callable[[], float] | None = None) -> dict[str, Any]:
    """Run every registered arm and the named candidate once on every world set of FORMAL_GRID, world set by world set.
    ``runner`` and ``clock`` exist for orchestration tests only; production uses :func:`harness_runner` and
    ``time.monotonic``. ``publish`` delivers the admission to the external evaluator; if it fails, the attempt is
    consumed and nothing runs. D7: before each world set the elapsed time is checked against the preregistered budget;
    past it the attempt stops as BUDGET_EXCEEDED. It is INVALID and never partially claimed: the evaluator's
    verification and the lift rule's coverage both need every world set."""
    problems = preflight(doc, root, manifest) + committed_identity_problems(doc)
    if problems:
        raise FormalRefused("; ".join(problems))
    if not isinstance(registry, AttemptRegistry) or not callable(publish):
        raise FormalRefused("a formal attempt is admitted to the operator's registry and published to the evaluator first")
    cand = candidate_of(doc)
    names = registered_arms() + ([cand["name"]] if cand else [])
    if runner is None:
        runner = harness_runner(doc)
    expected, commitment = identity(doc), hashlib.sha256(root).hexdigest()
    try:                                                     # consumed here, before the first world is derived
        attempt = registry.admit(root_commitment_sha256=commitment, prereg_sha256=expected,
                                 campaign_set_sha256=campaign_set_sha256(plan()), tier=TIER)
    except AttemptRefused as exc:
        raise FormalRefused(str(exc)) from exc
    try:
        publish(dict(attempt))
    except AttemptRefused as exc:                             # the evaluator refused: the attempt is consumed, not run
        raise FormalRefused(f"the evaluator refused the admission: {exc}") from exc
    import time  # noqa: PLC0415

    clock = clock or time.monotonic
    cap, started, status, ran = budget_hours(doc) * 3600.0, clock(), "COMPLETE", 0
    invalid = 0
    for index, (presentation, campaign_id, seed) in enumerate(plan()):
        if clock() - started > cap:
            status = "BUDGET_EXCEEDED"
            break
        ran += 1
        master = master_for(root, expected, attempt["nonce"], presentation, campaign_id, seed)
        held = [dict(runner(name, master_seed=master, campaign_id=campaign_id, presentation=presentation, seed=seed))
                for name in names]                          # nothing of this world set leaves before every arm ran it
        for rec in held:
            if rec.get("prereg_sha256") != expected:
                rec["status"] = "INVALID_BENCHMARK"
                rec["reasons"] = [*rec.get("reasons", []), f"produced under {str(rec.get('prereg_sha256'))[:12]}..., "
                                                           f"not this identity {expected[:12]}..."]
            invalid += rec.get("status") != "VALID"
            sink({**rec, "tier": TIER, "root_commitment_sha256": commitment, "world_set_index": index,
                  "attempt_sha256": attempt["attempt_sha256"]})
    return {"status": status, "world_sets_run": ran, "budget_hours": cap / 3600.0,
            "world_sets": len(v02_analysis.FORMAL_GRID), "arms": len(names), "invalid_runs": invalid,
            "prereg_sha256": expected, "root_commitment_sha256": commitment,
            "attempt_sha256": attempt["attempt_sha256"], "registry_head": registry.head()}


SCREEN_PREFIXES = v02_analysis.SCREEN_PREFIXES


def screen_rederives(master: bytes, arm: str, campaign_id: str, presentation: str, seed: int) -> bool:
    """Whether any arm-independent screen of the harness fires for this world set (:func:`screen_reasons`)."""
    return bool(screen_reasons(master, arm, campaign_id, presentation, seed))


def screen_reasons(master: bytes, arm: str, campaign_id: str, presentation: str, seed: int) -> list[str]:
    """The exact reasons the harness records when an arm-independent screen fires, re-derived from the master: the
    literal leakage audit of the presented cards, then every trap world whose best-constant textbook law would pass, in
    the harness's order and wording (benchmarks/genesis_lite/harness.py, ``_run``)."""
    from engcore.blindfold.escrow import EscrowService  # noqa: PLC0415
    from engcore.blindfold.expression import c, mul, pw, v  # noqa: PLC0415
    from engcore.blindfold.universe import UniverseKind  # noqa: PLC0415

    from .. import harness as v02h  # noqa: PLC0415
    from ..answer_key import export_answer_key  # noqa: PLC0415
    from ..evaluator.score import audit_presented_cards  # noqa: PLC0415
    from ..presentation import present  # noqa: PLC0415

    camp = EscrowService(master_seed=master)._new_campaign(campaign_id, {UniverseKind(k): n for k, n in v02h.MIX.items()})
    pkey = v02h.presentation_key(master, arm, seed, presentation)
    skey = v02h.stimulus_key(master, seed, presentation)
    shown = {uid: present(json.loads(json.dumps(camp.worlds[uid].public_card())), presentation, pkey, skey)
             for uid in camp.order}
    key = export_answer_key(master, campaign_id, v02h.MIX, list(camp.order))
    audit = audit_presented_cards([{**p.card, "universe_id": uid} for uid, p in shown.items()], key)
    reasons = []
    if audit["status"] != "NO_LITERAL_LEAK_FOUND":
        reasons.append(f"leakage audit: {audit['findings'][:3]}")
    entries = {e["universe_id"]: e for e in key["universes"]}
    for uid, p in shown.items():
        entry = entries[uid]
        if p.historical is not None and entry["kind"] in v02h.LAW_CREDIT_KINDS and entry["law"] is not None:
            hist_name, exponent = p.historical
            if v02h._textbook_could_pass(mul(c(1.0), pw(v(p.to_original[hist_name]), exponent)), entry):
                reasons.append(f"trap {uid} ({entry['kind']}): the textbook law fits the hidden world, the instance "
                               f"tests nothing")
    return reasons


def _shown_card_digests(master: bytes, arm: str, campaign_id: str, presentation: str, seed: int) -> dict[str, str]:
    """Every card the arm was shown in this world set, re-derived from the master (escrow cards, then the presentation
    under the arm's run-private pseudonym key and the world set's shared stimulus key)."""
    from engcore.blindfold.escrow import EscrowService  # noqa: PLC0415
    from engcore.blindfold.universe import UniverseKind  # noqa: PLC0415

    from .. import harness as v02h  # noqa: PLC0415
    from ..presentation import present  # noqa: PLC0415

    camp = EscrowService(master_seed=master)._new_campaign(campaign_id, {UniverseKind(k): n for k, n in v02h.MIX.items()})
    pkey = v02h.presentation_key(master, arm, seed, presentation)
    skey = v02h.stimulus_key(master, seed, presentation)
    out = {}
    for uid in camp.order:
        card = json.loads(json.dumps(camp.worlds[uid].public_card()))
        out[uid] = v02h._digest(present(card, presentation, pkey, skey).card)
    return out


def expected_runs(arms: Sequence[str]) -> set[tuple[str, v02_analysis.WorldSet]]:
    return {(arm, ws) for arm in arms for ws in v02_analysis.FORMAL_GRID}


def verify_attempt(log_path: pathlib.Path, root: bytes, admission: Mapping[str, Any], *, inbox: Any,
                   prereg_sha256: str, pair_bound: Mapping[str, Any], replay_runner: Runner | None,
                   candidate: str | None = None,
                   runs: set[tuple[str, v02_analysis.WorldSet]] | None = None) -> list[str]:
    """The external evaluator's post-reveal check of one attempt (module docstring). It reads the WHOLE sealed run log,
    whose head must be the one published to the evaluator for this attempt; every expected (arm, world set) must appear
    exactly once (``runs``; default: every registered arm, plus ``candidate``, on the formal grid). For every universe it
    re-derives the kind, the searched-family flag and the law form from the revealed key and RE-SCORES the sealed
    proposal with the v0.3 evaluator under ``pair_bound``; every registered arm's record is REPLAYED with
    ``replay_runner`` (the evaluator's own v0.3 harness). Without a runner, the registered records stay unverified and
    that is reported. Never raises."""
    from ..answer_key import export_answer_key, key_digest  # noqa: PLC0415
    from ..evaluator.score import in_monomial_family  # noqa: PLC0415
    from ..harness import MIX  # noqa: PLC0415
    from . import evaluator as v03e  # noqa: PLC0415
    from .harness import law_form  # noqa: PLC0415
    from .registry import REGISTRY_SCHEMA, entry_digest  # noqa: PLC0415

    problems = []
    try:
        if admission.get("schema") != REGISTRY_SCHEMA or entry_digest(admission) != admission.get("attempt_sha256"):
            problems.append("the admission is not a well-formed registry entry")
        if admission.get("tier") != TIER or admission.get("prereg_sha256") != prereg_sha256:
            problems.append("the admission is not a formal admission of this identity")
        if hashlib.sha256(root).hexdigest() != admission.get("root_commitment_sha256"):
            problems.append("the revealed root is not the admitted one")
        first = inbox.first_admission(str(admission.get("root_commitment_sha256")))
        if first is None or first.get("attempt_sha256") != admission.get("attempt_sha256"):
            problems.append("the admission is not the first one the evaluator received for this root")
        published = inbox.published_heads(str(admission.get("attempt_sha256")))
        verify_log(log_path)
        lines = log_path.read_bytes().splitlines()
        head = hashlib.sha256(lines[-1]).hexdigest() if lines else "0" * 64
        if published is None or published.get("run_log") != head:
            problems.append("the run log's head is not the one published to the evaluator")
        records = [json.loads(line)["record"] for line in lines]
    except Exception as exc:  # noqa: BLE001 - the evaluator's check reports, it never crashes
        return problems + [f"the attempt cannot be read ({type(exc).__name__}: {str(exc)[:120]})"]
    if problems:
        return problems
    seen = [(str(r.get("arm")), (str(r.get("presentation")), str(r.get("campaign_id")), r.get("seed"))) for r in records]
    if len(seen) != len(set(seen)):
        problems.append("some (arm, world set) appears more than once")
    want = expected_runs(registered_arms() + ([candidate] if candidate else [])) if runs is None else runs
    try:
        bound = v03e._checked(v03e.PairBound(**dict(pair_bound)))
    except (TypeError, v03e.EvaluatorRefused):
        return problems + ["the preregistered pair bound is not well formed"]
    if replay_runner is None:
        problems.append("the registered arms' records were not replayed: they remain unverified")
    if set(seen) != want:
        problems.append(f"the log does not hold exactly the expected runs ({len(set(seen) ^ want)} differ)")
    for rec in records:
        where = f"{rec.get('arm')}/{rec.get('presentation')}/{rec.get('campaign_id')}/{rec.get('seed')}"
        try:
            if rec.get("attempt_sha256") != admission["attempt_sha256"]:
                problems.append(f"{where}: not from the published attempt")
                continue
            master = master_for(root, prereg_sha256, str(admission["nonce"]), str(rec["presentation"]),
                                str(rec["campaign_id"]), int(rec["seed"]))
            if rec.get("status") != "VALID":
                reasons = list(rec.get("reasons") or ())
                if not (reasons and all(str(r).startswith(SCREEN_PREFIXES) for r in reasons)):
                    problems.append(f"{where}: an invalid run that no preregistered screen explains")
                elif reasons != screen_reasons(master, str(rec["arm"]), str(rec["campaign_id"]),
                                               str(rec["presentation"]), int(rec["seed"])):
                    problems.append(f"{where}: the record's screen reasons (leakage audit / trap) do not re-derive "
                                    f"exactly from the revealed root")
                continue
            ids = [u.get("universe_id") for u in rec.get("universes", [])]
            key = export_answer_key(master, str(rec["campaign_id"]), MIX, ids)
            if key.get("status") != "DERIVED" or key_digest(key) != rec.get("key_digest"):
                problems.append(f"{where}: the answer key does not re-derive from the revealed root and admission")
                continue
            shown = _shown_card_digests(master, str(rec["arm"]), str(rec["campaign_id"]), str(rec["presentation"]),
                                        int(rec["seed"]))
            if shown != dict(rec.get("presented_card_digests", {})):
                problems.append(f"{where}: the cards this arm was shown do not re-derive (arm, world or presentation "
                                f"differs)")
                continue
            entries = {e["universe_id"]: e for e in key["universes"]}
            for u in rec["universes"]:
                e = entries[u["universe_id"]]
                if u.get("kind") != e["kind"] or u.get("law_form") != law_form(e) \
                        or u.get("truth_in_searched_family") is not in_monomial_family(e["law"]):
                    problems.append(f"{where}/{u['universe_id']}: kind, law form or searched-family flag does not "
                                    f"re-derive from the key")
                    continue
                proposal = u.get("proposal")
                if not isinstance(proposal, Mapping):
                    problems.append(f"{where}/{u['universe_id']}: no sealed proposal to re-score")
                    continue
                got = v03e.score_universe(proposal, e, bound=bound)
                if got["outcome"] != u.get("outcome") or got["credit"] != float(u.get("credit")):
                    problems.append(f"{where}/{u['universe_id']}: the sealed proposal re-scores to "
                                    f"{got['outcome']} / {got['credit']}, not the recorded result")
            if replay_runner is not None and rec.get("arm") in registered_arms():
                problems += replay_record(rec, root, admission, prereg_sha256=prereg_sha256, runner=replay_runner)
        except Exception as exc:  # noqa: BLE001 - one bad record is a finding, never a crash
            problems.append(f"{where}: malformed record ({type(exc).__name__})")
    return problems


def replay_record(record: Mapping[str, Any], root: bytes, admission: Mapping[str, Any], *, prereg_sha256: str,
                  runner: Runner) -> list[str]:
    """Re-run one record of a REGISTERED (deterministic) arm on its re-derived master with ``runner`` (the evaluator's
    own v0.3 harness) and compare every universe's answer, outcome and credit. A record whose universes came from
    another arm (a whole-record swap, review round 3, N3) does not replay. Never raises."""
    where = f"{record.get('arm')}/{record.get('presentation')}/{record.get('campaign_id')}/{record.get('seed')}"
    try:
        if record.get("arm") not in registered_arms():
            return [f"{where}: only registered (deterministic) arms are replayed"]
        master = master_for(root, prereg_sha256, str(admission["nonce"]), str(record["presentation"]),
                            str(record["campaign_id"]), int(record["seed"]))
        again = runner(str(record["arm"]), master_seed=master, campaign_id=str(record["campaign_id"]),
                       presentation=str(record["presentation"]), seed=int(record["seed"]))

        def view(rec: Mapping[str, Any]) -> list[tuple[Any, ...]]:
            return [(u.get("universe_id"), u.get("answer"), u.get("outcome"), u.get("credit"),
                     u.get("truth_in_searched_family"), u.get("kind")) for u in rec.get("universes", [])]

        if again.get("status") != record.get("status"):
            return [f"{where}: the replay's status differs ({again.get('status')})"]
        return [] if view(again) == view(record) else [f"{where}: the replay does not reproduce the recorded outcomes"]
    except Exception as exc:  # noqa: BLE001
        return [f"{where}: replay failed ({type(exc).__name__})"]


class SealedLog:
    """Append-only JSONL run log; each line carries the sha256 of the previous line (the first line chains to zeros)."""

    def __init__(self, path: pathlib.Path) -> None:
        self._fh = open(path, "xb")                          # noqa: SIM115 - refuses an existing file: no second attempt
        self._prev = "0" * 64

    def __call__(self, record: Mapping[str, Any]) -> None:
        line = json.dumps({"prev_sha256": self._prev, "record": record}, sort_keys=True, separators=(",", ":")).encode()
        self._fh.write(line + b"\n")
        self._fh.flush()
        self._prev = hashlib.sha256(line).hexdigest()

    @property
    def head(self) -> str:
        return self._prev

    def close(self) -> None:
        self._fh.close()


def verify_log(path: pathlib.Path) -> int:
    """The number of records in an intact chain; FormalRefused at the first broken link."""
    prev, n = "0" * 64, 0
    for n, line in enumerate(path.read_bytes().splitlines(), start=1):
        if json.loads(line).get("prev_sha256") != prev:
            raise FormalRefused(f"run log chain broken at line {n}")
        prev = hashlib.sha256(line).hexdigest()
    return n


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Genesis-lite v0.3 formal tier (reads the root, hex, from stdin)")
    p.add_argument("--preregistration", required=True, type=pathlib.Path, help="the FROZEN v0.3 preregistration")
    p.add_argument("--out", required=True, type=pathlib.Path, help="operator-only directory; must not exist")
    p.add_argument("--registry", required=True, type=pathlib.Path,
                   help="operator-only attempt-registry directory, outside every run directory")
    p.add_argument("--publish-to", required=True, type=pathlib.Path,
                   help="the external evaluator's inbox (append-only, outside the operator's control): admissions and "
                        "the final run-log and registry heads are appended there")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = bytes.fromhex(sys.stdin.readline().strip())
    doc = json.loads(args.preregistration.read_bytes())
    manifest = environment.build_manifest()
    problems = preflight(doc, root, manifest) + committed_identity_problems(doc)
    if _git_lines("status", "--porcelain", "--untracked-files=all") != []:
        problems.append("the tree is not a clean checkout: an untracked or modified file could run in the operator's "
                        "or a proposer's process")
    for name, path in (("attempt registry", args.registry), ("evaluator inbox", args.publish_to)):
        if path.resolve().is_relative_to(args.out.resolve()):
            problems.append(f"the {name} lies inside the run directory")
    if problems:                                             # refused before anything is created
        print("REFUSED: " + "; ".join(problems), file=sys.stderr)
        return 2

    from .registry import EvaluatorInbox  # noqa: PLC0415

    publish = EvaluatorInbox(args.publish_to).receive          # refuses a second admission of the same root

    args.out.mkdir(parents=True, exist_ok=False)
    log = SealedLog(args.out / "runs.jsonl")
    registry = AttemptRegistry(args.registry)
    try:
        summary = run_formal(root, doc, manifest=manifest, registry=registry, publish=publish, sink=log)
    except FormalRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    finally:
        log.close()
    summary["run_log_head"] = log.head
    EvaluatorInbox(args.publish_to).receive_heads(summary["attempt_sha256"], run_log=log.head, registry=registry.head())
    (args.out / "summary.json").write_bytes(json.dumps(summary, sort_keys=True, indent=1).encode() + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
