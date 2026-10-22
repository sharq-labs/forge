"""Section 15: the Gen1 failure class, reproduced synthetically and met by the Gen2 world/action space.

The protocol offers two current levels, {1.0 A, 2.0 A} (declared protocol metadata), and a pulse duration settable
in [20 s, 200 s].  Generation 1 can only pose the current as a continuous box [1.0, 2.0] A, exactly as the
battery_rediscovery_v1 adapter did; its real initial design (``engcore.mind.minimal.runner.initial_design``, seed 0)
then requests currents between the levels.  Each Gen1 request is submitted, unchanged, through the Gen2 Mind port.

This shows a grounding improvement (an unsupported request is refused with its reason and the declared alternatives
are listed), not a scientific-performance improvement.  No battery v1/v2/v3 data, answer or truth is read.

    python -m benchmarks.mind_gen2_world_v1.gen1_repro     # writes results/GEN1_REPRODUCTION.json
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

from engcore.mind.minimal.problem import ExperimentalProblem, InputSpec
from engcore.mind.minimal.runner import initial_design
from engcore.mind.world import FeasibleActionSpace, MindWorldPort, ProposedAction
from engcore.scientific import Quantity
from engcore.sria.decision.hypotheses import ProposalProvenance, ProposerKind

from . import arms
from . import fixtures as fx

OUT = pathlib.Path(__file__).resolve().parent / "results" / "GEN1_REPRODUCTION.json"
SCHEMA = "forge.mind.gen2_world.gen1_reproduction/1"
SEED = 0
GEN1 = ProposalProvenance(ProposerKind.ALGORITHM, "engcore.mind.minimal.runner.initial_design")


def gen1_problem() -> ExperimentalProblem:
    """The problem as Gen1 can pose it: the two levels become a continuous box (the v1 adapter's ``_box``)."""
    return ExperimentalProblem("gen1-repro:two-level-protocol", (InputSpec("I_A", 1.0, 2.0, "A"),
                                                                InputSpec("t_on_s", 20.0, 200.0, "s")),
                               (), "y", "V", 24, 1.0, {})


def run() -> dict[str, Any]:
    world = fx.gen1_pool_world()
    space = FeasibleActionSpace.build(world)
    port = MindWorldPort(space)
    problem = gen1_problem()
    rows = []
    for i, point in enumerate(initial_design(problem, SEED)):
        proposal = ProposedAction("pool_query", world.revision_id,
                                  {"I_A": Quantity(point["I_A"], "A"), "t_on_s": Quantity(point["t_on_s"], "s")}, (),
                                  GEN1)
        decision = port.propose(proposal)
        alternatives = space.alternatives(proposal, "I_A")
        rows.append({"index": i, "gen1_request": {"I_A": point["I_A"], "t_on_s": point["t_on_s"]},
                     "gen1_role_only": arms.gen1_role_only(world, proposal)["verdict"],
                     "gen2_status": decision.status.value, "gen2_codes": list(decision.codes()),
                     "alternatives_I_A": [o.to_dict() for o in alternatives["options"]],
                     "decision_digest": decision.digest})
    literal = ProposedAction("pool_query", world.revision_id, {"I_A": Quantity(1.15, "A"), "t_on_s": Quantity(55.62, "s")},
                             (), fx.HUMAN)
    lit = port.propose(literal)
    lit_alt = space.alternatives(literal, "I_A")
    statuses = sorted({r["gen2_status"] for r in rows})
    return {
        "schema": SCHEMA, "world_revision": world.revision_id, "space_id": space.space_id, "seed": SEED,
        "gen1_problem_digest": problem.digest,
        "declared_levels_A": [1.0, 2.0],
        "literal_case": {"GEN1_STYLE_PROPOSAL": "I_A = 1.15 A, t_on_s = 55.62 s",
                         "GEN1_ROLE_ONLY": arms.gen1_role_only(world, literal)["verdict"],
                         "GEN2_WORLD_ACTIONSPACE": lit.status.value, "codes": list(lit.codes()),
                         "reason": [r.to_dict() for r in lit.reasons],
                         "feasible_alternatives_I_A": [o.to_dict() for o in lit_alt["options"]],
                         "alternatives_label": lit_alt["label"]},
        "gen1_initial_design": {"requests": len(rows),
                                "gen1_role_only_found_feasible": sum(r["gen1_role_only"] == "FEASIBLE" for r in rows),
                                "gen2_statuses": statuses,
                                "gen2_infeasible_protocol": sum(r["gen2_status"] == "INFEASIBLE_PROTOCOL" for r in rows),
                                "requests_on_a_declared_level": sum(r["gen1_request"]["I_A"] in (1.0, 2.0) for r in rows),
                                "rows": rows},
        "journal_entries": len(port.journal),
    }


def main(argv: list[str]) -> int:
    payload = run()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes((json.dumps(payload, sort_keys=True, indent=1, allow_nan=False) + "\n").encode("utf-8"))
    lit = payload["literal_case"]
    stream = payload["gen1_initial_design"]
    print(f"literal 1.15 A: GEN1_ROLE_ONLY={lit['GEN1_ROLE_ONLY']} GEN2={lit['GEN2_WORLD_ACTIONSPACE']} "
          f"alternatives={[a['magnitude'] for a in lit['feasible_alternatives_I_A']]} A")
    print(f"Gen1 initial design: {stream['requests']} requests, Gen1 found FEASIBLE {stream['gen1_role_only_found_feasible']}, "
          f"Gen2 INFEASIBLE_PROTOCOL {stream['gen2_infeasible_protocol']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
