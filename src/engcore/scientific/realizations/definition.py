"""Computational realization of a scientific model.

A scientific model is not the same thing as its numerical implementation.
The model states *what relation is claimed to hold*; a realization states
*how that claim is computed*, in what mathematical form, and with what a
solver must be able to do. One model may have many realizations — a
closed-form simplification, a reduced-order form, a native discretization, an
external package — differing in cost, applicability and evidence while
representing the same science.

Collapsing the two loses the ability to say "the model is valid here but this
particular realization is not adequate", which is one of the most useful
statements a scientific planner can make.

Scope of MODEL0-R
-----------------
This record carries identity, formulation, capability declarations and
assumptions. It deliberately carries **no** material, geometry, field, mesh,
state-history or coupling structure: those are later milestones, and
inventing placeholder shapes for them now would freeze the wrong contract.

Why there is no fidelity field
------------------------------
An earlier draft of this record required a ``fidelity`` field typed by a
``RealizationFidelity`` enum with the members ``ANALYTICAL``,
``REDUCED_ORDER``, ``ENGINEERING``, ``NUMERICAL`` and ``HIGH_FIDELITY``.
It is removed, and **nothing replaces it**.

*Those members are not one axis.* They are at least four, conflated:

``ANALYTICAL`` vs ``NUMERICAL``
    Solution character — closed form versus discretized and iterated.
``REDUCED_ORDER``
    A reduction operation applied to a full-order model. Orthogonal to
    solution character: a POD-Galerkin ROM is reduced-order *and* numerical.
``ENGINEERING``
    Provenance — a handbook correlation or design-code method. Epistemic,
    and already carried at the model layer by ``ModelType``
    (``EMPIRICAL_CORRELATION``, ``APPROXIMATION``).
``HIGH_FIDELITY``
    A *relative* resolution claim that only means something against a stated
    reference. DNS is high-fidelity beside LES; LES beside RANS; RANS beside
    a lumped correlation. Absolute, it asserts nothing checkable.

Because the field held one member, the honest combinations could not be
written down. ``numerical + reduced_order`` and ``numerical + high_fidelity``
are the ordinary cases — nearly every reduced-order and every high-fidelity
realization in practice is numerical — and each forced a caller to discard
one true fact to record the other. A required field that silently deletes
information about its most common subjects is worse than no field.

Widening it to a set was rejected too: a set of members drawn from four
unnamed axes is still not a classification, and this milestone does not have
the evidence to name those axes. The axes that *are* evidenced already have
homes:

* :class:`ModelFormulation` — the computational form, one axis, disjoint
  members, decidable from the record itself.
* ``assumptions`` — where "reduced to 12 POD modes" is stated as the
  falsifiable claim it is, rather than compressed into a label.
* ``engcore.design.FidelityLadder`` — relative fidelity, ranked explicitly
  and *per study*, which is the only scope in which "higher fidelity" has a
  truth value.
* ``ModelType`` / ``ModelValidationStatus`` — epistemic character and
  established evidence, at the model layer where they belong.

A ``ModelRealizationDefinition`` is therefore allowed to exist without
claiming a universal fidelity category, because no such category was ever
defensible. If a later milestone needs one, it will arrive with the study
context that makes it answerable.

There is also **no metadata mapping**. An open dictionary would let every
deferred concept in through the back door, untyped and unvalidated, and the
resulting records would be unreadable to the planner meant to consume them.
A concept that cannot be stated cleanly here is deferred explicitly rather
than smuggled in.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..capabilities import (
    ScientificCapability,
    capability_identifiers,
    scientific_capabilities,
)
from ..errors import InvalidModelRealization, ScientificCoreError
from ..ir.problem import ModelReference
from ..serialization import require_schema, schema_string
from ..solvers.capability import (
    SolverCapability,
    SolverCapabilityId,
    solver_capability_identifiers,
    solver_capability_ids,
)

REALIZATION_SCHEMA = schema_string("model_realization_definition")
IMPLEMENTATION_REFERENCE_SCHEMA = schema_string("implementation_reference")
REALIZATION_REFERENCE_SCHEMA = schema_string("realization_reference")


@dataclass(frozen=True)
class RealizationReference:
    """Points at a registered realization without importing it.

    The exact counterpart of
    :class:`~engcore.scientific.ir.problem.ModelReference`, and it exists for
    the same reason: a record that needs to name a realization must not embed
    one. Embedding would fork the record — a provenance entry could carry a
    stale set of assumptions while the registered realization moved on — and
    would put the realization's whole contract inside every result that
    mentions it.

    It carries identity and nothing else. In particular it carries no solver,
    no backend and no execution detail: a realization is not one execution,
    and which realization ran must stay separable from what ran it.
    """

    realization_id: str
    version: str

    def __post_init__(self) -> None:
        for label in ("realization_id", "version"):
            raw = str(getattr(self, label)).strip()
            if not raw:
                raise InvalidModelRealization(
                    f"realization reference requires a non-empty {label}"
                )
            object.__setattr__(self, label, raw)

    @property
    def key(self) -> tuple[str, str]:
        return (self.realization_id, self.version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REALIZATION_REFERENCE_SCHEMA,
            "realization_id": self.realization_id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RealizationReference":
        require_schema(payload, REALIZATION_REFERENCE_SCHEMA)
        return cls(
            realization_id=payload["realization_id"],
            version=payload["version"],
        )


class ModelFormulation(str, Enum):
    """The mathematical form in which a realization poses the problem.

    This is **not** :class:`~engcore.scientific.models.definition.ModelType`,
    whose meaning is epistemic — how far a model is derived versus fitted.
    A fundamental relation may be realized algebraically or as a PDE; an
    empirical correlation may be realized as an algebraic expression. The two
    axes are independent, and ``ModelType`` keeps its existing meaning
    untouched.

    It is also not a :class:`~engcore.scientific.solvers.SolverCapability`:
    stating that a realization is a PDE says what it *is*, not that some
    particular backend can integrate it.

    Why ``SURROGATE`` is not a member
    ---------------------------------
    An earlier draft listed it beside these. It is not the same axis. The
    members below answer *what mathematical form is posed*; "surrogate"
    answers *by what strategy the realization was obtained* — and a surrogate
    is itself posed in one of these forms. A response-surface surrogate is
    algebraic; a learned latent-dynamics surrogate is an ODE; a neural
    operator is none of these in the same sense. Offering ``SURROGATE`` as a
    sixth member therefore forced a caller to discard the mathematical form
    in order to record the strategy, for exactly the realizations whose form
    a solver most needs to know.

    Surrogate character is **deferred, not renamed**: no member, field or
    flag replaces it here. If a coherent realization-strategy axis is needed
    later, it arrives as its own contract with evidence for its members —
    not as a foreign member smuggled into this one.
    """

    ALGEBRAIC = "algebraic"
    ODE = "ode"
    DAE = "dae"
    PDE = "pde"
    DISCRETE = "discrete"


@dataclass(frozen=True)
class ImplementationReference:
    """Identity of the code that actually computes a realization.

    Opaque to the core by construction: these strings are recorded for
    provenance and never interpreted. No core logic may branch on an
    implementation identity — the moment it does, the universal layer has
    learned about one specific backend.
    """

    implementation_id: str
    version: str
    reference: str = ""

    def __post_init__(self) -> None:
        for label in ("implementation_id", "version"):
            raw = str(getattr(self, label)).strip()
            if not raw:
                raise InvalidModelRealization(
                    f"implementation reference requires a non-empty {label}"
                )
            object.__setattr__(self, label, raw)
        object.__setattr__(self, "reference", str(self.reference))

    @property
    def key(self) -> tuple[str, str]:
        return (self.implementation_id, self.version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": IMPLEMENTATION_REFERENCE_SCHEMA,
            "implementation_id": self.implementation_id,
            "version": self.version,
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ImplementationReference":
        require_schema(payload, IMPLEMENTATION_REFERENCE_SCHEMA)
        return cls(
            implementation_id=payload["implementation_id"],
            version=payload["version"],
            reference=payload.get("reference", ""),
        )


@dataclass(frozen=True)
class ModelRealizationDefinition:
    """A versioned computational realization of one scientific model.

    ``model`` is a :class:`~engcore.scientific.ir.problem.ModelReference` and
    nothing else. A realization points *at* a model; it never embeds or
    copies one. Embedding would fork the scientific record — a realization
    could then carry a stale validity domain while the registered model moved
    on — and it would let a realization quietly restate the science it is
    only supposed to implement.

    ``required_solver_capabilities`` holds
    :class:`~engcore.scientific.solvers.capability.SolverCapabilityId` values
    for the same reason: a realization *references* solver capabilities, so
    what it stores must be exactly what it can serialize and reload
    unchanged. Holding full declarations would mean reloading a record
    silently blanked their descriptions; holding bare strings would mean a
    typo widened a capability gap instead of failing. Note what is absent —
    no concrete solver, backend, tolerance or resource appears anywhere in
    this record. Those are execution properties, and a realization that named
    one would have made changing a linear solver into a change of scientific
    identity.
    """

    realization_id: str
    version: str
    model: ModelReference
    formulation: ModelFormulation
    name: str = ""
    description: str = ""
    provided_capabilities: frozenset[ScientificCapability] = frozenset()
    required_capabilities: frozenset[ScientificCapability] = frozenset()
    required_solver_capabilities: frozenset[SolverCapabilityId] = frozenset()
    assumptions: tuple[str, ...] = ()
    implementation: ImplementationReference | None = None

    def __post_init__(self) -> None:
        for label in ("realization_id", "version"):
            raw = str(getattr(self, label)).strip()
            if not raw:
                raise InvalidModelRealization(
                    f"realization requires a non-empty {label}"
                )
            object.__setattr__(self, label, raw)

        if not isinstance(self.model, ModelReference):
            raise InvalidModelRealization(
                f"realization {self.realization_id!r} must reference its "
                f"scientific model with a ModelReference, not "
                f"{type(self.model).__name__} — a realization points at a "
                f"model, it never embeds one"
            )

        object.__setattr__(self, "formulation", ModelFormulation(self.formulation))

        provided = scientific_capabilities(self.provided_capabilities)
        required = scientific_capabilities(self.required_capabilities)
        if not provided:
            raise InvalidModelRealization(
                f"realization {self.realization_id!r} must declare at least "
                f"one provided scientific capability; a realization that "
                f"provides nothing can never satisfy anything"
            )
        overlap = provided & required
        if overlap:
            raise InvalidModelRealization(
                f"realization {self.realization_id!r} both provides and "
                f"requires {sorted(c.identifier for c in overlap)} — a "
                f"realization cannot depend on itself"
            )
        object.__setattr__(self, "provided_capabilities", provided)
        object.__setattr__(self, "required_capabilities", required)

        # Solver requirements are stored as validated identities, never as
        # bare strings. A realization requiring "core:pde " and a solver
        # providing "core:pde" must not be two different facts, and a typo
        # must fail here rather than quietly widen a capability gap later.
        try:
            solver_ids = solver_capability_ids(self.required_solver_capabilities)
        except ScientificCoreError as exc:
            raise InvalidModelRealization(
                f"realization {self.realization_id!r} declares an invalid "
                f"solver capability: {exc}"
            ) from exc
        object.__setattr__(self, "required_solver_capabilities", solver_ids)

        object.__setattr__(self, "assumptions", tuple(self.assumptions))

        if self.implementation is not None and not isinstance(
            self.implementation, ImplementationReference
        ):
            raise InvalidModelRealization(
                f"realization {self.realization_id!r}: implementation must be "
                f"an ImplementationReference"
            )

    @property
    def key(self) -> tuple[str, str]:
        return (self.realization_id, self.version)

    def reference(self) -> RealizationReference:
        """A citable identity for this realization.

        Additive: a method, not a field. The record's serialized shape is
        unchanged, and nothing about the realization contract moves.
        """
        return RealizationReference(self.realization_id, self.version)

    @property
    def model_key(self) -> tuple[str, str]:
        """Identity of the scientific model this realization implements."""
        return self.model.key

    def provides(self, capability: ScientificCapability | str) -> bool:
        return ScientificCapability.coerce(capability) in self.provided_capabilities

    def requires(self, capability: ScientificCapability | str) -> bool:
        return ScientificCapability.coerce(capability) in self.required_capabilities

    def requires_solver_capability(
        self, capability: SolverCapabilityId | SolverCapability | str
    ) -> bool:
        return (
            SolverCapabilityId.coerce(capability)
            in self.required_solver_capabilities
        )

    def solver_capability_gap(
        self, available: Iterable[SolverCapabilityId | SolverCapability | str]
    ) -> frozenset[SolverCapabilityId]:
        """Solver capabilities this realization needs that are not available.

        Reports the gap; it decides nothing. Choosing a solver is a future
        planner's job, and an empty gap is a necessary condition for running
        this realization, never a sufficient one.
        """
        return self.required_solver_capabilities - solver_capability_ids(
            available
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REALIZATION_SCHEMA,
            "realization_id": self.realization_id,
            "version": self.version,
            "model": self.model.to_dict(),
            "formulation": self.formulation.value,
            "name": self.name,
            "description": self.description,
            "provided_capabilities": list(
                capability_identifiers(self.provided_capabilities)
            ),
            "required_capabilities": list(
                capability_identifiers(self.required_capabilities)
            ),
            "required_solver_capabilities": list(
                solver_capability_identifiers(self.required_solver_capabilities)
            ),
            "assumptions": list(self.assumptions),
            "implementation": (
                self.implementation.to_dict() if self.implementation else None
            ),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "ModelRealizationDefinition":
        require_schema(payload, REALIZATION_SCHEMA)
        if "fidelity" in payload:
            raise InvalidModelRealization(
                "this payload carries a 'fidelity' key; MODEL0-R records no "
                "universal fidelity category (see this module's docstring). "
                "Rejected rather than ignored: silently dropping it would "
                "let a caller believe a claim was stored that never was. "
                "State the computational form in 'formulation', the "
                "approximation in 'assumptions', and any ranking in a "
                "study-scoped engcore.design.FidelityLadder."
            )
        implementation = payload.get("implementation")
        return cls(
            realization_id=payload["realization_id"],
            version=payload["version"],
            model=ModelReference.from_dict(payload["model"]),
            formulation=ModelFormulation(payload["formulation"]),
            name=payload.get("name", ""),
            description=payload.get("description", ""),
            provided_capabilities=scientific_capabilities(
                payload.get("provided_capabilities", ())
            ),
            required_capabilities=scientific_capabilities(
                payload.get("required_capabilities", ())
            ),
            required_solver_capabilities=solver_capability_ids(
                payload.get("required_solver_capabilities", ())
            ),
            assumptions=tuple(payload.get("assumptions", ())),
            implementation=(
                ImplementationReference.from_dict(implementation)
                if implementation
                else None
            ),
        )
