"""Conduction1D with its solved field carried as referenced bulk data.

This is the DATA-BOUNDARY0 path. It runs the **unmodified** frozen
`Conduction1DSolver` through its public `ScientificSolver` protocol and
produces a `ScientificResult` whose scalar metrics are exactly what
`solve_slab` produces, and whose solved field is present as a
`ScientificDataReference` instead of being discarded or inlined.

Why this module is not inside ``engcore/domains/thermal/``
---------------------------------------------------------
It cannot be. The entire thermal tree is pinned byte-for-byte by three frozen
experiments::

    experiments/thermal_t1/t1_config.py::THERMAL_FROZEN_FILE_DIGESTS
    experiments/thermal_t2/t2_config.py::T1_FROZEN_FILE_DIGESTS
    experiments/thermal_t3/t3_config.py::T2_FROZEN_FILE_DIGESTS

and by ``test_every_thermal_source_file_is_pinned``, which asserts *set
equality* between the pinned map and every ``*.py`` under that directory.
Editing a file there breaks the digest pin; adding a file there breaks the set
equality. T1/T2/T3's central claim — that their measured bias is a property of
*that* solver — is evidence this milestone has no authority to spend, so the
tree is left untouched and the new path lives beside it.

That constraint turns out to be the strongest available evidence for the
milestone's backward-compatibility requirement. The bulk-data boundary is
introduced around a production solver that cannot be edited at all: no
signature changed, no line rewritten, no test re-pinned.

Where the field goes, and when
------------------------------
::

    prepare → solve → validate           in-process, same-solve consumers;
                     → extract_metrics    both may read diagnostics["field"]
            → capture_bulk               "field" is REMOVED from diagnostics,
                                          stored, replaced by a typed reference
            → ScientificResult(data_references=…)

**The ordering rule, stated because the next domain bridge will copy it:**
capture happens after *every* in-process, same-solve consumer — that is
``validate`` **and** ``extract_metrics`` — and before the scientific record is
built.

Both halves matter. `ScientificSolver` says nothing about which lifecycle
stages may read bulk diagnostics, and a solver that derives a scalar at
interpretation time (an integrated coefficient, an L2 field norm, a maximum
over a subdomain) legitimately reads the array in ``extract_metrics``. Capturing
before that stage would hand it a diagnostics dict with the array missing.
`Conduction1DSolver.extract_metrics` happens to read only ``raw.values``, so the
wrong order would have worked here and failed in the next domain — which is
exactly the kind of accident a convention copied from a first example
propagates.

Capture happens before the record is built because nothing crossing into the
control plane may carry O(mesh) data. Between the last in-process consumer and
the record is the boundary this milestone exists to establish.

What this module does not do
----------------------------
No field model, no mesh, no topology, no transfer, no probe, no coupling, no
uncertainty over the field. It moves one labelled array from a solver to a
store and names it.
"""

from __future__ import annotations

from typing import Mapping

from ...data.capture import BulkCaptureSpec, capture_bulk
from ...data.store import BulkDataStore, InMemoryBulkStore
from ...scientific.ir.problem import ScientificProblem
from ...scientific.results.provenance import ProvenanceRecord
from ...scientific.results.result import ScientificResult
from ...scientific.results.uncertainty import Uncertainty
from ..thermal.conduction1d.problem import (
    CONDUCTION_MODELS,
    FIELD_UNIT,
    ConductionSlab,
    build_conduction_problem,
    verify_problem_matches_slab,
)
from ..thermal.conduction1d.solver import (
    BACKEND,
    SOLVER_ID,
    SOLVER_VERSION,
    Conduction1DSolver,
)

#: The diagnostics key the frozen solver writes its field under.
FIELD_DIAGNOSTIC_KEY = "field"

#: Logical name the field carries as scientific data. Namespaced like the
#: domain's scalar metrics (``u:midpoint``, ``u:max_abs``), because it is the
#: same field they are summaries of. ``u`` is a normalized dimensionless field
#: and is never a temperature.
FIELD_DATA_NAME = "u:field"

FIELD_CAPTURE = BulkCaptureSpec(
    diagnostic_key=FIELD_DIAGNOSTIC_KEY,
    name=FIELD_DATA_NAME,
    unit=FIELD_UNIT,
)


def solve_slab_with_bulk_field(
    slab: ConductionSlab,
    *,
    run_id: str,
    store: BulkDataStore | None = None,
    solver: Conduction1DSolver | None = None,
    problem: ScientificProblem | None = None,
    software_version: str = "engcore.domains.thermal_models.conduction1d_bulk/0.1.0",
    git_commit: str | None = None,
    timestamp: str | None = None,
    environment: Mapping[str, str] | None = None,
    parent_run_id: str | None = None,
) -> tuple[ScientificResult, BulkDataStore]:
    """Solve one slab and return the result plus the store holding its field.

    The store is returned rather than hidden because it is a *runtime* fact the
    caller now owns: it decides where the bytes live, when they are relocated
    and when they are dropped. None of that reaches the returned result, which
    is the claim under test.

    Defaults to a fresh :class:`InMemoryBulkStore`, so the call works with no
    storage configuration at all — the same ergonomics as ``solve_slab``.
    """
    solver = solver or Conduction1DSolver()
    store = store if store is not None else InMemoryBulkStore()
    problem = problem or build_conduction_problem(slab)
    verify_problem_matches_slab(problem, slab)
    solver.bind_slab(slab, problem.problem_id)

    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)

    # Same-solve, in-process consumers. Both may read the array directly, and
    # nothing either produces carries it onward.
    report = solver.validate(prepared, raw)
    metrics = solver.extract_metrics(prepared, raw)

    # THE BOUNDARY. After this line the field is not in `diagnostics` and is
    # reachable only through `references` and a resolver.
    raw, references = capture_bulk(
        raw, store, (FIELD_CAPTURE,), required=raw.succeeded
    )

    model_identities = tuple((m.model_id, m.version) for m in CONDUCTION_MODELS)
    assumptions = CONDUCTION_MODELS[0].assumptions

    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version=software_version,
        git_commit=git_commit,
        models=model_identities,
        solvers=((SOLVER_ID, SOLVER_VERSION),),
        inputs={
            "alpha": slab.diffusivity,
            "length": slab.length,
            "end_time": slab.end_time,
        },
        assumptions=assumptions,
        tolerances=solver.settings.as_mapping(),
        environment=dict(environment or {}),
        timestamp=timestamp,
        parent_run_id=parent_run_id,
        metadata={
            "slab_id": slab.slab_id,
            "slab_fingerprint": slab.fingerprint(),
            "time_integration": "backward_euler",
            "space_discretization": "central_difference_2nd_order",
            "backend": BACKEND,
            "slab_canonical": slab.to_dict(),
        },
    )

    result = ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=model_identities,
        solver=solver.identity,
        convergence=raw.convergence,
        validation=report,
        # Unchanged from `solve_slab`: one solve quantifies no discretization
        # error, and the field being addressable does not change that.
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification performed; discretization error "
                "is established by the refinement gate, not by one solve"
            )
            for name in metrics
        },
        assumptions=assumptions,
        warnings=raw.warnings,
        data_references=references,
        provenance=provenance,
        metadata={
            "slab_id": slab.slab_id,
            "slab_fingerprint": slab.fingerprint(),
            # `raw.diagnostics` no longer holds the field; no filtering needed,
            # and none is done. That absence is the point.
            "numerics": dict(raw.diagnostics),
            "residuals": dict(raw.residuals),
            "iterations": raw.iterations,
            "wall_seconds_telemetry": raw.wall_seconds,
        },
    )
    return result, store
