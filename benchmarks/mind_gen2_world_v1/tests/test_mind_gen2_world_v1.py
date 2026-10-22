"""GEN2-BR1 benchmark integrity: frozen cases, an independent oracle, coverage, reproducible results, real Gen1 code."""

from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys

import pytest

from benchmarks.mind_gen2_world_v1 import arms, cases as C, fixtures as fx, gen1_repro, run_benchmark as rb
from engcore.mind.repsem.roles import VariableRole
from engcore.mind.world import DiscreteLevels, FeasibilityStatus

HERE = pathlib.Path(rb.__file__).resolve().parent


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_bytes().decode("utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out.add(("." * node.level) + (node.module or ""))
    return out


def test_the_frozen_cases_are_what_the_generator_produces_and_pass_their_audit():
    payload = C.load()
    assert C.dump(C.build()) == C.CASES_PATH.read_bytes()
    assert payload["count"] == len(payload["cases"]) and not any(c["audit"] for c in payload["cases"])


def test_the_oracle_never_sees_the_checker_and_the_generator_never_calls_it():
    assert not any("mind.world" in m for m in _imports(HERE / "oracle.py"))
    tree = ast.parse((HERE / "cases.py").read_bytes().decode("utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"FeasibleActionSpace", "check", "clear", "replay_decision", "MindWorldPort", "ExecutionGate"}


def test_the_gen1_arm_runs_the_real_gen1_code():
    imported = _imports(HERE / "arms.py")
    assert {"engcore.mind.minimal.experiments", "engcore.mind.minimal.problem"} <= imported
    w = fx.gen1_pool_world()
    problem, why = arms.gen1_problem(w, "pool_query")
    assert problem is not None and why == "" and [x.name for x in problem.inputs] == ["I_A", "t_on_s"]


def test_the_fixtures_cover_every_role_domain_kind_and_status_in_at_least_two_worlds():
    worlds = {name: build() for name, build in fx.WORLDS.items()}
    for role in VariableRole:
        assert sum(any(v.role is role for v in w.variables) for w in worlds.values()) >= 2, role
    kinds = {}
    for name, w in worlds.items():
        for a in w.actions:
            for c in a.controls:
                kind = "discrete" if isinstance(c.domain, DiscreteLevels) else c.domain.kind.value
                kinds.setdefault(kind, set()).add(name)
    assert {k for k, v in kinds.items() if len(v) >= 2} >= {"discrete", "continuous", "integer", "categorical"}
    statuses = {}
    for case in C.load()["cases"]:
        statuses.setdefault(case["expected"]["status"], set()).add(case["world"])
    assert {s.value for s in FeasibilityStatus} == set(statuses)
    assert all(len(v) >= 2 for v in statuses.values())


def test_the_committed_scores_reproduce():
    stored = json.loads((HERE / "results" / "BENCHMARK.json").read_bytes())
    cases = C.load()["cases"]
    worlds = rb._worlds(cases)
    rows = rb.decisions(cases, worlds)
    assert rb.decisions_digest(rows) == stored["decisions_digest"]
    assert json.loads(json.dumps(rb.score(rows))) == stored["scores"]
    g2 = stored["scores"]["GEN2_WORLD_ACTIONSPACE"]
    assert g2["false_admissions"] == 0 and g2["false_rejections"] == 0 and not g2["misses"]


def test_the_gen1_reproduction_reproduces():
    stored = json.loads((HERE / "results" / "GEN1_REPRODUCTION.json").read_bytes())
    assert json.loads(json.dumps(gen1_repro.run())) == stored
    lit = stored["literal_case"]
    assert (lit["GEN1_ROLE_ONLY"], lit["GEN2_WORLD_ACTIONSPACE"]) == ("ADMIT", "INFEASIBLE_PROTOCOL")
    assert [a["magnitude"] for a in lit["feasible_alternatives_I_A"]] == [1.0, 2.0]


@pytest.mark.parametrize("seed", rb.HASH_SEEDS)
def test_decisions_do_not_depend_on_the_hash_seed(seed):
    stored = json.loads((HERE / "results" / "BENCHMARK.json").read_bytes())
    env = dict(os.environ, PYTHONHASHSEED=seed)
    out = subprocess.run([sys.executable, "-m", "benchmarks.mind_gen2_world_v1.run_benchmark", "--decisions-digest"],
                         capture_output=True, text=True, env=env, check=True, cwd=str(HERE.parents[1]))
    assert out.stdout.strip().splitlines()[-1] == stored["decisions_digest"]
