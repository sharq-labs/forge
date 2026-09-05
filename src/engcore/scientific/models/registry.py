"""Deterministic in-memory model registry.

Explicitly instance-based: there is no module-level singleton, so tests,
studies and future services cannot mutate one another's model set. Storage
and remote ingestion are deferred.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Mapping

from ..errors import DuplicateRegistrationError, ModelNotFoundError
from .definition import ScientificModelDefinition


class ModelRegistry:
    """Maps ``(model_id, version)`` to a model definition."""

    def __init__(self, models: Iterable[ScientificModelDefinition] = ()) -> None:
        self._models: dict[tuple[str, str], ScientificModelDefinition] = {}
        for model in models:
            self.register(model)

    # ---- mutation -------------------------------------------------------
    def register(self, model: ScientificModelDefinition) -> None:
        if not isinstance(model, ScientificModelDefinition):
            raise TypeError("ModelRegistry accepts ScientificModelDefinition only")
        if model.key in self._models:
            raise DuplicateRegistrationError(
                f"model {model.model_id!r} version {model.version!r} "
                f"is already registered"
            )
        self._models[model.key] = model

    def unregister(self, model_id: str, version: str) -> None:
        key = (str(model_id), str(version))
        if key not in self._models:
            raise ModelNotFoundError(
                f"no model {model_id!r} version {version!r} to unregister"
            )
        del self._models[key]

    # ---- lookup ---------------------------------------------------------
    def get(self, model_id: str, version: str) -> ScientificModelDefinition:
        key = (str(model_id), str(version))
        try:
            return self._models[key]
        except KeyError:
            available = ", ".join(
                f"{mid}@{ver}" for mid, ver in sorted(self._models)
            ) or "<empty registry>"
            raise ModelNotFoundError(
                f"no model {model_id!r} version {version!r}; available: {available}"
            ) from None

    def resolve(self, reference) -> ScientificModelDefinition:
        """Resolve a :class:`ModelReference`-shaped object."""
        return self.get(reference.model_id, reference.version)

    def contains(self, model_id: str, version: str) -> bool:
        return (str(model_id), str(version)) in self._models

    def list(
        self,
        *,
        domain: str | None = None,
        model_type=None,
        capability: str | None = None,
        provides_metric: str | None = None,
    ) -> tuple[ScientificModelDefinition, ...]:
        """Deterministic, filtered listing sorted by ``(model_id, version)``."""
        results = []
        for key in sorted(self._models):
            model = self._models[key]
            if domain is not None and model.domain != domain:
                continue
            if model_type is not None and model.model_type != model_type:
                continue
            if capability is not None and capability not in model.required_capabilities:
                continue
            if (
                provides_metric is not None
                and provides_metric not in model.provided_metrics
            ):
                continue
            results.append(model)
        return tuple(results)

    def versions(self, model_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(ver for mid, ver in self._models if mid == str(model_id))
        )

    # ---- container protocol ---------------------------------------------
    def __len__(self) -> int:
        return len(self._models)

    def __iter__(self) -> Iterator[ScientificModelDefinition]:
        for key in sorted(self._models):
            yield self._models[key]

    def to_dict(self) -> dict:
        return {
            "schema": "model_registry/1",
            "models": [self._models[k].to_dict() for k in sorted(self._models)],
        }

    @classmethod
    def from_dict(cls, payload: Mapping) -> "ModelRegistry":
        return cls(
            ScientificModelDefinition.from_dict(m)
            for m in payload.get("models", ())
        )
