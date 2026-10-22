"""GEN2-BR1.1 benchmark integrity: the committed authority matrix and the BR1 re-score reproduce, and say what they say."""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from benchmarks.mind_gen2_authority_v1 import rescore
from benchmarks.mind_gen2_authority_v1 import run_benchmark as rb

HERE = pathlib.Path(rb.__file__).resolve().parent


def test_the_authority_matrix_reproduces():
    assert rb._dump(rb.matrix()) == rb.AUTHORITY_PATH.read_bytes()


def test_the_br1_rescore_reproduces():
    assert rescore.dump(rescore.build()) == rescore.PATH.read_bytes()


def test_nothing_unverified_is_ever_admitted_and_every_admission_replays():
    s = json.loads(rb.AUTHORITY_PATH.read_bytes())["summary"]
    assert s["mutations_admitted"] == 0 and s["mutations_total"] >= 100
    assert s["owner_changes_admitted"] == 0 and s["owner_changes_total"] >= 25
    assert s["replay_reproduced"] == s["replay_total"] == s["base_total"]
    refused = [x for w in json.loads(rb.AUTHORITY_PATH.read_bytes())["worlds"].values() for x in w["base"].values()
               if not x["admitted"]]
    assert len(refused) == len(s["base_not_admitted"]) and all(x["status"] == "MISSING_INFORMATION" for x in refused)
    assert {c for x in refused for c in x["codes"]} <= {           # only what reads a current value is refused
        "PRECONDITION_ENCLOSURE_REQUIRED", "STATE_DOMAIN_ENCLOSURE_REQUIRED", "APPLICABILITY_INPUT_NOT_EXACT"}


def test_the_br1_rescore_never_moves_toward_feasible_and_gains_only_the_br1_1_codes():
    r = json.loads(rescore.PATH.read_bytes())
    assert r["moved_to_feasible"] == 0 and set(r["new_codes"]) <= set(r["allowed_new_codes"])
    assert r["changed"] == len(r["changes"]) == r["status_changed"] + r["codes_only_changed"]


def test_the_gen1_failure_class_stays_refused_with_declared_alternatives():
    g = json.loads(rb.AUTHORITY_PATH.read_bytes())["gen1_failure_class"]
    assert g["status"] == "INFEASIBLE_PROTOCOL" and "LEVEL_NOT_DECLARED" in g["codes"] and not g["admitted"]
    assert [a["magnitude"] for a in g["alternatives_I_A"]] == [1.0, 2.0]
    assert g["label"] == "admissible options under the declared world, not recommendations"


def test_every_world_is_verified_and_bound():
    worlds = json.loads(rb.AUTHORITY_PATH.read_bytes())["worlds"]
    assert set(worlds) == set(rb.NAMES)
    assert all(w["verified"] and w["bindings"] >= 2 for w in worlds.values())


# ---- R2-F7: the exported BR1 decisions are re-derived from BR1's own code, not only matched by digest ------------------
@pytest.mark.expensive
def test_br1_decisions_are_rederived_from_the_br1_commit(tmp_path):
    """``BR1_DECISIONS.json`` carries BR1's ``decisions_digest`` (over the full records), which its status/codes map
    cannot be re-hashed to.  So the map itself is re-derived: BR1's code at the BR1 commit, on its frozen cases."""
    from benchmarks.mind_gen2_authority_v1 import br1_decisions
    root = pathlib.Path(__file__).resolve().parents[3]
    probe = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{br1_decisions.BR1_COMMIT}^{{commit}}"],
                           capture_output=True)
    if probe.returncode != 0:
        pytest.skip("the BR1 commit is not in this clone")
    checkout = tmp_path / "br1"            # a throwaway clone: the repository under test is only read, never changed
    subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(root), str(checkout)],
                   capture_output=True, check=True)
    subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", br1_decisions.BR1_COMMIT],
                   capture_output=True, check=True)
    exported = br1_decisions.export(checkout)
    committed = json.loads(br1_decisions.PATH.read_bytes())
    assert exported["decisions_digest"] == committed["decisions_digest"]
    assert exported["decisions"] == committed["decisions"]
