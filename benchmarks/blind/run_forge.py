"""Run Forge across the frozen blind challenge. ONCE.

    python benchmarks/blind/run_forge.py

**This module never reads TRUTH.json.** The run is blind in both directions:
it hands each frozen payload to the boundary the challenge spec names for its
system, records what came back, and stops. Comparison is :mod:`compare`'s job,
and separating them is what stops a runner that "helpfully" retried a case
whose answer looked wrong.

It refuses to overwrite ``FORGE_FIRST_RUN.json``. The first blind run is the
primary scientific artifact of the round — preserved *especially* if it is bad
— so a re-run after a fix writes ``FORGE_POST_FIX.json`` beside it and the
first stays where it is. ``--post-fix`` is how you say you meant it.

It also checks the seal before it starts. Running against a corpus whose bytes
no longer match ``FREEZE.json`` would produce a number about a challenge nobody
can reconstruct.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
V1 = HERE / "v1"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

#: Exception names that mean "the boundary refused to build this", as opposed
#: to "Forge fell over". The first seven are the set `benchmarks/hard/
#: score_hard.py` already uses, adopted unchanged so the two scorers agree on
#: what a refusal is; the last two are the model-contract tiers' own.
BOUNDARY_REFUSALS = frozenset({
    "MissingUnitError", "WrongDimensionError", "UnknownFieldError",
    "MissingFieldError", "MalformedPayloadError", "InvalidScientificProblem",
    "ScientificValidationError", "ReactorConfigurationError",
    "SlabConfigurationError", "UnitCompatibilityError",
})


def _facts(verdict, violated, unknown, satisfied, *, note="", detail=""):
    return {
        "verdict": verdict,
        "violated": sorted(violated),
        "unknown": sorted(unknown),
        "satisfied": sorted(satisfied),
        "note": note,
        "detail": detail,
    }


def _electrothermal(payload):
    from engcore.mcp.problem import run_electrothermal_case

    run = run_electrothermal_case(payload)
    verdicts = {report.verdict.value.upper() for report in run.reports}
    verdict = next((v for v in ("NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE",
                                "SUPPORTED") if v in verdicts), "NO_REPORT")
    violated, unknown, satisfied = set(), set(), set()
    for report in run.reports:
        for record in report.validity:
            violated.update(f"{record.model_id}::{n}"
                            for n in record.assessment.violated)
            unknown.update(f"{record.model_id}::{n}"
                           for n in record.assessment.unknown)
            satisfied.update(f"{record.model_id}::{n}"
                             for n in record.assessment.satisfied)
    refused = run.run.outcome.name == "TRANSFER_REFUSED"
    failed = sorted({c.name for report in run.reports
                     for c in (report.failed_checks or ())})
    return _facts(verdict, violated, unknown, satisfied,
                  note="coupling_refused" if refused else "",
                  detail=";".join(failed))


def _battery(payload):
    """Scored over the battery models, exactly as `score_hard.py` scopes it.

    `run_self_heating_discharge` accepts no applicability declaration for the
    thermal body it marches, so the lumped model in every battery report is
    honestly UNKNOWN and no battery case can reach SUPPORTED over the whole
    report. Scoring the whole report would measure that one gap 120 times and
    nothing else. The scope is declared in BLIND_CHALLENGE_SPEC.json.
    """
    from engcore.mcp.battery import run_battery_case

    run = run_battery_case(payload)
    statuses = {r.model_id: r.assessment.status.value for r in run.report.validity
                if r.model_id.startswith("battery.")}
    if any(v == "outside_validated_domain" for v in statuses.values()):
        verdict = "NOT_SUPPORTED"
    elif any(v == "unknown" for v in statuses.values()):
        verdict = "INSUFFICIENT_EVIDENCE"
    else:
        verdict = "SUPPORTED"
    violated, unknown, satisfied = set(), set(), set()
    for record in run.report.validity:
        if not record.model_id.startswith("battery."):
            continue
        violated.update(f"{record.model_id}::{n}"
                        for n in record.assessment.violated)
        unknown.update(f"{record.model_id}::{n}" for n in record.assessment.unknown)
        satisfied.update(f"{record.model_id}::{n}"
                         for n in record.assessment.satisfied)
    return _facts(verdict, violated, unknown, satisfied)


#: The eleven names a reactor declaration carries. A payload missing one of
#: them cannot be built into a `ReactorRun` at all, so the assembled context is
#: driven directly — which is the documented assembly point and the only way
#: to ask the contract tier about a missing declaration.
_REACTOR_FIELDS = (
    "temperature", "concentration", "k0", "activation_energy",
    "heat_of_reaction", "density", "heat_capacity", "feed_concentration",
    "feed_temperature", "coolant_temperature", "residence_time",
)


def _kinetics(payload):
    from engcore.domains.kinetics.cstr import (
        CSTR_MODEL, ReactorChemistry, ReactorOperation, ReactorRun,
    )
    from engcore.domains.kinetics.cstr.context import cstr_validity_context
    from engcore.domains.kinetics.cstr.problem import ASSEMBLER_NAMESPACE
    from engcore.scientific.units.quantity import Quantity

    def q(key, unit):
        raw = payload.get(key)
        if raw is None:
            return None
        magnitude, _, spelling = raw.strip().partition(" ")
        return Quantity(float(magnitude), spelling.strip())

    declared = {
        "temperature": q("temperature", "kelvin"),
        "concentration": q("concentration", "mole/meter**3"),
        "k0": q("k0", "1/second"),
        "activation_energy": q("activation_energy", "joule/mole"),
        "heat_of_reaction": q("heat_of_reaction", "joule/mole"),
        "density": q("density", "kilogram/meter**3"),
        "heat_capacity": q("heat_capacity", "joule/kilogram/kelvin"),
        "feed_concentration": q("feed_concentration", "mole/meter**3"),
        "feed_temperature": q("feed_temperature", "kelvin"),
        "coolant_temperature": q("coolant_temperature", "kelvin"),
        "residence_time": q("residence_time", "second"),
    }
    complete = all(declared[name] is not None for name in _REACTOR_FIELDS)
    note = ""
    if complete:
        # The whole path, construction guards included. This is where a
        # declaration outside the envelope is refused before any condition is
        # assessed.
        volume = q("reactor_volume", "meter**3")
        residence = declared["residence_time"]
        flow = Quantity(
            volume.magnitude_in("meter**3")
            / residence.magnitude_in("second"), "meter**3/second")
        operation = ReactorOperation(
            volume=volume, flow_rate=flow,
            feed_concentration=declared["feed_concentration"],
            feed_temperature=declared["feed_temperature"],
            coolant_temperature=declared["coolant_temperature"],
            ua=q("ua", "watt/kelvin"), end_time=q("end_time", "second"))
        run = ReactorRun(
            run_label="blind",
            chemistry=ReactorChemistry(
                k0=declared["k0"], activation_energy=declared["activation_energy"],
                heat_of_reaction=declared["heat_of_reaction"],
                density=declared["density"],
                heat_capacity=declared["heat_capacity"]),
            operation=operation,
            initial_concentration=declared["concentration"],
            initial_temperature=declared["temperature"])
        context = run.validity_context()
    else:
        # A missing declaration cannot reach a constructor that requires it,
        # so the context is assembled from what IS declared. The group that
        # cannot be derived is absent rather than defaulted, which is what
        # leaves its condition UNKNOWN.
        context = cstr_validity_context(
            {k: v for k, v in declared.items() if v is not None},
            reserved=ASSEMBLER_NAMESPACE)
        note = "assembled_from_partial_declaration"

    assessment = context.assess(CSTR_MODEL)
    model = CSTR_MODEL.model_id
    violated = {f"{model}::{n}" for n in assessment.violated}
    unknown = {f"{model}::{n}" for n in assessment.unknown}
    satisfied = {f"{model}::{n}" for n in assessment.satisfied}
    if violated:
        verdict = "NOT_SUPPORTED"
    elif unknown:
        verdict = "INSUFFICIENT_EVIDENCE"
    else:
        verdict = "SUPPORTED"
    return _facts(verdict, violated, unknown, satisfied, note=note)


def _conduction(payload):
    from engcore.domains.thermal.conduction1d.problem import (
        ConductionSlab, SlabDiscretization,
    )
    from engcore.domains.thermal_models.conduction1d_schemes import (
        EXPLICIT_REALIZATION, IMPLICIT_REALIZATION, assess_realization,
    )
    from engcore.scientific.units.quantity import Quantity

    def q(key):
        magnitude, _, spelling = payload[key].strip().partition(" ")
        return Quantity(float(magnitude), spelling.strip())

    slab = ConductionSlab(
        slab_id="blind", length=q("length"), diffusivity=q("diffusivity"),
        end_time=q("end_time"),
        discretization=SlabDiscretization(int(payload["n_cells"]),
                                          int(payload["n_steps"])))
    explicit = payload["realization"].endswith("explicit_forward_euler")
    realization = EXPLICIT_REALIZATION if explicit else IMPLICIT_REALIZATION
    assessment = assess_realization(realization, slab)
    key = realization.realization_id
    violated = {f"{key}::{n}" for n in assessment.violated}
    unknown = {f"{key}::{n}" for n in assessment.unknown}
    satisfied = {f"{key}::{n}" for n in assessment.satisfied}
    status = assessment.status.value
    if status == "outside_validated_domain":
        verdict = "NOT_SUPPORTED"
    elif status == "unknown":
        verdict = "INSUFFICIENT_EVIDENCE"
        if not unknown:
            # An A-stable scheme declares no condition, so the domain is empty
            # and reports UNKNOWN with nothing named. The truth layer emits a
            # synthetic `realization_applicability` for exactly this, so the
            # two channels can be compared at all.
            unknown = {f"{key}::realization_applicability"}
    else:
        verdict = "SUPPORTED"
    return _facts(verdict, violated, unknown, satisfied,
                  note=f"assessment_status={status}")


_RUNNERS = {
    "electrothermal": _electrothermal,
    "battery": _battery,
    "kinetics_cstr": _kinetics,
    "conduction_1d": _conduction,
}


def run_one(path_text: str) -> dict:
    path = pathlib.Path(path_text)
    case = json.loads(path.read_text(encoding="utf-8"))
    started = time.perf_counter()
    try:
        result = _RUNNERS[case["system"]](case["payload"])
    except Exception as exc:                              # noqa: BLE001
        name = type(exc).__name__
        result = _facts(
            "REJECTED_AT_BOUNDARY" if name in BOUNDARY_REFUSALS
            else f"ERROR:{name}",
            (), (), (), note=name, detail=str(exc)[:300])
    result["case_id"] = case["id"]
    result["system"] = case["system"]
    result["seconds"] = time.perf_counter() - started
    return result


def _seal_ok() -> tuple[bool, str]:
    freeze = json.loads((V1 / "FREEZE.json").read_text(encoding="utf-8"))
    paths = sorted((V1 / "cases").glob("*.json"))
    lines = [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}"
             for p in paths]
    computed = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    if computed != freeze["case_set_digest"]:
        return False, "the case set no longer matches FREEZE.json"
    truth = hashlib.sha256((V1 / "TRUTH.json").read_bytes()).hexdigest()
    if truth != freeze["truth_digest"]:
        return False, "TRUTH.json no longer matches FREEZE.json"
    return True, freeze["case_set_digest"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--post-fix", action="store_true",
                        help="write FORGE_POST_FIX.json instead; the first run "
                             "is never replaced")
    parser.add_argument("--label", default="",
                        help="what this post-fix run is testing")
    args = parser.parse_args()

    ok, detail = _seal_ok()
    if not ok:
        print(f"REFUSED: {detail}")
        return 1

    target = V1 / ("FORGE_POST_FIX.json" if args.post_fix
                   else "FORGE_FIRST_RUN.json")
    if target.exists() and not args.post_fix:
        print("REFUSED: FORGE_FIRST_RUN.json already exists. The first blind "
              "run is the result of this round and is never overwritten; a "
              "re-run after a fix goes in FORGE_POST_FIX.json (--post-fix).")
        return 1

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--short"], cwd=REPO,
                           capture_output=True, text=True).stdout.strip()

    paths = [str(p) for p in sorted((V1 / "cases").glob("*.json"))]
    print(f"running Forge over {len(paths)} frozen cases at HEAD {head[:12]} ...")
    started = time.perf_counter()
    rows: list[dict] = []
    with futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(run_one, paths, chunksize=8):
            rows.append(row)
    wall = time.perf_counter() - started

    seconds = sorted(r["seconds"] for r in rows)
    n = len(seconds)
    artifact = {
        "challenge_id": "forge-blind-v1",
        "run_kind": "POST_FIX" if args.post_fix else "FIRST_RUN",
        "label": args.label,
        "head_sha": head,
        "worktree_clean_at_run": not dirty,
        "case_set_digest": detail,
        "case_count": len(rows),
        "wall_seconds": wall,
        "per_case_seconds": {
            "p50": seconds[n // 2],
            "p95": seconds[min(n - 1, int(0.95 * n))],
            "max": seconds[-1],
            "total": sum(seconds),
        },
        "results": {r["case_id"]: r for r in rows},
    }
    blob = json.dumps(artifact, sort_keys=True, separators=(",", ":"),
                      allow_nan=False) + "\n"
    target.write_text(blob, encoding="utf-8")

    if not args.post_fix:
        (V1 / "FIRST_RUN_SEAL.json").write_text(json.dumps({
            "first_run_digest": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
            "pre_forge_freeze_sha": _pre_forge_sha(),
            "run_head_sha": head,
            "case_set_digest": detail,
            "statement":
                "The first blind run, sealed by digest. It is the result of "
                "this round whatever it says. A re-run after a fix is a "
                "POST_FIX artifact and never replaces this one.",
        }, sort_keys=True, indent=1) + "\n", encoding="utf-8")

    print(f"wrote {target.name}: {len(rows)} results in {wall:.1f}s "
          f"(p50 {seconds[n // 2] * 1e3:.1f} ms, p95 "
          f"{seconds[min(n - 1, int(0.95 * n))] * 1e3:.1f} ms per case)")
    return 0


def _pre_forge_sha() -> str:
    """The commit that sealed the challenge, found rather than typed.

    The last commit that touched `v1/FREEZE.json`. Reading it from git rather
    than recording it by hand means the seal cannot name a SHA that never
    carried the freeze.
    """
    out = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "benchmarks/blind/v1/FREEZE.json"],
        cwd=REPO, capture_output=True, text=True)
    return out.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
