"""Emit the blind challenge and seal it. Runs NO Forge.

    python benchmarks/blind/freeze.py

Writes ``benchmarks/blind/v1/`` — the cases, the truth, the manifest, the
oracle-disagreement log and ``FREEZE.json``, which carries the digest of each
of them. After this runs and its output is committed, the challenge exists as
bytes with a name, and any later change to those bytes is visible as a digest
that no longer matches.

**The order is the whole point.** Cases first, truth second, digests third,
commit fourth, Forge fifth. Nothing here imports ``engcore`` and nothing here
can: ``tests/test_blind_challenge_guards.py`` audits this module's import
graph and fails if it grows an edge into the runtime.

Phase 1N, the quality guards, run before anything is written. A corpus with a
duplicate payload, a case whose truth is incomplete, an unregistered oracle id
or an undeclared unit is not sealed and the script exits non-zero — because a
seal over a corpus nobody checked is a seal over whatever was there.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from benchmarks.blind import bound_registry as reg           # noqa: E402
from benchmarks.blind.build_truth import (                   # noqa: E402
    TRUTH_BUILDER_VERSION, build_truth,
)
from benchmarks.blind.families import (                      # noqa: E402
    MEASURED_STATE_AGREEMENT, PLANNED_COUNTS, PLAN_VERSION, RESOLUTION_FLOOR,
    planned_total,
)
from benchmarks.blind.generate import (                      # noqa: E402
    GENERATOR_VERSION, MASTER_SEED, generate_corpus, units_used,
)
from benchmarks.blind.oracles import battery as battery_oracle    # noqa: E402
from benchmarks.blind.oracles import conduction as conduction_oracle  # noqa: E402
from benchmarks.blind.oracles import electrothermal as et_oracle  # noqa: E402
from benchmarks.blind.oracles import kinetics as kinetics_oracle  # noqa: E402
from benchmarks.blind.oracles import spice as spice_oracle    # noqa: E402
from benchmarks.blind.oracles.units import (                  # noqa: E402
    ORACLE_UNIT_TABLE_VERSION, assert_vocabulary_closed,
)

OUT = HERE / "v1"

#: Every oracle this challenge may name. A truth record naming an id that is
#: not here fails the quality guard, for the same reason `tests/oracles`
#: registers its own: an oracle nobody can look up is a citation nobody can
#: check.
ORACLE_REGISTER = {
    et_oracle.ORACLE_ID: {
        "class": "INDEPENDENT_ANALYTIC",
        "statement": "The coupled electro-thermal fixed point and every "
                     "quantity the validity conditions are stated over, "
                     "written from the literature definitions and evaluated "
                     "on plain floats in SI.",
        "independent_of_forge": True,
        "executable": True,
        "limitations": "Shares the CONTRACT with the runtime -- what each "
                       "condition means and which state coordinate it is read "
                       "at. The arithmetic is independent; the reading of the "
                       "specification is common to both, by design.",
    },
    et_oracle.SECOND_ORACLE_ID: {
        "class": "INDEPENDENT_ANALYTIC",
        "statement": "Classical RK4 march of the same lumped balance the "
                     "closed form integrates, with the heat held at I^2 R for "
                     "the interval exactly as the declared model states it.",
        "independent_of_forge": True,
        "executable": True,
        "limitations": "A different ALGORITHM against the same equation. It "
                       "verifies the integration, not the choice of equation. "
                       "The nonlinear variant is reported beside it as a "
                       "model-fidelity note and arbitrates nothing.",
    },
    spice_oracle.SPICE_ORACLE_ID: {
        "class": "INDEPENDENT_EXECUTABLE",
        "statement": "ngspice solves the series loop from a netlist written "
                     "here, and the loop current is read back and compared.",
        "independent_of_forge": True,
        "executable": True,
        "limitations": "A netlist carries no temperature, so this bounds the "
                       "ELECTRICAL solve alone -- the resistances handed to it "
                       "are already the oracle's answer to the thermal "
                       "question. Absent ngspice the coverage is lost, not "
                       "satisfied.",
    },
    battery_oracle.ORACLE_ID: {
        "class": "INDEPENDENT_ANALYTIC",
        "statement": "Coulomb counting, the Rint terminal relation, Peukert "
                     "derating and the self-heating march, written from Plett "
                     "(2015) and Peukert (1897), evaluated at both ends of "
                     "every marched step.",
        "independent_of_forge": True,
        "executable": True,
        "limitations": "The Rint model has no diffusion or polarisation "
                       "dynamics; this checks its algebra and the contract, "
                       "not its fidelity to a real cell.",
    },
    battery_oracle.SECOND_ORACLE_ID: {
        "class": "INDEPENDENT_ANALYTIC",
        "statement": "The state of charge re-derived once from the total "
                     "charge that crossed rather than accumulated step by "
                     "step, and the cell temperature re-derived by RK4 rather "
                     "than by the closed form.",
        "independent_of_forge": True,
        "executable": True,
        "limitations": "Shares the definitions; bounds an accumulation or "
                       "integration error, not a wrong model.",
    },
    kinetics_oracle.ORACLE_ID: {
        "class": "INDEPENDENT_ANALYTIC",
        "statement": "The CSTR's six declared conditions and the adiabatic "
                     "ceiling in closed form, plus the record's own "
                     "construction guards, which refuse a declaration before "
                     "any condition is assessed.",
        "independent_of_forge": True,
        "executable": True,
        "limitations": "The ceiling is an upper bound derived from the "
                       "Z = T + beta C invariant, not a prediction of where "
                       "the trajectory goes.",
    },
    kinetics_oracle.SECOND_ORACLE_ID: {
        "class": "INDEPENDENT_ANALYTIC",
        "statement": "Fixed-step RK4 of the two balances, reporting the "
                     "hottest state the trajectory reaches. It exists to "
                     "FALSIFY the analytic ceiling.",
        "independent_of_forge": True,
        "executable": True,
        "limitations": "An explicit fixed-step march on a stiff exothermic "
                       "reactor overshoots and leaves the region the bound is "
                       "proved over; such a trajectory is reported as diverged "
                       "and convicts nothing.",
    },
    conduction_oracle.ORACLE_ID: {
        "class": "INDEPENDENT_ANALYTIC",
        "statement": "von Neumann stability of FTCS in closed form: the "
                     "amplification of the highest representable mode is "
                     "1 - 4r, so |g| > 1 once r > 1/2.",
        "independent_of_forge": True,
        "executable": True,
        "limitations": "A statement about a diffusion problem. A negative "
                       "declared diffusivity is not one, and `alpha > 0` is "
                       "the condition that catches it.",
    },
    conduction_oracle.SECOND_ORACLE_ID: {
        "class": "INDEPENDENT_ANALYTIC",
        "statement": "The exact highest discrete eigenmode is seeded, FTCS is "
                     "actually marched, and the growth per step is measured. "
                     "The criterion's own prediction put to an experiment.",
        "independent_of_forge": True,
        "executable": True,
        "limitations": "The finite grid is slightly MORE forgiving than r = "
                       "1/2, so the declared bound is conservative rather than "
                       "wrong; only growth at r <= 1/2 would falsify it.",
    },
}

#: Every disagreement between two independently implemented oracles that was
#: found and resolved BEFORE the freeze. Phase 1M: the log is frozen with the
#: challenge, because a disagreement nobody wrote down is a disagreement that
#: gets resolved twice, differently.
#:
#: These are recorded as they were found, with the resolution and its
#: justification. **None of them was resolved by asking Forge.** Every one was
#: settled by deciding which of the two oracles was being asked a question it
#: was not stated over.
PRE_FREEZE_DISAGREEMENTS = [
    {
        "id": "DIS-001",
        "found_at": "oracle development, before case generation",
        "candidates": "the conduction `cond.alpha` family (3 candidates at "
                      "the time of discovery)",
        "oracle_a": conduction_oracle.ORACLE_ID,
        "oracle_b": conduction_oracle.SECOND_ORACLE_ID,
        "difference": "The FTCS march measured growth at a Fourier number of "
                      "-1.6e-4, -7.7e-4 and -1942, and reported the r <= 1/2 "
                      "stability bound as falsified.",
        "tolerance_basis": "not a tolerance question: the two agreed on the "
                           "amplification factor to 2.2e-16; they disagreed "
                           "about what it MEANT.",
        "resolution": "Oracle B was wrong, and about its own scope. "
                      "r = alpha dt / dx^2 is negative when the declared "
                      "diffusivity is, and |1 - 4r| > 1 for every r < 0, so a "
                      "backwards-diffusing slab grows trivially. The von "
                      "Neumann criterion is a statement about a diffusion "
                      "problem and a negative diffusivity is not one. "
                      "`falsifies_bound` now requires 0 <= r <= 1/2.",
        "excluded": False,
        "exclusion_reason": "",
        "resolved_by_consulting_forge": False,
    },
    {
        "id": "DIS-002",
        "found_at": "oracle development, before case generation",
        "candidates": "one kinetics `kin.ceiling` candidate",
        "oracle_a": kinetics_oracle.ORACLE_ID,
        "oracle_b": kinetics_oracle.SECOND_ORACLE_ID,
        "difference": "The RK4 march reported a peak of 9847 K against an "
                      "analytic ceiling of 999 K, i.e. the ceiling falsified.",
        "tolerance_basis": "the trajectory's own physicality, not a number: "
                           "the same march ended at -3.9e22 K and a "
                           "concentration of +1.3e23 mol/m3.",
        "resolution": "Oracle B was wrong. A fixed-step explicit integrator on "
                      "a stiff exothermic reactor overshoots, and the "
                      "overshoot left the region the bound is PROVED over -- "
                      "the proof needs C >= 0. A numerical artefact is not a "
                      "counterexample to a theorem. The march now reports "
                      "`diverged` when it drives the concentration negative or "
                      "the temperature through absolute zero, and convicts "
                      "nothing. A trajectory that stays physical and still "
                      "passes the ceiling would still falsify it.",
        "excluded": False,
        "exclusion_reason": "",
        "resolved_by_consulting_forge": False,
    },
    {
        "id": "DIS-003",
        "found_at": "oracle development, before case generation",
        "candidates": "33 electro-thermal candidates across 11 families",
        "oracle_a": et_oracle.ORACLE_ID,
        "oracle_b": et_oracle.SECOND_ORACLE_ID,
        "difference": "Stage temperatures disagreed by up to 1.1e-2 relative "
                      "— larger than the 1e-3 placement distance, which would "
                      "have made 33 decidable cases UNRESOLVED.",
        "tolerance_basis": "the deciding condition's own distance from its "
                           "bound: a disagreement matters exactly when it "
                           "could move the condition across it.",
        "resolution": "NEITHER oracle was wrong; they were answering "
                      "different questions. Oracle B re-evaluated R(T) at "
                      "every RK4 stage and so marched the NONLINEAR balance, "
                      "while the declared lumped model — and the closed form "
                      "that solves it — holds the heat at I^2 R across the "
                      "interval. The gap was the linearisation error of the "
                      "declared model, a real fact about the approximation "
                      "and not an implementation defect. Oracle B now marches "
                      "the same balance with the resistance frozen, which is a "
                      "pure integration check and agrees to round-off; the "
                      "nonlinear gap is reported beside it as a model-fidelity "
                      "note and arbitrates nothing.",
        "excluded": False,
        "exclusion_reason": "",
        "resolved_by_consulting_forge": False,
    },
    {
        "id": "DIS-004",
        "found_at": "oracle development, before case generation",
        "candidates": "the electro-thermal ARITHMETIC_SENSITIVE stratum",
        "oracle_a": et_oracle.ORACLE_ID,
        "oracle_b": et_oracle.SECOND_ORACLE_ID,
        "difference": "For cases placed exactly ON a bound the deciding "
                      "distance is ~1e-13, so ANY disagreement is formally "
                      "material and every such case became UNRESOLVED.",
        "tolerance_basis": f"RESOLUTION_FLOOR = {RESOLUTION_FLOOR}, five "
                           "orders above the measured runtime/oracle "
                           "disagreement.",
        "resolution": "A gap must now exceed max(deciding distance, "
                      "RESOLUTION_FLOOR) to be material. Below the floor the "
                      "case is already ARITHMETIC_SENSITIVE and out of the "
                      "primary denominator; calling it UNRESOLVED as well "
                      "counted one limitation twice.",
        "excluded": False,
        "exclusion_reason": "the 35 cases at the floor are RETAINED in the "
                            "archive, tagged ARITHMETIC_SENSITIVE, and scored "
                            "separately rather than in the primary "
                            "denominator.",
        "resolved_by_consulting_forge": False,
    },
]


def _digest_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _digest_file(path: pathlib.Path) -> str:
    return _digest_bytes(path.read_bytes())


def case_set_digest(paths: list[pathlib.Path]) -> str:
    """Digest of the case set as bytes on disk: filename and content of each.

    Deliberately the same shape as ``benchmarks/hard/score_hard.case_set_digest``
    so the two can be read the same way: a set that gained, lost or edited one
    case carries a different digest and is VISIBLY a different challenge.
    """
    lines = [f"{p.name} {_digest_file(p)}" for p in sorted(paths)]
    return _digest_bytes("\n".join(lines).encode("utf-8"))


def _source_digest() -> dict[str, str]:
    """Every module that produced the challenge, by content.

    The generator and the truth builder are part of the evidence: a corpus is
    only reproducible if the thing that made it is pinned too.
    """
    roots = [
        HERE / "generate.py", HERE / "build_truth.py", HERE / "families.py",
        HERE / "bound_registry.py", HERE / "admissibility.py",
        HERE / "freeze.py",
        HERE / "oracles" / "units.py", HERE / "oracles" / "electrothermal.py",
        HERE / "oracles" / "battery.py", HERE / "oracles" / "kinetics.py",
        HERE / "oracles" / "conduction.py", HERE / "oracles" / "spice.py",
    ]
    return {p.relative_to(HERE.parent.parent).as_posix(): _digest_file(p)
            for p in roots}


# ---------------------------------------------------------------------------
# Phase 1N — the quality guards
# ---------------------------------------------------------------------------

def quality_guards(cases: list[dict], truths: list[dict]) -> list[str]:
    """Everything that must hold before a byte is written. Returns failures."""
    failures: list[str] = []

    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids):
        duplicated = sorted({i for i in ids if ids.count(i) > 1})
        failures.append(f"duplicate case ids: {duplicated}")

    digests: dict[str, str] = {}
    for truth in truths:
        seen = digests.get(truth["payload_digest"])
        if seen is not None:
            failures.append(
                f"duplicate payload: {truth['case_id']} and {seen} are the "
                f"same bytes")
        digests[truth["payload_digest"]] = truth["case_id"]

    required = (
        "case_id", "system", "payload_digest", "independent_verdict",
        "truth_class", "evaluated_conditions", "satisfied_conditions",
        "violated_conditions", "unknown_conditions", "valid_reason_set",
        "reason_classes", "causal_catcher_set", "primary_catcher_status",
        "oracle_ids", "bound_ids", "policy_dependencies",
        "numerical_tolerance_basis", "truth_confidence_class",
        "unresolved_dependencies", "boundary_stratum",
    )
    for truth in truths:
        missing = [field for field in required if field not in truth]
        if missing:
            failures.append(f"{truth['case_id']}: truth is missing {missing}")
        for oracle_id in truth["oracle_ids"]:
            if oracle_id not in ORACLE_REGISTER:
                failures.append(
                    f"{truth['case_id']}: oracle {oracle_id!r} is not in the "
                    f"register")
        for bound_id in truth["bound_ids"]:
            if bound_id not in reg.BY_ID:
                failures.append(
                    f"{truth['case_id']}: bound {bound_id!r} is not registered")
        for name in truth["policy_dependencies"]:
            if not reg.is_policy(name, system=(
                    "kinetics_cstr" if truth["system"] == "kinetics_cstr" else "")):
                failures.append(
                    f"{truth['case_id']}: {name!r} is declared a policy "
                    f"dependency but the register does not class it as one")
        if truth["truth_class"] == "UNRESOLVED" and not truth["unresolved_dependencies"]:
            failures.append(
                f"{truth['case_id']}: UNRESOLVED with no dependency named")

    # No NaN or Inf anywhere in a payload that is not a malformed case, whose
    # whole point is to carry one.
    for case in cases:
        if case["family_kind"] == "malformed":
            continue
        blob = json.dumps(case["payload"])
        for token in ("NaN", "Infinity", "-Infinity", "nan", "inf "):
            if token in blob:
                failures.append(
                    f"{case['id']}: non-finite {token!r} in a payload that is "
                    f"not a malformed case")
                break

    # No legacy hold-out case, and no payload copied from the existing corpus.
    existing = HERE.parent / "hard"
    existing_digests: set[str] = set()
    for directory in ("cases_hard", "cases_battery"):
        folder = existing / directory
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8")).get("payload")
            existing_digests.add(hashlib.sha256(json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest())
    for truth in truths:
        if truth["payload_digest"] in existing_digests:
            failures.append(
                f"{truth['case_id']}: payload is byte-identical to an existing "
                f"benchmark case")

    # A case whose DECLARATION is inadmissible tests the boundary, not the
    # science, and only the families built to do that may do it. Anything else
    # refused at construction is a generator defect wearing a truth: it would
    # score as a Forge mismatch and measure nothing. 152 of 444 cases were in
    # exactly that state before this guard existed.
    deliberate = ("malformed", )
    deliberate_families = ("kin.envelope", "kin.positivity", "cond.alpha",
                           "bat.efficiency")
    stray = [
        f"{t['case_id']} ({t['family']}): {t.get('construction_refusal')}"
        for case, t in zip(cases, truths)
        if t.get("construction_refusal")
        and case["family_kind"] not in deliberate
        and case["family"] not in deliberate_families
    ]
    if stray:
        failures.append(
            f"{len(stray)} cases would be refused at construction but belong "
            f"to no family built to be refused; the first few are "
            f"{stray[:6]}")

    try:
        assert_vocabulary_closed(units_used())
    except Exception as exc:                       # noqa: BLE001
        failures.append(f"unit vocabulary: {exc}")

    return failures


# ---------------------------------------------------------------------------
# distribution, measured rather than asserted
# ---------------------------------------------------------------------------

def _distribution_contrast(cases: list[dict]) -> dict:
    """How this corpus's parameters differ from the existing Hard benchmark's.

    Measured on both corpora rather than described, because a claim to have
    varied the distribution is exactly the kind of claim that is easy to make
    and easy to be wrong about.
    """
    def et_scalars(payloads):
        out: dict[str, list[float]] = {
            "source_voltage_v": [], "reference_resistance_ohm": [],
            "ambient_conductance_w_per_k": [], "ambient_temperature_k": [],
            "n_stages": [],
        }
        for payload in payloads:
            stages = payload.get("stages") or []
            if not stages:
                continue
            out["n_stages"].append(float(len(stages)))
            try:
                out["source_voltage_v"].append(
                    et_oracle.to_si(payload["source_voltage"], "V"))
                for stage in stages:
                    out["reference_resistance_ohm"].append(et_oracle.to_si(
                        stage["conductor"]["reference_resistance"], "ohm"))
                    out["ambient_conductance_w_per_k"].append(et_oracle.to_si(
                        stage["body"]["ambient_conductance"], "W/K"))
                    out["ambient_temperature_k"].append(et_oracle.to_si(
                        stage["body"]["ambient_temperature"], "K"))
            except Exception:                      # noqa: BLE001
                continue
        return out

    def summarise(values: list[float]) -> dict | None:
        finite = sorted(v for v in values if v == v and abs(v) != float("inf"))
        if not finite:
            return None
        n = len(finite)
        return {"n": n, "min": finite[0], "p50": finite[n // 2],
                "max": finite[-1],
                "decades_spanned": (
                    round(__import__("math").log10(finite[-1] / finite[0]), 2)
                    if finite[0] > 0.0 else None)}

    mine = et_scalars([c["payload"] for c in cases
                       if c["system"] == "electrothermal"])
    existing_payloads = []
    folder = HERE.parent / "hard" / "cases_hard"
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            existing_payloads.append(
                json.loads(path.read_text(encoding="utf-8"))["payload"])
    theirs = et_scalars(existing_payloads)
    return {
        "note": "Electro-thermal scalars only, measured on both corpora. The "
                "comparison is against the FULL existing set, development and "
                "sealed hold-out together, because the question is whether "
                "this challenge's parameters are new -- not which split they "
                "would have landed in.",
        "blind_v1": {k: summarise(v) for k, v in mine.items()},
        "existing_hard": {k: summarise(v) for k, v in theirs.items()},
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    import collections

    print("generating (no Forge, no truth) ...")
    cases, rejections = generate_corpus()
    print(f"  {len(cases)} cases, {len(rejections)} rejections")

    print("building truth (independent oracles only) ...")
    truths = [build_truth(case) for case in cases]

    print("quality guards ...")
    failures = quality_guards(cases, truths)
    if failures:
        print("REFUSED — the corpus is not sealable:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("  all guards pass")

    OUT.mkdir(parents=True, exist_ok=True)
    case_dir = OUT / "cases"
    if case_dir.exists():
        for stale in case_dir.glob("*.json"):
            stale.unlink()
    case_dir.mkdir(parents=True, exist_ok=True)

    for case in cases:
        path = case_dir / f"{case['id']}.json"
        path.write_text(
            json.dumps(case, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8")
    case_paths = sorted(case_dir.glob("*.json"))

    truth_blob = json.dumps(
        {"version": TRUTH_BUILDER_VERSION,
         "truths": {t["case_id"]: t for t in truths}},
        sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    (OUT / "TRUTH.json").write_text(truth_blob, encoding="utf-8")

    strata = collections.Counter(t["boundary_stratum"] for t in truths)
    classes = collections.Counter(t["truth_class"] for t in truths)
    verdicts = collections.Counter(t["independent_verdict"] for t in truths)
    catchers = collections.Counter(t["primary_catcher_status"] for t in truths)
    per_system = collections.Counter(t["system"] for t in truths)
    dual = collections.Counter(t["second_oracle_status"] for t in truths)
    hits = sum(1 for t in truths
               if t["intended_stratum"] == t["boundary_stratum"])

    manifest = {
        "challenge_id": "forge-blind-v1",
        "version": "1.0.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "plan_version": PLAN_VERSION,
        "generator_version": GENERATOR_VERSION,
        "truth_builder_version": TRUTH_BUILDER_VERSION,
        "bound_registry_version": reg.BOUND_REGISTRY_VERSION,
        "oracle_unit_table_version": ORACLE_UNIT_TABLE_VERSION,
        "master_seed": MASTER_SEED,
        "seed_derivation": "sha256(f'{MASTER_SEED}:{system}:{family}:{index}')"
                           "[:8], big-endian. Per case, so a family added later "
                           "cannot redraw an earlier one.",
        "planned_counts": PLANNED_COUNTS,
        "planned_total": planned_total(),
        "actual_counts": dict(per_system),
        "actual_total": len(cases),
        "rejections": rejections,
        "rejection_counts": dict(collections.Counter(
            r["reason"] for r in rejections)),
        "verdict_counts": dict(verdicts),
        "truth_class_counts": dict(classes),
        "boundary_stratum_counts": dict(strata),
        "causal_status_counts": dict(catchers),
        "second_oracle_counts": dict(dual),
        "intended_stratum_hits": hits,
        "intended_stratum_misses": len(truths) - hits,
        "intended_stratum_note":
            "A miss is not a defect. A family TARGETS a stratum by solving for "
            "a declaration; what the case IS, is whatever the oracle measured "
            "afterwards, and the measured stratum is what the truth carries. "
            "Misses are counted here so the gap between intent and content is "
            "visible rather than assumed away.",
        "resolvable_total": sum(
            1 for t in truths
            if t["truth_class"] != "UNRESOLVED"
            and t["truth_confidence_class"] == "DECIDED"),
        "arithmetic_sensitive_total": sum(
            1 for t in truths
            if t["truth_confidence_class"] == "ARITHMETIC_SENSITIVE"),
        "unresolved_total": sum(1 for t in truths
                                if t["truth_class"] == "UNRESOLVED"),
        "denominator_policy":
            "The primary denominator is the DECIDED, non-UNRESOLVED set. "
            "ARITHMETIC_SENSITIVE cases stay in the archive and are scored "
            "separately; UNRESOLVED cases are scored not at all. Neither is "
            "counted as a Forge failure and neither is counted as a pass.",
        "resolution_floor": RESOLUTION_FLOOR,
        "measured_state_agreement": MEASURED_STATE_AGREEMENT,
        "oracle_register": ORACLE_REGISTER,
        "dual_oracle_available": {
            "electrical_ngspice": spice_oracle.available(),
        },
        "units_emitted": sorted(units_used()),
        "distribution_contrast": _distribution_contrast(cases),
        "excluded_by_design": [
            "Thermal-runaway and non-converging electro-thermal designs. The "
            "VERDICT of such a case is decidable, but the CONDITION SET a "
            "refused coupling reports is a property of the iteration driver's "
            "bookkeeping rather than of the science, so an independent oracle "
            "cannot state it without copying the driver. Cases whose fixed "
            "point does not converge are rejected pre-freeze under "
            "`oracle_non_convergence` and counted. This challenge therefore "
            "does NOT test refusal-path reporting.",
            "Every capability named in the round's exclusion list: "
            "ContextOfUse, ScientificClaim, ScientificArtifact, arrays, "
            "fields, meshes, new domains, new solvers, new APIs, MCP "
            "features, UI.",
        ],
    }
    manifest_blob = json.dumps(manifest, sort_keys=True, indent=1,
                               allow_nan=False) + "\n"
    (OUT / "MANIFEST.json").write_text(manifest_blob, encoding="utf-8")

    disagreement_blob = json.dumps({
        "note": "Every disagreement between two independently implemented "
                "oracles found BEFORE the freeze, with its resolution. None "
                "was resolved by consulting Forge.",
        "pre_freeze": PRE_FREEZE_DISAGREEMENTS,
        "post_generation_live": [
            {"case_id": t["case_id"], "status": t["second_oracle_status"],
             "worst_relative_gap": t["second_oracle_worst_gap"],
             "notes": t["second_oracle_notes"]}
            for t in truths
            if t["second_oracle_status"] not in ("AGREED", "SINGLE_ORACLE",
                                                 "NOT_REACHED")],
    }, sort_keys=True, indent=1, allow_nan=False) + "\n"
    (OUT / "ORACLE_DISAGREEMENTS.json").write_text(disagreement_blob,
                                                   encoding="utf-8")

    freeze = {
        "challenge_id": "forge-blind-v1",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases),
        "case_set_digest": case_set_digest(case_paths),
        "truth_digest": _digest_bytes(truth_blob.encode("utf-8")),
        "manifest_digest": _digest_bytes(manifest_blob.encode("utf-8")),
        "oracle_disagreements_digest": _digest_bytes(
            disagreement_blob.encode("utf-8")),
        "generator_digest": _source_digest(),
        "oracle_registry_digest": _digest_bytes(json.dumps(
            ORACLE_REGISTER, sort_keys=True).encode("utf-8")),
        "bound_registry_digest": _digest_bytes(json.dumps(
            {b.bound_id: (b.condition, b.bound_class, b.soft)
             for b in reg.BY_ID.values()}, sort_keys=True).encode("utf-8")),
        "truth_class_counts": dict(classes),
        "verdict_counts": dict(verdicts),
        "forge_has_not_been_run": True,
        "statement":
            "These digests were computed before Forge was executed against "
            "this corpus even once. The commit that carries this file is the "
            "scientific firewall: anything dated after it that changes a case "
            "or a truth byte is visible as a digest that no longer matches.",
    }
    (OUT / "FREEZE.json").write_text(
        json.dumps(freeze, sort_keys=True, indent=1) + "\n", encoding="utf-8")

    print(f"\nwrote {len(case_paths)} cases to {case_dir}")
    print(f"  case_set_digest  {freeze['case_set_digest']}")
    print(f"  truth_digest     {freeze['truth_digest']}")
    print(f"  manifest_digest  {freeze['manifest_digest']}")
    print(f"\n  planned {planned_total()} / actual {len(cases)}  "
          f"({len(rejections)} rejected)")
    print(f"  verdicts     {dict(verdicts)}")
    print(f"  truth classes{dict(classes)}")
    print(f"  strata       {dict(strata)}")
    print(f"  resolvable   {manifest['resolvable_total']}  "
          f"arithmetic-sensitive {manifest['arithmetic_sensitive_total']}  "
          f"unresolved {manifest['unresolved_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
