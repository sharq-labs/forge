"""Run the GEN2-BR1 synthetic feasibility benchmark: both arms, replay, serialization stability, performance.

Development evidence only.  This is a feasibility (grounding) benchmark on synthetic contract fixtures, not a
scientific-rediscovery benchmark and not an evaluation of any physics.

    python -m benchmarks.mind_gen2_world_v1.run_benchmark          # writes results/BENCHMARK.json + PERFORMANCE.json
    python -m benchmarks.mind_gen2_world_v1.run_benchmark --decisions-digest

``BENCHMARK.json`` is deterministic (no clock, no host facts) and must reproduce byte for byte; ``PERFORMANCE.json``
holds the timings and the host they were taken on.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from typing import Any

from engcore.mind.repsem import canonical_bytes
from engcore.mind.world import FeasibleActionSpace, ScientificWorld, replay_decision
from engcore.sria.decision.replay import ReplayOutcome

from . import arms
from . import cases as C
from . import fixtures as fx

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "results" / "BENCHMARK.json"
TERMINOLOGY = ("A per-case verdict is FEASIBLE or NOT_FEASIBLE under the action-feasibility check (Gen1: its own "
               "validity check; NOT_POSABLE when Gen1 cannot state the proposal).  The brief's section 24 names map to "
               "these counters: VALID_ACTIONS_ADMITTED = valid_found_feasible, INVALID_ACTIONS_REJECTED = "
               "invalid_found_not_feasible, FALSE_ADMISSIONS = false_feasible, FALSE_REJECTIONS = false_not_feasible.  "
               "None of them is evidence admission (sria.admission) or any scientific verdict.")
PERF = HERE / "results" / "PERFORMANCE.json"
SCHEMA = "forge.mind.gen2_world.benchmark/1"
PERF_SCHEMA = "forge.mind.gen2_world.performance/1"
HASH_SEEDS = ("0", "4242")


def _dump(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=1, allow_nan=False) + "\n").encode("utf-8")


def _worlds(cases: list[dict[str, Any]]) -> dict[str, ScientificWorld]:
    out = {}
    for case in cases:
        key = json.dumps([case["world"], case["variant"]], sort_keys=True)
        if key not in out:
            out[key] = C.variant(case["world"], case["variant"])
    return out


def _world_key(case: dict[str, Any]) -> str:
    return json.dumps([case["world"], case["variant"]], sort_keys=True)


def decisions(cases: list[dict[str, Any]], worlds: dict[str, ScientificWorld]) -> list[dict[str, Any]]:
    spaces = {k: FeasibleActionSpace.build(w) for k, w in worlds.items()}
    rows = []
    for case in cases:
        k = _world_key(case)
        w, sp = worlds[k], spaces[k]
        p = C.proposal(case, w)
        g2 = arms.gen2(sp, p)
        g1 = arms.gen1_role_only(w, p)
        rows.append({"case": case, "world": w, "proposal": p, "gen2": g2, "gen1": g1})
    return rows


def decisions_digest(rows: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(canonical_bytes(r["gen2"]["decision"].to_dict()))
    return h.hexdigest()


def _rate(n: int, d: int) -> Any:
    return None if d == 0 else round(n / d, 6)


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gen2 = Counter()
    gen1 = Counter()
    by_world: dict[str, Counter] = defaultdict(Counter)
    by_kind: dict[str, dict[str, set]] = defaultdict(lambda: {"worlds": set(), "worlds_correct": set(), "statuses": set()})
    misses = []
    posable_rows = [r for r in rows if r["gen1"]["verdict"] != "NOT_POSABLE"]
    for r in rows:
        exp = r["case"]["expected"]
        truth_ok = exp["status"] == "FEASIBLE"
        g = r["gen2"]
        found = g["verdict"] == "FEASIBLE"
        status_ok = g["status"] == exp["status"]
        codes_ok = set(exp["codes"]) <= set(g["codes"])
        gen2["cases"] += 1
        gen2["status_correct"] += status_ok
        gen2["codes_correct"] += codes_ok
        if truth_ok:
            gen2["valid"] += 1
            gen2["valid_found_feasible"] += found
            gen2["false_not_feasible"] += not found
        else:
            gen2["invalid"] += 1
            gen2["invalid_found_not_feasible"] += not found
            gen2["false_feasible"] += found
        if not (status_ok and codes_ok):
            misses.append({"case_id": r["case"]["case_id"], "expected": exp, "status": g["status"], "codes": g["codes"]})
        w = r["case"]["world"]
        by_world[w]["cases"] += 1
        by_world[w]["correct"] += status_ok and codes_ok
        kinds = [m["kind"] for m in r["case"]["mutations"]] or ["BASE"]
        for kind in kinds:
            by_kind[kind]["worlds"].add(w)
            by_kind[kind]["statuses"].add(g["status"])
            if status_ok and codes_ok:
                by_kind[kind]["worlds_correct"].add(w)
        v1 = r["gen1"]["verdict"]
        gen1["cases"] += 1
        gen1[f"verdict_{v1}"] += 1
        if v1 != "NOT_POSABLE":
            a1 = v1 == "FEASIBLE"
            if truth_ok:
                gen1["valid"] += 1
                gen1["valid_found_feasible"] += a1
                gen1["false_not_feasible"] += not a1
            else:
                gen1["invalid"] += 1
                gen1["invalid_found_not_feasible"] += not a1
                gen1["false_feasible"] += a1
    head = Counter()
    for r in posable_rows:
        truth_ok = r["case"]["expected"]["status"] == "FEASIBLE"
        for arm, verdict in (("gen2", r["gen2"]["verdict"]), ("gen1", r["gen1"]["verdict"])):
            found = verdict == "FEASIBLE"
            head[f"{arm}_valid_found_feasible"] += truth_ok and found
            head[f"{arm}_false_not_feasible"] += truth_ok and not found
            head[f"{arm}_invalid_found_not_feasible"] += (not truth_ok) and not found
            head[f"{arm}_false_feasible"] += (not truth_ok) and found
        head["valid"] += truth_ok
        head["invalid"] += not truth_ok
    unit = [r for r in rows if any(m["kind"] == "WRONG_UNIT" for m in r["case"]["mutations"])]
    unit_posable = [r for r in unit if r["gen1"]["verdict"] != "NOT_POSABLE"]
    gen1_false_feasible_kinds = Counter(m["kind"] for r in posable_rows if r["gen1"]["verdict"] == "FEASIBLE"
                                         and r["case"]["expected"]["status"] != "FEASIBLE"
                                         for m in r["case"]["mutations"] if not m["kind"].startswith("VALID"))
    gen1_false_not_feasible_kinds = Counter(([m["kind"] for m in r["case"]["mutations"]] or ["BASE"])[0]
                                         for r in posable_rows if r["gen1"]["verdict"] == "NOT_FEASIBLE"
                                         and r["case"]["expected"]["status"] == "FEASIBLE")
    not_posable = Counter(r["case"]["world"] for r in rows if r["gen1"]["verdict"] == "NOT_POSABLE")
    multi_world = {k: v for k, v in by_kind.items() if len(v["worlds"]) >= 2}
    return {
        "GEN2_WORLD_ACTIONSPACE": {
            **dict(gen2),
            "valid_found_feasible_rate": _rate(gen2["valid_found_feasible"], gen2["valid"]),
            "invalid_found_not_feasible_rate": _rate(gen2["invalid_found_not_feasible"], gen2["invalid"]),
            "status_accuracy": _rate(gen2["status_correct"], gen2["cases"]),
            "reason_code_accuracy": _rate(gen2["codes_correct"], gen2["cases"]),
            "misses": misses,
        },
        "GEN1_ROLE_ONLY": {
            **dict(gen1),
            "status_accuracy": "N/A (Gen1 returns a bool and one reason string, no typed status)",
            "not_posable_by_world": dict(sorted(not_posable.items())),
            "false_feasible_by_mutation": dict(sorted(gen1_false_feasible_kinds.items())),
            "false_not_feasible_by_case_kind": dict(sorted(gen1_false_not_feasible_kinds.items())),
        },
        "head_to_head_on_gen1_posable_cases": {"cases": len(posable_rows), **dict(sorted(head.items()))},
        "unit_errors": {
            "cases": len(unit),
            "gen2_not_feasible_with_UNIT_INCOMPATIBLE": sum(r["gen2"]["verdict"] == "NOT_FEASIBLE"
                                                        and "UNIT_INCOMPATIBLE" in r["gen2"]["codes"] for r in unit),
            "gen1_posable": len(unit_posable),
            "gen1_found_feasible": sum(r["gen1"]["verdict"] == "FEASIBLE" for r in unit_posable),
        },
        "cross_domain": {
            "worlds": {w: {"cases": c["cases"], "correct": c["correct"], "pass_rate": _rate(c["correct"], c["cases"])}
                       for w, c in sorted(by_world.items())},
            "mutation_kinds_in_two_or_more_worlds": len(multi_world),
            "kinds_correct_in_every_world": sum(v["worlds"] == v["worlds_correct"] for v in multi_world.values()),
            "kinds_with_one_status_across_worlds": sum(len(v["statuses"]) == 1 for v in multi_world.values()),
            "per_kind": {k: {"worlds": len(v["worlds"]), "worlds_correct": len(v["worlds_correct"]),
                             "statuses": sorted(v["statuses"])} for k, v in sorted(by_kind.items())},
        },
    }


def replay_and_serialization(rows: list[dict[str, Any]], worlds: dict[str, ScientificWorld]) -> dict[str, Any]:
    outcomes = Counter()
    for r in rows:
        result = replay_decision(r["gen2"]["decision"].to_dict(), r["world"].to_dict(), r["proposal"].to_dict())
        outcomes[result.outcome.value] += 1
    stable = 0
    for w in worlds.values():
        payload = w.to_dict()
        again = ScientificWorld.from_dict(payload)
        same = (canonical_bytes(again.to_dict()) == canonical_bytes(payload)
                and FeasibleActionSpace.build(again).space_id == FeasibleActionSpace.build(w).space_id)
        stable += same
    return {"replayed": sum(outcomes.values()), "outcomes": dict(sorted(outcomes.items())),
            "replay_exact_rate": _rate(outcomes[ReplayOutcome.REPRODUCED.value], sum(outcomes.values())),
            "world_variants": len(worlds), "world_round_trips_byte_identical": stable}


def cross_process(digest: str) -> dict[str, Any]:
    out = {}
    for seed in HASH_SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, "-m", "benchmarks.mind_gen2_world_v1.run_benchmark", "--decisions-digest"],
                              capture_output=True, text=True, env=env, check=True)
        out[seed] = proc.stdout.strip().splitlines()[-1]
    return {"in_process": digest, "by_hash_seed": out, "identical": all(v == digest for v in out.values())}


def performance(cases: list[dict[str, Any]], repeats: int = 25) -> dict[str, Any]:
    builds = {}
    sizes = {}
    rebuilds = {}
    spaces = {}
    for name, build in sorted(fx.WORLDS.items()):
        times = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            w = build()
            times.append(time.perf_counter() - t0)
        payload = w.to_dict()
        sizes[name] = len(canonical_bytes(payload))
        rt = []
        st = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            ScientificWorld.from_dict(payload)
            rt.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            FeasibleActionSpace.build(w)
            st.append(time.perf_counter() - t0)
        builds[name] = round(statistics.median(times) * 1e3, 3)
        rebuilds[name] = round(statistics.median(rt) * 1e3, 3)
        spaces[name] = round(statistics.median(st) * 1e3, 3)
    worlds = _worlds(cases)
    prepared = []
    for case in cases:
        k = _world_key(case)
        sp = FeasibleActionSpace.build(worlds[k])
        prepared.append((sp, C.proposal(case, worlds[k])))
    samples = []
    for sp, p in prepared:
        for _ in range(5):
            t0 = time.perf_counter()
            sp.check(p)
            samples.append((time.perf_counter() - t0) * 1e3)
    samples.sort()

    def pct(x: float) -> float:
        return round(samples[min(len(samples) - 1, int(round(x * (len(samples) - 1))))], 4)

    reference = []
    from benchmarks.mind_repsem_v1 import fixtures as repsem_fx
    from engcore.mind.repsem import assess
    spec = repsem_fx.build("IDENTIFIABLE", 0)
    for _ in range(3):
        t0 = time.perf_counter()
        assess(spec, repsem_fx.FAMILIES)
        reference.append((time.perf_counter() - t0) * 1e3)

    return {"schema": PERF_SCHEMA,
            "host": {"platform": platform.platform(), "python": platform.python_version(), "cpu_count": os.cpu_count(),
                     "bytecode_writing_disabled": bool(os.environ.get("PYTHONDONTWRITEBYTECODE"))},
            "repeats": repeats,
            "REFERENCE_SOLVER_MS": {"what": "one Gen1 repsem judgment (scipy least-squares model fit) on the synthetic "
                                            "mind_repsem_v1 IDENTIFIABLE fixture, seed 0: an in-repo solver execution",
                                    "median": round(statistics.median(reference), 3)},
            "WORLD_BUILD_MS_median_by_world": builds, "WORLD_BUILD_MS": round(statistics.median(builds.values()), 3),
            "WORLD_FROM_DICT_MS_median_by_world": rebuilds,
            "ACTIONSPACE_BUILD_MS_median_by_world": spaces, "ACTIONSPACE_BUILD_MS": round(statistics.median(spaces.values()), 3),
            "FEASIBILITY_samples": len(samples), "FEASIBILITY_P50_MS": pct(0.5), "FEASIBILITY_P95_MS": pct(0.95),
            "FEASIBILITY_MAX_MS": round(samples[-1], 4),
            "SERIALIZED_WORLD_BYTES_by_world": sizes, "SERIALIZED_WORLD_BYTES_max": max(sizes.values())}


def main(argv: list[str]) -> int:
    payload = C.load()
    if C.dump(C.build()) != C.CASES_PATH.read_bytes():
        print("CASES DIFFER from what the frozen generator produces; refusing to score", file=sys.stderr)
        return 2
    cases = payload["cases"]
    worlds = _worlds(cases)
    rows = decisions(cases, worlds)
    digest = decisions_digest(rows)
    if "--decisions-digest" in argv:
        print(digest)
        return 0
    result = {"schema": SCHEMA, "cases_sha256": hashlib.sha256(C.CASES_PATH.read_bytes()).hexdigest(),
              "cases": len(cases), "decisions_digest": digest, "terminology": TERMINOLOGY, "scores": score(rows),
              "replay_and_serialization": replay_and_serialization(rows, worlds), "cross_process": cross_process(digest)}
    OUT.write_bytes(_dump(result))
    PERF.write_bytes(_dump(performance(cases)))
    s = result["scores"]
    g2, g1 = s["GEN2_WORLD_ACTIONSPACE"], s["GEN1_ROLE_ONLY"]
    print(f"GEN2: valid found FEASIBLE {g2['valid_found_feasible']}/{g2['valid']}, invalid found NOT_FEASIBLE "
          f"{g2['invalid_found_not_feasible']}/{g2['invalid']}, false FEASIBLE {g2['false_feasible']}, false "
          f"NOT_FEASIBLE {g2['false_not_feasible']}, "
          f"status {g2['status_correct']}/{g2['cases']}, codes {g2['codes_correct']}/{g2['cases']}")
    print(f"GEN1: not posable {g1.get('verdict_NOT_POSABLE', 0)}, valid found FEASIBLE "
          f"{g1.get('valid_found_feasible', 0)}/{g1.get('valid', 0)}, invalid found NOT_FEASIBLE "
          f"{g1.get('invalid_found_not_feasible', 0)}/{g1.get('invalid', 0)}, false FEASIBLE "
          f"{g1.get('false_feasible', 0)}, false NOT_FEASIBLE {g1.get('false_not_feasible', 0)}")
    rs = result["replay_and_serialization"]
    print(f"replay {rs['outcomes']}, round trips {rs['world_round_trips_byte_identical']}/{rs['world_variants']}, "
          f"cross-process identical {result['cross_process']['identical']}")
    return 0 if not g2["misses"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
