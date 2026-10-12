"""Roadmap V2 R8: discovery performance, measured per tier, reported as compact batch records.

    python -m tools.discovery_performance [--candidates N] [--json PATH]

Tiers (measured separately, wall clock, this machine, single process):

* Tier 0 -- proposal admission: law-grammar validation + canonical structure digest + de-duplication.
* Tier 1 -- multi-fidelity screening: ``design.fidelity_graph.screen`` under an admitted link, with every non-promotion
  recorded in the EliminationLedger (re-screened on record).  TRUST OVERHEAD = that time minus the raw low-fidelity
  evaluation time (the raw model here is analytic, so the ratio is an upper bound on the relative overhead).
* Tier 2 -- sealed falsification: register + seal + authority release + judge, per verdict.
* Tier 3 -- Blindfold campaign end to end (escrow, observe, admission, sealed score, adjudication) per universe.

Useful promotions per compute-hour use a DECLARED cost model for the high-fidelity evaluations (seconds per run, stated in
the output); the FORGE machinery time is measured.  The false-elimination rate is reported twice: the ledger's own
recorded audit (what FORGE knows) and the ground truth of this synthetic population (what it could not know).  Every
batch record carries counts, seconds and a digest of the candidate ids -- not one record per candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BatchRecord:
    tier: str
    items: int
    accepted: int
    rejected: int
    seconds: float
    ids_digest: str

    @property
    def per_second(self) -> float:
        return self.items / self.seconds if self.seconds > 0 else float("inf")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "per_second": round(self.per_second, 1)}


def _ids_digest(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def tier0(n: int, seed: int) -> BatchRecord:
    from engcore.blindfold.expression import c, mul, pw, structure_digest, v, validate
    rng = random.Random(seed)
    exprs = [mul(c(rng.uniform(0.1, 10)), pw(v(rng.choice("abc")), round(rng.uniform(-2, 2), 2)),
                 pw(v(rng.choice("abc")), round(rng.uniform(-2, 2), 2))) for _ in range(n)]
    t0 = time.perf_counter()
    seen, kept = set(), 0
    for e in exprs:
        validate(e)
        d = structure_digest(e)
        if d not in seen:
            seen.add(d)
            kept += 1
    dt = time.perf_counter() - t0
    return BatchRecord("tier0_admission", n, kept, n - kept, dt, _ids_digest([str(i) for i in range(n)]))


def tier1(n: int, seed: int, high_cost_s: float) -> tuple[list[BatchRecord], dict[str, Any]]:
    from engcore.design.fidelity_graph import (
        EliminationLedger, FalseEliminationPolicy, FidelityLink, FidelityNode, LinkAdmissionPolicy, PairedEvaluation, ScreeningOutcome,
        Sense, ValidityDomain, draw_audit, measure_link, record_audit, screen,
    )
    from engcore.design.multifidelity import standard_ladder
    ladder = standard_ladder()
    low = FidelityNode(ladder.rung("analytic"), "model:beam", "euler_bernoulli", "1")
    high = FidelityNode(ladder.rung("numerical"), "model:beam", "fem_p2", "1")
    rng = random.Random(seed)

    def truth(x: float) -> float:                             # the "high fidelity": low + bias + scatter
        return 2.0 * x + 0.5 + rng.gauss(0.0, 0.3)
    pairs = [PairedEvaluation(f"cal{i}", {"x": 10.0 * i / 59}, 2.0 * (10.0 * i / 59), truth(10.0 * i / 59)) for i in range(60)]
    link = FidelityLink("beam.deflection", low, high, "deflection", "mm", ValidityDomain({"x": (0.0, 10.0)}, {"x": "m"}),
                        measure_link(pairs, threshold=10.0, sense=Sense.AT_MOST, near_band=1.0))
    link = link.admit(LinkAdmissionPolicy("perf.admission", 20, 0.9, 0.8), actor="perf", reason="benchmark")
    xs = [rng.uniform(0.0, 10.0) for _ in range(n)]
    highs = {f"k{i}": truth(x) for i, x in enumerate(xs)}

    t0 = time.perf_counter()
    raw = [2.0 * x for x in xs]
    raw_s = time.perf_counter() - t0

    ledger = EliminationLedger()
    t0 = time.perf_counter()
    decisions = []
    for i, (x, lv) in enumerate(zip(xs, raw)):
        d = screen(f"k{i}", low_value=lv, point={"x": x}, link=link, low_node=low, observable="deflection")
        decisions.append(d)
        if d.outcome is not ScreeningOutcome.PROMOTE:
            ledger.record(d, link=link, low_node=low)
    screen_s = time.perf_counter() - t0
    promoted = [d.candidate_key for d in decisions if d.outcome is ScreeningOutcome.PROMOTE]
    eliminated = [d.candidate_key for d in decisions if d.outcome is ScreeningOutcome.ELIMINATE]
    useful = [k for k in promoted if highs[k] <= 10.0]
    truly_false = [k for k in eliminated if highs[k] <= 10.0]       # ground truth (unknowable to FORGE without high fidelity)
    policy = FalseEliminationPolicy("perf.audit", fraction=0.1, strata=3, bound=0.2, min_audits=3)
    t0 = time.perf_counter()
    drawn = draw_audit(ledger, link, policy)
    _link2, audit = record_audit(ledger, link, {k: highs[k] for k in drawn}, policy, actor="perf")
    audit_s = time.perf_counter() - t0
    hours = (screen_s + audit_s + (len(promoted) + len(drawn)) * high_cost_s) / 3600.0
    batches = [BatchRecord("tier1_raw_low_fidelity", n, n, 0, raw_s, _ids_digest(list(highs))),
               BatchRecord("tier1_screen_and_record", n, len(promoted), len(decisions) - len(promoted), screen_s, _ids_digest(list(highs))),
               BatchRecord("tier1_audit", len(drawn), len(drawn) - audit.false_eliminations, audit.false_eliminations, audit_s,
                           _ids_digest(list(drawn)))]
    summary = {
        "trust_overhead_us_per_candidate": round((screen_s - raw_s) / n * 1e6, 2),
        "trust_overhead_ratio_vs_analytic_low_model": round(screen_s / raw_s, 1) if raw_s > 0 else None,
        "promoted": len(promoted), "useful_promotions": len(useful), "eliminated": len(eliminated),
        "declared_high_fidelity_cost_s": high_cost_s,
        "useful_promotions_per_compute_hour": round(len(useful) / hours, 1) if hours > 0 else None,
        "false_elimination_rate_recorded_audit": audit.false_elimination_rate,
        "false_elimination_rate_ground_truth": round(len(truly_false) / len(eliminated), 4) if eliminated else None,
        "audited": audit.audited, "link_suspended_by_audit": audit.suspended,
    }
    return batches, summary


def tier2(n: int) -> BatchRecord:
    from engcore.claims.falsification import CriterionKind, EvidenceSource, ExposureAuthority, Falsifier, judge
    from engcore.sria.decision import Hypothesis, HypothesisKind, HypothesisPrediction
    auth = ExposureAuthority("perf")
    reg = auth.registry("perf")
    t0 = time.perf_counter()
    refuted = 0
    for i in range(n):
        h = Hypothesis(hypothesis_id=f"h{i}", model_ref="m", kind=HypothesisKind.EQUATION, statement=f"y = {i}",
                       predictions=(HypothesisPrediction("y", "m", f"cond:{i}"),), falsifier_refs=(f"f{i}@v1",))
        t = reg.register(h)
        f = Falsifier(f"f{i}", h.hypothesis_id, h.content_digest, "y", "m", {"i": i}, EvidenceSource.MEASUREMENT_RECORD,
                      CriterionKind.PREDICTION_DEVIATION, {"k": 3.0, "predicted": 5.0, "prediction_uncertainty": 0.01, "resolution": 0.2})
        reg.seal(f, t)
        e = auth.release(evidence_id=f"e{i}", source=EvidenceSource.MEASUREMENT_RECORD, observable="y", unit="m",
                         value=5.0 + (0.5 if i % 4 == 0 else 0.0), uncertainty=0.01, conditions={"i": i})
        refuted += judge(f.digest, reg, e).verdict.value == "refuted"
    dt = time.perf_counter() - t0
    return BatchRecord("tier2_seal_release_judge", n, n - refuted, refuted, dt, _ids_digest([f"h{i}" for i in range(n)]))


def tier3(universes: int, seed: int) -> tuple[BatchRecord, int]:
    from engcore.blindfold import EvaluatorConfig, InProcessTransport, run_campaign
    from engcore.blindfold.baselines import careful
    from engcore.blindfold.escrow import EscrowService
    mix = {"discoverable": universes // 2, "no_solution": universes - universes // 2}
    t0 = time.perf_counter()
    rep, _ = run_campaign(InProcessTransport(EscrowService(bytes([seed % 256]) * 32)), campaign_id="perf", mix=mix, proposer=careful,
                          proposer_identity={"kind": "algorithm", "id": "careful"}, config=EvaluatorConfig("perf", "1"))
    dt = time.perf_counter() - t0
    s = rep.summary()
    return BatchRecord("tier3_blindfold_campaign", universes, sum(a.credit > 0 for a in rep.adjudications),
                       sum(a.credit <= 0 for a in rep.adjudications), dt, rep.outcome_digest), s["queries"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidates", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--high-cost-s", type=float, default=60.0, help="declared cost of one high-fidelity evaluation")
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)
    t0b = tier0(args.candidates, args.seed)
    t1b, t1s = tier1(args.candidates, args.seed, args.high_cost_s)
    t2b = tier2(min(args.candidates, 2000))
    t3b, queries = tier3(16, args.seed)
    out = {"batches": [b.to_dict() for b in (t0b, *t1b, t2b, t3b)], "tier1": t1s, "tier3_observe_queries": queries,
           "tier3_observe_queries_per_second": round(queries / t3b.seconds, 1) if t3b.seconds > 0 else None,
           "note": "wall clock, one process, this machine; high-fidelity cost is DECLARED, not measured"}
    text = json.dumps(out, indent=2)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
