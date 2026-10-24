"""battery_rediscovery_v1 pins: v0 identity, scanner semantics, mutation power, provenance, representability, rule."""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil

import pytest

from benchmarks.battery_rediscovery_v1 import freeze, leakage as lk, mutation
from benchmarks.battery_rediscovery_v1.candidate.common import (
    NOT_ASSESSABLE, NOT_SUPPORTED, REFUSED, REVIEW, SUPPORTED, load_pack,
)
from benchmarks.battery_rediscovery_v1.evaluator import conclusion as cr
from benchmarks.battery_rediscovery_v1.evaluator import representability as rp

HERE = pathlib.Path(__file__).resolve().parents[1]
V0 = HERE.parent / "battery_rediscovery_v0"
C1 = [lk.protected("C1", "760", "F")]


def test_copied_files_are_byte_identical_to_v0_frozen_files():
    v0 = json.loads((V0 / "PLAN.json").read_bytes())["frozen_files"]
    for f in freeze.COPIED_FROM_V0:
        assert hashlib.sha256((HERE / f).read_bytes()).hexdigest() == v0[f"benchmarks/battery_rediscovery_v0/{f}"], f


def test_v0_history_records_the_three_readings():
    h = json.loads((HERE / "V0_HISTORY.json").read_bytes())
    assert (h["PREREGISTERED_RESULT"], h["POST_SEAL_AMENDMENT_RESULT"], h["CONFIRMED_RESULT"]) == (
        "LEAKAGE_INVALIDATED", "REPRESENTATION_BOTTLENECK", "NONE")
    for group in h["files"].values():
        for f, sha in group.items():
            assert hashlib.sha256((V0 / f).read_bytes()).hexdigest() == sha, f


@pytest.mark.parametrize("text", ["760", "760.0", "+760", "-760", "7.60e2", "7.6E+02", "760 F", "760F", "C1=760",
                                  '"C1_F": 760', "the historical C1 was 760 F", "0.76 kF", "760000 mF", "760.000"])
def test_scanner_detects_every_form_of_the_protected_value(text):
    assert lk.numeric_hits(text, C1), text


@pytest.mark.parametrize("text", ["760.006", "1760", "76001", "2760.0", "a760b", "x_760_y", "760006", "760.7",
                                  "sha 7f53760ab", "B0760", "760abc"])
def test_scanner_ignores_longer_numbers_and_identifiers(text):
    assert not lk.numeric_hits(text, C1), text


def test_scanner_compares_long_transcriptions_and_short_writings_by_value():
    v = [lk.protected("tau", "171.58884102278594", "s"), lk.protected("rmse", "8.40160566720805", "mV"),
         lk.protected("R0", "0.02065143453238383", "ohm")]
    for text in ("171.589", "171.6 s", "172", "8.4 mV", "8.40", "0.00840 V", "20.7 mohm", "0.0207", "0.020651"):
        assert lk.numeric_hits(text, v), text
    for text in ("171.590", "8.41", "0.0208", "20.8 mohm", "0.020652"):
        assert not lk.numeric_hits(text, v), text


def test_frozen_pre_run_mutation_report_passes_and_binds_the_scanner():
    rep = json.loads((HERE / "MUTATION_REPORT_pre_run.json").read_bytes())
    assert rep["status"] == "PASS" and rep["leaks_caught"] == rep["leak_mutations"] > 400
    assert rep["benign_triggered"] == 0 and rep["benign_controls"] > 200 and rep["unmutated_carriers_clean"]
    assert rep["scanner_sha256"] == hashlib.sha256((HERE / "leakage.py").read_bytes()).hexdigest()
    kinds = {c["kind"] for c in rep["cases"] if c["expected"] == "DETECT"}
    assert {"integer_or_reported", "decimal_equivalent", "scientific", "value_plus_unit", "prose_label", "result_label",
            "text_token", "measurement_array"} <= kinds


def test_mutation_suite_has_power_on_synthetic_values():
    rep = mutation.run(list(mutation.SYNTHETIC[:2]), "test")
    assert rep["status"] == "PASS", rep["failures"][:3]


def test_provenance_flags_an_altered_measurement_and_passes_the_frozen_pack(tmp_path):
    assert lk.provenance_findings() == []
    d = tmp_path / "pack"
    shutil.copytree(HERE / "candidate" / "pack", d)
    prob = json.loads((d / "P2.json").read_bytes())
    prob["sets"]["calibration"]["trajectories"][0]["t_s"][5] = 760.0
    (d / "P2.json").write_bytes((json.dumps(prob, sort_keys=True, indent=1) + "\n").encode())
    assert lk.provenance_findings(d)


def test_candidate_tree_is_clean_for_the_pre_run_protected_values():
    rep = lk.audit(list(mutation.SYNTHETIC) + mutation.historical_values(), phase="test")
    assert rep["status"] == "PASS", (rep["numeric"][:2], rep["text"], rep["pack_schema"], rep["provenance"])


def test_representability_classification_uses_reachable_sets_not_answers():
    exact = {"reachable": [NOT_ASSESSABLE], "semantics": rp.EXACT}
    proxy = {"reachable": [SUPPORTED, NOT_SUPPORTED, NOT_ASSESSABLE, REFUSED], "semantics": rp.PROXY}
    none = {"reachable": [NOT_ASSESSABLE], "semantics": rp.NONE}
    only_refuse = {"reachable": [REFUSED], "semantics": rp.PROXY}
    assert rp.classify(NOT_ASSESSABLE, exact) == "REPRESENTABLE_EXACTLY"
    assert rp.classify(NOT_SUPPORTED, proxy) == "REPRESENTABLE_APPROXIMATELY"
    assert rp.classify(NOT_SUPPORTED, none) == "NOT_REPRESENTABLE"
    assert rp.classify(NOT_ASSESSABLE, none) == "REPRESENTABLE_APPROXIMATELY"
    assert rp.classify(NOT_SUPPORTED, only_refuse) == "NOT_REPRESENTABLE"
    assert rp.classify(NOT_ASSESSABLE, only_refuse) == "REPRESENTABLE_APPROXIMATELY"
    assert rp.classify(SUPPORTED, {"reachable": None, "semantics": None}) == "UNKNOWN"
    assert rp.classify(None, proxy) is None


def test_frozen_reachable_sets_equal_a_recomputation_from_the_pack():
    plan = json.loads((HERE / "PLAN.json").read_bytes())
    again = json.loads(json.dumps({pid: rp.reachable(p) for pid, p in load_pack(HERE / "candidate" / "pack").items()}))
    assert plan["representability"]["reachable"] == again


def _inst(spec: list[tuple[str, str, str]]) -> dict:
    return {f"i{k}": {"class": c, "mind_outcome": m, "careful_outcome": o} for k, (c, m, o) in enumerate(spec)}


R, N, E = "REPRESENTABLE_APPROXIMATELY", "NOT_REPRESENTABLE", "REPRESENTABLE_EXACTLY"
OK, BAD = "CORRECT", "FALSE_REFUSE"


def _concl(spec, **kw):
    base = dict(leakage_ok=True, end_to_end=True, replay_ok=True, careful_total=8, trivial_best=2)
    base.update(kw)
    return cr.conclude(a=cr.analyse(_inst(spec)), **base)["conclusion"]


def test_conclusion_rule_order_and_thresholds():
    confirmed = [(R, OK, OK)] * 3 + [(N, BAD, OK)] * 4 + [(R, BAD, OK)]
    assert _concl(confirmed) == "REPRESENTATION_BOTTLENECK_CONFIRMED"
    poor_on_r = [(R, OK, OK)] + [(R, BAD, OK)] * 3 + [(N, BAD, OK)] * 4
    assert _concl(poor_on_r) == "REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY"
    mostly_r = [(R, BAD, OK)] * 6 + [(N, BAD, OK)] + [(N, OK, OK)] * 2
    assert _concl(mostly_r) == "REPRESENTATION_BOTTLENECK_NOT_CONFIRMED"
    no_fail = [(R, OK, OK)] * 3 + [(N, OK, OK)] * 3
    assert _concl(no_fail) == "REPRESENTATION_BOTTLENECK_NOT_CONFIRMED"
    assert _concl(confirmed, trivial_best=8) == "BENCHMARK_NOT_DISCRIMINATING"
    assert _concl(confirmed, replay_ok=False) == "INCONCLUSIVE"
    assert _concl([(R, OK, OK)] * 2 + [(N, BAD, OK)] * 4) == "INCONCLUSIVE"
    assert _concl(confirmed + [("UNKNOWN", BAD, OK)]) == "INCONCLUSIVE"
    assert _concl(confirmed, leakage_ok=False) == "LEAKAGE_INVALIDATED"


def test_v1_has_no_amendment_mechanism():
    for p in [HERE / "evaluator" / "run_evaluation.py", HERE / "seal.py", HERE / "launch.py", HERE / "freeze.py"]:
        text = p.read_bytes().decode()
        assert "--amend" not in text and "amendment:" not in text and "amendment=" not in text, p.name


def test_plan_is_frozen_and_pins_every_file():
    raw = (HERE / "PLAN.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (HERE / "PLAN.sha256").read_bytes().split()[0].decode()
    plan = json.loads(raw)
    assert plan["frozen_files"] == freeze.frozen_digests()
    assert plan["leakage"]["scanner_sha256"] == hashlib.sha256((HERE / "leakage.py").read_bytes()).hexdigest()
    assert plan["amendments"].startswith("none permitted")
