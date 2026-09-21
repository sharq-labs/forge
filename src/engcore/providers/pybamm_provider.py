"""PyBaMM as an external scientific provider. Forge does not own these equations.

What PyBaMM owns
----------------
The battery equations, their numerical solution, and the implementation of
every model named in :data:`MODEL_CATALOGUE`. Nothing in this module restates a
PyBaMM equation, re-derives one, or wraps one as a Forge-native equation. The
adapter translates a Forge request into PyBaMM's own API and translates what
comes back into Forge's canonical vocabulary. If a number here is wrong because
the physics is wrong, it is wrong in PyBaMM.

What Forge owns
---------------
Everything that decides whether the number may be relied on: which model was
selected and why (:data:`MODEL_CATALOGUE`), which parameters governed it and on
whose authority (:class:`ParameterAuthority`), whether the model's declared
applicability covers the cell being asked about (:meth:`ParameterAuthority.screen`),
what the answer is called (:data:`CANONICAL_QOIS`), what ran
(:class:`~engcore.providers.contract.ProviderExecutionReceipt`), and whether any
of it amounts to evidence -- which happens downstream, in the same credibility
and claim path a native solve travels.

THE ORDER MATTERS, AND IT IS NOT A PERFORMANCE CHOICE
------------------------------------------------------
Applicability is screened **before** PyBaMM is called. ``CLAUDE.md`` states the
invariant -- *model applicability precedes evidence-bearing execution* -- and
the reason is not that a refused solve wastes time. It is that a solve that has
already happened is a number somebody can read. Screening afterwards produces a
result and a refusal at the same moment, and every system that has ever done
that has eventually shipped the number.

The consequence is visible and intended: ``SPMe`` with the ``Chen2020``
parameter set solves in a quarter of a second and describes a 5 A.h NMC811
pouch cell. Asked about a 2 A.h 18650 from the NASA archive, this adapter
returns ``MODEL_NOT_APPLICABLE`` and PyBaMM is never called. The provider did
not fail. The science was declined.

Model selection is explicit (P13)
----------------------------------
``request.model_key`` names one model from the allowlist. There is no
recommender, no scoring, no automatic fallback to a cheaper model when an
expensive one refuses. A fallback would mean the system answering a question
the caller did not ask with a model the caller did not choose, and recording
neither.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from ..data.store import BulkDataStore, store_values
from ..domains.battery.context import CELL_TEMPERATURE
from ..domains.battery.flagship import (
    OPEN_CIRCUIT_VOLTAGE_METRIC,
    STATE_OF_CHARGE_METRIC,
    TERMINAL_VOLTAGE_METRIC,
)
from ..scientific.ir.problem import ModelReference
from ..scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from ..scientific.results.result import ScientificResult
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.results.validation import (
    ValidationCheck,
    ValidationOutcome,
    ValidationReport,
)
from ..scientific.solvers.protocol import ConvergenceState, SolverIdentity
from ..scientific.units.quantity import Quantity
from .contract import (
    ExecutionOutcome,
    ProviderCapability,
    ProviderExecutionReceipt,
    ProviderIdentity,
    ProviderRequest,
    ProviderResult,
    digest_of,
    unavailable_result,
)
from .environment import EnvironmentIdentity

PROVIDER_NAME = "pybamm"
ADAPTER_VERSION = "engcore.providers.pybamm_provider/0.1.0"

#: Canonical Forge QoI names this adapter can produce, each with the PyBaMM
#: variable it is read from and the unit Forge states it in.
#:
#: The Forge names are imported from the battery domain wherever the domain
#: already has one, so that a PyBaMM terminal voltage and a native terminal
#: voltage are the *same* name and a consumer cannot tell them apart. ``current``
#: and ``time`` have no domain constant because the native models take them as
#: inputs rather than producing them; they are named here and nowhere else.
CURRENT_METRIC = "current"
TIME_METRIC = "time"

CANONICAL_QOIS: Mapping[str, tuple[str, str]] = {
    TERMINAL_VOLTAGE_METRIC: ("Voltage [V]", "volt"),
    CURRENT_METRIC: ("Current [A]", "ampere"),
    TIME_METRIC: ("Time [s]", "second"),
    STATE_OF_CHARGE_METRIC: ("SoC", "dimensionless"),
    CELL_TEMPERATURE: ("Cell temperature [K]", "kelvin"),
    OPEN_CIRCUIT_VOLTAGE_METRIC: ("Open-circuit voltage [V]", "volt"),
}

#: Forge's sign convention, declared rather than inherited. Positive current is
#: **discharge**, which is what ``domains.battery`` means by ``I`` in
#: ``z_end = z_0 - I t / (eta Q)`` and what PyBaMM means by ``Current [A]``.
#: They agree; the agreement is recorded because a convention that is merely
#: true is a convention that silently flips the day one side changes.
DISCHARGE_POSITIVE = True


# =====================================================================
# P3 — fidelity as an explicit axis, and deliberately not a ranking
# =====================================================================

@dataclass(frozen=True)
class PyBaMMModelSpec:
    """One allowlisted PyBaMM model, described in terms Forge can reason with.

    ``fidelity_class`` is a **label, not an order**. Nothing in this module
    compares two fidelity classes, and there is no "higher is better" anywhere:
    DFN resolves solid diffusion and electrolyte transport that SPM does not,
    and on a 1 C constant-current discharge of a well-characterised cell that
    resolution may buy nothing while costing two orders of magnitude. Which
    model has enough evidence for a given claim is a question for the trust
    path, which sees the validation evidence; it is not a property of the model
    that could be written down here.

    ``physics_excluded`` is the field that does work. A model's exclusions are
    what make a refusal statable: the Sprint 3 recovery's holdout failure was
    diagnosed as missing impedance growth precisely because the native model
    declared that exclusion, and an external model with no exclusion list could
    not have been diagnosed at all.
    """

    model_key: str
    family: str
    fidelity_class: str
    constructor: str
    physics_included: tuple[str, ...]
    physics_excluded: tuple[str, ...]
    #: Declared, relative, and never used to choose. Measured wall time is
    #: recorded on every receipt, so the declaration can be checked.
    expected_cost_class: str
    declared_applicability: tuple[str, ...]
    produces: frozenset[str]
    #: The OPEN interval the model's charge-state variable is defined on, or
    #: ``None`` when the model has no such variable.
    #:
    #: Measured, not assumed. PyBaMM's equivalent-circuit model carries
    #: ``Maximum SoC`` and ``Minimum SoC`` as termination events, and at a
    #: requested state of exactly 1.0 the event is non-positive at the initial
    #: condition: the solve terminates before its first step and returns a
    #: one-element time vector. That is a property of the model's state
    #: interval, so it is declared here and screened as applicability, rather
    #: than reaching a caller as a provider crash.
    #:
    #: The native Forge cell model does **not** share this limit -- its charge
    #: state is a closed fraction and z = 1 is an ordinary starting point -- so
    #: a run the native model answers and this one declines is a real
    #: difference between two implementations, reported as a refusal and never
    #: repaired by nudging the request.
    state_of_charge_interval: tuple[float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_key": self.model_key,
            "family": self.family,
            "fidelity_class": self.fidelity_class,
            "constructor": self.constructor,
            "physics_included": list(self.physics_included),
            "physics_excluded": list(self.physics_excluded),
            "expected_cost_class": self.expected_cost_class,
            "declared_applicability": list(self.declared_applicability),
            "produces": sorted(self.produces),
            "state_of_charge_interval": (
                None
                if self.state_of_charge_interval is None
                else list(self.state_of_charge_interval)
            ),
        }


_ECM_EXCLUSIONS = (
    "solid-phase diffusion",
    "electrolyte transport",
    "concentration overpotential",
    "irreversible capacity fade",
    "impedance growth with age",
    "lithium plating",
)

_ECHEM_COMMON_EXCLUSIONS = (
    "irreversible capacity fade",
    "impedance growth with age",
    "lithium plating",
    "mechanical degradation",
)

MODEL_CATALOGUE: Mapping[str, PyBaMMModelSpec] = {
    "thevenin_1rc": PyBaMMModelSpec(
        model_key="thevenin_1rc",
        family="equivalent_circuit",
        fidelity_class="lumped_empirical",
        constructor="pybamm.equivalent_circuit.Thevenin",
        physics_included=(
            "open-circuit voltage against state of charge",
            "series ohmic resistance",
            "one RC polarization branch",
            "lumped cell/jig thermal balance",
        ),
        physics_excluded=_ECM_EXCLUSIONS,
        expected_cost_class="milliseconds",
        declared_applicability=(
            "a cell whose OCV(SoC) curve, series resistance and one relaxation "
            "time constant have been characterised on that cell",
        ),
        produces=frozenset(
            {
                TERMINAL_VOLTAGE_METRIC,
                CURRENT_METRIC,
                TIME_METRIC,
                STATE_OF_CHARGE_METRIC,
                CELL_TEMPERATURE,
                OPEN_CIRCUIT_VOLTAGE_METRIC,
            }
        ),
        state_of_charge_interval=(0.0, 1.0),
    ),
    "spm": PyBaMMModelSpec(
        model_key="spm",
        family="single_particle",
        fidelity_class="reduced_order",
        constructor="pybamm.lithium_ion.SPM",
        physics_included=(
            "solid-phase diffusion in one representative particle per electrode",
            "Butler-Volmer interfacial kinetics",
            "open-circuit potentials of both electrodes",
        ),
        physics_excluded=_ECHEM_COMMON_EXCLUSIONS
        + (
            "electrolyte concentration gradients",
            "electrolyte potential gradients",
        ),
        expected_cost_class="tenths of a second",
        declared_applicability=(
            "low to moderate rate, where electrolyte gradients are small",
            "a cell whose electrode materials, geometry and transport "
            "parameters are those of the governing parameter set",
        ),
        produces=frozenset(
            {TERMINAL_VOLTAGE_METRIC, CURRENT_METRIC, TIME_METRIC}
        ),
    ),
    "spme": PyBaMMModelSpec(
        model_key="spme",
        family="single_particle",
        fidelity_class="reduced_order_with_electrolyte",
        constructor="pybamm.lithium_ion.SPMe",
        physics_included=(
            "everything SPM includes",
            "electrolyte concentration and potential, to leading order",
        ),
        physics_excluded=_ECHEM_COMMON_EXCLUSIONS
        + ("through-thickness variation of reaction rate",),
        expected_cost_class="tenths of a second",
        declared_applicability=(
            "low to moderate rate, wider than SPM because electrolyte "
            "gradients are represented",
            "a cell whose electrode materials, geometry and transport "
            "parameters are those of the governing parameter set",
        ),
        produces=frozenset(
            {TERMINAL_VOLTAGE_METRIC, CURRENT_METRIC, TIME_METRIC}
        ),
    ),
    "dfn": PyBaMMModelSpec(
        model_key="dfn",
        family="porous_electrode",
        fidelity_class="full_order",
        constructor="pybamm.lithium_ion.DFN",
        physics_included=(
            "Doyle-Fuller-Newman porous electrode theory",
            "through-thickness solid and electrolyte fields",
            "particle-resolved solid diffusion",
        ),
        physics_excluded=_ECHEM_COMMON_EXCLUSIONS,
        expected_cost_class="seconds",
        declared_applicability=(
            "the widest rate range of the three electrochemical models",
            "a cell whose electrode materials, geometry and transport "
            "parameters are those of the governing parameter set",
        ),
        produces=frozenset(
            {TERMINAL_VOLTAGE_METRIC, CURRENT_METRIC, TIME_METRIC}
        ),
    ),
}

#: The allowlist, as a set, for callers that want to state it (P13).
ALLOWED_MODELS = frozenset(MODEL_CATALOGUE)


# =====================================================================
# P4 — parameter set authority
# =====================================================================

@dataclass(frozen=True)
class CellUnderTest:
    """The physical cell a request is about. Declared by the caller, never guessed.

    The first four fields are required. A request that does not say what cell it
    is about cannot be screened against a parameter set's chemistry, and a
    screen that passed on absent information would be the opposite of a screen.

    ``cell_temperature_k`` is optional and is a **different quantity** from the
    ambient, not a refinement of it. Which one a screen may use is decided by
    the authority's :attr:`ParameterAuthority.temperature_basis`, because a
    validity band measured against cell temperature says nothing about ambient:
    on this repository's own battery corpus a 4 A discharge at 4 degC ambient
    self-heats past 40 degC, and a screen that compared the ambient against a
    cell-temperature band refused it on a quantity the band was never about.
    That was a real defect in the first version of this screen, found by the
    comparison benchmark's counterfactual probe.
    """

    cell_id: str
    chemistry: str
    nominal_capacity_ah: float
    ambient_temperature_k: float
    cell_temperature_k: float | None = None

    def __post_init__(self) -> None:
        for label in ("cell_id", "chemistry"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"a cell under test requires a {label}")
            object.__setattr__(self, label, value)
        for label in ("nominal_capacity_ah", "ambient_temperature_k"):
            value = float(getattr(self, label))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{label} must be finite and positive")
            object.__setattr__(self, label, value)
        if self.cell_temperature_k is not None:
            value = float(self.cell_temperature_k)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("cell_temperature_k must be finite and positive")
            object.__setattr__(self, "cell_temperature_k", value)

    def temperature_on(self, basis: str) -> float | None:
        """The temperature this cell offers on ``basis``, or ``None``.

        ``None`` is refused by the screen rather than replaced by the other
        quantity. Substituting an ambient for a cell temperature is exactly the
        confusion this method exists to prevent.
        """
        if basis == "ambient":
            return self.ambient_temperature_k
        if basis == "cell":
            return self.cell_temperature_k
        raise ValueError(f"unknown temperature basis {basis!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "chemistry": self.chemistry,
            "nominal_capacity_ah": self.nominal_capacity_ah,
            "ambient_temperature_k": self.ambient_temperature_k,
            "cell_temperature_k": self.cell_temperature_k,
        }


#: How far a parameter set's nominal capacity may sit from the cell's before
#: the set is declared to be describing a different cell. Not a tuning knob: a
#: 25 % capacity difference is a different electrode loading, and every
#: transport and kinetic parameter scales with it.
CAPACITY_TOLERANCE = 0.25


@dataclass(frozen=True)
class ParameterAuthority:
    """Who says these parameters, and what cell they describe.

    PyBaMM offers named parameter sets (``Chen2020``, ``Marquis2019``,
    ``ECM_Example``) and arbitrary ``ParameterValues``. Both arrive here through
    one record, because the scientific question is the same for both: *on whose
    authority do these numbers describe this cell?*

    The rule P4 states -- never silently mutate a named set -- is enforced
    structurally rather than by convention: :meth:`derive` is the only way to
    attach overrides, it returns a **new** authority with its own digest and
    ``source="forge_derived"``, and it records the digest of the authority it
    came from. There is no setter and the record is frozen, so a named set
    cannot be edited in place by any caller.

    ``temperature_validity_k`` is the band the authority is prepared to stand
    behind. ``None`` means the authority does not state one, which is UNKNOWN
    and is refused by :meth:`screen` -- not treated as "any temperature".
    """

    authority_id: str
    source: str
    parameter_set_name: str
    defining_provider_version: str
    chemistry: str
    nominal_capacity_ah: float
    temperature_validity_k: tuple[float, float] | None
    #: Which temperature :attr:`temperature_validity_k` is stated against --
    #: ``"ambient"`` or ``"cell"``. Part of the authority because the band is
    #: meaningless without it, and a default of ``"ambient"`` would be a guess
    #: that happens to be wrong for every authority conditioned on the cell.
    temperature_basis: str = "ambient"
    units: Mapping[str, str] = field(default_factory=dict)
    overrides: Mapping[str, Any] = field(default_factory=dict)
    parent_authority_digest: str | None = None
    notes: str = ""

    _SOURCES = ("pybamm_named_set", "forge_derived", "forge_declared")

    def __post_init__(self) -> None:
        for label in (
            "authority_id",
            "source",
            "parameter_set_name",
            "defining_provider_version",
            "chemistry",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"a parameter authority requires a {label}")
            object.__setattr__(self, label, value)
        if self.source not in self._SOURCES:
            raise ValueError(
                f"parameter authority source {self.source!r} is not one of "
                f"{self._SOURCES}"
            )
        capacity = float(self.nominal_capacity_ah)
        if not math.isfinite(capacity) or capacity <= 0.0:
            raise ValueError("nominal_capacity_ah must be finite and positive")
        object.__setattr__(self, "nominal_capacity_ah", capacity)
        band = self.temperature_validity_k
        if band is not None:
            low, high = (float(band[0]), float(band[1]))
            if not (math.isfinite(low) and math.isfinite(high)) or low >= high:
                raise ValueError("temperature_validity_k must be a finite increasing pair")
            object.__setattr__(self, "temperature_validity_k", (low, high))
        if self.temperature_basis not in ("ambient", "cell"):
            raise ValueError(
                f"temperature_basis {self.temperature_basis!r} is neither "
                f"'ambient' nor 'cell'; a validity band whose quantity is not "
                f"named cannot be screened against anything"
            )
        object.__setattr__(
            self, "units", dict(sorted((str(k), str(v)) for k, v in self.units.items()))
        )
        object.__setattr__(
            self,
            "overrides",
            dict(sorted((str(k), v) for k, v in self.overrides.items())),
        )
        if self.overrides and self.source == "pybamm_named_set":
            raise ValueError(
                "a named PyBaMM parameter set carrying overrides is a set that "
                "has been mutated while still claiming the publisher's "
                "authority. Use ParameterAuthority.derive() instead"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "source": self.source,
            "parameter_set_name": self.parameter_set_name,
            "defining_provider_version": self.defining_provider_version,
            "chemistry": self.chemistry,
            "nominal_capacity_ah": self.nominal_capacity_ah,
            "temperature_validity_k": (
                None
                if self.temperature_validity_k is None
                else list(self.temperature_validity_k)
            ),
            "temperature_basis": self.temperature_basis,
            "units": dict(self.units),
            "overrides": {k: _jsonable(v) for k, v in self.overrides.items()},
            "parent_authority_digest": self.parent_authority_digest,
            "notes": self.notes,
        }

    def digest(self) -> str:
        return digest_of(self.to_dict())

    def derive(
        self,
        *,
        authority_id: str,
        overrides: Mapping[str, Any],
        chemistry: str | None = None,
        nominal_capacity_ah: float | None = None,
        temperature_validity_k: tuple[float, float] | None = None,
        notes: str = "",
    ) -> "ParameterAuthority":
        """A new authority that owns these overrides. The parent is unchanged.

        The derived record is ``forge_derived``: the overridden numbers are
        Forge's, not the publisher's, and the publisher must not be cited for
        them. ``parent_authority_digest`` keeps the lineage readable so a
        reviewer can ask what was changed and from what.
        """
        if not overrides:
            raise ValueError(
                "deriving an authority with no overrides would mint a second "
                "identity for the same numbers"
            )
        merged = dict(self.overrides)
        merged.update(overrides)
        return ParameterAuthority(
            authority_id=authority_id,
            source="forge_derived",
            parameter_set_name=self.parameter_set_name,
            defining_provider_version=self.defining_provider_version,
            chemistry=self.chemistry if chemistry is None else chemistry,
            nominal_capacity_ah=(
                self.nominal_capacity_ah
                if nominal_capacity_ah is None
                else nominal_capacity_ah
            ),
            temperature_validity_k=(
                self.temperature_validity_k
                if temperature_validity_k is None
                else temperature_validity_k
            ),
            temperature_basis=self.temperature_basis,
            units=dict(self.units),
            overrides=merged,
            parent_authority_digest=self.digest(),
            notes=notes,
        )

    def screen(self, cell: CellUnderTest) -> tuple[bool, tuple[str, ...]]:
        """Does this authority claim to describe ``cell``? Reasons, always.

        Three declared conditions, and every failure is reported rather than
        short-circuited, because a caller repairing one mismatch needs to know
        about the other two.
        """
        reasons: list[str] = []
        if self.chemistry.strip().lower() != cell.chemistry.strip().lower():
            reasons.append(
                f"chemistry mismatch: the parameter authority describes "
                f"{self.chemistry!r} and the cell under test is "
                f"{cell.chemistry!r}. Electrode open-circuit potentials and "
                f"kinetic parameters are chemistry-specific"
            )
        relative = abs(self.nominal_capacity_ah - cell.nominal_capacity_ah) / max(
            cell.nominal_capacity_ah, 1e-12
        )
        if relative > CAPACITY_TOLERANCE:
            reasons.append(
                f"capacity mismatch: the parameter authority describes a "
                f"{self.nominal_capacity_ah:g} A.h cell and the cell under "
                f"test is {cell.nominal_capacity_ah:g} A.h "
                f"({relative:.0%} apart, limit {CAPACITY_TOLERANCE:.0%})"
            )
        band = self.temperature_validity_k
        if band is None:
            reasons.append(
                "the parameter authority declares no temperature validity "
                "band. That is UNKNOWN, and UNKNOWN is not 'any temperature'"
            )
        else:
            observed = cell.temperature_on(self.temperature_basis)
            if observed is None:
                reasons.append(
                    f"the authority's validity band is stated against the "
                    f"{self.temperature_basis} temperature and the cell under "
                    f"test declares none. The other temperature is a different "
                    f"quantity, not a substitute for it"
                )
            elif not (band[0] <= observed <= band[1]):
                reasons.append(
                    f"{self.temperature_basis} temperature outside the "
                    f"authority's declared band: {observed:g} K is not within "
                    f"[{band[0]:g}, {band[1]:g}] K"
                )
        return (not reasons, tuple(reasons))


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


#: The two PyBaMM named sets this sprint uses, as authorities. Values are what
#: each publication states about the cell it characterises; they are recorded
#: here so that a screen has something to screen against, and they are the
#: reason ``Chen2020`` is refused for an 18650 from the NASA archive.
NAMED_AUTHORITIES: Mapping[str, ParameterAuthority] = {
    "Chen2020": ParameterAuthority(
        authority_id="pybamm.Chen2020",
        source="pybamm_named_set",
        parameter_set_name="Chen2020",
        defining_provider_version="pybamm",
        chemistry="NMC811/graphite-SiOx",
        nominal_capacity_ah=5.0,
        temperature_validity_k=(288.15, 308.15),
        units={"capacity": "ampere_hour", "temperature": "kelvin"},
        notes=(
            "LG M50 21700 cylindrical cell characterised by Chen et al. (2020). "
            "Recorded from the publication's own description of the cell, not "
            "from any Forge measurement"
        ),
    ),
    "ECM_Example": ParameterAuthority(
        authority_id="pybamm.ECM_Example",
        source="pybamm_named_set",
        parameter_set_name="ECM_Example",
        defining_provider_version="pybamm",
        chemistry="unspecified",
        nominal_capacity_ah=100.0,
        temperature_validity_k=None,
        units={"capacity": "ampere_hour", "temperature": "kelvin"},
        notes=(
            "PyBaMM's own demonstration equivalent-circuit parameter set. It "
            "names no chemistry and declares no temperature validity, which is "
            "why it screens as UNKNOWN against any real cell: it is an example, "
            "not a characterisation"
        ),
    ),
}


# =====================================================================
# The request, in Forge's vocabulary
# =====================================================================

@dataclass(frozen=True)
class CurrentProtocol:
    """The load, as Forge states it. Positive is discharge.

    Two shapes, because two exist in this sprint's evidence: a constant current
    for a synthetic or datasheet-style ask, and a sampled profile for a measured
    trajectory. A PyBaMM ``Experiment`` string is deliberately NOT accepted:
    it is provider syntax, and a request written in it could not be put to a
    second provider.
    """

    duration_s: float
    constant_current_a: float | None = None
    times_s: tuple[float, ...] = ()
    currents_a: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        duration = float(self.duration_s)
        if not math.isfinite(duration) or duration <= 0.0:
            raise ValueError("a current protocol needs a finite positive duration")
        object.__setattr__(self, "duration_s", duration)
        sampled = bool(self.times_s) or bool(self.currents_a)
        if (self.constant_current_a is None) == (not sampled):
            raise ValueError(
                "a current protocol is either a constant current or a sampled "
                "profile, never both and never neither"
            )
        if sampled:
            times = tuple(float(v) for v in self.times_s)
            currents = tuple(float(v) for v in self.currents_a)
            if len(times) != len(currents) or len(times) < 2:
                raise ValueError(
                    "a sampled current profile needs matching time and current "
                    "arrays of at least two points"
                )
            if any(b <= a for a, b in zip(times, times[1:])):
                raise ValueError("sampled profile times must be strictly increasing")
            object.__setattr__(self, "times_s", times)
            object.__setattr__(self, "currents_a", currents)
        else:
            object.__setattr__(self, "constant_current_a", float(self.constant_current_a))

    @property
    def is_sampled(self) -> bool:
        return bool(self.times_s)

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_s": self.duration_s,
            "constant_current_a": self.constant_current_a,
            "sample_count": len(self.times_s),
            # The samples themselves are digested rather than listed: a request
            # digest that inlined a 10 Hz trajectory would be unreadable, and
            # the digest is what the identity actually needs.
            "profile_digest": (
                digest_of(
                    {
                        "times_s": list(self.times_s),
                        "currents_a": list(self.currents_a),
                    }
                )
                if self.times_s
                else None
            ),
            "sign_convention": "positive_is_discharge",
        }


def build_request(
    *,
    model_key: str,
    authority: ParameterAuthority,
    cell: CellUnderTest,
    protocol: CurrentProtocol,
    qois: Sequence[str],
    initial_state_of_charge: float,
    solver_options: Mapping[str, Any] | None = None,
) -> ProviderRequest:
    """Assemble a canonical provider request. No PyBaMM vocabulary crosses here."""
    return ProviderRequest(
        capability=ProviderCapability.TIME_SERIES_SIMULATION,
        model_key=model_key,
        parameter_authority=authority.digest(),
        qois=tuple(qois),
        inputs={
            "cell": cell.to_dict(),
            "protocol": protocol.to_dict(),
            "initial_state_of_charge": float(initial_state_of_charge),
        },
        configuration=dict(solver_options or {}),
    )


# =====================================================================
# The provider
# =====================================================================

class PyBaMMProvider:
    """Runs one allowlisted PyBaMM model against one Forge parameter authority.

    Construction takes the authority, the cell and the protocol as *arguments*
    rather than reading them from the request, for the same reason
    ``NgspiceInvocation`` is an argument: a request carries digests, which are
    identity, and identity must not have to be reversible into the objects it
    identifies. The request states what was asked; this object holds what is
    needed to ask it.
    """

    def __init__(
        self,
        *,
        authority: ParameterAuthority,
        cell: CellUnderTest,
        protocol: CurrentProtocol,
        parameter_values_factory=None,
        store: BulkDataStore | None = None,
    ) -> None:
        self._authority = authority
        self._cell = cell
        self._protocol = protocol
        self._factory = parameter_values_factory
        self._store = store
        self._environment = EnvironmentIdentity.capture()

    # -- the ScientificProvider protocol -------------------------------

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAME

    def available(self) -> bool:
        try:
            import pybamm  # noqa: F401
        except Exception:
            return False
        return True

    def capabilities(self) -> frozenset[ProviderCapability]:
        return frozenset({ProviderCapability.TIME_SERIES_SIMULATION})

    def execute(self, request: ProviderRequest) -> ProviderResult:
        """Screen, then run, then translate. In that order, always."""
        digest = request.digest()

        # --- Forge-side screens, before the provider is touched --------
        if request.capability not in self.capabilities():
            return self._refused(
                digest,
                ExecutionOutcome.FORGE_REFUSED,
                f"this provider offers {sorted(c.value for c in self.capabilities())} "
                f"and was asked for {request.capability.value}",
            )
        spec = MODEL_CATALOGUE.get(request.model_key)
        if spec is None:
            return self._refused(
                digest,
                ExecutionOutcome.FORGE_REFUSED,
                f"model {request.model_key!r} is not on the allowlist "
                f"{sorted(ALLOWED_MODELS)}. Selection is explicit and there is "
                f"no fallback",
            )
        if request.parameter_authority != self._authority.digest():
            return self._refused(
                digest,
                ExecutionOutcome.FORGE_REFUSED,
                "the request names a parameter authority this provider was not "
                "built with; a run must be governed by the authority it cites",
            )
        missing = sorted(set(request.qois) - spec.produces)
        if missing:
            return self._refused(
                digest,
                ExecutionOutcome.FORGE_REFUSED,
                f"model {spec.model_key} does not produce {missing}. The "
                f"quantity is absent, not zero and not derivable here",
            )
        applicable, reasons = self._authority.screen(self._cell)
        interval = spec.state_of_charge_interval
        if interval is not None:
            soc = float(request.inputs["initial_state_of_charge"])
            if not (interval[0] < soc < interval[1]):
                reasons = reasons + (
                    f"the requested initial charge state {soc:g} is not strictly "
                    f"inside {spec.model_key}'s open state interval "
                    f"({interval[0]:g}, {interval[1]:g}); the model's own "
                    f"termination events are non-positive at the boundary and "
                    f"the solve would end before its first step",
                )
                applicable = False
        if not applicable:
            return self._refused(
                digest,
                ExecutionOutcome.MODEL_NOT_APPLICABLE,
                "; ".join(reasons),
            )

        # --- the provider ---------------------------------------------
        if not self.available():
            return unavailable_result(
                request,
                "pybamm is not importable in this interpreter; install the "
                "forge[battery-pybamm] extra",
            )
        return self._run(request, spec, digest)

    # -- internals ------------------------------------------------------

    def _refused(
        self, digest: str, outcome: ExecutionOutcome, detail: str
    ) -> ProviderResult:
        return ProviderResult(
            receipt=ProviderExecutionReceipt(
                identity=None,
                request_digest=digest,
                outcome=outcome,
                detail=detail,
            )
        )

    def _identity(self, spec: PyBaMMModelSpec, solver_name: str, configuration: Mapping[str, Any]):
        import pybamm

        return ProviderIdentity(
            provider_name=PROVIDER_NAME,
            provider_version=pybamm.__version__,
            model_identity=f"{spec.constructor}@{spec.model_key}",
            solver_identity=solver_name,
            configuration_digest=digest_of(
                {
                    "model": spec.to_dict(),
                    "authority": self._authority.to_dict(),
                    "protocol": self._protocol.to_dict(),
                    "configuration": {str(k): _jsonable(v) for k, v in configuration.items()},
                }
            ),
            environment_identity=self._environment.digest(),
            adapter_version=ADAPTER_VERSION,
        )

    def _parameter_values(self):
        """Build PyBaMM ``ParameterValues`` under the declared authority.

        The factory is how a Forge-declared authority supplies numbers PyBaMM
        has no named set for -- the NASA 18650 in this sprint's benchmark. When
        no factory is given, the authority must name a PyBaMM set, and the
        overrides it carries are applied to a **copy**.
        """
        import pybamm

        if self._factory is not None:
            values = self._factory()
        else:
            values = pybamm.ParameterValues(self._authority.parameter_set_name).copy()
        if self._authority.overrides:
            values.update(dict(self._authority.overrides), check_already_exists=False)
        return values

    def _run(
        self, request: ProviderRequest, spec: PyBaMMModelSpec, digest: str
    ) -> ProviderResult:
        import numpy as np
        import pybamm

        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        clock = time.perf_counter()
        try:
            model = _construct(spec)
            values = self._parameter_values()
            soc = float(request.inputs["initial_state_of_charge"])
            _apply_protocol(values, self._protocol, soc, spec)
            simulation = pybamm.Simulation(model, parameter_values=values)
            solution = simulation.solve([0.0, self._protocol.duration_s])
            solver_name = type(simulation.solver).__name__
        except Exception as exc:  # provider side, and never a scientific verdict
            return ProviderResult(
                receipt=ProviderExecutionReceipt(
                    identity=None,
                    request_digest=digest,
                    outcome=ExecutionOutcome.PROVIDER_ERROR,
                    detail=f"{type(exc).__name__}: {exc}",
                    wall_seconds=time.perf_counter() - clock,
                    started_at=started,
                )
            )
        elapsed = time.perf_counter() - clock
        identity = self._identity(spec, solver_name, request.configuration)

        try:
            series = {
                name: np.asarray(
                    solution[CANONICAL_QOIS[name][0]].entries, dtype=float
                ).ravel()
                for name in request.qois
            }
        except Exception as exc:
            return ProviderResult(
                receipt=ProviderExecutionReceipt(
                    identity=identity,
                    request_digest=digest,
                    outcome=ExecutionOutcome.PROVIDER_ERROR,
                    detail=(
                        f"the provider solved but a requested canonical QoI "
                        f"could not be read back: {type(exc).__name__}: {exc}"
                    ),
                    wall_seconds=elapsed,
                    started_at=started,
                )
            )

        nonfinite = sorted(n for n, a in series.items() if not np.all(np.isfinite(a)))
        if nonfinite or any(a.size == 0 for a in series.values()):
            return ProviderResult(
                receipt=ProviderExecutionReceipt(
                    identity=identity,
                    request_digest=digest,
                    outcome=ExecutionOutcome.NUMERICAL_FAILURE,
                    detail=(
                        f"non-finite or empty canonical output: {nonfinite or 'empty'}"
                    ),
                    wall_seconds=elapsed,
                    started_at=started,
                )
            )

        result = self._to_scientific_result(
            request, spec, identity, series, elapsed, digest
        )
        return ProviderResult(
            receipt=ProviderExecutionReceipt(
                identity=identity,
                request_digest=digest,
                outcome=ExecutionOutcome.OK,
                detail=f"{len(series[TIME_METRIC]) if TIME_METRIC in series else 0} samples",
                wall_seconds=elapsed,
                started_at=started,
            ),
            result=result,
        )

    def _to_scientific_result(
        self,
        request: ProviderRequest,
        spec: PyBaMMModelSpec,
        identity: ProviderIdentity,
        series: Mapping[str, Any],
        elapsed: float,
        digest: str,
    ) -> ScientificResult:
        """The same record a native solve produces. That is the whole claim.

        ``values`` carry the end-of-protocol canonical QoIs, which is the shape
        the native battery models produce for one interval. The full canonical
        trajectories go to ``data_references`` -- content identity, never
        location -- when a bulk store was supplied.

        ``uncertainty`` is UNKNOWN for every value, stated rather than omitted.
        PyBaMM quantifies no uncertainty and this adapter invents none; the
        Core's rule that missing uncertainty never becomes zero is exactly why
        the field is filled with an explicit UNKNOWN instead of left empty.
        """
        model_id = f"pybamm.{spec.model_key}"
        model_version = identity.provider_version
        solver = SolverIdentity(
            solver_id=f"pybamm.{identity.solver_identity}",
            version=identity.provider_version,
            backend=PROVIDER_NAME,
        )
        values = {
            name: Quantity(float(array[-1]), CANONICAL_QOIS[name][1])
            for name, array in series.items()
        }
        references = ()
        if self._store is not None:
            references = tuple(
                store_values(
                    self._store,
                    f"{model_id}:{name}",
                    [float(v) for v in array],
                    unit=CANONICAL_QOIS[name][1],
                )
                for name, array in sorted(series.items())
            )
        provenance = ProvenanceRecord(
            run_id=f"pybamm-{digest[:16]}",
            software_version=ADAPTER_VERSION,
            bindings=(
                ExecutionBinding(
                    model=ModelReference(model_id, model_version),
                    realization=None,
                    solver=solver,
                ),
            ),
            inputs={
                "initial_state_of_charge": Quantity(
                    float(request.inputs["initial_state_of_charge"]), "dimensionless"
                ),
                "ambient_temperature": Quantity(
                    self._cell.ambient_temperature_k, "kelvin"
                ),
                "nominal_capacity": Quantity(
                    self._cell.nominal_capacity_ah, "ampere_hour"
                ),
            },
            assumptions=spec.physics_included,
            # P10: versions, not locations. Every entry here can change a
            # number; nothing here says where a file lives.
            environment=dict(
                {
                    "python_version": self._environment.python_version,
                    "platform_tag": self._environment.platform_tag,
                    "provider_adapter": ADAPTER_VERSION,
                    "parameter_authority": self._authority.digest(),
                    "parameter_set_name": self._authority.parameter_set_name,
                    "provider_configuration": identity.configuration_digest,
                    "request_digest": digest,
                },
                **{
                    f"distribution.{k}": v
                    for k, v in self._environment.distributions.items()
                },
            ),
            metadata={"provider_identity": identity.to_dict()},
        )
        return ScientificResult(
            result_id=f"pybamm-{digest[:16]}",
            problem_id=f"battery.cell.{self._cell.cell_id}",
            values=values,
            models=((model_id, model_version),),
            solver=solver,
            convergence=ConvergenceState.CONVERGED,
            validation=_provider_validation_report(spec, series),
            validity_not_assessed={
                model_id: (
                    "this provider adapter screens the governing parameter "
                    "authority against the cell under test before executing; "
                    "it does not assess the model's own validity conditions, "
                    "which PyBaMM declares in its own terms and Forge has not "
                    "translated"
                )
            },
            uncertainty={
                name: Uncertainty.unknown(
                    "PyBaMM quantifies no uncertainty for this quantity and "
                    "this adapter invents none"
                )
                for name in values
            },
            assumptions=spec.physics_included,
            warnings=tuple(
                f"excluded physics: {item}" for item in spec.physics_excluded
            ),
            data_references=references,
            provenance=provenance,
            metadata={
                "provider": PROVIDER_NAME,
                "model_key": spec.model_key,
                "fidelity_class": spec.fidelity_class,
                "wall_seconds": elapsed,
            },
        )


def _construct(spec: PyBaMMModelSpec):
    """Build the PyBaMM model the allowlist entry names.

    Resolved from the recorded dotted path rather than a match statement, so
    the catalogue entry is the single statement of which class is meant.
    """
    import pybamm

    module: Any = pybamm
    for part in spec.constructor.split(".")[1:]:
        module = getattr(module, part)
    return module()


def _apply_protocol(values, protocol: CurrentProtocol, soc: float, spec: PyBaMMModelSpec) -> None:
    """Write the Forge protocol into PyBaMM's own parameter vocabulary."""
    import numpy as np
    import pybamm

    if protocol.is_sampled:
        current = pybamm.Interpolant(
            np.asarray(protocol.times_s, dtype=float),
            np.asarray(protocol.currents_a, dtype=float),
            pybamm.t,
            interpolator="linear",
        )
    else:
        current = float(protocol.constant_current_a)
    values["Current function [A]"] = current
    if spec.family == "equivalent_circuit":
        values["Initial SoC"] = float(soc)


def _provider_validation_report(
    spec: PyBaMMModelSpec, series: Mapping[str, Any]
) -> ValidationReport:
    """Checks the adapter can honestly make, and the level they establish: none.

    Two checks run. Both are real -- a monotone time base and finite outputs
    would each catch a broken translation -- and **neither establishes a
    ``ValidationLevel``**. The reason is the one ``domains/electrical/ngspice.py``
    gives for its own weakest checks: they compare an output against the shape
    it was asked for, with no independent reference. An external provider's
    reputation is not evidence for a specific prediction, so nothing here may
    grant a level that would let it become one.
    """
    import numpy as np

    checks: list[ValidationCheck] = []
    times = series.get(TIME_METRIC)
    if times is not None:
        monotone = bool(np.all(np.diff(np.asarray(times, dtype=float)) > 0.0))
        checks.append(
            ValidationCheck(
                name="provider_time_base_monotone",
                outcome=ValidationOutcome.PASS if monotone else ValidationOutcome.FAIL,
                detail=(
                    "the provider's returned time base increases strictly; a "
                    "repeated or reversed sample would mean the translation "
                    "read the wrong array"
                ),
                evidence=(f"samples={len(times)}",),
            )
        )
    finite = all(
        bool(np.all(np.isfinite(np.asarray(a, dtype=float)))) for a in series.values()
    )
    checks.append(
        ValidationCheck(
            name="provider_outputs_finite",
            outcome=ValidationOutcome.PASS if finite else ValidationOutcome.FAIL,
            detail=(
                "every canonical QoI the provider returned is finite. This is "
                "a translation check, not agreement with anything"
            ),
            evidence=(f"qois={sorted(series)}",),
        )
    )
    return ValidationReport(checks=tuple(checks))


__all__ = [
    "ADAPTER_VERSION",
    "ALLOWED_MODELS",
    "CANONICAL_QOIS",
    "CAPACITY_TOLERANCE",
    "CURRENT_METRIC",
    "DISCHARGE_POSITIVE",
    "MODEL_CATALOGUE",
    "NAMED_AUTHORITIES",
    "PROVIDER_NAME",
    "TIME_METRIC",
    "CellUnderTest",
    "CurrentProtocol",
    "ParameterAuthority",
    "PyBaMMModelSpec",
    "PyBaMMProvider",
    "build_request",
]
