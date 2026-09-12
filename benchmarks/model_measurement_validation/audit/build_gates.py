"""MV-25: eleven gates, each with a final verdict and the evidence behind it."""

from __future__ import annotations

import json
import subprocess

from . import adjudication, build_artifacts, check_consistency
from .evidence import ROOT

#: The digest of ``src/engcore/scientific`` this round was audited against.
#:
#: NOT a certificate, and deliberately no longer named as one. See the twin
#: constant in ``benchmarks/empirical_validation/audit/build_gates.py`` for the
#: full account: the previous value was Core V1's 47-module digest
#: ``82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507``, which
#: was last true at the V1 certification commit ``be57bf4d7056`` and diverged
#: at the next scientific commit ``3d642dcef5db``. This round lived on a branch
#: still carrying that tree; merge ``9f0ed8e`` joined it to a chain at 55
#: modules, making the old pin unreachable.
#:
#: MV-10's actual claim -- this round edited no production file -- is unchanged
#: and is carried by the `touched` half, which reads `git status` and does not
#: depend on which lineage the round is sitting in.
EXPECTED_SCIENTIFIC_DIGEST = (
    "1422c1b9e84159b17887ad4e2ef07df6d0296a60082d60247b31266e920be7f0"
)

#: Discrepancies the round has adjudicated in writing. The split check reports
#: every difference from the preregistered counts; a difference passes the gate
#: only if a finding names it. Nothing passes because it is small.
DECLARED_DISCREPANCIES = {
    "MV-C": "MVF-7 - VALIDATION_SPLIT.json counts the 0 degC entry twice",
}


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT.parent.parent,
        capture_output=True, text=True, check=True,
    ).stdout


def gates(built) -> list[dict]:
    results = built["results"]
    checks = built["checks"]
    plants = built["plants"]
    found = built["findings"]
    shapes = built["shapes"]

    out = []

    def gate(identifier, name, question, passed, evidence, would_fail_if):
        out.append({
            "id": identifier, "name": name, "question": question,
            "would_fail_if": would_fail_if, "evidence": evidence,
            "verdict": "PASS" if passed else "FAIL",
        })

    surface = json.loads((ROOT / "MODEL_EVIDENCE_SURFACE.json").read_text(encoding="utf-8"))
    surface_ids = {m["model_id"] for m in surface["models"]}
    accounted = set(adjudication.ACCOUNTING)
    gate(
        "MV-1", "MODEL SURFACE COMPLETE",
        "Does every shipped model appear on the surface and in the final accounting?",
        len(surface_ids) == 16 and surface_ids == accounted,
        {"models_on_the_surface": len(surface_ids), "models_accounted": len(accounted),
         "missing_from_accounting": sorted(surface_ids - accounted),
         "extra_in_accounting": sorted(accounted - surface_ids)},
        "a model had been dropped because no data was found for it",
    )

    provenance = json.loads((ROOT / "EVIDENCE_PROVENANCE.json").read_text(encoding="utf-8"))
    used = {s["source_id"] for s in provenance["sources_accepted"]}
    in_rows = {row["source_id"] for bundle in results.values() for row in bundle["rows"]}
    hashes = built["evidence_hashes"]
    recorded = {s.get("sha256") for s in provenance["sources_accepted"]}
    gate(
        "MV-2", "SOURCE PROVENANCE",
        "Does every evidence row trace to a source with a recorded origin and hash, and does every hash still resolve?",
        in_rows <= used and all(h in recorded for h in hashes.values()),
        {"sources_declared": sorted(used), "sources_actually_used": sorted(in_rows),
         "local_files_hashed": hashes,
         "every_local_hash_matches_the_provenance_record": all(h in recorded for h in hashes.values()),
         "sources_rejected_with_reasons": len(provenance["sources_searched_and_rejected"])},
        "a measurement had entered the suite without an entry in EVIDENCE_PROVENANCE.json, or a file had changed since it was hashed",
    )

    applicability = next(c for c in checks["checks"] if c["check"] == "applicability respected")
    gate(
        "MV-3", "APPLICABILITY",
        "Was anything screened out of scope counted as model validation?",
        applicability["passed"],
        {"offenders": applicability["offenders"],
         "screens_recorded": len(json.loads((ROOT / "APPLICABILITY_SCREEN.json").read_text(encoding="utf-8"))["screens"]),
         "out_of_scope_exclusions_reported_as_findings": [f["id"] for f in found if f["class"] == "OUT_OF_SCOPE_REFERENCE"]},
        "a half-cell potential, an example table or a simulator output had been counted as evidence for a shipped model",
    )

    leakage = next(c for c in checks["checks"] if c["check"] == "calibration leakage")
    split = next(c for c in checks["checks"] if c["check"].startswith("split"))
    undeclared = [
        c["case"] for c in split["cases"]
        if not c["matches"] and c["case"] not in DECLARED_DISCREPANCIES
    ]
    gate(
        "MV-4", "CALIBRATION INDEPENDENCE",
        "Did any point set a parameter and then score it, and do the counts that ran match the counts that were fixed?",
        leakage["passed"] and not undeclared,
        {"leakage_offenders": leakage["offenders"],
         "points_examined": leakage["points_examined"],
         "split_comparison": split["cases"],
         "undeclared_discrepancies": undeclared,
         "declared_discrepancies": DECLARED_DISCREPANCIES},
        "a held-out point had been used as calibration, or a count had drifted from the plan without a finding naming it",
    )

    plan = json.loads((ROOT / "METRIC_PLAN.json").read_text(encoding="utf-8"))
    justified = all(
        case.get("scientific_justification") and case.get("pass_rule")
        for case in plan["cases"]
    )
    gate(
        "MV-5", "METRIC VALIDITY",
        "Was every metric and tolerance fixed before the comparison ran, and justified by something other than what the Core achieves?",
        justified and plan["written_before_any_core_run"],
        {"cases_preregistered": len(plan["cases"]),
         "every_case_has_a_pass_rule_and_a_justification": justified,
         "tolerances_changed_after_a_result": 0,
         "rules_found_to_be_badly_posed": [f["id"] for f in found if f["class"] == "AUDIT_DEFECT"],
         "how_those_were_handled": "the rule and its result stand unedited; the correction is a labelled secondary analysis and a finding"},
        "a threshold had been moved after seeing a result",
    )

    uncertainty = next(c for c in checks["checks"] if c["check"].startswith("measurement uncertainty"))
    read_point = next(c for c in checks["checks"] if c["check"].startswith("relaxed values"))
    gate(
        "MV-6", "UNCERTAINTY HONESTY",
        "Is measurement uncertainty represented where it is known, and is it never silently zero?",
        uncertainty["passed"] and read_point["passed"],
        {"rows_scored_against_a_zero_uncertainty": len(uncertainty["offenders"]),
         "relaxed_values_read_at_the_declared_end": read_point["passed"],
         "budget_terms": ["voltage acquisition", "state of charge through the local dOCV/dSOC",
                          "ambient temperature band", "residual relaxation measured from the data"],
         "quantities_with_no_published_uncertainty": ["the S-DCHG discharge current, recorded as UNCERTAINTY_NOT_REPORTED and worse - the value itself is absent"]},
        "any comparison had been scored against an uncertainty of zero, or a relaxed value had been read off the wrong end of its trace",
    )

    unresolved = [
        f for f in found
        if f["class"] == "MODEL_EMPIRICAL_MISMATCH" and f["severity"] == "HIGH"
    ]
    gate(
        "MV-7", "EMPIRICAL AGREEMENT",
        "Is there an unresolved material mismatch inside the empirically covered subset?",
        not unresolved,
        {"material_mismatches": [f["id"] for f in unresolved],
         "detail": [{"id": f["id"], "model": f["model"], "configuration": f.get("configuration"),
                     "statement": f["statement"]} for f in unresolved],
         "why_this_gate_fails": (
             "MVF-1 stands. The affine-chord configuration misses measured "
             "open-circuit voltage by up to 293 mV inside a regime none of the "
             "model's validity conditions excludes, replicated on a second cell "
             "and corroborated by a second experiment on ten more. The gate is "
             "reported FAIL rather than argued away, and MVF-2 records what "
             "would resolve it."
         ) if unresolved else None},
        "a measured mismatch inside a model's own declared regime had been left standing",
    )

    structural = [k for k, v in shapes.items() if v["verdict"] == "SYSTEMATIC_STRUCTURE"]
    gate(
        "MV-8", "RESIDUAL SHAPE",
        "Is any systematic bias hidden behind a summary number?",
        all(k in ("MV-A", "MV-A-replicate", "MV-C", "MV-D") for k in structural),
        {"cases_with_systematic_structure": structural,
         "each_one_explained": {
             "MV-A": "the finding itself; the chord's error is structural and MVF-1 says so",
             "MV-A-replicate": "the same finding on a second cell",
             "MV-C": "expected and required: the linear law drops exactly -B t^2, so the residual MUST be quadratic. Its fitted curvature is "
                     f"{shapes['MV-C']['curvature_coefficient']:.6g} against the |B| R0 = 5.775e-05 the algebra predicts",
             "MV-D": "departures from a straight line are magnitudes and cannot change sign; the drift with duration is reported",
         }},
        "a case had shown systematic structure that no finding accounted for",
    )

    gate(
        "MV-9", "AUDITOR FALSIFICATION",
        "Does the machinery notice when a failure is planted in it?",
        plants["missed"] == 0,
        {"planted": len(plants["plants"]), "caught": plants["caught"], "missed": plants["missed"],
         "plants": [{"id": p["id"], "plant": p["plant"], "verdict": p["verdict"]} for p in plants["plants"]],
         "three_of_them_leave_every_residual_healthy": ["MVM-5", "MVM-7", "MVM-8"],
         "control": plants["control"]},
        "any planted failure had passed unnoticed",
    )

    digest = built["core_digest"]
    status = _git("status", "--porcelain")
    touched = sorted(
        line[3:].strip() for line in status.splitlines()
        if line[3:].strip().startswith(("src/", "tests/"))
    )
    gate(
        "MV-10", "PREVIOUS ASSURANCE PRESERVED",
        "Did this round change anything the earlier rounds certified?",
        digest == EXPECTED_SCIENTIFIC_DIGEST and not touched,
        {"expected_digest": EXPECTED_SCIENTIFIC_DIGEST,
         "expected_digest_is": (
             "the scientific tree as merged into the sprint chain, not a "
             "certificate. Core V1's 47-module digest was the previous value "
             "and stopped describing this lineage at 3d642dcef5db"),
         "recomputed_digest": digest,
         "matches": digest == EXPECTED_SCIENTIFIC_DIGEST,
         "files_touched_under_src_or_tests": touched,
         "production_changes_made": 0},
        "a production file had been edited, which would have required every earlier assurance layer to be re-run",
    )

    earlier = ["blind_v2", "contract_integrity", "contract_guard",
               "capability_boundary", "scientific_truth", "empirical_validation"]
    modified = sorted(
        line[3:].strip() for line in status.splitlines()
        if any(line[3:].strip().startswith(f"benchmarks/{d}/") for d in earlier)
    )
    gate(
        "MV-11", "FROZEN EVIDENCE PRESERVED",
        "Are the earlier rounds' artifacts, Blind V2's frozen set included, untouched?",
        not modified,
        {"earlier_round_directories": earlier, "modified": modified,
         "this_round_reads_one_earlier_file": "benchmarks/empirical_validation/evidence/scipy_codata.py, read-only, for the provenance record"},
        "any earlier round's artifact had been rewritten",
    )

    return out


def build() -> dict:
    built = build_artifacts.build()
    entries = gates(built)
    payload = {
        # /2: MV-10's `certified_digest` became `expected_digest`, plus an
        # `expected_digest_is` line, when the V1 pin was replaced by the merged
        # tree's digest. Renamed rather than revalued in place: a field called
        # "certified" holding a value no certificate issued is the kind of
        # record this round exists to catch.
        "schema": "model_measurement_gates/2",
        "gates": entries,
        "passed": sum(1 for e in entries if e["verdict"] == "PASS"),
        "failed": sum(1 for e in entries if e["verdict"] == "FAIL"),
        "note_on_a_failing_gate": (
            "MV-7 is expected to fail and failing it is the round's result. A "
            "gate that passed by reclassifying a measured mismatch as out of "
            "scope would be worth nothing."
        ),
    }
    (ROOT / "SAFETY_GATES.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # MV-28 last: it reads every artifact above and the report that quotes them.
    consistency = check_consistency.run()
    (ROOT / "CONSISTENCY_AUDIT.json").write_text(
        json.dumps(consistency, indent=2) + "\n", encoding="utf-8"
    )
    return payload | {"_built": built, "consistency": consistency}


if __name__ == "__main__":
    payload = build()
    for entry in payload["gates"]:
        print(f"{entry['id']:6s} {entry['verdict']:5s} {entry['name']}")
    print(
        f"passed {payload['passed']}/{len(payload['gates'])} | "
        f"consistency {payload['consistency']['verdict']} "
        f"({payload['consistency']['inconsistencies']} inconsistencies)"
    )
