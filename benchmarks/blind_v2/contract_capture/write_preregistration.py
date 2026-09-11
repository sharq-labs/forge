"""Write the Blind v2 pre-registration: spec, system inventory, source reads.

Run before a single case exists. The spec states what the challenge will do;
the inventory states what it found shipped; the source-read manifest states
exactly which production bytes were read to learn how to build a legal
request, with a digest for each so the claim is checkable.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
BLIND = HERE.parent
REPO = BLIND.parent.parent
sys.path.insert(0, str(BLIND))

from challenge import build as build_module  # noqa: E402
from challenge import generator, shadows, truth  # noqa: E402
from challenge.systems import SYSTEMS  # noqa: E402


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


SOURCE_READS = [
    (
        "src/engcore/scientific/models/definition.py",
        "the public model record: which fields a model declares, what a "
        "validity condition record contains, and the vocabulary of "
        "ValidityStatus and UnknownReason. Read as source text, lines 1-140.",
        "source_text",
        "OVERREAD: lines 90-140 of this read include `_within`, which is the "
        "range predicate's implementation and not its declaration. Recorded "
        "as a boundary breach rather than argued away. What it revealed -- "
        "that the comparison is exact and applies no tolerance -- was NOT "
        "used to design any case: every boundary case is stratified by the "
        "declared inclusivity flag, which is part of each condition's own "
        "published record, and the exact-boundary family reports what the "
        "arithmetic actually achieved rather than assuming an exact compare.",
    ),
    (
        "src/engcore/scientific/models/registry.py",
        "how a model is looked up by (model_id, version). Read as source "
        "text, lines 1-60.",
        "source_text",
        None,
    ),
    (
        "src/engcore/scientific/ir/problem.py",
        "the ScientificProblem field list and the validity_context docstring, "
        "which states that a caller-declared context is built from typed "
        "parameters and that a reserved derived name is refused. Read by "
        "runtime introspection only.",
        "introspection",
        None,
    ),
    (
        "src/engcore/scientific/units/quantity.py",
        "which unit spellings the public Quantity constructor accepts, their "
        "dimensions, and whether each is a ratio scale. Exercised on unit "
        "strings alone -- no v2 payload was constructed. Read by runtime "
        "introspection only.",
        "introspection",
        None,
    ),
]

INTROSPECTED = [
    ("src/engcore/domains/thermal_models/lumped.py", "ThermalBody construction and the lumped assessment entry point"),
    ("src/engcore/domains/thermal_models/context.py", "the declared derived quantities of the lumped domain and their published definitions"),
    ("src/engcore/domains/thermal/conduction1d/problem.py", "ConductionSlab and SlabDiscretization construction"),
    ("src/engcore/domains/thermal/conduction1d/solver.py", "the public slab solve entry point"),
    ("src/engcore/domains/thermal/conduction1d/reference.py", "the declared reference field signature"),
    ("src/engcore/domains/battery/models.py", "the four declared cell model records"),
    ("src/engcore/domains/battery/cell.py", "CellSpecification, DischargeLoad and the four assessment entry points"),
    ("src/engcore/domains/battery/context.py", "the declared derived quantities of the battery domain"),
    ("src/engcore/domains/electrical/dc/models.py", "the declared DC model records, ComponentRating and the assessment entry points"),
    ("src/engcore/domains/electrical/dc/problem.py", "DC problem construction and naming"),
    ("src/engcore/domains/electrical/dc/circuit.py", "DCCircuit construction"),
    ("src/engcore/domains/electrical/dc/components.py", "Resistor and source construction"),
    ("src/engcore/domains/electrical/dc/solver.py", "the public circuit solve entry point"),
    ("src/engcore/domains/electrical/dc/validation.py", "the public names of the DC validation settings"),
    ("src/engcore/domains/electrical/material.py", "TemperatureDependentConductor, MaterialLimits and the two resistance assessment entry points"),
    ("src/engcore/domains/electrical/dc_applicability.py", "the two applicability model records and their problem builders"),
    ("src/engcore/domains/kinetics/cstr/problem.py", "ReactorChemistry, ReactorOperation, ReactorRun and IntegrationSettings"),
    ("src/engcore/domains/kinetics/cstr/context.py", "the declared derived quantities of the CSTR domain"),
    ("src/engcore/domains/kinetics/cstr/alternatives.py", "the constant-rate comparison model record"),
    ("src/engcore/domains/derived_context.py", "the two-namespace validity context contract"),
]


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    surface = json.loads((BLIND / "CONTRACT_SURFACE.json").read_text(encoding="utf-8"))
    register = json.loads((BLIND / "BOUND_REGISTER.json").read_text(encoding="utf-8"))

    # ---- source-read manifest -------------------------------------------
    reads = []
    for path, reason, kind, incident in SOURCE_READS:
        reads.append(
            {
                "path": path,
                "reason": reason,
                "read_kind": kind,
                "sha256": digest(REPO / path),
                "boundary_incident": incident,
            }
        )
    for path, reason in INTROSPECTED:
        reads.append(
            {
                "path": path,
                "reason": reason,
                "read_kind": "introspection",
                "sha256": digest(REPO / path),
                "boundary_incident": None,
            }
        )
    reads.sort(key=lambda r: r["path"])
    manifest = {
        "schema": "blind_v2_allowed_source_reads/1",
        "what_this_is": (
            "Every production file whose CONTENT reached this challenge before "
            "the freeze, and why. `source_text` means the bytes were read; "
            "`introspection` means only the public record -- a signature, a "
            "docstring, a declared record's to_dict -- was read at runtime. "
            "Files whose names alone were listed by a directory walk are not "
            "here, because a name is not content."
        ),
        "boundary_incidents": [r for r in reads if r["boundary_incident"]],
        "reads": reads,
    }
    (BLIND / "PRE_FREEZE_ALLOWED_SOURCE_READS.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # ---- system inventory ------------------------------------------------
    systems = []
    for spec in SYSTEMS:
        models = [m for m in surface["models"] if m["system"] == spec.system_id]
        primary = next(m for m in models if m["model_id"] == spec.model_id)
        systems.append(
            {
                "system_id": spec.system_id,
                "primary_model": {"model_id": primary["model_id"], "version": primary["version"]},
                "all_models": [
                    {
                        "model_id": m["model_id"],
                        "version": m["version"],
                        "model_type": m["model_type"],
                        "validation_status": m["validation_status"],
                        "condition_count": len(m["conditions"]),
                    }
                    for m in models
                ],
                "declared_inputs": [
                    {
                        "name": i["name"],
                        "source_kind": i["source_kind"],
                        "unit_exemplar": i["unit_exemplar"],
                        "required": i["required"],
                    }
                    for i in primary["inputs"]
                ],
                "declared_outputs": primary["outputs"],
                "input_dimensions": sorted(
                    {i["unit_exemplar"] for i in primary["inputs"] if i["unit_exemplar"]}
                ),
                "public_construction_restrictions": [
                    "every declared quantity arrives as a Quantity with a unit the "
                    "registry defines and the dimension the record states",
                    "a parameter carrying a name reserved as a derived quantity is refused",
                    "an optional declaration left out removes the conditions that "
                    "depend on it from IN_DOMAIN reach; it does not default",
                ],
                "independently_calculable_truth": sorted(
                    set(spec.levers) | set(spec.evidence)
                ),
                "unit_spellings_exercised": {
                    k: list(v) for k, v in sorted(spec.units.items())
                },
                "span_fields": sorted(spec.span_fields),
                "dual_oracle_conditions": sorted(spec.dual_conditions),
                "predicted_metrics": bool(spec.metrics),
            }
        )
    inventory = {
        "schema": "blind_v2_system_inventory/1",
        "measured_at": now,
        "certified_core_commit": head,
        "system_count": len(systems),
        "model_count": surface["model_count"],
        "note": (
            "Six systems, sixteen shipped model records, discovered from the "
            "declared contract surface and not assumed. The historical "
            "expectation was 'approximately six' and the code says exactly "
            "six; the split is the model_id's own first two segments, which "
            "is how the shipped records name themselves."
        ),
        "systems": systems,
    }
    (BLIND / "SYSTEM_INVENTORY.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # ---- challenge spec --------------------------------------------------
    spec_payload = {
        "schema": "blind_v2_challenge_spec/1",
        "challenge_id": "FORGE-BLIND-V2",
        "version": "2.0.0",
        "created": now,
        "certified_core_commit": head,
        "certified_core_tree_sha256": "82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507",
        "certification_snapshot": "certification/current_core_v1.json",
        "generator_seed": generator.SEED,
        "target_system_count": len(SYSTEMS),
        "target_primary_cases": build_module.TARGET_PER_SYSTEM * len(SYSTEMS),
        "minimum_cases_per_system": 80,
        "target_cases_per_system": build_module.TARGET_PER_SYSTEM,
        "families_per_system": build_module.QUOTAS,
        "family_assignment_rule": (
            "A case is filed under the family its truth turned out to be, not "
            "the family it was aimed at. The generator states an intent; the "
            "oracles decide; a mismatch is a logged rejection, never a relabel."
        ),
        "truth_outcome_vocabulary": [
            "SUPPORTED",
            "NOT_SUPPORTED",
            "INSUFFICIENT_EVIDENCE",
            "REJECTED_AT_BOUNDARY",
        ],
        "reserved_non_verdicts": ["CHALLENGE_ERROR", "CORE_ERROR"],
        "truth_classes": [
            "INDEPENDENT_SCIENTIFIC",
            "POLICY_DEPENDENT",
            "MIXED_SCIENCE_AND_POLICY",
            "CONTRACT_ONLY",
            "UNRESOLVED",
        ],
        "oracle_plan": {
            "thermal.lumped": "analytic closed form vs in-challenge RK4 with refinement; dimensionless groups from Incropera 6th ed.",
            "electrical.material": "exact rational evaluation of the linear form vs in-challenge RK4 on dR/dT",
            "battery.cell": "closed-form charge balance and Rint chord vs in-challenge RK4 on dz/dt",
            "kinetics.cstr": "the exact invariant ceiling vs in-challenge RK4 integration of the balances, which must respect it",
            "thermal.conduction1d": "separation of variables (exact) vs in-challenge Crank-Nicolson with a Thomas sweep",
            "electrical.dc": "a real ngspice subprocess vs modified nodal analysis assembled and solved in-challenge",
        },
        "dual_oracle_plan": {
            "target_share_of_scientifically_decided_cases": 0.50,
            "target_per_system": 30,
            "independence_levels": {
                "A": "external executable against an in-challenge route",
                "B": "analytic closed form against an independent numerical solver",
                "C": "two genuinely different numerical methods",
                "D": "the same equation in a different code layout -- NOT counted",
            },
            "tolerance_rule": (
                "Every tolerance is fixed here, before any run, from the "
                "oracles' own convergence or from the interface's precision. "
                "ngspice prints about seven significant figures, so the "
                "external route can be shown to agree to 2e-6 and no closer. "
                "No tolerance may be widened after seeing the system's answer."
            ),
        },
        "boundary_strategy": {
            "margins": [name for name, _ in generator.MARGINS],
            "method": (
                "bisect the declaration in log space until the bracket is two "
                "adjacent floats, then walk single ULPs to land on the bound "
                "where the arithmetic permits"
            ),
            "boundary_kinds": [
                "MATHEMATICAL_BOUNDARY",
                "REPRESENTABLE_BOUNDARY",
                "WITHIN_1_ULP_BOUNDARY",
            ],
            "no_manufactured_equality": (
                "exact float equality is never manufactured where a unit "
                "transform cannot preserve it; the case records what it "
                "actually achieved"
            ),
        },
        "unit_diversity_strategy": {
            "principle": "physical equivalence across unit spelling, on this challenge's own unit algebra",
            "affine_rule": (
                "an affine unit may state a temperature and may never state a "
                "span; a span rendered on an affine scale is a deliberate "
                "refusal probe with its own family"
            ),
            "undefined_unit_probe": build_module.UNDEFINED_UNIT,
            "undefined_unit_note": (
                "the round's brief names 'kilohm'; the shipped registry "
                "defines 'kiloohm' and not 'kilohm', so declaring 'kilohm' is "
                "a legitimate refusal probe and not an invented unit"
            ),
            "metamorphic_share_target": 0.20,
        },
        "refusal_strategy": {
            "stages_probed": [
                "unit_compatibility",
                "schema_type",
                "scientific_applicability",
            ],
            "modes": [
                "undefined_unit",
                "wrong_dimension",
                "non_finite",
                "affine_span",
                "forced_non_positive",
            ],
            "channel_ambiguity_rule": (
                "where a physically invalid but dimensionally legal value could "
                "be refused at construction OR caught as a condition violation, "
                "the case records both as acceptable and is marked "
                "channel_ambiguous. Both are refusals; neither can be a false "
                "accept."
            ),
        },
        "missing_evidence_strategy": (
            "drop the declarations a condition's own record says it needs. The "
            "expected outcome is INSUFFICIENT_EVIDENCE, never a pass."
        ),
        "compound_defect_strategy": (
            "two or more conditions outside their bounds at once, with the "
            "mechanism set and the causal class recorded from counterfactual "
            "repair rather than assumed"
        ),
        "metamorphic_strategy": {
            "target_shadows": 200,
            "transformations": list(shadows.TRANSFORMATIONS),
            "rule": (
                "a shadow carries no independent truth. Its semantic outcome "
                "must equal its parent's, except affine_span_probe, which is "
                "declared NOT semantics-preserving and exists to separate the "
                "readings a system might take."
            ),
        },
        "causal_reason_strategy": (
            "repair one declared defect back to its nominal value, leave every "
            "other defect where it is, recompute independent truth, and see "
            "whether the verdict moves. Frozen before any run."
        ),
        "precedence_rule": {
            "statement": (
                "violation dominates unknown in this challenge's own outcome "
                "rule. Where a case carries both, it is marked "
                "precedence_dependent."
            ),
            "scoring": (
                "precedence_dependent cases are scored on the safety axis "
                "(accept versus refuse) and reported separately on the exact "
                "verdict axis. Registered here, before any case exists, so "
                "that the split cannot be mistaken for post-hoc leniency."
            ),
        },
        "allowed_source_reads": "PRE_FREEZE_ALLOWED_SOURCE_READS.json",
        "bound_register": "BOUND_REGISTER.json",
        "bound_class_counts": register["class_counts"],
        "forbidden_historical_inputs": [
            "benchmarks/hard case payloads and truth",
            "benchmarks/blind (v1) cases, truth and answer keys",
            "benchmarks/oracles",
            "tests/oracles truth modules",
            "every sealed holdout, which this round does not open",
            "published test counts in documentation, which are stale and were "
            "not used as a numeric authority",
        ],
        "decision_rules": {
            "false_accept": (
                "the system reports SUPPORTED where independent truth refuses. "
                "One genuine false accept means the generalization gate cannot "
                "return PASS."
            ),
            "core_defect": (
                "any genuine production defect exposed means the certified "
                "revision failed this gate, whatever the score afterwards"
            ),
            "invalid_challenge": (
                "freeze not proven to predate the run, truth edited after the "
                "run, first-run artifact rewritten, no-peek audit failing, or "
                "truth defects extensive enough that the challenge cannot "
                "support its own conclusions"
            ),
            "no_score_target": (
                "no numerical accuracy is required and none is aimed at. A low "
                "score with a valid diagnosis is the successful outcome."
            ),
        },
    }
    (BLIND / "CHALLENGE_SPEC.json").write_text(
        json.dumps(spec_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for name in ("CHALLENGE_SPEC.json", "SYSTEM_INVENTORY.json", "PRE_FREEZE_ALLOWED_SOURCE_READS.json"):
        print(f"{name}  sha256={digest(BLIND / name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
