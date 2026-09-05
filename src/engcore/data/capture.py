"""Capture — the point where bulk data leaves the untyped escape hatch.

Existing solver adapters put arrays in ``RawSolverOutput.diagnostics``, which
is an anonymous ``Mapping[str, Any]`` that gets serialized whole. That is
tolerable while the only consumer is in-process and same-solve — the array
never crosses into a scientific record — and intolerable the moment anything
downstream needs it, because then an O(mesh) array is inside a dictionary with
no type, no unit and no content identity.

:func:`capture_bulk` is the boundary. It takes the raw output a solver
produced, moves the named arrays into a store, and returns a raw output in
which those diagnostics keys **no longer exist** and typed references stand in
their place. After this call nothing downstream can reach the array except
through a reference and a resolver.

Deliberately universal
----------------------
This module knows no domain. The caller says which diagnostics keys hold bulk
arrays and what unit those arrays carry, because that is domain knowledge and
domain knowledge belongs to the domain. ``engcore.data`` importing a named
domain pack would be the same architecture failure as the core doing it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from ..scientific.errors import ScientificCoreError
from ..scientific.results.data_reference import ScientificDataReference
from ..scientific.solvers.protocol import RawSolverOutput
from .errors import BulkDataError
from .store import BulkDataStore, store_values


@dataclass(frozen=True)
class BulkCaptureSpec:
    """One array to lift out of ``diagnostics`` and into a store."""

    #: The ``diagnostics`` key the solver wrote the array under.
    diagnostic_key: str
    #: The logical name it will carry as scientific data, namespaced like a
    #: metric. Not a filename; see ``ScientificDataReference.name``.
    name: str
    #: The unit every element carries. ``"dimensionless"`` must be explicit.
    unit: str


def capture_bulk(
    raw: RawSolverOutput,
    store: BulkDataStore,
    specs: Iterable[BulkCaptureSpec],
    *,
    required: bool = True,
) -> tuple[RawSolverOutput, tuple[ScientificDataReference, ...]]:
    """Move named bulk arrays out of ``raw.diagnostics`` into ``store``.

    Returns a new ``RawSolverOutput`` — the input is frozen and is not mutated
    — with those keys removed and the resulting references attached, plus the
    references themselves for convenience.

    ``required=False`` tolerates a missing key, which is what a failed or
    diverged solve legitimately produces: a solve that never reached a solution
    has no field, and demanding one would turn an honest failure into a crash.
    """
    diagnostics = dict(raw.diagnostics)
    references: list[ScientificDataReference] = []
    for spec in specs:
        if spec.diagnostic_key not in diagnostics:
            if required:
                raise BulkDataError(
                    f"raw output has no diagnostic {spec.diagnostic_key!r} to "
                    f"capture as {spec.name!r}"
                )
            continue
        values: Sequence[float] = diagnostics.pop(spec.diagnostic_key)
        try:
            references.append(
                store_values(store, spec.name, values, unit=spec.unit)
            )
        except (ScientificCoreError, TypeError, ValueError) as exc:
            # A milestone about typed failure does not get to raise whatever
            # `array('d', ...)` happened to raise from three frames down.
            raise BulkDataError(
                f"diagnostic {spec.diagnostic_key!r} could not be captured as "
                f"bulk data {spec.name!r}: {exc}"
            ) from exc
    captured = tuple(references)
    return (
        replace(
            raw,
            diagnostics=diagnostics,
            data_references=tuple(raw.data_references) + captured,
        ),
        captured,
    )
