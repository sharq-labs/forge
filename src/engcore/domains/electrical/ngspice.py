"""ngspice as a concrete solver for the existing Electrical DC problem.

`HETERO-NGSPICE`. The first execution path in this repository run by code Crafty
did not write. It solves **the same scientific problem**, against **the same
model records**, through **the same realization records**, and returns **the same
`ScientificResult` contract** as the native MNA path. What differs is the
concrete solver, and that difference lives in `SolverIdentity` — which is the
whole claim under test.

    DCCircuit + ScientificProblem      existing records, unchanged
            |
            |  emit provider syntax
            v
    SPICE netlist text                 provider syntax, NOT Crafty IR
            |
            |  <invocation> -b   (netlist on stdin; no path crosses)
            v
    ngspice process
            |
            |  parse "name = value"
            v
    Quantity-valued metrics            existing units contract
            |
            |  build_validation_report  <- the SAME validity authority as native
            v
    ScientificResult

What this module is not
-----------------------
Not a provider framework. There is no registry, no `ProviderDefinition`, no
capability graph and no backend hierarchy. There is one adapter for one provider,
because one provider is the entire evidence. A second external provider whose
process-execution needs actually overlap is the named trigger for generalising;
until then a shared abstraction would be a guess with one member.

Three things this module refuses to do
--------------------------------------
**1. It never branches on provider text.** ngspice's stdout and stderr are
carried verbatim into ``RawSolverOutput.warnings`` — the contract's sanctioned
uninterpreted channel — and are never read to decide anything. Mapping
``"Warning: singular matrix"`` onto ``ConvergenceState.FAILED`` would make a
serialized scientific field depend on an English string from one build of one
version, which is provider syntax entering scientific semantics.

**2. It never lets provider identity into a scientific record.** The invocation
— including the fact that this machine reaches ngspice through WSL — is
configuration held by :class:`NgspiceInvocation` and passed as an argument. It
appears in no `ScientificProblem`, no `ScientificModelDefinition`, no
`ModelRealizationDefinition` and no `ProvenanceRecord`. Moving the executable
must leave the serialized result byte-identical, and a test asserts it.

**3. It never synthesises a result it did not get.** A provider failure raises
:class:`NgspiceExecutionFailure`, which inherits ``Exception`` and deliberately
**not** ``ScientificCoreError`` — the same separation ``engcore.data`` draws for
``BulkDataError``. A failure to *run* is not a failure to *converge*, and neither
is a failure to be *valid*.

The measured limit, stated where a reader will meet it
------------------------------------------------------
On a structurally **singular** circuit, ngspice-42 exits 0, emits the complete
requested quantity set as zeros, and warns only on stderr. The native path
refuses the same circuit outright (``convergence=FAILED``, zero metrics). This
adapter therefore reports a converged result where the native path reports a
scientific failure, and Crafty's own validation checks pass it, because every
check is trivially satisfied at zero.

That asymmetry is **not repaired here**, and the reason is that every available
repair is worse: reading stderr breaks refusal 1, and a Crafty-side connectivity
pre-check would be new domain logic added asymmetrically to make one provider
imitate another. It is recorded as a measured property of provider substitution.
See ``docs/milestones/heterogeneous-ngspice-evidence.md``.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import ModelReference, ScientificProblem
from ...scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from ...scientific.results.result import ScientificResult
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.results.validation import (
    ValidationCheck,
    ValidationOutcome,
    ValidationReport,
)
from ...scientific.solvers.capability import SolverCapability
from ...scientific.solvers.admission import require_agreement, require_finite
from ...scientific.solvers.protocol import (
    DeclaredSupport,
    ConvergenceState,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from ...scientific.units.quantity import Quantity
from .dc import (
    ELECTRICAL_DC_LINEAR,
    DCCircuit,
    assemble,
    assumptions_for_models,
    build_dc_problem,
    dc_solver_capabilities,
    models_for_circuit,
    verify_problem_matches_circuit,
)
from .dc.components import CURRENT_UNIT, POWER_UNIT, VOLTAGE_UNIT
from .dc.solver import NODE_VOLTAGE_METRIC, SOURCE_CURRENT_METRIC
from .dc.validation import DCValidationSettings, build_validation_report
from .dc_realizations import realizations_for_models

__all__ = [
    "DEFAULT_INVOCATION",
    "NGSPICE_SOLVER_ID",
    "NgspiceExecutionFailure",
    "NgspiceInvocation",
    "NgspiceDCSolver",
    "NgspiceUnavailable",
    "build_netlist",
    "parse_print_output",
    "solve_circuit_with_ngspice",
]

NGSPICE_SOLVER_ID = "engcore.electrical.dc.ngspice"

#: Printed significant digits requested from the provider. ngspice's default
#: `print` format emits 6-7 significant digits, which would bound the achievable
#: agreement at ~1e-6 and make the *text channel* — rather than the arithmetic —
#: the limit of the equivalence claim. At 12 the provider emits 13 significant
#: digits and the transport stops being the bound.
NUMDGT = 12


# =====================================================================
# Failure — an execution concern, not a scientific one
# =====================================================================

class NgspiceProviderError(Exception):
    """Base for every way the external provider can fail to deliver.

    Inherits ``Exception`` and **not** ``ScientificCoreError``, deliberately.
    ``engcore.data`` draws the same line for ``BulkDataError``: a store being
    unreachable is not a scientific error, and neither is a solver process
    failing to run. Collapsing them would make "the provider was not installed"
    indistinguishable from "the science does not hold", which is the exact
    conflation this milestone exists to prevent.
    """


class NgspiceUnavailable(NgspiceProviderError):
    """The provider could not be launched at all."""


class NgspiceExecutionFailure(NgspiceProviderError):
    """The provider ran and did not deliver what was asked.

    Covers a non-zero exit, unparsable output, and **any requested quantity
    absent from the output**. That last case is a provider failure rather than a
    scientific one because the adapter genuinely cannot tell "absent because the
    solve had no unique solution" from "absent because the adapter asked for a
    name this provider does not define". An ambiguous absence is reported, never
    interpreted.
    """


# =====================================================================
# Invocation — configuration, never a scientific record
# =====================================================================

@dataclass(frozen=True)
class NgspiceInvocation:
    """How to reach the provider on this machine. **Runtime, not science.**

    Holds an argv prefix rather than a path, because on this machine ngspice is
    not directly executable from Windows at all: it is reached as
    ``wsl.exe -e ngspice``. A single ``executable_path`` field could not express
    that, and inventing one would have quietly assumed a portability this
    milestone has not earned.

    Nothing here is ever serialized into a scientific record. This object is an
    argument, in the same way a ``BulkDataStore`` holds locations while
    ``ScientificDataReference`` holds none.
    """

    command: tuple[str, ...] = ("wsl.exe", "-e", "ngspice")
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        command = tuple(str(part) for part in self.command)
        if not command:
            raise NgspiceUnavailable(
                "an ngspice invocation requires at least one argv element"
            )
        object.__setattr__(self, "command", command)
        if not (self.timeout_seconds > 0.0):
            raise NgspiceUnavailable("timeout must be strictly positive")

    @classmethod
    def from_environment(cls) -> "NgspiceInvocation":
        """Read ``CRAFTY_NGSPICE_ARGV`` if set, else the default.

        Discovery through the environment is infrastructure behaviour. It is
        what makes relocating the provider a configuration change rather than a
        change to any scientific record.
        """
        raw = os.environ.get("CRAFTY_NGSPICE_ARGV", "").strip()
        if not raw:
            return cls()
        return cls(command=tuple(shlex.split(raw)))

    def run(self, netlist: str) -> subprocess.CompletedProcess:
        """Feed a netlist on stdin and capture the result.

        stdin rather than a temp file, deliberately: no filesystem path crosses
        the process boundary, so there is nothing to translate between host and
        guest conventions and nothing machine-specific to leak.
        """
        try:
            return subprocess.run(
                [*self.command, "-b"],
                input=netlist,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise NgspiceUnavailable(
                f"could not launch the ngspice provider as {self.command!r}: "
                f"{exc}. This is an execution failure, not a scientific one"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise NgspiceExecutionFailure(
                f"the ngspice provider did not return within "
                f"{self.timeout_seconds}s"
            ) from exc

    def probe_version(self) -> str:
        """The provider's own reported version, read at run time.

        Never hard-coded. A pinned string would make provenance lie the moment
        the binary changed, and provenance that can lie is worse than provenance
        that is absent.
        """
        try:
            done = subprocess.run(
                [*self.command, "--version"],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise NgspiceUnavailable(
                f"could not launch the ngspice provider as {self.command!r}"
            ) from exc
        # stdout only, anchored to a line start, and a character class that
        # stops at punctuation. An earlier form searched `stdout + stderr`
        # with `ngspice-(\S+)`, which takes the FIRST match anywhere — so a
        # preceding diagnostic mentioning `ngspice-` captured that fragment
        # instead of the banner, and `ngspice-42,` yielded the version string
        # `"42,"`. This value becomes part of a serialized SolverIdentity and
        # participates in ExecutionBinding.key, so a corrupt capture is a
        # corrupt identity.
        match = re.search(
            r"^\s*\**\s*ngspice-([0-9][A-Za-z0-9._+~-]*)",
            done.stdout,
            re.MULTILINE,
        )
        if not match:
            raise NgspiceExecutionFailure(
                "the provider did not report a recognisable ngspice version"
            )
        return match.group(1)


DEFAULT_INVOCATION = NgspiceInvocation()


# =====================================================================
# Translation: Crafty circuit -> provider syntax
# =====================================================================

@dataclass(frozen=True)
class _Netlist:
    """A compiled netlist plus the naming map needed to read the answer back.

    ``PreparedSolve.payload`` is documented as the home for exactly this — its
    docstring names "a compiled netlist" as an example — so this is not a new
    concept, it is the existing one being used for the case it anticipated.
    """

    text: str
    node_names: Mapping[str, str]        # Crafty node id -> provider node
    resistor_names: Mapping[str, str]    # Crafty component id -> provider element
    source_names: Mapping[str, str]
    requested: tuple[str, ...]           # provider expressions asked for


def _provider_names(circuit: DCCircuit) -> _Netlist:
    """Assign provider-legal names, deterministically, by sorted Crafty id.

    Crafty node and component ids are arbitrary strings. SPICE has its own
    lexical rules — a datum that must be node ``0``, element names that must
    begin with a type letter — and escaping Crafty's ids into them would be a
    guess about which characters this provider tolerates.

    So nothing is escaped: names are **assigned**. Every Crafty identity maps to
    an index-derived provider name, the map travels with the prepared solve, and
    the answer is read back through it. Collisions are impossible by
    construction, and no Crafty identifier ever has to be SPICE-legal.
    """
    reference = circuit.reference_node
    others = sorted(n for n in circuit.node_ids if n != reference)
    nodes = {reference: "0"}
    nodes.update({node: f"n{i}" for i, node in enumerate(others)})

    resistors = {
        r.component_id: f"r{i}"
        for i, r in enumerate(sorted(circuit.resistors, key=lambda c: c.component_id))
    }
    sources = {
        s.component_id: f"v{i}"
        for i, s in enumerate(
            sorted(circuit.voltage_sources, key=lambda c: c.component_id)
        )
    }
    return _Netlist("", nodes, resistors, sources, ())


def build_netlist(circuit: DCCircuit) -> _Netlist:
    """Emit provider syntax for one circuit. Pure and deterministic.

    The same circuit always produces byte-identical text, which is what makes
    the translation testable without running anything.
    """
    if circuit.current_sources:
        raise InvalidScientificProblem(
            "this adapter emits resistors and ideal voltage sources only; the "
            "circuit declares a current source, and emitting an element whose "
            "translation has not been exercised would be a guess"
        )
    names = _provider_names(circuit)
    lines = [f"crafty {circuit.circuit_id}"]

    for source in sorted(circuit.voltage_sources, key=lambda c: c.component_id):
        lines.append(
            f"{names.source_names[source.component_id]} "
            f"{names.node_names[source.positive_node]} "
            f"{names.node_names[source.negative_node]} "
            f"DC {source.voltage.magnitude_in(VOLTAGE_UNIT):.17g}"
        )
    for resistor in sorted(circuit.resistors, key=lambda c: c.component_id):
        lines.append(
            f"{names.resistor_names[resistor.component_id]} "
            f"{names.node_names[resistor.node_a]} "
            f"{names.node_names[resistor.node_b]} "
            f"{resistor.resistance.magnitude_in('ohm'):.17g}"
        )

    requested: list[str] = []
    for node_id in sorted(circuit.node_ids):
        if node_id != circuit.reference_node:
            requested.append(f"v({names.node_names[node_id]})")
    for cid in sorted(names.source_names):
        requested.append(f"i({names.source_names[cid]})")
    for cid in sorted(names.resistor_names):
        requested.append(f"@{names.resistor_names[cid]}[i]")
        requested.append(f"@{names.resistor_names[cid]}[p]")

    lines += [
        ".op",
        ".control",
        f"set numdgt={NUMDGT}",
        "run",
        "print " + " ".join(requested),
        ".endc",
        ".end",
        "",
    ]
    return _Netlist(
        text="\n".join(lines),
        node_names=names.node_names,
        resistor_names=names.resistor_names,
        source_names=names.source_names,
        requested=tuple(requested),
    )


# =====================================================================
# Translation: provider output -> numbers
# =====================================================================

_PRINT_LINE = re.compile(
    r"^\s*(?P<name>[^\s=]+)\s*=\s*(?P<value>[-+0-9.eEnaif]+)\s*$"
)


def parse_print_output(stdout: str) -> dict[str, float]:
    """Every ``name = value`` line the provider printed, lower-cased.

    Names are lower-cased because ngspice echoes them that way regardless of how
    they were written — SPICE is case-insensitive. That is provider syntax, and
    normalising it is the adapter's job precisely so that nothing above this
    layer has to know it.

    A line that is not of this shape is skipped rather than raising: ngspice
    interleaves banners, timing and memory statistics with the values, and none
    of that is an error.
    """
    values: dict[str, float] = {}
    for line in stdout.splitlines():
        match = _PRINT_LINE.match(line)
        if not match:
            continue
        try:
            values[match.group("name").strip().lower()] = float(
                match.group("value")
            )
        except ValueError:
            continue
    return values


# =====================================================================
# The solver
# =====================================================================

@dataclass(frozen=True)
class PreparedNgspiceSolve:
    """The circuit, its compiled netlist and the invocation that will run it."""

    circuit: DCCircuit
    netlist: _Netlist
    invocation: NgspiceInvocation


class NgspiceDCSolver(DeclaredSupport):
    """Satisfies ``ScientificSolver``, executed by a process Crafty did not write.

    Every stage of the protocol keeps its meaning: ``prepare`` compiles provider
    input, ``solve`` returns uninterpreted backend output, ``extract_metrics``
    re-enters the unit-aware world, and ``validate`` is **the native domain's own
    ``build_validation_report``** — the same function, over the same metrics,
    applying the same physical checks. The validity authority does not change
    when the provider does, which is the point.
    """

    def __init__(
        self,
        invocation: NgspiceInvocation | None = None,
        settings: SolverSettings | None = None,
    ) -> None:
        self.invocation = invocation or NgspiceInvocation.from_environment()
        self.settings = settings or SolverSettings(
            options={"numdgt": NUMDGT, "analysis": "op"}
        )
        self._circuits: dict[str, DCCircuit] = {}
        self._version: str | None = None

    # -- identity ---------------------------------------------------------
    @property
    def version(self) -> str:
        """Read from the provider once, then reused within this solver."""
        if self._version is None:
            self._version = self.invocation.probe_version()
        return self._version

    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(
            solver_id=NGSPICE_SOLVER_ID,
            version=self.version,
            backend="ngspice",
        )

    @property
    def capabilities(self) -> frozenset[SolverCapability]:
        """The same capabilities the native solver declares.

        Not a coincidence and not a copy for convenience: both solvers execute
        the same realization, whose ``required_solver_capabilities`` is one set.
        A provider that declared different capabilities for the same computation
        would be claiming the computation is different.
        """
        return dc_solver_capabilities()

    # -- binding ----------------------------------------------------------
    def bind_circuit(self, circuit: DCCircuit, problem_id: str) -> None:
        if not isinstance(circuit, DCCircuit):
            raise InvalidScientificProblem("bind_circuit expects a DCCircuit")
        self._circuits[str(problem_id)] = circuit

    #: What this solver is for. The core compares.
    #:
    #: ``served_models`` is deliberately empty and the real discriminator is in
    #: :meth:`additional_support_gap`. This adapter does not implement a fixed
    #: list of models; it implements *any* model that has a declared MNA
    #: realization in this domain, and asking "does the problem name one of
    #: mine" would be the wrong question in both directions -- it would accept
    #: a named model with no realization and reject a realized one this list
    #: had not been updated for.
    serves_capabilities = frozenset({ELECTRICAL_DC_LINEAR.name})
    served_models = ()

    def additional_support_gap(self, problem) -> tuple[str, ...]:
        """Every model named must have a declared realization in this domain.

        Capability coverage alone is not the right question, and an earlier
        form that asked only that was wrong in two ways: it answered yes for a
        problem declaring no capabilities at all (the empty set is a subset of
        anything -- now the core's ``serves_capabilities`` check), and yes for
        a circuit containing a current source, which :func:`build_netlist` then
        refuses. A solver that answers yes and then raises has broken the
        protocol's own contract: *"True when this solver can legitimately
        handle the problem ... never by attempting a solve"*.

        Conditioning on realizations is not a proxy for which elements this
        adapter can emit; it is the same fact stated scientifically. A model
        with no MNA realization record is a model whose computation this
        adapter cannot claim to perform.
        """
        if not problem.models:
            return ("the problem names no model, so nothing is realized here",)
        realized = {
            r.model.model_id for r in realizations_for_models(problem.models)
        }
        unrealized = sorted(
            {model.model_id for model in problem.models} - realized
        )
        if unrealized:
            return (
                f"{unrealized} have no declared MNA realization in this "
                f"domain, so this adapter cannot claim to perform their "
                f"computation",
            )
        return ()

    # -- lifecycle --------------------------------------------------------
    def prepare(self, problem: ScientificProblem) -> PreparedSolve:
        circuit = self._circuits.get(problem.problem_id)
        if circuit is None:
            raise InvalidScientificProblem(
                f"no circuit is bound to problem {problem.problem_id!r}; call "
                f"bind_circuit first"
            )
        # The same guard the native path runs, for the same reason: a result
        # whose provenance contradicts the circuit that produced it is worse
        # than no result.
        verify_problem_matches_circuit(problem, circuit)
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=self.settings,
            payload=PreparedNgspiceSolve(
                circuit=circuit,
                netlist=build_netlist(circuit),
                invocation=self.invocation,
            ),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        """Run the provider. Uninterpreted output in, uninterpreted output out."""
        state: PreparedNgspiceSolve = prepared.payload
        started = time.perf_counter()
        done = state.invocation.run(state.netlist.text)
        elapsed = time.perf_counter() - started

        if done.returncode != 0:
            raise NgspiceExecutionFailure(
                f"the ngspice provider exited {done.returncode}. This is a "
                f"provider execution failure and is not a statement about the "
                f"science: no result is synthesised. Provider output:\n"
                f"{(done.stdout or '')[-2000:]}\n{(done.stderr or '')[-2000:]}"
            )

        values = parse_print_output(done.stdout)
        missing = [q for q in state.netlist.requested if q.lower() not in values]
        if missing:
            raise NgspiceExecutionFailure(
                f"the ngspice provider returned without "
                f"{len(missing)} requested quantit(ies): {sorted(missing)}. "
                f"An absent quantity is ambiguous — the adapter cannot tell a "
                f"solve that produced nothing from a name this provider does "
                f"not define — so it is reported, not interpreted"
            )

        return RawSolverOutput(
            # NOT derived from the exit code and NOT derived from any warning
            # text. The complete requested set was obtained; that, and only
            # that, is what is being reported.
            convergence=ConvergenceState.CONVERGED,
            values=values,
            # NOT 1. The provider was never asked how many iterations it
            # took, and RawSolverOutput is "what the numerical backend
            # actually returned". None is the honest value the field permits.
            iterations=None,
            wall_seconds=elapsed,
            # Verbatim, uninterpreted, never branched on.
            warnings=tuple(
                line
                for line in (done.stderr or "").splitlines()
                if line.strip()
            ),
            diagnostics={"returncode": done.returncode},
        )

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> dict[str, Quantity]:
        """Provider numbers become unit-carrying Crafty metrics.

        The metric names are the **native domain's**, not the provider's. A
        consumer of this result — including the electro-thermal coupling loop —
        cannot tell from the metric namespace which solver produced it, and that
        is the substitution working.
        """
        state: PreparedNgspiceSolve = prepared.payload
        circuit = state.circuit
        netlist = state.netlist
        values = raw.values

        def provider(expression: str) -> float:
            return values[expression.lower()]

        voltages: dict[str, float] = {circuit.reference_node: 0.0}
        for node_id in circuit.node_ids:
            if node_id != circuit.reference_node:
                voltages[node_id] = provider(f"v({netlist.node_names[node_id]})")
        # Admitted before anything is derived from them. The element gate below
        # reconciles three channels against each other and against a declared
        # resistance; a node potential feeds that gate and was never checked on
        # its own, so a NaN node voltage reached the gate as an operand rather
        # than as a value the gate was inspecting. Every provider number this
        # method turns into a metric passes through a finiteness refusal now.
        require_finite(
            voltages,
            error=NgspiceExecutionFailure,
            source="the provider's node voltages",
        )

        metrics: dict[str, Quantity] = {}
        for node_id, value in voltages.items():
            metrics[f"{NODE_VOLTAGE_METRIC}:{node_id}"] = Quantity(
                value, VOLTAGE_UNIT
            )

        total_dissipation = 0.0
        for resistor in circuit.resistors:
            cid = resistor.component_id
            element = netlist.resistor_names[cid]
            current = provider(f"@{element}[i]")
            power = provider(f"@{element}[p]")
            # Derived from the provider's own node voltages, exactly as the
            # native path derives it from its own solution vector.
            v_ab = voltages[resistor.node_a] - voltages[resistor.node_b]
            # THE ADMISSION GATE. Nothing downstream may see a power this
            # relation rejects — see _admit_element_power.
            self._admit_element_power(
                component_id=cid,
                v_drop=v_ab,
                current=current,
                power=power,
                ohms=resistor.resistance.magnitude_in("ohm"),
            )
            total_dissipation += power
            metrics[f"resistor_voltage:{cid}"] = Quantity(v_ab, VOLTAGE_UNIT)
            metrics[f"resistor_current:{cid}"] = Quantity(current, CURRENT_UNIT)
            metrics[f"resistor_power:{cid}"] = Quantity(power, POWER_UNIT)

        delivered = 0.0
        for source in circuit.voltage_sources:
            cid = source.component_id
            current = provider(f"i({netlist.source_names[cid]})")
            require_finite(
                {f"source_current:{cid}": current},
                error=NgspiceExecutionFailure,
                source="the provider's source current channel",
            )
            terminal = (
                voltages[source.positive_node] - voltages[source.negative_node]
            )
            absorbed = terminal * current
            delivered -= absorbed
            metrics[f"{SOURCE_CURRENT_METRIC}:{cid}"] = Quantity(
                current, CURRENT_UNIT
            )
            metrics[f"source_power:{cid}"] = Quantity(absorbed, POWER_UNIT)

        if circuit.resistors:
            metrics["total_resistor_dissipation"] = Quantity(
                total_dissipation, POWER_UNIT
            )
        if circuit.voltage_sources:
            metrics["total_source_delivered_power"] = Quantity(
                delivered, POWER_UNIT
            )
        return metrics

    #: Absolute and relative slack for the admission relations below. Both
    #: sides are computed in double precision from values the provider printed
    #: to 13 significant digits, so agreement is expected near machine epsilon;
    #: `1e-9` is the DC domain's own tolerance and is loose against that by
    #: orders of magnitude, while still catching any convention error — a sign
    #: flip, a factor of two, absorbed-versus-delivered — by orders more.
    ADMISSION_ATOL = 1e-9
    ADMISSION_RTOL = 1e-9

    @classmethod
    def _admit_element_power(
        cls, *, component_id: str, v_drop: float, current: float,
        power: float, ohms: float,
    ) -> None:
        """Refuse a provider element power that its own voltage and current deny.

        **Why this raises instead of being reported.** ``resistor_power:<id>``
        is not an ordinary metric: it is the endpoint the electro-thermal
        composition transports into ``heat_input``. A wrong value there is not a
        wrong number in a report — it is wrong physics entering a coupled loop
        that will converge confidently around it.

        That was measured, not assumed. A provider whose power channel used a
        different convention produced ``validation_status = FAIL`` on the
        electrical result **and the coupled loop transported it anyway**,
        converging to a temperature 18.05 K away from the truth. The loop reads
        ``result.value(...)``; it does not read validation reports, and it is
        not its job to. A check whose only effect is a field nothing consults is
        not a guard.

        So admission happens here, at the boundary the contract describes as
        where numeric output "re-enters the unit-aware scientific world". A
        refusal is a :class:`NgspiceExecutionFailure` — the existing category
        for *the provider ran and did not deliver what was asked* — so no
        ``ScientificResult`` is synthesised and there is nothing downstream to
        transport. It is **not** a scientific verdict: Crafty's own
        ``build_validation_report`` remains the sole authority on whether an
        admitted answer is physically consistent.

        **The two relations, and why neither is self-comparison.**
        ngspice reports node potentials, element currents and element powers on
        three *separate* output channels (``v(...)``, ``@r[i]``, ``@r[p]``), and
        the resistance is Crafty's own declaration, never the provider's:

        1. ``I ≈ V_drop / R`` — Ohm's law, anchoring the provider's current
           channel to a quantity **Crafty declared**. Catches a current sign or
           scale convention error.
        2. ``P ≈ V_drop · I`` — the definition of power, relating the provider's
           power channel to its voltage and current channels. Catches a power
           convention error, including absorbed-versus-delivered.

        Neither compares the power against itself through another
        representation: relation 2's right-hand side contains no power channel
        at all, and relation 1's contains neither current nor power.

        **The sign convention, decided explicitly.** ``build_netlist`` emits
        ``R<i> <node_a> <node_b> <ohms>`` in the Crafty circuit's own terminal
        order, so the provider's ``@r[i]`` is positive when current flows
        ``node_a -> node_b`` — the same convention as Crafty's
        ``resistor_current``, and measured to agree exactly. ``resistor_power``
        is **absorbed** power, hence non-negative for a passive element with
        ``R > 0``; a negative value means the provider reports delivered power
        and its convention is not the one assumed here. That is checked
        separately, because a sign flip on *both* current and power would
        satisfy relation 2 while inverting the physics.
        """
        # FINITENESS FIRST, and not for tidiness. Both relations below are
        # tolerance comparisons, and `abs(nan - x) > tol` is False -- so a
        # provider returning NaN disagreed with nothing and walked through both
        # of them, and through the sign check underneath, which is also a
        # comparison. Infinity did the same whenever both operands were
        # infinite, because `abs(inf - inf)` is NaN.
        #
        # A comparison cannot detect what is being asked of it here, so the
        # check that can runs first, in the core -- see
        # `engcore.scientific.solvers.admission`, where the rule is stated once
        # for every present and future provider rather than in this method.
        require_finite(
            {
                "v_drop": v_drop,
                "current": current,
                "power": power,
                "resistance": ohms,
            },
            error=NgspiceExecutionFailure,
            source=f"the provider, for element {component_id!r}",
        )

        expected_current = v_drop / ohms
        expected_power = v_drop * current

        require_agreement(
            actual=current,
            expected=expected_current,
            atol=cls.ADMISSION_ATOL,
            rtol=cls.ADMISSION_RTOL,
            error=NgspiceExecutionFailure,
            detail=(
                f"provider element current for {component_id!r} is "
                f"{current:.12g} A, but the provider's own node voltages give "
                f"V_drop/R = {expected_current:.12g} A. The provider's current "
                f"convention is not the one this adapter emits the netlist in; "
                f"no result is synthesised rather than transporting it"
            ),
            operands={"v_drop": v_drop, "resistance": ohms},
        )
        require_agreement(
            actual=power,
            expected=expected_power,
            atol=cls.ADMISSION_ATOL,
            rtol=cls.ADMISSION_RTOL,
            error=NgspiceExecutionFailure,
            detail=(
                f"provider element power for {component_id!r} is "
                f"{power:.12g} W, but V_drop * I from the provider's own "
                f"voltage and current channels gives {expected_power:.12g} W. "
                f"resistor_power is transported into a thermal coupling, so an "
                f"unreconciled value is refused rather than admitted"
            ),
            operands={"v_drop": v_drop, "current": current},
        )
        if power < -cls.ADMISSION_ATOL:
            raise NgspiceExecutionFailure(
                f"provider element power for {component_id!r} is negative "
                f"({power:.12g} W). A passive element absorbs power; a negative "
                f"value means the provider reports delivered rather than "
                f"absorbed power, which is a different convention from the one "
                f"this adapter assumes"
            )

    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        """Crafty's own checks, over the provider's numbers.

        The **same** ``build_validation_report`` the native solver calls: KCL at
        every node, the resistor constitutive relation, the ideal source
        relation, the power balance and the linear-system residual. Whether an
        answer is physically consistent is Crafty's question, and the answer
        must not depend on who computed it.

        Making that literally true required one thing worth naming.
        ``build_validation_report`` takes the native ``PreparedDCSystem`` and a
        solution vector, so the validity authority is coupled to the native
        solver's internal representation and cannot simply be handed a
        provider's numbers. But ``assemble`` is documented as *"pure assembly,
        no solving"* — so Crafty's equations can be built without Crafty solving
        anything, and the provider's answer can be substituted into them.

        That turns the reuse into something stronger than reuse:
        ``linear_system_residual`` now checks **ngspice's solution against
        Crafty's own assembled MNA system**. The external answer is verified
        against the domain's equations rather than merely against itself.
        """
        state: PreparedNgspiceSolve = prepared.payload
        metrics = self.extract_metrics(prepared, raw)
        system = assemble(state.circuit)
        solution = self._solution_vector(system, metrics)
        report = build_validation_report(
            system, solution, metrics, DCValidationSettings()
        )
        return ValidationReport(
            checks=(
                *report.checks,
                self._precondition_check(system),
                self._provider_metric_check(state.circuit, metrics),
            ),
            notes=report.notes,
        )

    @staticmethod
    def _precondition_check(system) -> ValidationCheck:
        """Is the assembled system non-singular — the realization's own precondition?

        **This check exists because the adversarial pass falsified the milestone
        without it**, and the argument belongs where the code is. On a
        structurally singular circuit ngspice returns a complete set of zeros
        with exit 0, and that zero vector is an *exact* solution of ``A x = z``:
        every nodal row balances, the constitutive relation holds as ``0 = 0``,
        and the source row is satisfied. **No check over ``(A, x)`` can detect
        it** — not KCL, not the residual, not the power balance. Only a property
        of ``A`` alone can, and that property is rank.

        The preregistration concluded that every repair was worse than
        disclosure, having enumerated two: reading provider stderr (rightly
        forbidden — provider text entering scientific semantics) and a
        Crafty-side connectivity pre-check (new domain logic, added
        asymmetrically). It missed a third, smaller than both: :func:`assemble`
        is *"pure assembly, no solving"* and ``validate`` **already calls it**,
        so the matrix is in hand. Testing its rank is neither provider text nor
        connectivity analysis nor new domain logic — it is the realization's own
        declared precondition, checked on an object the adapter builds anyway.

        Note what it deliberately does **not** touch: ``convergence``. The
        provider genuinely returned a complete set, so ``CONVERGED`` stays an
        honest report of what the backend did. What becomes ``FAIL`` is the
        *scientific* verdict — which is the sharper separation, and it makes the
        two paths agree on the science while differing only on the numerics.
        """
        import numpy as np

        rank = int(np.linalg.matrix_rank(system.matrix))
        satisfied = rank == system.size
        return ValidationCheck(
            name="realization_precondition_non_singular",
            outcome=ValidationOutcome.PASS if satisfied else ValidationOutcome.FAIL,
            residual=float(system.size - rank),
            tolerance=0.0,
            detail=(
                f"rank(A) = {rank} of {system.size}. The MNA realization "
                f"declares that the assembled system is non-singular; outside "
                f"that precondition a returned solution is one of infinitely "
                f"many and is not a scientific answer, however exactly it "
                f"satisfies the equations."
            ),
        )

    @staticmethod
    def _provider_metric_check(circuit, metrics) -> ValidationCheck:
        """Record, in the report, that the admission relations were satisfied.

        This is the *reporting* half of :meth:`_admit_element_power`. The gate
        already refused anything that violates the relations, so by the time a
        report exists this check can only pass — and that is precisely why it is
        still here: a reader of a stored result should be able to see **that**
        the provider's power was reconciled, and against what, without having to
        know that an exception would have prevented the record existing.

        An earlier form of this milestone had only this check and no gate. It
        detected a corrupted provider power correctly and changed nothing: the
        coupling loop reads values, not reports, and converged 18.05 K off.
        """
        worst = 0.0
        for resistor in circuit.resistors:
            cid = resistor.component_id
            ohms = resistor.resistance.magnitude_in("ohm")
            v_ab = metrics[f"resistor_voltage:{cid}"].magnitude_in(VOLTAGE_UNIT)
            current = metrics[f"resistor_current:{cid}"].magnitude_in(CURRENT_UNIT)
            power = metrics[f"resistor_power:{cid}"].magnitude_in(POWER_UNIT)
            worst = max(
                worst,
                abs(current - v_ab / ohms),      # I  vs  V/R   (declared R)
                abs(power - v_ab * current),     # P  vs  V*I   (three channels)
            )
        tolerance = NgspiceDCSolver.ADMISSION_ATOL
        return ValidationCheck(
            name="provider_element_metric_consistency",
            outcome=(
                ValidationOutcome.PASS if worst <= tolerance
                else ValidationOutcome.FAIL
            ),
            residual=worst,
            tolerance=tolerance,
            detail=(
                f"provider element current against V_drop/R with R declared by "
                f"Crafty, and provider element power against V_drop*I from the "
                f"provider's own voltage and current channels: worst deviation "
                f"{worst:.3e}. resistor_power is a declared coupling endpoint, "
                f"so a violation is refused at admission and never reaches a "
                f"result; this check records that the reconciliation held."
            ),
        )


    @staticmethod
    def _solution_vector(system, metrics: Mapping[str, Quantity]):
        """The provider's answer, laid out in Crafty's own unknown ordering.

        ``PreparedDCSystem`` documents that layout: node voltages in
        ``node_order``, then one branch current per voltage source in
        ``source_order``. Reconstructing it is pure re-indexing — no value is
        recomputed, and nothing is inferred.
        """
        import numpy as np

        vector = np.zeros(system.size, dtype=np.float64)
        for index, node_id in enumerate(system.node_order):
            vector[index] = metrics[
                f"{NODE_VOLTAGE_METRIC}:{node_id}"
            ].magnitude_in(VOLTAGE_UNIT)
        for offset, source_id in enumerate(system.voltage_source_order):
            vector[system.n_nodes + offset] = metrics[
                f"{SOURCE_CURRENT_METRIC}:{source_id}"
            ].magnitude_in(CURRENT_UNIT)
        return vector


# =====================================================================
# Orchestration, mirroring solve_circuit
# =====================================================================

def solve_circuit_with_ngspice(
    circuit: DCCircuit,
    *,
    run_id: str,
    solver: NgspiceDCSolver | None = None,
    problem: ScientificProblem | None = None,
    software_version: str = "engcore.domains.electrical.ngspice/0.1.0",
    parent_run_id: str | None = None,
) -> ScientificResult:
    """The full contract lifecycle for one circuit, run by the external provider.

    Deliberately the same shape as the native ``solve_circuit``, and deliberately
    a *separate* function rather than a flag on it: the DC package is left
    byte-unchanged so that the native path remains a clean control for the
    comparison this milestone measures.

    The provenance it writes carries ``bindings`` — model -> realization ->
    solver — which the native ``solve_circuit`` does not, because it predates
    ``MODEL0-R``. The realization records are shared with the native path; only
    the solver differs.
    """
    solver = solver or NgspiceDCSolver()
    problem = problem or build_dc_problem(circuit)
    verify_problem_matches_circuit(problem, circuit)
    solver.bind_circuit(circuit, problem.problem_id)

    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    report = solver.validate(prepared, raw)

    active_models = models_for_circuit(circuit)
    model_identities = tuple((m.model_id, m.version) for m in active_models)
    assumptions = assumptions_for_models(active_models)

    realizations = {r.model.model_id: r for r in realizations_for_models(active_models)}
    identity = solver.identity
    bindings = tuple(
        ExecutionBinding(
            model=ModelReference(model.model_id, model.version),
            realization=(
                realizations[model.model_id].reference()
                if model.model_id in realizations
                else None
            ),
            solver=identity,
        )
        for model in active_models
    )

    inputs: dict[str, Quantity] = {}
    for resistor in circuit.resistors:
        inputs[f"R:{resistor.component_id}"] = resistor.resistance
    for source in circuit.voltage_sources:
        inputs[f"Vs:{source.component_id}"] = source.voltage

    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version=software_version,
        bindings=bindings,
        inputs=inputs,
        assumptions=assumptions,
        tolerances=solver.settings.tolerances,
        parent_run_id=parent_run_id,
        # Deliberately no environment, no executable path, no argv, no netlist
        # and no provider stdout. The provider's *version* travels in
        # SolverIdentity, which is where execution provenance belongs; where the
        # binary happens to live is an execution fact and must not change what
        # this result means.
        metadata={
            "circuit_id": circuit.circuit_id,
            "circuit_fingerprint": circuit.fingerprint(),
        },
    )

    return ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=model_identities,
        solver=identity,
        convergence=raw.convergence,
        validation=report,
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification is performed by this provider "
                "adapter; element values are taken as exact"
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
