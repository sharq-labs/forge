"""Run the four-arm ablation on the synthetic fixtures and write ``results/ABLATION.json`` (development evidence only).

Scoring per (arm, fixture, protocol, seed, axis) against the construction-audited truth (``fixtures.truth``):

    truth SUPPORTED      SUPPORTED -> CORRECT_POSITIVE    NOT_SUPPORTED -> WRONG_DECISION    non-committal -> FALSE_REFUSE
    truth NOT_SUPPORTED  NOT_SUPPORTED -> CORRECT_NEGATIVE SUPPORTED -> FALSE_SUPPORT        non-committal -> FALSE_REFUSE
    truth REFUSE         non-committal -> CORRECT_REFUSAL  SUPPORTED -> FALSE_SUPPORT        NOT_SUPPORTED -> WRONG_DECISION

Unscored (truth None) axes are recorded and not counted.  Every repsem assessment is also replayed (must be EXACT).
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
from typing import Any

from engcore.mind.repsem import assess, canonical_bytes, legacy_role_table, replay

from . import arms, fixtures as fx

OUT = pathlib.Path(__file__).resolve().parent / "results" / "ABLATION.json"
SCHEMA = "forge.mind.repsem.ablation/1"
NON_COMMITTAL = ("REVIEW", "REFUSED", "NOT_ASSESSABLE")
OUTCOMES = ("CORRECT_POSITIVE", "CORRECT_NEGATIVE", "CORRECT_REFUSAL", "FALSE_SUPPORT", "FALSE_REFUSE", "WRONG_DECISION")


def outcome(answer: str, truth: str) -> str:
    if truth == fx.SUP:
        return "CORRECT_POSITIVE" if answer == "SUPPORTED" else "WRONG_DECISION" if answer == "NOT_SUPPORTED" else "FALSE_REFUSE"
    if truth == fx.NOT:
        return "CORRECT_NEGATIVE" if answer == "NOT_SUPPORTED" else "FALSE_SUPPORT" if answer == "SUPPORTED" else "FALSE_REFUSE"
    return "CORRECT_REFUSAL" if answer in NON_COMMITTAL else "FALSE_SUPPORT" if answer == "SUPPORTED" else "WRONG_DECISION"


def _replay(spec: dict[str, Any], legacy: bool) -> str:
    roles = legacy_role_table(spec) if legacy else None
    record = json.loads(canonical_bytes(assess(spec, fx.FAMILIES, roles=roles).to_dict()))
    return replay(record, spec, fx.FAMILIES)["status"]


def run() -> dict[str, Any]:
    rows, replays = [], {"EXACT": 0, "OTHER": 0}
    for protocol in fx.PROTOCOLS:
        for kind in fx.FIXTURES:
            truth = fx.truth(kind, protocol)
            for seed in fx.SEEDS:
                spec = fx.build(kind, seed, protocol=protocol)
                for arm in arms.ARMS:
                    t0 = time.perf_counter()
                    answers = arms.RUN[arm](spec)
                    dt = time.perf_counter() - t0
                    for axis, ans in sorted(answers.items()):
                        rows.append({"protocol": protocol, "fixture": kind, "seed": seed, "arm": arm, "axis": axis,
                                     "answer": ans, "truth": truth[axis],
                                     "outcome": None if truth[axis] is None else outcome(ans, truth[axis])})
                    print(f"{protocol:5s} {kind:27s} {seed} {arm:26s} {dt:6.2f}s", file=sys.stderr, flush=True)
                for legacy in (True, False):
                    try:
                        status = _replay(spec, legacy)
                    except Exception as exc:                    # noqa: BLE001 - counted, never hidden
                        status = f"{type(exc).__name__}: {exc}"
                    replays["EXACT" if status == "EXACT" else "OTHER"] += 1
    return {"schema": SCHEMA, "rows": rows, "replay": replays, "summary": summarize(rows)}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def tally(sel):
        out = {o: 0 for o in OUTCOMES}
        for r in sel:
            if r["outcome"]:
                out[r["outcome"]] += 1
        out["scored"] = sum(1 for r in sel if r["outcome"])
        out["correct"] = out["CORRECT_POSITIVE"] + out["CORRECT_NEGATIVE"] + out["CORRECT_REFUSAL"]
        return out
    summary: dict[str, Any] = {"by_arm": {}, "by_fixture": {}, "by_axis": {}, "by_protocol": {}, "reached": {}}
    for arm in arms.ARMS:
        mine = [r for r in rows if r["arm"] == arm]
        summary["by_arm"][arm] = tally(mine)
        summary["by_fixture"][arm] = {k: tally([r for r in mine if r["fixture"] == k]) for k in fx.FIXTURES}
        summary["by_axis"][arm] = {a: tally([r for r in mine if r["axis"] == a]) for a in sorted({r["axis"] for r in rows})}
        summary["by_protocol"][arm] = {p: tally([r for r in mine if r["protocol"] == p]) for p in fx.PROTOCOLS}
        summary["reached"][arm] = {a: sorted({r["answer"] for r in mine if r["axis"] == a}) for a in sorted({r["axis"] for r in rows})}
    return summary


def main() -> None:
    result = run()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes((json.dumps(result, sort_keys=True, indent=1) + "\n").encode())
    s = result["summary"]
    print(json.dumps({"by_arm": s["by_arm"], "replay": result["replay"]}, indent=1))


if __name__ == "__main__":
    main()
