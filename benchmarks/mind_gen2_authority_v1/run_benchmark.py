"""GEN2-BR1.1 benchmark: authority-bound admission on five synthetic worlds plus the Gen1 two-level protocol.

Development evidence on synthetic contract fixtures only; no scientific claim.  Two outputs:

* ``results/AUTHORITY.json`` (deterministic): per world, the admission outcome of every BR1 base proposal on the
  current verified world; the outcome after each kind of owner change (state advanced, provider down, model record
  replaced, declaration revised, ledger charged); every payload mutation of ``mutations.py`` (refused at rebuild, or
  the AUTHORITY codes admission returns); replay of every admission; and the Gen1 failure class.
* ``results/PERFORMANCE.json`` (timings, host-dependent): BR1's own measurements on BR1's frozen cases, now run on
  the BR1.1 code (WORLD_BUILD, ACTIONSPACE_BUILD, FEASIBILITY p50/p95), and the BR1.1 additions on the owned worlds
  (projection, authority verification, admission).

    python -m benchmarks.mind_gen2_authority_v1.run_benchmark            # write both
    python -m benchmarks.mind_gen2_authority_v1.run_benchmark --check    # AUTHORITY.json reproduces
"""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import pathlib
import platform
import statistics
import subprocess
import sys
import time
from typing import Any

from benchmarks.mind_gen2_world_v1 import cases as C, run_benchmark as br1_rb
from engcore.mind.repsem import canonical_bytes
from engcore.mind.world import (
    AdmissionRecord, FeasibleActionSpace, ScientificWorld, WorldRefused, admit, authorize_dispatch, replay_admission,
    verify_world,
)
from engcore.scientific import ScientificCoreError
from engcore.sria.decision import ActionFamily

from . import fixtures as ax
from .mutations import MUTATIONS, NEEDS

HERE = pathlib.Path(__file__).resolve().parent
AUTHORITY_PATH = HERE / "results" / "AUTHORITY.json"
PERFORMANCE_PATH = HERE / "results" / "PERFORMANCE.json"
SCHEMA = "forge.mind.gen2_authority.benchmark/1"
NAMES = ("battery", "hvac_chamber", "hvac_field", "drone", "motor", "gen1_pool")


def owned(name: str) -> ax.Owned:
    return ax.gen1_pool() if name == "gen1_pool" else ax.WORLDS[name]()


def proposals(name: str) -> dict[str, Any]:
    if name == "gen1_pool":
        return {"pool_query": ({"I_A": ax.q(1.0, "A"), "t_on_s": ax.q(60, "s")}, ("y",))}
    return ax.base(name)


def _outcome(r: Any) -> dict[str, Any]:
    return {"status": r.status.value, "codes": list(r.codes()), "admitted": r.admitted is not None}


def _owner_changes(o: ax.Owned) -> dict[str, Any]:
    """Each kind of owner change, as a function from the owned world to the authorities after it."""
    changes: dict[str, Any] = {}
    if o.run is not None:
        changes["state_advanced"] = lambda: o.authorities(state=o.run.result)

        def head_moved():                          # the same live reader, following the execution side's head
            fresh = owned(o.name)
            fresh.advance()
            return fresh.authorities()
        changes["run_head_advanced_in_place"] = head_moved
    if o.base_world.providers:
        changes["provider_down"] = lambda: o.authorities(providers=ax.provider_registry(
            o, down=tuple(p.provider_id for p in o.base_world.providers)))

        def down_in_place():                       # the same registry; the execution side re-probes
            fresh = owned(o.name)
            for p in o.base_world.providers:
                fresh.take_down(p.provider_id)
            return fresh.authorities(refresh=True)
        changes["provider_down_in_place_reprobed"] = down_in_place
    if o.base_world.applicability:
        def replaced():
            m = o.models.list()[0]
            cond = m.validity.conditions[0]
            narrowed = dataclasses.replace(m, validity=dataclasses.replace(m.validity, conditions=(
                dataclasses.replace(cond, maximum=ax.q(cond.maximum.magnitude * 0.5, cond.maximum.units)),)))
            return o.authorities(models=ax.ModelRegistry((narrowed,) + tuple(o.models.list()[1:])))
        changes["model_record_replaced"] = replaced
    changes["declaration_revised"] = lambda: o.authorities(declarations=(dataclasses.replace(
        o.declaration, revision=o.declaration.revision + 1),))

    def charged():
        fresh = owned(o.name)
        account = next(iter(fresh.ledgers.values()), None)
        if account is not None:
            account.settle(charge_id="elsewhere", action_id="other", iteration=1, family=ActionFamily.EXPLORE,
                           realized=1.0)
        else:
            exp = next(iter(fresh.experiments.values()))
            exp.record(ax.ScientificEvaluation("elsewhere", {}, status=ax.EvaluationStatus.NOT_CONVERGED))
        return fresh.authorities()
    changes["budget_charged"] = charged
    return changes


def matrix() -> dict[str, Any]:
    out: dict[str, Any] = {"schema": SCHEMA, "worlds": {}}
    for name in NAMES:
        o = owned(name)
        w = o.world
        space = FeasibleActionSpace.build(w)
        base = {}
        replays = {}
        for aid, (assignments, observe) in sorted(proposals(name).items()):
            r = admit(space, o.propose(aid, assignments, observe), o.authorities())
            base[aid] = _outcome(r)
            record = json.loads(json.dumps(AdmissionRecord.of(r, o.authorities()).to_dict()))
            replays[aid] = replay_admission(record).outcome.value
        moved = {}
        first = next(aid for aid, x in base.items() if x["admitted"])
        assignments, observe = proposals(name)[first]
        for change, authorities in sorted(_owner_changes(o).items()):
            r = admit(space, o.propose(first, assignments, observe), authorities())
            moved[change] = _outcome(r)
        mutations = {}
        for mutation in sorted(MUTATIONS):
            payload = copy.deepcopy(w.to_dict())
            need = NEEDS.get(mutation)
            if need == "budget" and not payload["budget"].get("statements") or need and need != "budget" and \
                    not payload[need]:
                mutations[mutation] = "not applicable"
                continue
            try:
                MUTATIONS[mutation](payload)
            except AssertionError:
                mutations[mutation] = "not applicable"
                continue
            payload.pop("content_digest", None)
            payload.pop("revision_id", None)
            try:
                forged = ScientificWorld.from_dict(payload)
            except (WorldRefused, ScientificCoreError, ValueError, KeyError, TypeError) as exc:
                mutations[mutation] = f"refused at rebuild ({type(exc).__name__})"
                continue
            r = admit(FeasibleActionSpace.build(forged), o.propose(first, assignments, observe, world=forged),
                      o.authorities())
            mutations[mutation] = _outcome(r)
        out["worlds"][name] = {
            "world_revision": w.revision_id, "bindings": len(w.authority_bindings()),
            "verified": verify_world(w, o.authorities()).ok, "base": base, "replay": replays,
            "owner_changes_on": first, "owner_changes": moved, "mutations": mutations,
        }
    o = owned("gen1_pool")
    p = o.propose("pool_query", {"I_A": ax.q(1.15, "A"), "t_on_s": ax.q(60, "s")})
    r = admit(FeasibleActionSpace.build(o.world), p, o.authorities())
    alt = FeasibleActionSpace.build(o.world).alternatives(p, "I_A")
    out["gen1_failure_class"] = {"proposal": "I_A = 1.15 A", **_outcome(r),
                                 "alternatives_I_A": [x.to_dict() for x in alt["options"]], "label": alt["label"]}
    worlds = out["worlds"].values()
    out["summary"] = {
        "base_admitted": sum(x["admitted"] for w in worlds for x in w["base"].values()),
        "base_total": sum(len(w["base"]) for w in worlds),
        "base_not_admitted": sorted(f"{n}/{a}: {x['status']} {x['codes']}" for n, w in out["worlds"].items()
                                    for a, x in w["base"].items() if not x["admitted"]),
        "owner_changes_admitted": sum(x["admitted"] for w in worlds for x in w["owner_changes"].values()),
        "owner_changes_total": sum(len(w["owner_changes"]) for w in worlds),
        "mutations_admitted": sum(isinstance(x, dict) and x["admitted"] for w in worlds
                                  for x in w["mutations"].values()),
        "mutations_total": sum(x != "not applicable" for w in worlds for x in w["mutations"].values()),
        "replay_reproduced": sum(x == "reproduced" for w in worlds for x in w["replay"].values()),
        "replay_total": sum(len(w["replay"]) for w in worlds),
    }
    return out


def _pct(samples: list[float], x: float) -> float:
    samples = sorted(samples)
    return round(samples[min(len(samples) - 1, int(round(x * (len(samples) - 1))))], 4)


def code_revision() -> str:
    """The commit the measured code is at (``+dirty`` when a Python file under ``src`` or ``benchmarks`` differs from
    it; results and reports are not code), else UNKNOWN."""
    root = pathlib.Path(__file__).resolve().parents[2]
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src/*.py", "benchmarks/*.py"], cwd=root,
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"
    return sha + ("+dirty" if dirty else "")


def performance(repeats: int = 25) -> dict[str, Any]:
    br1 = br1_rb.performance(C.load()["cases"], repeats=repeats)
    projection, verify, admission, sizes, check, dispatch = {}, [], [], {}, [], []
    for name in NAMES:
        o = owned(name)
        authorities = o.authorities()
        times = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            w = ax.project_world(o.declaration, authorities)
            times.append((time.perf_counter() - t0) * 1e3)
        projection[name] = round(statistics.median(times), 3)
        sizes[name] = len(canonical_bytes(w.to_dict()))
        space = FeasibleActionSpace.build(w)
        prepared = [o.propose(aid, a, obs, world=w) for aid, (a, obs) in sorted(proposals(name).items())]
        for _ in range(repeats):
            t0 = time.perf_counter()
            verify_world(w, authorities)
            verify.append((time.perf_counter() - t0) * 1e3)
            for p in prepared:
                t0 = time.perf_counter()
                space.check(p)
                check.append((time.perf_counter() - t0) * 1e3)
                t0 = time.perf_counter()
                result = admit(space, p, authorities)
                admission.append((time.perf_counter() - t0) * 1e3)
                if result.admitted is not None:
                    t0 = time.perf_counter()
                    authorize_dispatch(result.admitted, authorities, accept_synthetic=True)
                    dispatch.append((time.perf_counter() - t0) * 1e3)
    return {
        "schema": "forge.mind.gen2_authority.performance/1",
        "code_revision": code_revision(),
        "host": {"platform": platform.platform(), "python": platform.python_version(), "cpu_count": os.cpu_count()},
        "repeats": repeats,
        "br1_cases_on_br1_1_code": {k: br1[k] for k in ("WORLD_BUILD_MS", "ACTIONSPACE_BUILD_MS", "FEASIBILITY_P50_MS",
                                                         "FEASIBILITY_P95_MS", "SERIALIZED_WORLD_BYTES",
                                                         "REFERENCE_SOLVER_MS") if k in br1},
        "PROJECTION_BUILD_MS_median_by_world": projection,
        "PROJECTION_BUILD_MS": round(statistics.median(projection.values()), 3),
        "AUTHORITY_VERIFY_P50_MS": _pct(verify, 0.5), "AUTHORITY_VERIFY_P95_MS": _pct(verify, 0.95),
        "CHECK_ON_OWNED_WORLDS_P50_MS": _pct(check, 0.5), "CHECK_ON_OWNED_WORLDS_P95_MS": _pct(check, 0.95),
        "ADMISSION_P50_MS": _pct(admission, 0.5), "ADMISSION_P95_MS": _pct(admission, 0.95),
        "DISPATCH_AUTHORIZATION_P50_MS": _pct(dispatch, 0.5), "DISPATCH_AUTHORIZATION_P95_MS": _pct(dispatch, 0.95),
        "SERIALIZED_OWNED_WORLD_BYTES": [min(sizes.values()), max(sizes.values())],
        "samples": {"verify": len(verify), "check": len(check), "admission": len(admission), "dispatch": len(dispatch)},
    }


def _dump(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=1, allow_nan=False) + "\n").encode("utf-8")


def main(argv: list[str]) -> int:
    payload = _dump(matrix())
    if "--check" in argv:
        ok = AUTHORITY_PATH.read_bytes() == payload
        print("AUTHORITY", "MATCHES" if ok else "DIFFERS")
        return 0 if ok else 1
    AUTHORITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTHORITY_PATH.write_bytes(payload)
    if "--no-performance" not in argv:
        PERFORMANCE_PATH.write_bytes(_dump(performance()))
    print(json.dumps(json.loads(payload)["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
