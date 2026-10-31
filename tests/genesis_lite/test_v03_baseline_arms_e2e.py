"""Each v0.3 development baseline arm runs a full v0.3 campaign: the run is VALID, the independent evaluator agrees, and
every answer is one the escrow scored (expensive tier: PySR starts Julia and fits per universe)."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("name,module", [("pysindy_stlsq", "pysindy"), ("bo_botorch_variance", "botorch"),
                                         ("pysr_symbolic", "pysr")])
def test_a_baseline_arm_runs_a_valid_v0_3_campaign(name, module):
    pytest.importorskip(module)
    from benchmarks.genesis_lite.arms_v3 import ARMS_V3
    from benchmarks.genesis_lite.harness import code_identity
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    rec = run_one_v3(name, ARMS_V3[name][0], master_seed=(11).to_bytes(4, "big") * 8, campaign_id=f"gl-v03-{name}",
                     presentation="anonymous")
    assert rec.status == "VALID", rec.reasons
    assert rec.evaluator_status == "VALID" and all(u["independent_agrees"] for u in rec.universes)
    assert len(rec.universes) == 6 and all(u["answer"] for u in rec.universes)
    assert code_identity()[1] == []
    assert not any("fallback" in u["rationale"] or "failed" in u["rationale"] for u in rec.universes), \
        [u["rationale"] for u in rec.universes]
