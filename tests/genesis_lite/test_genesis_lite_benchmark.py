"""Genesis-lite v0 (BR-16): adversarial benchmark tests F1-F8, freezing and evaluator independence.

Every unsafe or invalid case must fail CLOSED with an explicit status (INVALID_BENCHMARK, EVALUATOR_DISAGREEMENT,
refused); every valid case must still run (positive controls).
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

import pytest

from benchmarks.genesis_lite import arms, evaluator, harness, preregistration
from benchmarks.genesis_lite.answer_key import export_answer_key
from benchmarks.genesis_lite.presentation import PRESENTATIONS, PresentationRefused, present
from engcore.blindfold import EvaluatorConfig
from engcore.blindfold.roles import DEFAULT_CREDIT

ROOT = pathlib.Path(__file__).resolve().parents[2]
MASTER = bytes(range(32))


def _run(arm: str, presentation: str = "anonymous", i: int = 0, **kw):
    return harness.run_one(arm, arms.ARMS[arm][0], master_seed=MASTER + bytes([i]), campaign_id=f"gl-test-{i}",
                           presentation=presentation, **kw)


def _outcome(rec, kind: str) -> dict:
    (u,) = [u for u in rec.universes if u["kind"] == kind]
    return u


# ---- positive control -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("presentation", PRESENTATIONS)
def test_positive_control_every_presentation_runs_valid_and_the_independent_grade_agrees(presentation):
    rec = _run("careful", presentation)
    assert rec.status == "VALID", rec.reasons
    assert rec.evaluator_status == "VALID" and rec.leakage_audit == "NO_LITERAL_LEAK_FOUND"
    assert sorted(u["kind"] for u in rec.universes) == sorted(harness.KINDS)
    assert all(u["independent_agrees"] for u in rec.universes)
    assert rec.security_boundary == "SECURITY_BOUNDARY_NOT_PROVEN"


# ---- F1: the correct answer is hidden -------------------------------------------------------------------------------
def test_f1_the_correct_answer_never_reaches_a_proposer_and_the_key_exists_only_after_sealing(monkeypatch):
    seen, events = [], []

    def spy(card, client, *, seed=0):
        seen.append(json.dumps(card, sort_keys=True))
        events.append("propose")
        return {"universe_id": card["universe_id"], "answer": "no_law"}

    real = harness.export_answer_key

    def export(*a, **k):
        events.append("export")
        return real(*a, **k)

    monkeypatch.setattr(harness, "export_answer_key", export)
    monkeypatch.setitem(arms.ARMS, "spy", (spy, "test spy", False, "floor"))
    for p in PRESENTATIONS:
        rec = _run("spy", p)
        assert rec.status == "VALID", rec.reasons
    chunks = "|".join(events).split("export")
    assert all(chunk.strip("|").split("|") == ["propose"] * len(harness.KINDS) for chunk in chunks[:-1])  # key after all seals
    assert len(chunks) == len(PRESENTATIONS) + 1 and chunks[-1] == ""
    for text in seen:
        card = json.loads(text)
        assert set(card) <= evaluator.score.CARD_KEYS
        shown = json.dumps({k: v for k, v in card.items() if k != "answers"}, sort_keys=True)
        for word in ("tolerance", "evaluation", "noise", "seed", "alternative", '"law"', "kind", "sigma"):
            assert word not in shown, word


# ---- F2: the historical answer is wrong ---------------------------------------------------------------------------
def test_f2_the_textbook_answer_fails_in_every_trap_world_and_each_trap_is_verified():
    for i in range(5):
        rec = _run("historical_answer", "trap", i)
        assert rec.status == "VALID", rec.reasons           # VALID includes: the textbook law cannot pass this world
        trap = _outcome(rec, "discoverable")
        assert trap["trap"] and trap["outcome"] == "law_fail" and trap["credit"] < 0
    anon = _run("historical_answer", "anonymous")
    assert all(u["answer"] == "insufficient_evidence" for u in anon.universes)   # no familiar vocabulary, no answer


def test_f2_a_trap_whose_textbook_law_would_pass_is_invalid_not_credited(monkeypatch):
    monkeypatch.setattr(harness, "_textbook_could_pass", lambda law, entry: True)
    rec = _run("careful", "trap")
    assert rec.status == "INVALID_BENCHMARK" and any("trap" in r for r in rec.reasons)


# ---- F3: the data are insufficient ----------------------------------------------------------------------------------
def test_f3_a_law_on_insufficient_evidence_earns_nothing_and_a_wrong_law_is_penalised():
    always = _outcome(_run("always_law"), "insufficient_evidence")
    assert always["answer"] == "law" and always["credit"] <= 0
    assert DEFAULT_CREDIT["insufficient_evidence"]["law_pass"] == 0.0 and DEFAULT_CREDIT["insufficient_evidence"]["law_fail"] < 0
    careful = _outcome(_run("careful"), "insufficient_evidence")
    assert careful["answer"] != "law"


# ---- F4: two mechanisms observationally indistinguishable -----------------------------------------------------------
def test_f4_naming_one_of_two_indistinguishable_laws_earns_no_credit_and_the_pair_does():
    rec = _run("careful")
    key = export_answer_key(MASTER + bytes([0]), "gl-test-0", harness.MIX, [u["universe_id"] for u in rec.universes])
    (entry,) = [e for e in key["universes"] if e["kind"] == "indistinguishable"]
    one = evaluator.score_universe({"answer": "law", "law": entry["law"]}, entry)
    pair = evaluator.score_universe({"answer": "indistinguishable", "laws": [entry["law"], entry["alternative_law"]]}, entry)
    assert one["outcome"] == "law_pass" and one["credit"] == 0.0      # right in the box, but it extrapolated blindly
    assert pair["outcome"] == "indistinguishable_hit" and pair["credit"] == 1.0


# ---- F5: an irrelevant correlate predicts the training examples -----------------------------------------------------
def test_f5_a_law_that_uses_the_spurious_correlate_fails_where_it_is_decoupled():
    rec = _run("always_law")
    spur = _outcome(rec, "spurious_correlate")
    assert spur["answer"] == "law" and spur["outcome"] == "law_fail"
    key = export_answer_key(MASTER + bytes([0]), "gl-test-0", harness.MIX, [u["universe_id"] for u in rec.universes])
    (entry,) = [e for e in key["universes"] if e["kind"] == "spurious_correlate"]
    assert evaluator.score_universe({"answer": "law", "law": entry["law"]}, entry)["outcome"] == "law_pass"  # truth passes


# ---- F6: an evaluator leak is deliberately injected -----------------------------------------------------------------
def test_f6_a_leaked_card_field_is_refused_before_the_proposer_sees_it():
    rec = _run("careful", card_hook=lambda card: {**card, "kind_hint": "spurious"})
    assert rec.status == "INVALID_BENCHMARK" and any("presentation refused" in r for r in rec.reasons)


def test_f6_a_hidden_number_smuggled_into_an_allowed_field_fails_the_post_reveal_audit():
    key = export_answer_key(MASTER + bytes([0]), "gl-test-0", harness.MIX,
                            [u["universe_id"] for u in _run("always_refuse").universes])
    tols = " ".join(repr(e["tolerance"]) for e in key["universes"])     # smuggled inside a free-text field
    rec = _run("careful", card_hook=lambda card: {**card, "task_text": card["task_text"] + " ref " + tols})
    assert rec.status == "INVALID_BENCHMARK" and rec.leakage_audit == "LITERAL_LEAK_FOUND"


def test_f6_a_crash_while_presenting_is_the_benchmarks_failure_not_the_proposers():
    rec = _run("careful", card_hook=lambda card: card["no_such_field"])
    assert rec.status == "INVALID_BENCHMARK" and any("presentation failed" in r for r in rec.reasons)


def test_f6_an_evaluator_disagreement_invalidates_the_run(monkeypatch):
    real = evaluator.score.score_universe

    def flipped(proposal, entry, **kw):
        out = real(proposal, entry, **kw)
        return {**out, "outcome": "law_pass" if out["outcome"] != "law_pass" else "law_fail"}

    monkeypatch.setattr(evaluator.score, "score_universe", flipped)
    rec = _run("careful")
    assert rec.status == "INVALID_BENCHMARK" and rec.evaluator_status == "EVALUATOR_DISAGREEMENT"


# ---- F7: a baseline and the future Mind receive the same information and budget ------------------------------------
def test_f7_every_arm_sees_the_same_cards_and_the_escrow_caps_every_arm_at_the_same_budget(monkeypatch):
    cards: dict[str, list[str]] = {}
    calls: dict[str, int] = {}

    def make(name, greedy):
        def arm(card, client, *, seed=0):
            cards.setdefault(name, []).append(json.dumps(card, sort_keys=True))
            pt = {x["name"]: x["range"][0] for x in card["inputs"]}
            for q in range(int(card["query_budget"]) + (5 if greedy else 0)):
                try:
                    client.observe(card["universe_id"], pt, query_id=f"{name}{q}")
                    calls[name] = calls.get(name, 0) + 1
                except Exception:  # noqa: BLE001 - the escrow refuses past the budget
                    break
            return {"universe_id": card["universe_id"], "answer": "no_law"}
        return arm

    monkeypatch.setitem(arms.ARMS, "baseline_like", (make("baseline_like", False), "t", False, "floor"))
    monkeypatch.setitem(arms.ARMS, "mind_like", (make("mind_like", True), "t", False, "floor"))
    a, b = _run("baseline_like", "anonymous"), _run("mind_like", "anonymous")
    assert a.status == b.status == "VALID"
    strip = lambda texts: [{k: v for k, v in json.loads(x).items() if k != "universe_id"} for x in texts]  # noqa: E731
    assert strip(cards["baseline_like"]) == strip(cards["mind_like"])      # identical except the run-private pseudonym
    assert calls["baseline_like"] == calls["mind_like"] == a.observe_calls == b.observe_calls   # the extra 5 were refused


# ---- F8: a scoring configuration changes after freezing -------------------------------------------------------------
def test_f8_a_changed_evaluator_config_invalidates_the_run_before_anything_is_scored():
    changed = {k: dict(v) for k, v in DEFAULT_CREDIT.items()}
    changed["no_solution"]["no_law"] = 5.0
    rec = _run("careful", config=EvaluatorConfig("forge.genesis_lite.v0", "1", credit=changed))
    assert rec.status == "INVALID_BENCHMARK" and not rec.universes


def test_f8_the_independent_evaluator_refuses_a_table_it_was_not_preregistered_with():
    with pytest.raises(evaluator.EvaluatorRefused):
        evaluator.evaluate_campaign({}, {"universes": []}, {}, expected_credit_digest="0" * 64)


def test_v0_evidence_is_preserved_byte_for_byte():
    """v0.1 is a new identity; the v0 preregistration and its pilot stay exactly as they were frozen."""
    import hashlib
    v0 = preregistration.V0_PREREG_PATH.read_bytes()
    assert hashlib.sha256(v0).hexdigest() == preregistration.V0_PREREG_SHA256
    assert preregistration.V0_PREREG_PATH.with_suffix(".sha256").read_bytes().strip().decode() == preregistration.V0_PREREG_SHA256
    pilot = json.loads((ROOT / "benchmarks/genesis_lite/pilot_results/v0-2026-10-14/summary.json").read_bytes())
    assert pilot["prereg_sha256"] == preregistration.V0_PREREG_SHA256
    doc = json.loads(preregistration.PREREG_PATH.read_bytes())
    assert doc["amends"]["preregistration_sha256"] == preregistration.V0_PREREG_SHA256
    assert doc["benchmark_id"] != json.loads(v0)["benchmark_id"]


def test_f8_the_committed_preregistration_is_exactly_what_the_code_rebuilds():
    committed = preregistration.PREREG_PATH.read_bytes()
    doc = json.loads(committed)
    assert preregistration.canonical(preregistration.build(doc["pilot_root_commitment_sha256"])) == committed
    assert preregistration.PREREG_PATH.with_suffix(".sha256").read_bytes().strip().decode() == preregistration.digest(doc)
    changed = {k: dict(v) for k, v in evaluator.CREDIT.items()}
    changed["confounded"]["law_pass"] = 0.0
    assert evaluator.credit_digest(changed) != doc["evaluator"]["credit_digest"]


# ---- evaluator independence and baseline honesty ---------------------------------------------------------------------
def test_the_independent_evaluator_imports_nothing_but_the_standard_library():
    stdlib = set(sys.stdlib_module_names)
    for path in sorted((ROOT / "benchmarks" / "genesis_lite" / "evaluator").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in stdlib for a in node.names), (path.name, ast.dump(node))
            elif isinstance(node, ast.ImportFrom) and not node.level:
                assert node.module.split(".")[0] in stdlib, (path.name, node.module)
    probe = ("import sys; sys.path[:0] = [sys.argv[1]]; import benchmarks.genesis_lite.evaluator as e; "
             "print(sorted(m for m in sys.modules if m.split('.')[0] == 'engcore'))")
    out = subprocess.run([sys.executable, "-I", "-c", probe, str(ROOT)], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"


def test_the_credit_tables_of_escrow_and_independent_evaluator_are_the_same_preregistered_table():
    assert evaluator.credit_digest(DEFAULT_CREDIT) == evaluator.CREDIT_DIGEST


def test_unavailable_baselines_are_reported_never_substituted():
    status = arms.availability()
    assert set(status) == set(arms.UNAVAILABLE_ARMS)
    assert all(s["status"] in ("NOT_AVAILABLE", "NOT_INTEGRATED", "NOT_APPLICABLE_IN_V0") for s in status.values())
    assert not set(arms.UNAVAILABLE_ARMS) & set(arms.ARMS)


def test_structure_search_arms_share_one_gate_and_differ_only_in_search():
    src = (ROOT / "benchmarks" / "genesis_lite" / "arms.py").read_text(encoding="utf-8")
    for name in ("monomial_enumeration", "random_structures", "greedy_forward", "space_filling", "extrapolating_fit"):
        body = src.split(f"def {name}(", 1)[1].split("\ndef ", 1)[0]
        assert "return _clean(_gate(card, rows, replicate," in body, name
    assert "_cv_mse(train" in src and "_hold_mse" not in src        # selection never touches the judging hold-out


# ---- review H1: runs over the same world cannot be linked by id or names ---------------------------------------------
def test_h1_two_runs_over_the_same_world_share_no_identifier_or_variable_name(monkeypatch):
    ids: dict[str, set] = {}
    names: dict[str, set] = {}

    def remember(tag):
        def arm(card, client, *, seed=0):
            ids.setdefault(tag, set()).add(card["universe_id"])
            names.setdefault(tag, set()).update(x["name"] for x in card["inputs"])
            return {"universe_id": card["universe_id"], "answer": "no_law"}
        return arm

    for tag, presentation, seed in (("r0", "renamed", 0), ("r1", "renamed", 1), ("p0", "paraphrased", 0), ("a0", "anonymous", 0)):
        monkeypatch.setitem(arms.ARMS, tag, (remember(tag), "t", False, "floor"))
        assert _run(tag, presentation, seed=seed).status == "VALID"
    tags = sorted(ids)
    for i, x in enumerate(tags):
        for y in tags[i + 1:]:
            assert not ids[x] & ids[y], (x, y)                    # a stateful proposer cannot merge runs by id
    assert names["r0"] != names["r1"]                                # renamed per run (token overlap by chance is possible)


# ---- review M3: golden scoring and the per-law fraction cross-check ------------------------------------------------
def _entry(kind="discoverable", law=None):
    pts = [({"x": x}, 2.0 * x) for x in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0)]
    return {"universe_id": "u", "kind": kind, "tolerance": 0.05, "noise_sigma": 0.01, "box": {"x": [1.0, 5.0]},
            "variables": ["x"], "evaluation": pts, "inbox": pts[:5], "law": law}


def test_m3_golden_cases_hand_computed():
    lin = {"mul": [{"const": 2.0}, {"var": "x"}]}
    assert evaluator.score_universe({"answer": "law", "law": lin}, _entry())["outcome"] == "law_pass"
    off = {"mul": [{"const": 2.2}, {"var": "x"}]}                              # 10% off everywhere: 0/10 within 5%
    r = evaluator.score_universe({"answer": "law", "law": off}, _entry())
    assert r["outcome"] == "law_fail" and r["fractions"] == [0.0] and r["credit"] == -1.0
    nine = {"piecewise": {"if_below": [{"var": "x"}, {"const": 9.5}], "then": lin, "else": off}}   # 9/10 within: passes
    assert evaluator.score_universe({"answer": "law", "law": nine}, _entry())["fractions"] == [0.9]
    eight = {"piecewise": {"if_below": [{"var": "x"}, {"const": 8.5}], "then": lin, "else": off}}  # 8/10: fails
    assert evaluator.score_universe({"answer": "law", "law": eight}, _entry())["outcome"] == "law_fail"
    rival = {"mul": [lin, {"add": [{"const": 1.0}, {"mul": [{"const": 0.01 / 5.0 ** 4}, {"pow": [{"var": "x"}, {"const": 4.0}]}]}]}]}
    hit = evaluator.score_universe({"answer": "indistinguishable", "laws": [lin, rival]}, _entry("indistinguishable"))
    assert hit["outcome"] == "indistinguishable_hit" and hit["credit"] == 1.0
    assert evaluator.score_universe({"answer": "no_law"}, _entry("no_solution"))["credit"] == 1.0


def test_m3_a_fraction_that_disagrees_with_the_escrow_invalidates_the_run(monkeypatch):
    real = evaluator.score.fraction_within
    monkeypatch.setattr(evaluator.score, "fraction_within", lambda law, truths, tol: min(1.0, real(law, truths, tol) + 1e-6))
    rec = _run("always_law")
    assert rec.status == "INVALID_BENCHMARK" and rec.evaluator_status == "EVALUATOR_DISAGREEMENT"


# ---- review M4: a crash is a recorded invalid run --------------------------------------------------------------------
def test_m4_an_exception_after_sealing_is_a_recorded_invalid_run(monkeypatch):
    def boom(*a, **k):
        raise evaluator.EvaluatorRefused("simulated evaluator failure")
    monkeypatch.setattr(harness.independent, "evaluate_campaign", boom)
    rec = _run("careful")
    assert rec.status == "INVALID_BENCHMARK" and any("run aborted" in r for r in rec.reasons)


# ---- review M1: the pilot refuses to run under a preregistration the code no longer rebuilds -----------------------
def test_m1_the_pilot_refuses_a_stale_preregistration(monkeypatch, tmp_path):
    from benchmarks.genesis_lite import pilot
    assert pilot.prereg_matches_code()[0]
    monkeypatch.setattr(arms, "OCCAM_SLACK", 0.5)                            # a tuned arm is a new benchmark identity
    assert not pilot.prereg_matches_code()[0]
    assert pilot.main(["--root-file", str(tmp_path / "nope"), "--out", str(tmp_path / "o")]) == 2


# ---- review H5: the world is the unit --------------------------------------------------------------------------------
def test_h5_seeds_over_one_world_are_one_unit_not_many():
    from benchmarks.genesis_lite import pilot
    recs = []
    for seed in range(5):
        r = harness.RunRecord("monomial_enumeration", seed, f"campaign-{seed}", "anonymous")   # campaign ids differ
        r.isolation = "proposer_process"
        r.universes = [{"kind": k, "credit": 1.0, "truth_in_searched_family": True, "region_tell": "box",
                        "universe_id": f"u-{k}", "outcome": "law_pass"} for k in harness.KINDS]
        recs.append(r)
    cell = pilot.summarize(recs)["cells"]["monomial_enumeration|discoverable|anonymous"]
    assert cell["worlds"] == 1 and cell["runs"] == 5


# ---- review M2 / H2 / H3 / L1 -----------------------------------------------------------------------------------------
def test_m2_the_region_tell_is_measured_from_the_card():
    card = {"inputs": [{"name": "a", "range": [1.0, 10.0]}], "assessment_region": {"a": [1.0, 10.0]}}
    assert evaluator.region_tell(card) == "box"
    assert evaluator.region_tell({**card, "assessment_region": {"a": [10 ** 1.4, 10 ** 2.2]}}) == "ordinary_extension"
    assert evaluator.region_tell({**card, "assessment_region": {"a": [10 ** 1.6, 10 ** 2.6]}}) == "pushed_extension"


def test_h2_the_searched_family_flag_matches_the_law_form():
    mono = {"mul": [{"const": 2.0}, {"pow": [{"var": "a"}, {"const": 0.37}]}]}
    assert evaluator.in_monomial_family(mono)
    assert not evaluator.in_monomial_family({"mul": [mono, {"exp": {"var": "a"}}]})
    assert not evaluator.in_monomial_family({"add": [mono, mono]})
    assert not evaluator.in_monomial_family(None)


def test_h3_the_pair_arm_answers_indistinguishable_with_an_admissible_pair_somewhere():
    answers = set()
    for i in range(6):
        rec = _run("extrapolation_pair", "anonymous", i)
        assert rec.status == "VALID", rec.reasons
        answers |= {u["answer"] for u in rec.universes}
    assert "indistinguishable" in answers


def test_l1_traps_are_verified_in_every_kind_where_a_law_earns_credit(monkeypatch):
    seen = []
    monkeypatch.setattr(harness, "_textbook_could_pass", lambda law, entry: seen.append(entry["kind"]) or False)
    assert _run("careful", "trap").status == "VALID"
    assert set(seen) == set(harness.LAW_CREDIT_KINDS) == {"discoverable", "spurious_correlate", "confounded"}


def test_presentation_rejects_an_unknown_variant():
    with pytest.raises(PresentationRefused):
        present({"universe_id": "x"}, "leaky", b"k")


def test_the_region_tell_and_the_family_flag_hold_on_generated_worlds_of_every_kind():
    """Confirmation review: checked on the generator's own worlds, not only on synthetic cards."""
    from engcore.blindfold.universe import UniverseKind, generate_universe
    pushed_kinds, box_kinds = set(), set()
    for i in range(30):
        for kind in UniverseKind:
            world = generate_universe(f"tell-{i}", kind)
            tell = evaluator.region_tell(world.public_card())
            if tell == "pushed_extension":
                pushed_kinds.add(kind.value)
            elif tell == "box":
                box_kinds.add(kind.value)
            if world.law is not None:
                text = json.dumps(world.law)
                outside = any(f'"{op}"' in text for op in ("exp", "add", "piecewise"))
                assert evaluator.in_monomial_family(world.law) is (not outside), (kind, text[:80])
    assert pushed_kinds <= {"indistinguishable"}
    assert "indistinguishable" not in box_kinds
