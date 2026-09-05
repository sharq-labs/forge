"""ElectricalDCSolver — a ScientificSolver over modified nodal analysis.

The five lifecycle stages stay strictly separated, because collapsing them is
how provenance gets lost:

``supports`` (capability question, never executes)
→ ``prepare`` (assemble ``A x = z``)
→ ``solve`` (SciPy linear solve, raw floats)
→ ``extract_metrics`` (units restored)
→ ``validate`` (independent physical checks)

Topology boundary
-----------------
``ScientificProblem`` carries no circuit — topology is domain-specific. A
circuit is bound to this solver instance with :meth:`bind_circuit`, keyed by
problem id, and travels onward inside ``PreparedSolve.payload``. The binding
table is domain-local state on the instance, never a global registry.

Singular systems
----------------
A floating sub-network or two ideal sources contradicting each other yields a
singular matrix. The solver reports failure. It never adds epsilon to the
diagonal, never falls back to least squares or a pseudo-inverse, and never
picks a datum on the caller's behalf: a system with no unique solution has no
unique solution, and inventing a plausible answer would be the worst possible
outcome for a platform whose purpose is trustworthy results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
from scipy.linalg import LinAlgError, LinAlgWarning, solve as scipy_solve

from ....scientific.errors import ScientificCoreError
from ....scientific.ir.problem import ScientificProblem
from ....scientific.results.provenance import ProvenanceRecord
from ....scientific.results.result import ScientificResult
from ....scientific.results.uncertainty import Uncertainty
from ....scientific.results.validation import ValidationReport
from ....scientific.solvers.protocol import (
    ConvergenceState,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from ....scientific.units.quantity import Quantity
from .circuit import CANONICAL_SCHEMA, DCCircuit
from .components import CURRENT_UNIT, POWER_UNIT, VOLTAGE_UNIT
from .errors import CircuitBindingError, ElectricalDCError
from .mna import PreparedDCSystem, assemble
from .models import (
    DC_MODELS,
    ELECTRICAL_DC_LINEAR,
    assumptions_for_models,
    dc_solver_capabilities,
    models_for_circuit,
)
from .problem import verify_problem_matches_circuit
from .validation import DCValidationSettings, build_validation_report

SOLVER_ID = "electrical.dc.mna"
SOLVER_VERSION = "0.1.0"
BACKEND = "scipy.linalg.solve"

NODE_VOLTAGE_METRIC = "node_voltage"
SOURCE_CURRENT_METRIC = "source_current"


@dataclass
class ElectricalDCSolver:
    """Linear resistive DC solver satisfying the ScientificSolver protocol."""

    settings: DCValidationSettings = field(default_factory=DCValidationSettings)
    _circuits: dict[str, DCCircuit] = field(default_factory=dict, repr=False)

    # ---- identity / capability -----------------------------------------
    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND)

    @property
    def capabilities(self):
        return dc_solver_capabilities()

    @property
    def solver_settings(self) -> SolverSettings:
        return SolverSettings(
            tolerances=self.settings.as_mapping(),
            options={"formulation": "modified_nodal_analysis", "backend": BACKEND},
        )

    # ---- domain-local circuit binding -----------------------------------
    def bind_circuit(self, circuit: DCCircuit, problem_id: str) -> None:
        """Associate a circuit with the problem that describes it.

        Rebinding is idempotent for the *same* physical system and rejected
        for a different one: silently swapping the circuit behind a problem
        id would let two results claim the same identity while describing
        different systems.
        """
        if not isinstance(circuit, DCCircuit):
            raise ElectricalDCError("bind_circuit expects a DCCircuit")
        key = str(problem_id)
        existing = self._circuits.get(key)
        if existing is not None:
            previous = existing.fingerprint()
            incoming = circuit.fingerprint()
            if previous != incoming:
                raise CircuitBindingError(
                    f"problem {key!r} is already bound to a different circuit "
                    f"(bound {previous[:12]}…, incoming {incoming[:12]}…); "
                    f"rebinding to a different physical system is refused — "
                    f"use a fresh solver or a distinct problem id"
                )
        self._circuits[key] = circuit

    def bound_circuit(self, problem_id: str) -> DCCircuit | None:
        return self._circuits.get(str(problem_id))

    # ---- lifecycle -------------------------------------------------------
    def supports(self, problem: ScientificProblem) -> bool:
        """Capability question only — never attempts a solve.

        Deliberately independent of whether a circuit happens to be bound:
        support is a property of the problem and this solver, not of the
        data currently loaded. A missing binding is an error at prepare
        time, not a claim of incompatibility.
        """
        if not isinstance(problem, ScientificProblem):
            return False
        declared = {capability.name for capability in self.capabilities}
        if not set(problem.required_capabilities).issubset(declared):
            return False
        # The problem must actually be a DC circuit analysis: it names at
        # least one of this domain's models.
        domain_models = {model.model_id for model in DC_MODELS}
        referenced = {reference.model_id for reference in problem.models}
        if not referenced & domain_models:
            return False
        return ELECTRICAL_DC_LINEAR.name in problem.required_capabilities

    def prepare(self, problem: ScientificProblem) -> PreparedSolve:
        circuit = self.bound_circuit(problem.problem_id)
        if circuit is None:
            raise ElectricalDCError(
                f"no circuit bound for problem {problem.problem_id!r}; call "
                f"bind_circuit() first — the universal IR carries no topology"
            )
        if not self.supports(problem):
            raise ElectricalDCError(
                f"problem {problem.problem_id!r} is not an Electrical DC "
                f"linear analysis"
            )
        # Integrity gate: prove the problem and the bound circuit describe
        # the same physical system before anything is assembled or solved.
        verify_problem_matches_circuit(problem, circuit)
        system = assemble(circuit)
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=self.solver_settings,
            payload=system,
            notes=(
                f"MNA system {system.size}x{system.size} "
                f"({system.n_nodes} node voltages, "
                f"{system.n_sources} source currents)",
            ),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        system: PreparedDCSystem = prepared.payload
        started = time.perf_counter()

        if system.size == 0:
            return RawSolverOutput(
                convergence=ConvergenceState.FAILED,
                warnings=("circuit has no unknowns to solve for",),
                wall_seconds=time.perf_counter() - started,
            )

        warnings_seen: list[str] = []
        try:
            import warnings as _warnings

            with _warnings.catch_warnings():
                _warnings.simplefilter("error", LinAlgWarning)
                solution = scipy_solve(system.matrix, system.rhs, assume_a="gen")
        except (LinAlgError, LinAlgWarning, ValueError) as exc:
            # Singular or numerically hopeless. No regularisation, no
            # pseudo-inverse, no least squares: report the failure.
            return RawSolverOutput(
                convergence=ConvergenceState.FAILED,
                warnings=(
                    "linear system could not be solved uniquely; the circuit "
                    "is singular (floating sub-network, or contradictory "
                    "ideal sources)",
                ),
                diagnostics={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "matrix_size": system.size,
                },
                wall_seconds=time.perf_counter() - started,
            )

        solution = np.asarray(solution, dtype=np.float64).reshape(-1)
        if not np.all(np.isfinite(solution)):
            return RawSolverOutput(
                convergence=ConvergenceState.FAILED,
                warnings=("linear solve produced non-finite values",),
                diagnostics={"matrix_size": system.size},
                wall_seconds=time.perf_counter() - started,
            )

        residual = system.matrix @ solution - system.rhs
        residual_norm = float(np.linalg.norm(residual))

        values: dict[str, float] = {}
        for node_id in system.circuit.node_ids:
            values[f"{NODE_VOLTAGE_METRIC}:{node_id}"] = system.node_voltage(
                solution, node_id
            )
        for source_id in system.voltage_source_order:
            values[f"{SOURCE_CURRENT_METRIC}:{source_id}"] = system.source_current(
                solution, source_id
            )

        return RawSolverOutput(
            convergence=ConvergenceState.CONVERGED,
            values=values,
            residuals={"linear_system": residual_norm},
            iterations=1,   # direct solve
            wall_seconds=time.perf_counter() - started,
            warnings=tuple(warnings_seen),
            diagnostics={
                "matrix_size": system.size,
                "solution": [float(v) for v in solution],
            },
        )

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> dict[str, Quantity]:
        """Restore units. This is the boundary where raw floats re-enter the
        unit-aware scientific world; a failed solve yields no metrics."""
        if not raw.succeeded:
            return {}

        system: PreparedDCSystem = prepared.payload
        circuit = system.circuit
        solution = np.asarray(raw.diagnostics["solution"], dtype=np.float64)
        voltages = {
            node_id: system.node_voltage(solution, node_id)
            for node_id in circuit.node_ids
        }

        metrics: dict[str, Quantity] = {}
        for node_id, value in voltages.items():
            metrics[f"{NODE_VOLTAGE_METRIC}:{node_id}"] = Quantity(value, VOLTAGE_UNIT)

        total_dissipation = 0.0
        for resistor in circuit.resistors:
            v_ab = voltages[resistor.node_a] - voltages[resistor.node_b]
            i_ab = v_ab / resistor.resistance_ohm
            power = v_ab * i_ab
            total_dissipation += power
            cid = resistor.component_id
            metrics[f"resistor_voltage:{cid}"] = Quantity(v_ab, VOLTAGE_UNIT)
            metrics[f"resistor_current:{cid}"] = Quantity(i_ab, CURRENT_UNIT)
            metrics[f"resistor_power:{cid}"] = Quantity(power, POWER_UNIT)

        delivered = 0.0
        for source in circuit.voltage_sources:
            cid = source.component_id
            current = system.source_current(solution, cid)
            terminal = (
                voltages[source.positive_node] - voltages[source.negative_node]
            )
            absorbed = terminal * current
            delivered -= absorbed
            metrics[f"{SOURCE_CURRENT_METRIC}:{cid}"] = Quantity(current, CURRENT_UNIT)
            metrics[f"source_power:{cid}"] = Quantity(absorbed, POWER_UNIT)

        for source in circuit.current_sources:
            cid = source.component_id
            absorbed = (
                voltages[source.from_node] - voltages[source.to_node]
            ) * source.current_ampere
            delivered -= absorbed
            metrics[f"current_source_power:{cid}"] = Quantity(absorbed, POWER_UNIT)

        if circuit.resistors:
            metrics["total_resistor_dissipation"] = Quantity(
                total_dissipation, POWER_UNIT
            )
        if circuit.voltage_sources or circuit.current_sources:
            metrics["total_source_delivered_power"] = Quantity(delivered, POWER_UNIT)

        return metrics

    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        if not raw.succeeded:
            from ....scientific.results.validation import (
                ValidationCheck,
                ValidationOutcome,
            )

            return ValidationReport(
                checks=(
                    ValidationCheck(
                        name="linear_system_solved",
                        outcome=ValidationOutcome.FAIL,
                        detail="; ".join(raw.warnings)
                        or "solver did not converge",
                    ),
                ),
                notes="no solution to validate",
            )

        system: PreparedDCSystem = prepared.payload
        solution = np.asarray(raw.diagnostics["solution"], dtype=np.float64)
        metrics = self.extract_metrics(prepared, raw)
        return build_validation_report(system, solution, metrics, self.settings)


def solve_circuit(
    circuit: DCCircuit,
    *,
    run_id: str,
    solver: ElectricalDCSolver | None = None,
    problem: ScientificProblem | None = None,
    software_version: str = "engcore.domains.electrical.dc/0.1.0",
    git_commit: str | None = None,
    timestamp: str | None = None,
    environment: Mapping[str, str] | None = None,
    parent_run_id: str | None = None,
) -> ScientificResult:
    """Run the full contract lifecycle for one circuit and return a result.

    Orchestration only: every stage goes through the protocol, nothing is
    bypassed. A singular circuit returns a result whose convergence is FAILED
    and whose validation report says so — recording that a circuit has no
    unique solution is a scientific finding worth keeping, not an exception
    to swallow.
    """
    from .problem import build_dc_problem, verify_problem_matches_circuit

    solver = solver or ElectricalDCSolver()
    problem = problem or build_dc_problem(circuit)
    # Reject an inconsistent pairing before binding, assembling or solving.
    verify_problem_matches_circuit(problem, circuit)
    solver.bind_circuit(circuit, problem.problem_id)

    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    report = solver.validate(prepared, raw)

    inputs: dict[str, Quantity] = {}
    for resistor in circuit.resistors:
        inputs[f"R:{resistor.component_id}"] = resistor.resistance
    for source in circuit.voltage_sources:
        inputs[f"Vs:{source.component_id}"] = source.voltage
    for source in circuit.current_sources:
        inputs[f"Is:{source.component_id}"] = source.current

    # One active model set, used identically in the problem, the result and
    # the provenance — these three must never disagree about what a result
    # depends on.
    active_models = models_for_circuit(circuit)
    model_identities = tuple((m.model_id, m.version) for m in active_models)
    assumptions = assumptions_for_models(active_models)

    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version=software_version,
        git_commit=git_commit,
        models=model_identities,
        solvers=((SOLVER_ID, SOLVER_VERSION),),
        inputs=inputs,
        assumptions=assumptions,
        tolerances=solver.settings.as_mapping(),
        environment=dict(environment or {}),
        timestamp=timestamp,
        parent_run_id=parent_run_id,
        metadata={
            "circuit_id": circuit.circuit_id,
            "reference_node": circuit.reference_node,
            "formulation": "modified_nodal_analysis",
            "backend": BACKEND,
            # Identity plus the full canonical topology: element values alone
            # cannot say which nodes they were wired between, so a fingerprint
            # answers "was it this circuit?" and the canonical record answers
            # "what exactly was solved?".
            "circuit_fingerprint": circuit.fingerprint(),
            "circuit_canonical_schema": CANONICAL_SCHEMA,
            "circuit_canonical": circuit.canonical_dict(),
        },
    )

    return ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=model_identities,
        solver=solver.identity,
        convergence=raw.convergence,
        validation=report,
        # No uncertainty quantification is performed: element values are
        # taken as exact and no tolerance propagation is done. Reporting
        # anything other than UNKNOWN here would be fabrication.
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification performed in Electrical DC V0"
            )
            for name in metrics
        },
        assumptions=assumptions,
        warnings=raw.warnings,
        provenance=provenance,
        metadata={
            "circuit_id": circuit.circuit_id,
            "circuit_fingerprint": circuit.fingerprint(),
        },
    )
