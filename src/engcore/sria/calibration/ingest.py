"""Read historical run corpora into canonical learning records.

Strictly read-only with respect to the campaign artifacts. The D5 validation
data in particular is frozen; this module opens those CSVs and never writes
near them.

Modelling choices worth stating, because they determine what the learners can
and cannot conclude:

* **Structure** is ``(search dimension, evaluation budget)`` — computational
  shape. The BBOB function number is *not* part of it: f12 and f13 at the same
  dimension and budget are the same computational structure presented with
  different landscapes, and pretending otherwise would create 24 single-member
  cells that generalise to nothing.
* **Environment** is one signature for both campaigns. They ran on the same
  machine with the same precision. Inventing two environments to make the data
  look richer would be fabrication.
* **Solver identity** carries the algorithm and the code version it ran under,
  which is the axis that genuinely changes cost here.
* **Group key** is the BBOB function id, used *only* to split. Grouping by
  function across both campaigns is the strict choice: it keeps f12-at-D2 and
  f12-at-D5 on the same side of the split, since they share a landscape family.

Every run in these corpora completed its full budget, so every record is
``SUCCESS`` with an uncensored cost. That is a fact about the data, not an
assumption imposed on it, and it is why the failure model reports insufficient
data rather than a confident constant.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Iterable, Sequence

from ..outcomes import AttributedCause, CensoringType, Disposition, Retryability
from ..signatures import EnvironmentSignature, StructureComponent, StructureSignature
from .learning_record import ComputationalLearningRecord

#: One machine, one precision — both campaigns.
CAMPAIGN_ENVIRONMENT = EnvironmentSignature(
    hardware_class="laptop.x86_64.cuda_rtx4060",
    precision="float64",
    solver_build=("engcore.validation.arena", "2.8.2-cocoex"),
    runtime={"os": "windows", "python": "3.14"},
)


def structure_for(dimension: int, budget: int) -> StructureSignature:
    """Computational shape of a black-box optimization run."""
    return StructureSignature(
        structure_kind="blackbox_search_run",
        components=(
            StructureComponent(
                kind="continuous_search_dimension", multiplicity=int(dimension)
            ),
        ),
        attributes={
            "evaluation_budget": str(int(budget)),
            "search_dimension": str(int(dimension)),
        },
    )


def _group_key_from_problem_id(problem_id: str) -> str:
    """``bbob_f012_i71_d05`` -> ``bbob_f012`` (landscape family)."""
    parts = problem_id.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return problem_id


def load_runs_csv(
    path: str | Path,
    *,
    code_version: str,
    dataset_id: str,
) -> tuple[ComputationalLearningRecord, ...]:
    """Load one ``runs.csv`` into learning records."""
    path = Path(path)
    records: list[ComputationalLearningRecord] = []

    with path.open(newline="", encoding="utf-8") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            dimension = int(row["dimension"])
            budget = int(row["budget"])
            evaluations = int(row["evaluations"])
            wall = float(row["wall_s"])
            best_f = float(row["best_f"])

            # A run that did not spend its budget, or returned a non-finite
            # objective, is not a clean SUCCESS. None occur in these corpora;
            # the branch exists so that a future corpus containing them is not
            # silently mislabelled.
            complete = evaluations == budget and math.isfinite(best_f)
            disposition = Disposition.SUCCESS if complete else Disposition.PARTIAL
            cause = AttributedCause.NONE if complete else AttributedCause.UNATTRIBUTED

            records.append(
                ComputationalLearningRecord(
                    record_id=f"{dataset_id}:{row['problem_id']}:{row['algorithm']}",
                    structure=structure_for(dimension, budget),
                    environment=CAMPAIGN_ENVIRONMENT,
                    solver_identity=(row["algorithm"], code_version),
                    disposition=disposition,
                    attributed_cause=cause,
                    informative_for_pf=complete,
                    retryability=Retryability.RETRYABLE,
                    covariates={
                        "search_dimension": float(dimension),
                        "evaluation_budget": float(budget),
                        "log10_budget": math.log10(max(budget, 1)),
                    },
                    realized_cost=wall,
                    cost_unit="second",
                    cost_censoring=CensoringType.NONE,
                    completion_fraction=(
                        evaluations / budget if budget else 0.0
                    ),
                    group_key=_group_key_from_problem_id(row["problem_id"]),
                    pairing_key=f"{dataset_id}:{row['problem_id']}",
                    provenance_ref=f"{dataset_id}#{index}",
                    diagnostics_ref=str(path),
                )
            )
    return tuple(records)


def load_corpus(sources: Iterable[tuple[str | Path, str, str]]):
    """Load several ``(path, code_version, dataset_id)`` corpora together."""
    out: list[ComputationalLearningRecord] = []
    for path, code_version, dataset_id in sources:
        if not Path(path).exists():
            continue
        out.extend(
            load_runs_csv(path, code_version=code_version, dataset_id=dataset_id)
        )
    return tuple(out)


def corpus_summary(records: Sequence[ComputationalLearningRecord]) -> dict:
    costs = [r.realized_cost for r in records if r.cost_is_observed]
    return {
        "records": len(records),
        "groups": len({r.group_key for r in records}),
        "structures": len({r.structure.digest for r in records}),
        "environments": len({r.environment.digest for r in records}),
        "solvers": sorted({r.solver_identity[0] for r in records}),
        "successes": sum(1 for r in records if r.computational_success),
        "failures": sum(1 for r in records if not r.computational_success),
        "observed_costs": len(costs),
        "cost_min_s": min(costs) if costs else None,
        "cost_max_s": max(costs) if costs else None,
    }
