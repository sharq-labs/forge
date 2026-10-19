"""Genesis-lite v0.3 DRAFT, P-4: the formal-tier driver over ``analysis.FORMAL_GRID``.

No formal driver existed (readiness row 11, deep audit D-09 / OBS-04). The pilot driver is not one: its master label
carries no tier, its root is revealed with its results, it runs arm by arm (so the records of world sets that later arms
have not yet seen sit in its output file), and it takes the root's path on the command line (the B-LEAK channel).

This driver:

* refuses unless the preregistration it is given is FROZEN, contains no ``OWNER_DECISION_REQUIRED``, names exactly the
  registered arms, commits the root by sha256 and commits the environment manifest (P-5), and the current manifest
  matches it. The committed v0.3 preregistration is DRAFT, so today it always refuses;
* refuses a RETIRED root: one whose commitment any earlier preregistration made (v0, v0.1, v0.2 pilot roots, all
  revealed with their pilots);
* derives one master per world set under a tier- and identity-tagged label, so a formal master never equals a pilot
  master even for the same root, and no world set reuses another's;
* runs WORLD-SET-MAJOR: every arm runs a world set before any of that world set's records leaves the driver, so a run
  log can never reveal a world set's kinds to an arm that has not run it yet (OBS-04);
* reads the root from STDIN, never from the command line;
* never relabels a record. A record produced under another identity becomes INVALID_BENCHMARK with the reason. The
  driver adds only ``tier``, ``root_commitment_sha256`` and ``world_set_index`` (D-09: the analysis can then require
  the formal commitment);
* accepts only the COMMITTED v0.3 preregistration bytes that the code rebuilds, never a dict that merely says FROZEN;
* ADMITS the attempt to the operator's attempt registry (:mod:`.registry`) BEFORE the first world is derived: one
  formal attempt per root, whatever the output directory, run label or preregistration identity, restart-safe;
* runs every arm through the v0.3 harness only (:func:`.harness.bind` + :func:`.harness.run_one`), never v0.2's;
* writes an append-only, hash-chained run log that refuses to open an existing file. Its head, with the registry
  head, is what the external evaluator receives (OD-8); a post-reveal recomputation of masters and key digests is the
  evaluator's job.

NOT done here: the OD-20 deployment itself. The driver cannot verify that the operator, escrow and secrets run under
another OS account or container. That is a preregistered start condition, checked by the deployment attack suite
(:mod:`.deployment_attacks`) and the independent isolation-probe rerun.
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
from .. import arms as arm_module
from . import environment
from .registry import AttemptRegistry, campaign_set_sha256

TIER = "formal"
LABEL = "forge.genesis_lite.v0_3/formal"
OWNER_DECISION_REQUIRED = "OWNER_DECISION_REQUIRED"
PREREG_DIR = pathlib.Path(__file__).resolve().parents[1] / "preregistration"

Runner = Callable[..., Mapping[str, Any]]


class FormalRefused(RuntimeError):
    """The formal tier cannot run (or its log cannot be trusted) as preregistered."""


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
        doc = json.loads(raw)
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


def master_for(root: bytes, presentation: str, campaign_id: str, seed: int) -> bytes:
    return hmac.new(root, f"{LABEL}/{presentation}/{seed}/{campaign_id}".encode(), hashlib.sha256).digest()


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


def preflight(doc: Mapping[str, Any], root: bytes, manifest: Mapping[str, Any]) -> list[str]:
    """Every reason the formal tier may not start under ``doc`` with ``root`` in the environment ``manifest``."""
    problems = []
    if doc.get("status") != "FROZEN":
        problems.append(f"the preregistration is {doc.get('status')!r}, not FROZEN (a DRAFT never drives a formal run)")
    if _mentions_owner_decision(doc):
        problems.append("the preregistration still contains OWNER_DECISION_REQUIRED")
    if set(doc.get("arms", {})) != set(arm_module.ARMS):
        problems.append("the preregistration does not name exactly the registered arms")
    formal = doc.get("formal", {}) if isinstance(doc.get("formal"), Mapping) else {}
    commitment = hashlib.sha256(root).hexdigest()
    if len(root) < 32:
        problems.append("the root is shorter than 32 bytes")
    if formal.get("root_commitment_sha256") != commitment:
        problems.append("the root does not match the preregistered root commitment")
    if commitment in retired_root_commitments(exclude_identity=identity(doc)):
        problems.append("the root is retired: an earlier preregistration committed it (and its pilot revealed it)")
    if formal.get("environment_manifest_sha256") != environment.manifest_digest(manifest):
        problems.append("the environment manifest differs from the preregistered one")
    return problems


def harness_runner(doc: Mapping[str, Any], manifest: Mapping[str, Any]) -> Runner:
    """The only production runner: the v0.3 harness bound to the committed identity in the formal tier."""
    from . import harness  # noqa: PLC0415 - harness imports preregistration, which imports this module
    from .preregistration import canonical  # noqa: PLC0415

    try:
        binding = harness.bind(canonical(dict(doc)), tier=TIER, manifest=manifest)
    except harness.HarnessRefused as exc:
        raise FormalRefused(f"the v0.3 harness refuses to bind: {exc}") from exc

    def runner(arm: str, *, master_seed: bytes, campaign_id: str, presentation: str, seed: int) -> Mapping[str, Any]:
        return harness.run_one(arm, binding=binding, master_seed=master_seed, campaign_id=campaign_id,
                               presentation=presentation, seed=seed).to_dict()

    return runner


def run_formal(root: bytes, doc: Mapping[str, Any], *, manifest: Mapping[str, Any], registry: AttemptRegistry,
               sink: Callable[[dict[str, Any]], None], runner: Runner | None = None,
               arms: Sequence[str] | None = None) -> dict[str, Any]:
    """Run every registered arm once on every world set of FORMAL_GRID, world set by world set. ``runner`` exists for
    orchestration tests only; production uses :func:`harness_runner`."""
    problems = preflight(doc, root, manifest) + committed_identity_problems(doc)
    if problems:
        raise FormalRefused("; ".join(problems))
    if not isinstance(registry, AttemptRegistry):
        raise FormalRefused("a formal attempt is admitted to the operator's attempt registry first")
    names = sorted(arm_module.ARMS) if arms is None else list(arms)
    if sorted(names) != sorted(arm_module.ARMS):
        raise FormalRefused("the formal tier runs every registered arm; a subset is not a formal run")
    if runner is None:
        runner = harness_runner(doc, manifest)
    expected, commitment = identity(doc), hashlib.sha256(root).hexdigest()
    from .registry import AttemptRefused  # noqa: PLC0415

    try:                                                     # consumed here, before the first world is derived
        attempt = registry.admit(root_commitment_sha256=commitment, prereg_sha256=expected,
                                 campaign_set_sha256=campaign_set_sha256(plan()), tier=TIER)
    except AttemptRefused as exc:
        raise FormalRefused(str(exc)) from exc
    invalid = 0
    for index, (presentation, campaign_id, seed) in enumerate(plan()):
        master = master_for(root, presentation, campaign_id, seed)
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
    return {"world_sets": len(v02_analysis.FORMAL_GRID), "arms": len(names), "invalid_runs": invalid,
            "prereg_sha256": expected, "root_commitment_sha256": commitment,
            "attempt_sha256": attempt["attempt_sha256"], "registry_head": registry.head()}


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
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = bytes.fromhex(sys.stdin.readline().strip())
    doc = json.loads(args.preregistration.read_bytes())
    manifest = environment.build_manifest()
    problems = preflight(doc, root, manifest) + committed_identity_problems(doc)
    if args.registry.resolve().is_relative_to(args.out.resolve()):
        problems.append("the attempt registry lies inside the run directory")
    if problems:                                             # refused before anything is created
        print("REFUSED: " + "; ".join(problems), file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=False)
    log = SealedLog(args.out / "runs.jsonl")
    try:
        summary = run_formal(root, doc, manifest=manifest, registry=AttemptRegistry(args.registry), sink=log)
    except FormalRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    finally:
        log.close()
    (args.out / "summary.json").write_bytes(json.dumps(summary, sort_keys=True, indent=1).encode() + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
