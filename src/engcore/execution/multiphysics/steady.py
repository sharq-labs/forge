"""A steady participant that solves one declared scientific problem per advance (Phase 2 BR8).

Domain packs that already solve their problems as :class:`ScientificResult`
records (the electrothermal composition is one) can join the authoritative
:class:`~engcore.execution.multiphysics.runtime.MultiphysicsRuntime` through this
adapter instead of running a coupling loop of their own.  The runtime keeps
every coupling decision -- order, convergence, relaxation, rollback, outcome,
conservation; the adapter only translates.

What it guarantees
------------------
* **Steady and stateless.**  The spec must be ``transient=False`` and
  checkpointable with deterministic restore; restoring is a no-op because there
  is no state, so an implicit window can replay it.
* **No invented initial output.**  ``initialize`` reports nothing: a steady
  result has no value before its first solve.  The runtime accepts that only for
  edges a serial sweep overwrites before they are read, or that are seeded.
* **The same transfer guard as the native loops.**  A result whose own
  validation FAILED is refused (:class:`ResultRefused`) when the participant
  supplies a coupling value from it (a sink may record it instead when its adapter declares
  ``refuse_failed_sink=False``, Phase 3.5); a result attributed to
  another problem is refused; a value is taken only by its declared quantity
  name.  A result whose solver reports a failed termination makes the advance
  ``internal_converged=False`` (a numerical failure the runtime may retry), never
  a transported value.
* **Uncertainty as the result states it**: ``result.uncertainty_of(name)``,
  explicitly UNKNOWN when none was computed.  Nothing is manufactured.
* **Provenance kept.**  Every result produced is kept, in order, on
  :attr:`ResultParticipant.results`, and its id is in the step diagnostics.
"""

from __future__ import annotations

import hashlib
from typing import Callable, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import CheckpointRecord, ParticipantSpec, PortKind
from ...scientific.results.result import ScientificResult
from ...scientific.solvers.protocol import ConvergenceState
from ...scientific.units.quantity import Quantity
from ...scientific.results.validation import ValidationOutcome
from .participant import (
    AdvanceRequest,
    AdvanceResult,
    CallbackParticipant,
    InitializationResult,
    RuntimeCheckpoint,
)

_SUCCESS = frozenset({ConvergenceState.CONVERGED, ConvergenceState.NOT_APPLICABLE})


class ResultRefused(InvalidScientificProblem):
    """A produced result may not supply a coupling value (it failed its own validation, or names another problem)."""

    def __init__(self, message: str, *, result: ScientificResult) -> None:
        super().__init__(message)
        self.result = result


class ResultParticipant(CallbackParticipant):
    """``solve(inputs, run_id) -> ScientificResult`` as a steady runtime participant.

    ``outputs`` maps each OUTPUT port of ``spec`` to the result quantity it
    carries; every output port must be mapped and every input must be scalar.
    """

    def __init__(
        self,
        spec: ParticipantSpec,
        *,
        problem_id: str,
        solve: Callable[[Mapping[str, Quantity], str], ScientificResult],
        outputs: Mapping[str, str],
        run_prefix: str = "steady",
        refuse_failed_sink: bool = True,
    ) -> None:
        if spec.transient:
            raise InvalidScientificProblem(
                f"ResultParticipant {spec.participant_id!r} solves a steady problem; its spec must be transient=False"
            )
        if not (spec.checkpointable and spec.deterministic_restore):
            raise InvalidScientificProblem(
                f"ResultParticipant {spec.participant_id!r} is stateless and must declare a deterministic checkpoint"
            )
        if any(port.kind is not PortKind.SCALAR for port in spec.ports):
            raise InvalidScientificProblem(
                f"ResultParticipant {spec.participant_id!r}: scientific results carry scalar quantities only"
            )
        declared = {port.port_id for port in spec.outputs}
        mapped = dict(outputs)
        if set(mapped) != declared:
            raise InvalidScientificProblem(
                f"ResultParticipant {spec.participant_id!r} maps outputs {sorted(mapped)}; "
                f"its spec declares {sorted(declared)}"
            )
        if not str(problem_id).strip() or not callable(solve):
            raise InvalidScientificProblem("ResultParticipant requires a problem id and a solve callable")
        self.problem_id = str(problem_id).strip()
        self.results: list[ScientificResult] = []
        self._solve = solve
        self._outputs = mapped
        self._prefix = str(run_prefix).strip() or "steady"
        if not isinstance(refuse_failed_sink, bool):
            raise InvalidScientificProblem("refuse_failed_sink must be a bool")
        self._refuse_failed_sink = refuse_failed_sink
        digest = hashlib.sha256(f"stateless:{spec.participant_id}:{self.problem_id}".encode()).hexdigest()

        super().__init__(
            spec,
            initialize=lambda _instant, _inputs, _uncertainty: InitializationResult({}, {}),
            advance=self._solve_once,
            checkpoint=lambda instant: RuntimeCheckpoint(
                CheckpointRecord(spec.participant_id, instant, digest, True), None
            ),
            restore=lambda _checkpoint: None,
        )

    def _solve_once(self, request: AdvanceRequest) -> AdvanceResult:
        inputs = dict(request.inputs)
        if any(not isinstance(value, Quantity) for value in inputs.values()):
            raise InvalidScientificProblem(
                f"ResultParticipant {self.spec.participant_id!r} received a field-valued input"
            )
        run_id = f"{self._prefix}-{len(self.results) + 1}-{self.problem_id}"
        result = self._solve(inputs, run_id)
        if not isinstance(result, ScientificResult):
            raise InvalidScientificProblem(
                f"the solve for {self.problem_id!r} returned {type(result).__name__}, not a ScientificResult"
            )
        self.results.append(result)
        if result.problem_id != self.problem_id:
            raise ResultRefused(
                f"the solve for {self.problem_id!r} returned a result attributed to "
                f"{result.problem_id!r}; its values would be misattributed",
                result=result,
            )
        # Phase 3.5 WS2: by default any failed result is refused.  ``refuse_failed_sink=False`` (declared by a
        # migrating adapter whose native loop guards only where a value TRAVELS, ``coupled._transport``) lets a
        # participant that supplies NO coupling value record its failed result (kept in ``results`` and the
        # step diagnostics, carried by the adapter's own record) instead of refusing the run
        if result.validation.status is ValidationOutcome.FAIL and (self._outputs or self._refuse_failed_sink):
            failed = ", ".join(check.name for check in result.validation.failures)
            raise ResultRefused(
                f"result {result.result_id!r} of {self.problem_id!r} failed its own validation ({failed}); "
                f"a value its producer's checks reject cannot supply a coupling value",
                result=result,
            )
        values = {port: result.value(quantity) for port, quantity in self._outputs.items()}
        uncertainty = {port: result.uncertainty_of(quantity) for port, quantity in self._outputs.items()}
        return AdvanceResult(
            end=request.end,
            outputs=values,
            uncertainty=uncertainty,
            substeps=1,
            internal_converged=result.convergence in _SUCCESS,
            diagnostics={
                "result_id": result.result_id,
                "problem_id": result.problem_id,
                "convergence": result.convergence.value,
                "validation": result.validation.status.value,
            },
        )


__all__ = ["ResultParticipant", "ResultRefused"]
