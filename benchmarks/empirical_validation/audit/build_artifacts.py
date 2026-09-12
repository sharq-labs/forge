"""Run everything and write the round's artifacts."""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

from reference import spice

from . import (
    construction,
    error_shape,
    falsification,
    independence,
    mutations,
    validation,
)
from .loader import ROOT, fixture
from .surface import SURFACE
from .tolerances import TOLERANCES


def _write(name: str, payload) -> None:
    (ROOT / name).write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------


def run_primary() -> dict:
    bundles = {
        "lumped": validation.lumped(),
        "slab": validation.slab(),
        "battery": validation.battery(),
        "conductor": validation.conductor(),
        "platinum": validation.platinum(),
        "circuits": validation.circuits(),
        "reactor_arrhenius": validation.reactor(),
        "reactor_constant_rate": validation.reactor(constant_rate=True),
    }
    return bundles


def run_holdout() -> dict:
    held = fixture("holdout")
    bundles = {
        "lumped": validation.lumped(
            case="holdout",
            initial_degC=held["lumped_body"]["initial_degC"],
            heat_input_mW=held["lumped_body"]["heat_input_mW"],
            duration_min=held["lumped_body"]["duration_min"],
        ),
        "slab": validation.slab(
            case="holdout",
            end_time_min=held["slab"]["end_time_min"],
            n_cells=held["slab"]["n_cells"],
            n_steps=held["slab"]["n_steps"],
        ),
        "battery": validation.battery(
            case="holdout",
            discharge_current_mA=held["battery_cell"]["discharge_current_mA"],
            initial_state_of_charge=held["battery_cell"]["initial_state_of_charge"],
            duration_min=held["battery_cell"]["duration_min"],
        ),
        "conductor": validation.conductor(
            case="holdout",
            operating_temperature_degC=held["conductor"]["operating_temperature_degC"],
        ),
        "platinum": validation.platinum(
            case="holdout",
            comparison_temperatures_degC=held["platinum"][
                "comparison_temperatures_degC"
            ],
        ),
        "circuits": validation.circuits(
            case="holdout", raw_circuits=[held["circuit"]]
        ),
        "reactor_arrhenius": validation.reactor(
            case="holdout",
            initial_concentration_mol_per_L=held["reactor"][
                "initial_concentration_mol_per_L"
            ],
            initial_temperature_degC=held["reactor"]["initial_temperature_degC"],
            coolant_temperature_degC=held["reactor"]["coolant_temperature_degC"],
            end_time_min=held["reactor"]["end_time_min"],
        ),
    }
    return bundles


def _flatten(bundles: dict) -> tuple[list[dict], list[dict]]:
    construction_rows: list[dict] = []
    validation_rows: list[dict] = []
    for bundle in bundles.values():
        construction_rows += bundle.get("construction", [])
        validation_rows += bundle.get("validation", [])
    return construction_rows, validation_rows


def _per_model(rows: list[dict]) -> dict:
    counts = collections.defaultdict(lambda: {"rows": 0, "disagreements": 0})
    for row in rows:
        counts[row["model"]]["rows"] += 1
        if row["verdict"] == "DISAGREES":
            counts[row["model"]]["disagreements"] += 1
    return dict(counts)


# ---------------------------------------------------------------------------


def build() -> dict:
    primary = run_primary()
    holdout = run_holdout()

    primary_construction, primary_validation = _flatten(primary)
    holdout_construction, holdout_validation = _flatten(holdout)

    shapes = error_shape.run_all()
    construction_mutations = mutations.run_all()
    harness = falsification.run_all()
    graph = independence.report()
    steady_rows = validation.cstr_steady_state_rows()

    primary_by_model = _per_model(primary_validation)
    holdout_by_model = _per_model(holdout_validation)

    # ---- EV-1 ----------------------------------------------------------
    surface = []
    for entry in SURFACE:
        counts = primary_by_model.get(entry["model_id"], {"rows": 0, "disagreements": 0})
        held = holdout_by_model.get(entry["model_id"], {"rows": 0, "disagreements": 0})
        surface.append(
            entry
            | {
                "independent_construction": "YES",
                "primary_rows": counts["rows"],
                "primary_disagreements": counts["disagreements"],
                "holdout_rows": held["rows"],
                "holdout_disagreements": held["disagreements"],
                "status": (
                    "INDEPENDENT_CONSTRUCTION_VALIDATED"
                    if counts["rows"] > 0 and counts["disagreements"] == 0
                    else "NO_ROWS"
                    if counts["rows"] == 0
                    else "DISAGREEMENT"
                ),
                "empirical_status": (
                    "EXTERNAL_EVIDENCE_AGREES"
                    if entry["empirical_evidence_possible"] == "YES"
                    and counts["disagreements"] == 0
                    else "PARTIAL_EXTERNAL_EVIDENCE"
                    if entry["empirical_evidence_possible"] == "PARTIAL"
                    else "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED"
                ),
            }
        )
    _write(
        "VALIDATION_SURFACE.json",
        {
            "schema": "validation_surface/1",
            "model_count": len(surface),
            "what_this_is": (
                "Every shipped model, how it is reached from a fixture that "
                "names no engcore type, and what external evidence exists for "
                "it in this environment. The two columns are kept apart: "
                "independent construction is not empirical evidence and is "
                "never reported as if it were."
            ),
            "empirical_evidence_possible_counts": dict(
                collections.Counter(e["empirical_evidence_possible"] for e in surface)
            ),
            "models": surface,
        },
    )

    # ---- EV-4 ----------------------------------------------------------
    all_construction = primary_construction + holdout_construction
    classification_counts = collections.Counter(
        row["classification"] for row in all_construction
    )
    _write(
        "PROBLEM_CONSTRUCTION.json",
        {
            "schema": "problem_construction/1",
            "what_this_is": (
                "Field by field, what the reference branch computed in SI from "
                "the raw fixture against what the engcore declaration reports "
                "for the same quantity. Answers question A on its own, before "
                "any solver output is compared."
            ),
            "round_off_band": construction.ROUND_OFF_BAND,
            "counts": dict(classification_counts),
            "fields_not_exact_or_transformed": [
                row
                for row in all_construction
                if row["classification"] not in ("EXACT", "TRANSFORMED_CORRECTLY")
            ],
            "rows": all_construction,
        },
    )

    # ---- EV-6 / EV-7 ---------------------------------------------------
    codata = ROOT / "evidence" / "scipy_codata.py"
    _write(
        "EVIDENCE_PROVENANCE.json",
        {
            "schema": "evidence_provenance/1",
            "rule": (
                "No number appears in this round as evidence without a source "
                "recorded here. A number with no provenance is not experimental "
                "evidence, whatever it agrees with."
            ),
            "sources": [
                {
                    "id": "CODATA-2022-R",
                    "level": "LEVEL 3 reference data",
                    "quantity": "molar gas constant",
                    "value_j_per_mol_k": 8.31446261815324,
                    "retrieved_from": (
                        "https://raw.githubusercontent.com/scipy/scipy/"
                        "v1.17.1/scipy/constants/_codata.py"
                    ),
                    "local_copy": "evidence/scipy_codata.py",
                    "sha256": _sha256(codata),
                    "bytes": codata.stat().st_size,
                    "table_identified_in_the_file_as": "CODATA 2022",
                    "exactness": (
                        "The 2019 SI redefinition fixes R = N_A k exactly, and "
                        "the table marks it (exact). The Core stores "
                        "8.314462618, a truncation at 1.8e-11 relative."
                    ),
                    "used_for": "the CSTR gas constant comparison",
                },
                {
                    "id": "IEC-60751-PT100",
                    "level": "LEVEL 3 reference data",
                    "quantity": (
                        "Callendar-Van Dusen coefficients for industrial "
                        "platinum resistance thermometers, t >= 0 degC"
                    ),
                    "values": {
                        "R0_ohm": 100.0,
                        "A_per_degC": 3.9083e-3,
                        "B_per_degC2": -5.775e-7,
                        "published_W_100": 1.3851,
                    },
                    "retrieved_from": None,
                    "how_it_got_here": (
                        "Recited from the published standard. This environment "
                        "has no licensed copy of IEC 60751 and its network "
                        "policy does not reach a host that serves one, so this "
                        "is a recitation and is labelled as such rather than "
                        "presented as a retrieved document."
                    ),
                    "cross_validation": (
                        "R(100)/R(0) recomputed from the recited A and B is "
                        "1.385055, against the 1.3851 the standard publishes. "
                        "The two agree to 3.25e-5 relative, inside the 3.61e-5 "
                        "that half of the last printed digit of 1.3851 allows. "
                        "A transcription error in A or B of one unit in the "
                        "last place would move this by more than that."
                    ),
                    "what_this_does_not_establish": (
                        "That the recited figures are the current edition's. A "
                        "consistency check against a ratio from the same "
                        "recitation cannot substitute for the document."
                    ),
                    "used_for": "the linear TCR truncation comparison",
                },
                {
                    "id": "NGSPICE-42",
                    "level": "LEVEL 4 external canonical implementation",
                    "quantity": "DC operating point of a resistive network",
                    "version": spice.version() if spice.available() else None,
                    # The argv PREFIX, not a path: on a host that reaches the
                    # provider through WSL there is no single Windows-executable
                    # path to record, and writing one would make this
                    # provenance line describe a binary nothing ran.
                    "invocation": list(spice.ARGV) if spice.ARGV else None,
                    "how_it_is_kept_independent": (
                        "Its netlist is emitted from fixtures/circuits.json by "
                        "reference/spice.py, which imports neither engcore nor "
                        "either adapter and carries its own kohm and mV "
                        "factors. IPM-7 demonstrates what happens when that "
                        "rule is broken."
                    ),
                    "used_for": "every DC node voltage comparison",
                },
            ],
            "levels_this_round_does_not_have": [
                {
                    "level": "LEVEL 1 empirical measurement",
                    "available": False,
                    "why": (
                        "No measured dataset exists in this environment and the "
                        "repository curates none. No number in this round is "
                        "labelled a measurement."
                    ),
                },
                {
                    "level": "LEVEL 2 published benchmark dataset",
                    "available": False,
                    "why": (
                        "The network policy reaches a small set of hosts; "
                        "nist.gov returns 403 through the proxy and no "
                        "benchmark dataset was retrievable."
                    ),
                },
            ],
        },
    )

    # ---- EV-11 to EV-18 ------------------------------------------------
    _write(
        "VALIDATION_RESULTS.json",
        {
            "schema": "validation_results/1",
            "tolerances": TOLERANCES,
            "primary": {
                "rows": len(primary_validation),
                "disagreements": sum(
                    1 for row in primary_validation if row["verdict"] == "DISAGREES"
                ),
                "by_evidence_level": dict(
                    collections.Counter(
                        row["evidence_level"] for row in primary_validation
                    )
                ),
                "by_model": primary_by_model,
                "rows_detail": primary_validation,
            },
            "holdout": {
                "what_this_is": (
                    "Operating points declared before any comparison was run "
                    "and not looked at until fixtures, adapters, metrics and "
                    "tolerances were frozen and the primary set had passed. "
                    "Nothing was fitted, so this is out-of-sample for the "
                    "HARNESS rather than for any model."
                ),
                "rows": len(holdout_validation),
                "disagreements": sum(
                    1 for row in holdout_validation if row["verdict"] == "DISAGREES"
                ),
                "by_model": holdout_by_model,
                "rows_detail": holdout_validation,
            },
            "oracle_self_resolution": {
                "lumped_rk4": primary["lumped"]["oracle_self_resolution"],
                "cstr_rk4_arrhenius": primary["reactor_arrhenius"][
                    "oracle_self_resolution"
                ],
                "cstr_rk4_constant_rate": primary["reactor_constant_rate"][
                    "oracle_self_resolution"
                ],
            },
            "oracle_refinement_ladders": {
                "lumped_rk4": primary["lumped"]["oracle_ladder"],
                "cstr_rk4_arrhenius": primary["reactor_arrhenius"]["oracle_ladder"],
            },
            "cstr_steady_states": steady_rows,
            "dc_diagnostics": primary["circuits"]["diagnostics"],
            "slab_predicted_error": primary["slab"]["predicted_error"],
        },
    )

    # ---- EV-17 ---------------------------------------------------------
    _write("ERROR_SHAPE.json", {"schema": "error_shape/1", **shapes})

    # ---- EV-19 ---------------------------------------------------------
    _write(
        "CONSTRUCTION_MUTATIONS.json",
        {
            "schema": "construction_mutations/1",
            "what_this_is": (
                "Seven corruptions of the PROBLEM STATEMENT, applied to one "
                "branch only. Five must be caught. Two must not be, and their "
                "blindness is the finding."
            ),
            "caught": sum(1 for m in construction_mutations if m["verdict"] == "DETECTED"),
            "blind_as_expected": sum(
                1 for m in construction_mutations if m["verdict"] == "BLIND_AS_EXPECTED"
            ),
            "unexpected": sum(
                1 for m in construction_mutations if m["verdict"] == "UNEXPECTED"
            ),
            "mutations": construction_mutations,
        },
    )

    # ---- EV-20 ---------------------------------------------------------
    _write("HARNESS_FALSIFICATION.json", {"schema": "harness_falsification/1", **harness})

    # ---- EV-26 ---------------------------------------------------------
    _write("INDEPENDENCE_GRAPH.json", graph)

    return {
        "primary": primary,
        "holdout": holdout,
        "primary_validation": primary_validation,
        "holdout_validation": holdout_validation,
        "construction": all_construction,
        "construction_counts": dict(classification_counts),
        "shapes": shapes,
        "mutations": construction_mutations,
        "harness": harness,
        "graph": graph,
        "surface": surface,
        "steady_rows": steady_rows,
    }


def core_digest() -> str:
    """The certified core digest, recomputed by the previous round's recipe.

    Deliberately the same recipe, byte for byte: a digest computed a different
    way would not be comparable with the number the previous round certified,
    and the point of recomputing it is to show this round changed nothing.
    """
    root = Path(__file__).resolve().parents[3] / "src" / "engcore" / "scientific"
    digest = hashlib.sha256()
    for path in sorted(
        p for p in root.rglob("*.py") if "__pycache__" not in p.parts
    ):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\x00")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


if __name__ == "__main__":
    result = build()
    print(
        json.dumps(
            {
                "primary_rows": len(result["primary_validation"]),
                "primary_disagreements": sum(
                    1
                    for row in result["primary_validation"]
                    if row["verdict"] == "DISAGREES"
                ),
                "holdout_rows": len(result["holdout_validation"]),
                "holdout_disagreements": sum(
                    1
                    for row in result["holdout_validation"]
                    if row["verdict"] == "DISAGREES"
                ),
                "construction": result["construction_counts"],
                "mutations": [m["verdict"] for m in result["mutations"]],
                "harness_control": result["harness"]["control"]["verdict"],
                "harness_injections": [
                    i["verdict"] for i in result["harness"]["injections"]
                ],
            },
            indent=2,
        )
    )
