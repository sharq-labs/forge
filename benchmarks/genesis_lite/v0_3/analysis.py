"""Genesis-lite v0.3 DRAFT evaluation contract: FDA-06 and O-1 on top of the frozen v0.2 rule.

Everything in ``benchmarks.genesis_lite.analysis`` (v0.2) holds unchanged except the two points below. Both make a lift
claim harder, never easier.

* FDA-06 (deep audit 2026-10-19, R-06 EXECUTED_REPRODUCED; ODC-06a/b as proposed). v0.2 capped only the DISCOVERABLE
  world of a world set whose truth lies outside every arm's searched family. An out-of-family ``spurious_correlate`` world
  kept its +1.0 ``law_pass`` (paired difference +1.0 from grammar reach alone), and ``confounded`` (``law_pass`` +1.0)
  was equally uncapped. Genesis §10.5 rule 4 (no lift from a class without a strong applicable baseline) governs over
  the v0.2 wording. v0.3 caps EVERY kind whose positive credit can come from a law or a law pair (a positive
  ``law_pass`` or ``indistinguishable_hit`` in the frozen table: discoverable, spurious_correlate, confounded and
  indistinguishable) per universe, and refuses a VALID record that lacks the flag for one of them. The RunRecord already
  carries the flag for every universe (``harness.py``), so no schema changes. ``indistinguishable`` is included because
  the v0.3 pair bound (FDA-05) removes the bracket route that a monomial baseline could use when the hidden truth is the
  generator's rival (``law * (1 + ...)``, outside the monomial family). A candidate whose grammar can express the rival
  keeps the pass route, so without the cap v0.3 would create a paired advantage from grammar reach alone (independent
  review 2026-10-19, finding 1).
* O-1 (ODC-O1a route B, as proposed). v0.2 fed Holm with the fraction of bootstrap means <= 0. That fraction is not a
  p-value: under a sign-symmetric null it rejects at alpha / 5 = 0.01 in 1/32 of six-world-set worlds (tested). v0.3
  takes p from the paired SIGN-FLIP randomisation test of the world-set differences (one-sided, statistic = their
  sum). It enumerates the exact null distribution when that is cheap (:data:`EXACT_WORK_LIMIT`). Otherwise it draws
  :data:`SIGN_FLIP_RESAMPLES` sign vectors from a SHAKE-256 stream and uses p = (b + 1) / (M + 1). That p is
  finite-sample valid for any M when the sign vectors are random. For a CLAIM the stream is keyed by the revealed formal
  root (D2, :func:`sign_flip_stream`): unknown to the proposer during the attempt and fixed once the root is committed.
  Whoever generates the root can still try roots before committing (open owner decision D2b). Without the root the
  public stream :data:`SIGN_FLIP_STREAM` is used and p is descriptive only. The exact path has no such caveat. The bootstrap is
  kept ONLY for the effect-size lower bound. Holm, ALPHA and the fixed family are unchanged.

  The null this tests is exchangeability of the two arms within a world set (a sign-symmetric difference). Capping makes
  the candidate's difference stochastically smaller, so it errs conservative. The test does NOT cover a composite null
  "mean difference <= 0" with an asymmetric difference distribution. Accepting that scope is part of ODC-O1a.

* Pilot P-2 (``docs/discovery/GENESIS_LITE_V0.md``): control cells are solved by arms that discover nothing
  (``single_setting`` earned 1.00 on confounded). v0.2 capped only cells where ``monomial_enumeration`` reaches full
  credit (REPRESENTATION_LIMITED). v0.3 also caps every CONTROL cell (a non-discoverable kind, per presentation) in which
  ANY registered non-adversarial arm reaches full credit with a lower bound >= 0.5 (CONTROL_SOLVED). Such a cell
  measures classification that a baseline already performs, so a candidate can lose there but never gain. The lower
  bound is the exact 2.5 % quantile of the binary bootstrap distribution (Binomial(n, p_hat) / n), which is
  deterministic and needs no resampling.
* The lift is a JOINT BENCHMARK lift (``claim_scope``), never a discovery-only lift. A discovery-only claim would need
  its own preregistered endpoint.

The v0.3 identity is DRAFT, so :func:`lift_decision` reports a coverage problem and claims nothing until the owner
freezes it (OD-19 for v0.3).
"""

from __future__ import annotations

import hashlib
import math
from fractions import Fraction
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from engcore.blindfold.roles import DEFAULT_CREDIT

from ..analysis import (  # noqa: F401 - re-exported: v0.3 changes nothing else
    ALPHA, CONTROL_KINDS, FORMAL_GRID, KINDS, NON_ADVERSARIAL_ROLES, NONINFERIORITY_MARGIN, PRESENTATION_MARGIN,
    PRIMARY_FAMILY, REPRESENTATION_ARM, SCREEN_CAP, AnalysisRefused, WorldSet, _record, _ws, best_per_kind,
    bootstrap_mean_ci, coverage_problems, representation_limited, screened_world_sets, strongest_baseline,
    world_credits,
)

#: outcomes through which a proposed law or law pair earns credit
LAW_OUTCOMES = ("law_pass", "indistinguishable_hit")
#: kinds whose positive credit can come from a law or a law pair: the cap covers each of them (FDA-06)
CAPPED_KINDS = tuple(k for k in KINDS if any(float(DEFAULT_CREDIT[k].get(o, 0.0)) > 0 for o in LAW_OUTCOMES))
#: every DEFAULT_CREDIT value is a multiple of 1/LATTICE, so every paired difference is too (checked at import)
LATTICE = 2
SIGN_FLIP_RESAMPLES = 19_999
SIGN_FLIP_STREAM = b"forge.genesis_lite.v0_3/sign_flip/1"      # the public stream: descriptive use only
#: D2 (owner, 2026-10-20): the stream of a CLAIM is keyed by the secret formal root, unknown until the reveal
SIGN_FLIP_KEY_LABEL = "forge.genesis_lite.v0_3/sign_flip_stream"
#: exact enumeration when (nonzero differences) x (support of the sum) is at most this
EXACT_WORK_LIMIT = 1_000_000
_CHUNK = 2048
SIGNIFICANCE = "paired sign-flip randomisation (one-sided); bootstrap for the lower bound only"
CLAIM_SCOPE = "JOINT_BENCHMARK_LIFT (all six kinds; never a discovery-only lift)"
CONTROL_SOLVED_LIMIT = 0.5

if not all(float(x * LATTICE).is_integer() for table in DEFAULT_CREDIT.values() for x in table.values()):
    raise RuntimeError("a DEFAULT_CREDIT value is off the 1/2 lattice: the sign-flip test cannot be exact")


def out_of_family(records: Iterable[Any]) -> dict[tuple[WorldSet, str], bool]:
    """(world set, kind) -> is that universe's true law outside the searched family, for every CAPPED kind.
    Refuses a VALID record without the flag for one of them, and two records that disagree about one universe."""
    out: dict[tuple[WorldSet, str], bool] = {}
    for raw in records:
        r = _record(raw)
        if r["status"] != "VALID":
            continue
        ws = _ws(r)
        for kind in CAPPED_KINDS:
            found = [u for u in r["universes"] if u["kind"] == kind]
            if len(found) != 1 or not isinstance(found[0].get("truth_in_searched_family"), bool):
                raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']} does not state truth_in_searched_family for "
                                      f"its {kind} universe")
            flag = not found[0]["truth_in_searched_family"]
            if out.setdefault((ws, kind), flag) != flag:
                raise AnalysisRefused(f"records disagree whether world set {ws}'s {kind} truth is in the searched family")
    return out


def capped(mine: Mapping[str, float], ref: Mapping[str, float], ws: WorldSet, limited: set[tuple[str, str]],
           off_family: Mapping[tuple[WorldSet, str], bool]) -> dict[str, float]:
    """The candidate's credits with every no-strong-baseline cell capped at the comparator's (lose, never gain): every
    CAPPED kind whose truth is out of family (unknown counts as out), and every REPRESENTATION_LIMITED cell."""
    return {k: min(c, ref[k]) if ((k in CAPPED_KINDS and off_family.get((ws, k), True)) or (k, ws[0]) in limited)
            else c for k, c in mine.items()}


def _lattice(diffs: Sequence[float]) -> list[int]:
    out = []
    for d in diffs:
        x = float(d) * LATTICE
        if not math.isfinite(x) or abs(x - round(x)) > 1e-9:
            raise AnalysisRefused(f"paired difference {d!r} is not a difference of DEFAULT_CREDIT values")
        out.append(int(round(x)))
    return out


def sign_flip_stream(revealed_root: bytes, prereg_sha256: str) -> bytes:
    """D2: the Monte-Carlo stream seed of a claim, derived from the revealed formal root (HMAC-SHA256 under its own
    label and the identity's digest). It is unknown to the proposer while the attempt runs and fixed once the root is
    committed, so no stream can be chosen AFTER the commitment. It does NOT stop whoever generates the root from trying
    many roots BEFORE committing (scientific review 2026-10-20, I-1; open owner decision D2b)."""
    import hmac  # noqa: PLC0415

    return hmac.new(revealed_root, f"{SIGN_FLIP_KEY_LABEL}/{prereg_sha256}".encode(), hashlib.sha256).digest()


def sign_flip_p(diffs: Sequence[float], *, exact_work_limit: int = EXACT_WORK_LIMIT,
                resamples: int = SIGN_FLIP_RESAMPLES, stream: bytes = SIGN_FLIP_STREAM) -> dict[str, Any]:
    """One-sided paired sign-flip p for H1 'the candidate is better': P(T* >= T_obs) with T = sum of the differences and
    T* the sum under independent fair sign flips. Exact (integer enumeration of the null distribution) when cheap,
    otherwise Monte-Carlo with p = (b + 1) / (M + 1) over SHAKE-256(``stream`` || index)."""
    ints = _lattice(diffs)
    t_obs = sum(ints)
    a = [abs(x) for x in ints if x]
    if not a:
        return {"p": 1.0, "method": "exact", "resamples": 0, "nonzero": 0}
    s = sum(a)
    if len(a) * (2 * s + 1) <= exact_work_limit:
        counts = [0] * (2 * s + 1)
        counts[s] = 1
        for x in a:                                          # counts[i] = sign patterns whose sum is i - s
            counts = [u + d for u, d in zip([0] * x + counts[:-x], counts[x:] + [0] * x)]
        p = Fraction(sum(counts[s + t_obs:]), 2 ** len(a))
        return {"p": float(p), "method": "exact", "resamples": 0, "nonzero": len(a)}
    vec = np.asarray(a, dtype=np.int64)
    nbytes, b = (len(a) + 7) // 8, 0
    for start in range(0, resamples, _CHUNK):
        stop = min(resamples, start + _CHUNK)
        raw = b"".join(hashlib.shake_256(stream + r.to_bytes(8, "big")).digest(nbytes)
                       for r in range(start, stop))
        bits = np.unpackbits(np.frombuffer(raw, dtype=np.uint8).reshape(stop - start, nbytes), axis=1)[:, :len(a)]
        b += int(((2 * (bits.astype(np.int64) @ vec) - s) >= t_obs).sum())
    return {"p": (b + 1) / (resamples + 1), "method": "monte_carlo", "resamples": resamples, "nonzero": len(a)}


def binary_lower_bound(hits: Sequence[float]) -> float:
    """The exact 2.5 % quantile of the bootstrap distribution of a binary mean: the smallest k / n with
    P(Binomial(n, p_hat) <= k) >= 0.025."""
    n = len(hits)
    if n == 0:
        return float("nan")
    s = int(round(sum(hits)))
    total, acc = n ** n, 0                     # P(X = k) = C(n, k) s^k (n - s)^(n - k) / n^n, in exact integers
    for k in range(n + 1):
        acc += math.comb(n, k) * s ** k * (n - s) ** (n - k)
        if 40 * acc >= total:
            return k / n
    return 1.0


def control_solved(on_grid: Mapping[str, Mapping[WorldSet, Mapping[str, float]]],
                   arms: Iterable[str]) -> set[tuple[str, str]]:
    """(control kind, presentation) cells in which some registered non-adversarial arm earns full credit with an exact
    binary-bootstrap lower bound >= CONTROL_SOLVED_LIMIT (pilot P-2)."""
    cells = set()
    for arm in arms:
        sets = on_grid.get(arm, {})
        for kind in CONTROL_KINDS:
            for presentation in PRIMARY_FAMILY[1:]:
                hits = [1.0 if k[kind] >= 1.0 else 0.0 for w, k in sets.items() if w[0] == presentation]
                if hits and binary_lower_bound(hits) >= CONTROL_SOLVED_LIMIT:
                    cells.add((kind, presentation))
    return cells


def holm(raw_p: Mapping[str, float], alpha: float = ALPHA) -> dict[str, bool]:
    """Holm step-down over the given family (the v0.2 procedure, unchanged)."""
    order = sorted(raw_p, key=lambda k: raw_p[k])
    out, still = {}, True
    for i, part in enumerate(order):
        still = still and raw_p[part] <= alpha / (len(order) - i)
        out[part] = still
    return out


def _code_problems() -> tuple[list[str], str]:
    from .preregistration import identity_problems  # noqa: PLC0415 - preregistration imports this module

    return identity_problems()


def registered_roles() -> dict[str, str]:
    """The v0.3 arm registry (every v0.2 arm plus the FDA-21 variants), never caller input."""
    from .arms import ARMS  # noqa: PLC0415

    return {name: entry[3] for name, entry in ARMS.items()}


def formal_binding_problems(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """D-09 and review 2026-10-20 finding 2. Every record must come from ONE admitted formal attempt of the v0.3
    harness under the preregistered root, w and environment. These are labels the operator's driver writes; their
    authority comes from the external evaluator, who receives the registry and run-log heads out of band, then after
    the reveal recomputes every master and key digest (:func:`.formal.verify_attempt`). A label alone is not evidence."""
    from .harness import HARNESS_ID  # noqa: PLC0415
    from .preregistration import PREREG_PATH  # noqa: PLC0415

    doc = __import__("json").loads(PREREG_PATH.read_bytes())
    root = doc["formal"]["root_commitment_sha256"]
    want = {"tier": "formal", "tier_bound": "formal", "harness": HARNESS_ID, "root_commitment_sha256": root,
            "pair_bound": doc["evaluator"]["pair_bound"],
            "environment_manifest_sha256": doc["formal"]["environment_manifest_sha256"]}
    problems = []
    if len(str(root)) != 64:
        problems.append("no formal root commitment is preregistered")
    for key, value in sorted(want.items(), key=lambda kv: kv[0]):
        bad = sum(r.get(key) != value for r in rows)
        if bad:
            problems.append(f"{bad} record(s) do not carry {key} = the preregistered/formal value")
    attempts = {r.get("attempt_sha256") for r in rows}
    if len(attempts) != 1 or None in attempts:
        problems.append(f"records come from {len(attempts)} attempt(s); a lift decision reads exactly one admitted attempt")
    return problems


def _formal_root_commitment() -> str:
    from .preregistration import PREREG_PATH  # noqa: PLC0415

    return str(__import__("json").loads(PREREG_PATH.read_bytes())["formal"]["root_commitment_sha256"])


def lift_decision(records: Iterable[Any], candidate: str, *, grid: Iterable[WorldSet] | None = None,
                  verification: Sequence[str] | None = None, revealed_root: bytes | None = None) -> dict[str, Any]:
    """The v0.2 lift rule with the FDA-06 cap and the O-1 significance. Claims nothing unless every condition holds,
    including a clean post-reveal verification of the attempt (``formal.verify_attempt`` returned no problem) and the
    revealed formal root, whose sha256 must be the preregistered commitment: the sign-flip stream is derived from it
    (D2). Without it the p values use the public stream and are descriptive only."""
    rows = [_record(r) for r in records]
    grid = FORMAL_GRID if grid is None else frozenset(grid)
    roles = registered_roles()
    if candidate in roles:
        raise AnalysisRefused(f"candidate {candidate!r} takes a registered arm's name; it would leave the comparison")
    strangers = sorted({r["arm"] for r in rows} - set(roles) - {candidate})
    if strangers:
        raise AnalysisRefused(f"records of unregistered arms: {strangers}; roles come from the frozen registry only")
    required = sorted(a for a, role in roles.items() if role in NON_ADVERSARIAL_ROLES)
    problems = [] if grid == FORMAL_GRID else ["the grid is not the preregistered formal grid: exploratory, no claim"]
    code_problems, identity = _code_problems()
    problems += code_problems + formal_binding_problems(rows)
    stream = SIGN_FLIP_STREAM
    if revealed_root is not None and not isinstance(revealed_root, bytes):
        raise AnalysisRefused(f"the revealed formal root must be bytes, got {type(revealed_root).__name__}")
    if revealed_root is None or hashlib.sha256(revealed_root).hexdigest() != _formal_root_commitment():
        problems.append("the revealed formal root is missing or is not the preregistered commitment: the sign-flip "
                        "stream is not the claim's (D2), p values are descriptive only")
    else:
        stream = sign_flip_stream(revealed_root, identity)
    if verification is None:
        problems.append("the attempt was not verified after the reveal (formal.verify_attempt)")
    elif verification:
        problems.append(f"the attempt's post-reveal verification found {len(verification)} problem(s)")
    screened = screened_world_sets(rows, [*required, candidate]) & grid
    if len(screened) > SCREEN_CAP * len(grid):
        problems.append(f"{len(screened)} of {len(grid)} world sets were screened (cap {SCREEN_CAP:.0%}): a benchmark "
                        f"defect, not a result")
    rows = [r for r in rows if _ws(r) not in screened]
    grid = grid - screened
    credits = world_credits(rows)
    off_family = out_of_family(rows)
    on_grid = {a: {w: k for w, k in sets.items() if w in grid} for a, sets in credits.items()}
    baseline, _scores = strongest_baseline({a: on_grid[a] for a in required if on_grid.get(a)}, roles)
    per_kind = best_per_kind({a: on_grid[a] for a in required if on_grid.get(a)}, roles)
    representation = set().union(*(representation_limited(on_grid.get(arm, {}))
                                   for arm in (REPRESENTATION_ARM, REPRESENTATION_ARM + "_dof")))
    solved = control_solved(on_grid, required)
    limited = representation | solved
    problems += coverage_problems(rows, candidate, grid, identity=identity)
    for arm in required:
        problems += coverage_problems(rows, arm, grid, comparator=candidate, identity=identity)
    mine = on_grid.get(candidate, {})
    theirs = on_grid.get(baseline, {}) if baseline else {}
    shared = sorted(set(mine) & set(theirs))
    tests, raw_p = {}, {}
    for part in PRIMARY_FAMILY:
        diffs = [sum(capped(mine[w], theirs[w], w, limited, off_family).values()) - sum(theirs[w].values())
                 for w in shared if part == "pooled" or w[0] == part]
        mean, low, _bootstrap_fraction = bootstrap_mean_ci(diffs)
        sf = sign_flip_p(diffs, stream=stream)
        tests[part] = {"world_sets": len(diffs), "mean_difference": mean, "lower95": low, "p": sf["p"],
                       "p_method": sf["method"]}
        raw_p[part] = sf["p"]
    holm_ok = holm(raw_p)
    presentations_ok = {part: tests[part]["world_sets"] > 0 and tests[part]["lower95"] > -PRESENTATION_MARGIN
                        for part in PRIMARY_FAMILY if part != "pooled"}
    noninf = {}
    for kind in KINDS:
        ref = on_grid.get(per_kind[kind], {}) if per_kind[kind] else {}
        diffs = [capped(mine[w], ref[w], w, limited, off_family)[kind] - ref[w][kind] for w in sorted(set(mine) & set(ref))]
        mean, low, _ = bootstrap_mean_ci(diffs)
        noninf[kind] = {"reference_arm": per_kind[kind], "mean_difference": mean, "lower95": low,
                        "ok": bool(diffs) and low > -NONINFERIORITY_MARGIN}
    claim = (not problems and baseline is not None and holm_ok["pooled"] and tests["pooled"]["lower95"] > 0
             and all(presentations_ok.values()) and all(v["ok"] for v in noninf.values()))
    return {"candidate": candidate, "strongest_baseline": baseline, "shared_world_sets": len(shared),
            "screened_world_sets": len(screened), "coverage_problems": problems,
            "representation_limited_cells": sorted(representation), "control_solved_cells": sorted(solved),
            "claim_scope": CLAIM_SCOPE,
            "out_of_family_universes": {k: sum(off_family.get((w, k), False) for w in shared) for k in CAPPED_KINDS},
            "primary": tests, "significance": SIGNIFICANCE, "holm_significant": holm_ok,
            "presentation_noninferiority": presentations_ok, "kind_noninferiority": noninf,
            "control_noninferiority": {k: noninf[k] for k in CONTROL_KINDS}, "lift_claimed": claim}
