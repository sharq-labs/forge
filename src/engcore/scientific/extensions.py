"""Runtime contract for installing scientific domain extensions.

A domain extension contributes declarations to registries the caller owns.  It
is not a process-global plugin manager and it performs no import discovery:
which extensions are loaded is an explicit runtime decision, preserving the
Scientific Core's existing instance-based registry discipline.

The contract binds four things that were previously only conventions:

* an extension has stable identity/version and a namespace;
* every model it owns declares a domain inside that namespace;
* every realization points either at a model owned by the extension or at an
  explicitly declared external model dependency;
* installing models, realizations and solver factories is transactional.  A
  failure in a later contribution rolls earlier contributions back instead of
  leaving a half-installed scientific runtime.

This module deliberately does not rank plugins, auto-download them, trust entry
points, or infer dependency versions.  Those are packaging/deployment policy,
not scientific-core semantics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .errors import ScientificCoreError, SolverNotFoundError
from .ir.problem import ModelReference
from .models.definition import ScientificModelDefinition
from .models.registry import ModelRegistry
from .realizations.definition import ModelRealizationDefinition
from .realizations.registry import RealizationRegistry
from .solvers.protocol import ScientificSolver
from .solvers.registry import SolverFactory, SolverRegistry

_NAMESPACE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")


def _identity(value: object, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ScientificCoreError(f"domain extension requires non-empty {label}")
    return text


def _namespace(value: object) -> str:
    text = _identity(value, label="namespace")
    if not _NAMESPACE.fullmatch(text):
        raise ScientificCoreError(
            f"domain extension namespace {text!r} must be lowercase dotted "
            "identifier segments"
        )
    return text


def _inside_namespace(domain: str, namespace: str) -> bool:
    return domain == namespace or domain.startswith(namespace + ".")


@dataclass(frozen=True)
class DomainExtension:
    """One explicit package of scientific declarations.

    ``external_models`` is important: a plugin may add a realization for a
    model defined by another extension, but that dependency must be written
    down.  A realization that merely happens to point outside the extension's
    namespace is otherwise indistinguishable from a typo.
    """

    extension_id: str
    version: str
    namespace: str
    models: tuple[ScientificModelDefinition, ...] = ()
    realizations: tuple[ModelRealizationDefinition, ...] = ()
    solver_factories: tuple[SolverFactory, ...] = ()
    external_models: tuple[ModelReference, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "extension_id", _identity(self.extension_id, label="extension_id"))
        object.__setattr__(self, "version", _identity(self.version, label="version"))
        object.__setattr__(self, "namespace", _namespace(self.namespace))
        object.__setattr__(self, "models", tuple(self.models))
        object.__setattr__(self, "realizations", tuple(self.realizations))
        object.__setattr__(self, "solver_factories", tuple(self.solver_factories))
        object.__setattr__(self, "external_models", tuple(self.external_models))
        object.__setattr__(self, "description", str(self.description))

        if not (self.models or self.realizations or self.solver_factories):
            raise ScientificCoreError(
                f"domain extension {self.extension_id!r} contributes nothing"
            )
        if any(not isinstance(model, ScientificModelDefinition) for model in self.models):
            raise ScientificCoreError("domain extension models must be ScientificModelDefinition records")
        if any(
            not isinstance(realization, ModelRealizationDefinition)
            for realization in self.realizations
        ):
            raise ScientificCoreError(
                "domain extension realizations must be ModelRealizationDefinition records"
            )
        if any(not callable(factory) for factory in self.solver_factories):
            raise ScientificCoreError("domain extension solver_factories must be callable")
        if any(not isinstance(reference, ModelReference) for reference in self.external_models):
            raise ScientificCoreError("external_models must contain ModelReference records")

        model_keys = [model.key for model in self.models]
        if len(set(model_keys)) != len(model_keys):
            raise ScientificCoreError(
                f"domain extension {self.extension_id!r} declares duplicate model identities"
            )
        realization_keys = [realization.key for realization in self.realizations]
        if len(set(realization_keys)) != len(realization_keys):
            raise ScientificCoreError(
                f"domain extension {self.extension_id!r} declares duplicate realization identities"
            )
        external_keys = [reference.key for reference in self.external_models]
        if len(set(external_keys)) != len(external_keys):
            raise ScientificCoreError(
                f"domain extension {self.extension_id!r} declares duplicate external model dependencies"
            )
        overlap = sorted(set(model_keys) & set(external_keys))
        if overlap:
            raise ScientificCoreError(
                f"domain extension {self.extension_id!r} lists owned model(s) {overlap} "
                "as external dependencies too"
            )

        for model in self.models:
            domain = str(model.domain).strip()
            if not domain:
                raise ScientificCoreError(
                    f"extension model {model.model_id!r} declares no domain; a plugin "
                    "cannot prove namespace ownership without one"
                )
            if not _inside_namespace(domain, self.namespace):
                raise ScientificCoreError(
                    f"extension {self.extension_id!r} owns namespace {self.namespace!r}, "
                    f"but model {model.model_id!r} declares domain {domain!r}"
                )

        allowed_models = set(model_keys) | set(external_keys)
        for realization in self.realizations:
            if realization.model_key not in allowed_models:
                raise ScientificCoreError(
                    f"realization {realization.realization_id!r}@{realization.version} "
                    f"points at model {realization.model_key}, which is neither owned "
                    "by this extension nor declared in external_models"
                )

    @property
    def key(self) -> tuple[str, str]:
        return self.extension_id, self.version

    @property
    def model_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(model.key for model in self.models))

    @property
    def realization_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(realization.key for realization in self.realizations))


@dataclass(frozen=True)
class InstalledExtension:
    """What one successful installation added; used for exact rollback/uninstall."""

    extension_id: str
    version: str
    model_keys: tuple[tuple[str, str], ...] = ()
    realization_keys: tuple[tuple[str, str], ...] = ()
    solver_keys: tuple[tuple[str, str], ...] = ()

    @property
    def key(self) -> tuple[str, str]:
        return self.extension_id, self.version


@dataclass
class DomainRuntime:
    """Explicit collection of registries plus transactional extension install.

    The runtime is intentionally instance-based.  Two tests, services or study
    sessions can load different extension sets without mutating each other.
    """

    models: ModelRegistry = field(default_factory=ModelRegistry)
    realizations: RealizationRegistry = field(default_factory=RealizationRegistry)
    solvers: SolverRegistry = field(default_factory=SolverRegistry)
    _installed: dict[tuple[str, str], InstalledExtension] = field(
        default_factory=dict, init=False, repr=False
    )

    @property
    def installed_extensions(self) -> tuple[InstalledExtension, ...]:
        return tuple(self._installed[key] for key in sorted(self._installed))

    def install(self, extension: DomainExtension) -> InstalledExtension:
        if not isinstance(extension, DomainExtension):
            raise TypeError("DomainRuntime.install requires DomainExtension")
        if extension.key in self._installed:
            raise ScientificCoreError(
                f"extension {extension.extension_id!r}@{extension.version} is already installed"
            )

        missing_external = [
            reference.key
            for reference in extension.external_models
            if not self.models.contains(reference.model_id, reference.version)
        ]
        if missing_external:
            raise ScientificCoreError(
                f"extension {extension.extension_id!r}@{extension.version} requires "
                f"external model(s) {sorted(missing_external)} that are not installed"
            )

        duplicate_models = [
            key for key in extension.model_keys if self.models.contains(*key)
        ]
        duplicate_realizations = [
            key
            for key in extension.realization_keys
            if self.realizations.contains(*key)
        ]
        if duplicate_models or duplicate_realizations:
            raise ScientificCoreError(
                f"extension {extension.extension_id!r}@{extension.version} collides with "
                f"existing declarations; models={duplicate_models}, "
                f"realizations={duplicate_realizations}"
            )

        added_models: list[tuple[str, str]] = []
        added_realizations: list[tuple[str, str]] = []
        added_solvers: list[tuple[str, str]] = []
        try:
            for model in extension.models:
                self.models.register(model)
                added_models.append(model.key)
            for realization in extension.realizations:
                self.realizations.register(realization)
                added_realizations.append(realization.key)
            for factory in extension.solver_factories:
                definition = self.solvers.register(factory)
                added_solvers.append(definition.identity.key)
        except Exception:
            # Reverse dependency order: solvers may refer to realizations, which
            # refer to models.  Roll back only contributions from this attempt.
            for solver_id, version in reversed(added_solvers):
                self.solvers.unregister(solver_id, version)
            for realization_id, version in reversed(added_realizations):
                self.realizations.unregister(realization_id, version)
            for model_id, version in reversed(added_models):
                self.models.unregister(model_id, version)
            raise

        receipt = InstalledExtension(
            extension_id=extension.extension_id,
            version=extension.version,
            model_keys=tuple(added_models),
            realization_keys=tuple(added_realizations),
            solver_keys=tuple(added_solvers),
        )
        self._installed[extension.key] = receipt
        return receipt

    def uninstall(self, extension_id: str, version: str) -> InstalledExtension:
        key = (str(extension_id).strip(), str(version).strip())
        try:
            receipt = self._installed[key]
        except KeyError:
            raise ScientificCoreError(
                f"extension {key[0]!r}@{key[1]} is not installed"
            ) from None

        for solver_id, solver_version in reversed(receipt.solver_keys):
            self.solvers.unregister(solver_id, solver_version)
        for realization_id, realization_version in reversed(receipt.realization_keys):
            self.realizations.unregister(realization_id, realization_version)
        for model_id, model_version in reversed(receipt.model_keys):
            self.models.unregister(model_id, model_version)
        del self._installed[key]
        return receipt


__all__ = ["DomainExtension", "InstalledExtension", "DomainRuntime"]
