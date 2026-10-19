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

After the reveal, :func:`verify_attempt` is the evaluator's check. It recomputes every master from the revealed root and
the published admission, re-derives every answer key, and compares its digest with each record's; a record that came
from any other world does not survive.

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


def candidate_code_problems(cand: Mapping[str, Any] | None) -> list[str]:
    root = pathlib.Path(__file__).resolve().parents[3]
    problems = []
    for rel, sha in sorted((cand or {}).get("code_sha256", {}).items()):
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            problems.append(f"the candidate's file {rel} is not in this tree")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            problems.append(f"the candidate's file {rel} is not the preregistered code")
    return problems


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
    if commitment in retired_root_commitments(exclude_identity=identity(doc)):
        problems.append("the root is retired: an earlier preregistration committed it (and its pilot revealed it)")
    if formal.get("environment_manifest_sha256") != environment.manifest_digest(manifest):
        problems.append("the environment manifest differs from the preregistered one")
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
               runner: Runner | None = None) -> dict[str, Any]:
    """Run every registered arm and the named candidate once on every world set of FORMAL_GRID, world set by world set.
    ``runner`` exists for orchestration tests only; production uses :func:`harness_runner`. ``publish`` delivers the
    admission to the external evaluator; if it fails, the attempt is consumed and nothing runs."""
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
    publish(dict(attempt))
    invalid = 0
    for index, (presentation, campaign_id, seed) in enumerate(plan()):
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
    return {"world_sets": len(v02_analysis.FORMAL_GRID), "arms": len(names), "invalid_runs": invalid,
            "prereg_sha256": expected, "root_commitment_sha256": commitment,
            "attempt_sha256": attempt["attempt_sha256"], "registry_head": registry.head()}


def verify_attempt(records: Sequence[Mapping[str, Any]], root: bytes, admission: Mapping[str, Any]) -> list[str]:
    """The external evaluator's post-reveal check of one attempt: every record names the published admission, and its
    answer-key digest is the one re-derived from the revealed root, the identity and the admission's nonce."""
    from ..answer_key import export_answer_key, key_digest  # noqa: PLC0415
    from ..harness import MIX  # noqa: PLC0415

    problems = []
    if hashlib.sha256(root).hexdigest() != admission.get("root_commitment_sha256"):
        problems.append("the revealed root is not the admitted one")
    for rec in records:
        where = f"{rec.get('arm')}/{rec.get('presentation')}/{rec.get('campaign_id')}/{rec.get('seed')}"
        if rec.get("attempt_sha256") != admission.get("attempt_sha256"):
            problems.append(f"{where}: not from the published attempt")
            continue
        master = master_for(root, str(admission["prereg_sha256"]), str(admission["nonce"]), str(rec["presentation"]),
                            str(rec["campaign_id"]), int(rec["seed"]))
        ids = [u.get("universe_id") for u in rec.get("universes", [])]
        key = export_answer_key(master, str(rec["campaign_id"]), MIX, ids)
        if key.get("status") != "DERIVED" or key_digest(key) != rec.get("key_digest"):
            problems.append(f"{where}: the answer key does not re-derive from the revealed root and admission")
    return problems


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
    for name, path in (("attempt registry", args.registry), ("evaluator inbox", args.publish_to)):
        if path.resolve().is_relative_to(args.out.resolve()):
            problems.append(f"the {name} lies inside the run directory")
    if problems:                                             # refused before anything is created
        print("REFUSED: " + "; ".join(problems), file=sys.stderr)
        return 2

    def publish(entry: Mapping[str, Any]) -> None:
        with open(args.publish_to, "ab") as fh:
            fh.write(json.dumps({"admission": dict(entry)}, sort_keys=True).encode() + b"\n")

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
    with open(args.publish_to, "ab") as fh:
        fh.write(json.dumps({"heads": {"run_log": log.head, "registry": registry.head()}}, sort_keys=True).encode() + b"\n")
    (args.out / "summary.json").write_bytes(json.dumps(summary, sort_keys=True, indent=1).encode() + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
