"""Deterministic in-memory realization registry.

Modelled on :class:`~engcore.scientific.models.registry.ModelRegistry` and
held to the same discipline: instance-based, no module-level singleton, no
silent choice, deterministic ordering.

What this registry does **not** do, on purpose
----------------------------------------------
It does not rank realizations, score them, or pick one. Preferring a
finely resolved realization over a cheap one is a scientific and economic
judgement that depends on the question being asked, and a registry that
quietly answered it would make every downstream result depend on
registration order and on an unstated preference. Lookup and filtering here
are total and explicit; selection belongs to a planner that does not exist
yet and must record its reasons when it does.

Every filter below is an exact match on a fact the record actually declares.
There is deliberately no fidelity filter, because MODEL0-R records no
fidelity: see ``definition.py`` for why that classification was removed
rather than narrowed.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Mapping

from ..capabilities import ScientificCapability
from ..errors import DuplicateRegistrationError, RealizationNotFoundError
from ..solvers.capability import SolverCapability, SolverCapabilityId
from .definition import ModelFormulation, ModelRealizationDefinition

REGISTRY_SCHEMA = "realization_registry/1"


class RealizationRegistry:
    """Maps ``(realization_id, version)`` to a computational realization."""

    def __init__(
        self, realizations: Iterable[ModelRealizationDefinition] = ()
    ) -> None:
        self._realizations: dict[tuple[str, str], ModelRealizationDefinition] = {}
        for realization in realizations:
            self.register(realization)

    # ---- mutation -------------------------------------------------------
    def register(self, realization: ModelRealizationDefinition) -> None:
        if not isinstance(realization, ModelRealizationDefinition):
            raise TypeError(
                "RealizationRegistry accepts ModelRealizationDefinition only"
            )
        if realization.key in self._realizations:
            raise DuplicateRegistrationError(
                f"realization {realization.realization_id!r} version "
                f"{realization.version!r} is already registered"
            )
        self._realizations[realization.key] = realization

    def unregister(self, realization_id: str, version: str) -> None:
        key = (str(realization_id), str(version))
        if key not in self._realizations:
            raise RealizationNotFoundError(
                f"no realization {realization_id!r} version {version!r} "
                f"to unregister"
            )
        del self._realizations[key]

    # ---- lookup ---------------------------------------------------------
    def get(
        self, realization_id: str, version: str
    ) -> ModelRealizationDefinition:
        key = (str(realization_id), str(version))
        try:
            return self._realizations[key]
        except KeyError:
            available = ", ".join(
                f"{rid}@{ver}" for rid, ver in sorted(self._realizations)
            ) or "<empty registry>"
            raise RealizationNotFoundError(
                f"no realization {realization_id!r} version {version!r}; "
                f"available: {available}"
            ) from None

    def contains(self, realization_id: str, version: str) -> bool:
        return (str(realization_id), str(version)) in self._realizations

    def versions(self, realization_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                ver
                for rid, ver in self._realizations
                if rid == str(realization_id)
            )
        )

    def for_model(
        self, model_id: str, version: str
    ) -> tuple[ModelRealizationDefinition, ...]:
        """Every realization declared for one exact scientific model identity.

        An empty result is a legitimate, meaningful answer: the science is
        known and no computational realization has been declared for it. That
        is a different state from "no such model", and callers must be able
        to tell them apart — so this returns an empty tuple rather than
        raising.
        """
        key = (str(model_id), str(version))
        return tuple(
            self._realizations[k]
            for k in sorted(self._realizations)
            if self._realizations[k].model_key == key
        )

    def list(
        self,
        *,
        model_id: str | None = None,
        formulation: ModelFormulation | str | None = None,
        provides: ScientificCapability | str | None = None,
        requires: ScientificCapability | str | None = None,
        requires_solver_capability: (
            SolverCapabilityId | SolverCapability | str | None
        ) = None,
    ) -> tuple[ModelRealizationDefinition, ...]:
        """Deterministic, filtered listing sorted by ``(realization_id, version)``.

        Filters conjoin. Every filter is an exact declared-fact match: none of
        them infers, substitutes or widens.
        """
        wanted_formulation = (
            ModelFormulation(formulation) if formulation is not None else None
        )
        wanted_provides = (
            ScientificCapability.coerce(provides) if provides is not None else None
        )
        wanted_requires = (
            ScientificCapability.coerce(requires) if requires is not None else None
        )
        wanted_solver = (
            SolverCapabilityId.coerce(requires_solver_capability)
            if requires_solver_capability is not None
            else None
        )

        results = []
        for key in sorted(self._realizations):
            realization = self._realizations[key]
            if model_id is not None and realization.model.model_id != model_id:
                continue
            if (
                wanted_formulation is not None
                and realization.formulation is not wanted_formulation
            ):
                continue
            if (
                wanted_provides is not None
                and wanted_provides not in realization.provided_capabilities
            ):
                continue
            if (
                wanted_requires is not None
                and wanted_requires not in realization.required_capabilities
            ):
                continue
            if (
                wanted_solver is not None
                and wanted_solver not in realization.required_solver_capabilities
            ):
                continue
            results.append(realization)
        return tuple(results)

    def providing(
        self, capability: ScientificCapability | str
    ) -> tuple[ModelRealizationDefinition, ...]:
        """Realizations declaring they provide this scientific capability."""
        return self.list(provides=capability)

    # ---- introspection --------------------------------------------------
    def provided_capabilities(self) -> frozenset[ScientificCapability]:
        """Every scientific capability any registered realization provides.

        This is what lets a future planner distinguish *capability unknown*
        (nothing in this registry has ever heard of it) from *capability
        unsupported* (it is provided, but no realization survived the other
        constraints). Without this the two collapse into one unhelpful
        "not found", and a user cannot tell a typo from a genuine gap.
        """
        declared: set[ScientificCapability] = set()
        for realization in self._realizations.values():
            declared |= realization.provided_capabilities
        return frozenset(declared)

    def required_solver_capabilities(self) -> tuple[SolverCapabilityId, ...]:
        """Solver capability identities any registered realization needs.

        Sorted by canonical name, and typed rather than stringly: this is the
        set a caller intersects against a ``SolverRegistry``, and an
        intersection between identities and free strings is exactly where a
        capability gap goes silently unnoticed.
        """
        declared: set[SolverCapabilityId] = set()
        for realization in self._realizations.values():
            declared |= realization.required_solver_capabilities
        return tuple(sorted(declared, key=lambda c: c.name))

    def model_keys(self) -> tuple[tuple[str, str], ...]:
        """Sorted identities of every scientific model that has a realization."""
        return tuple(
            sorted({r.model_key for r in self._realizations.values()})
        )

    # ---- container protocol ---------------------------------------------
    def __len__(self) -> int:
        return len(self._realizations)

    def __iter__(self) -> Iterator[ModelRealizationDefinition]:
        for key in sorted(self._realizations):
            yield self._realizations[key]

    def to_dict(self) -> dict:
        return {
            "schema": REGISTRY_SCHEMA,
            "realizations": [
                self._realizations[k].to_dict()
                for k in sorted(self._realizations)
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping) -> "RealizationRegistry":
        return cls(
            ModelRealizationDefinition.from_dict(r)
            for r in payload.get("realizations", ())
        )
