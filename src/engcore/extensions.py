"""Runtime contract for installing scientific domain extensions.

A domain extension contributes declarations to registries the caller owns. It
is orchestration *above* the Scientific Core, not a new scientific primitive:
which extensions are loaded is an explicit runtime decision and no plugin state
is process-global.

The contract binds five things that were previously conventions:

* an extension has stable identity/version and a namespace;
* every model it owns declares a domain inside that namespace;
* every realization points either at an owned model or at an explicitly
  declared external model dependency;
* an optional SRIA ``DomainPack`` is validated and identity-bound to the exact
  runtime extension before any registry mutation;
* installing models, realizations and solver factories is transactional. A
  later failure rolls earlier contributions back instead of leaving a
  half-installed runtime.

It deliberately does not auto-discover imports, download packages, rank
extensions, or infer dependency versions. Those are deployment policy rather
than scientific semantics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .scientific.errors import ScientificCoreError
from .scientific.ir.problem import ModelReference
from .scientific.models.definition import ScientificModelDefinition
from .scientific.models.registry import ModelRegistry
from .scientific.realizations.definition import ModelRealizationDefinition
from .scientific.realizations.registry import RealizationRegistry
from .scientific.solvers.registry import SolverFactory, SolverRegistry
from .sria.domain_pack import validate_domain_pack

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


def _inside_namespace(model_domain: str, namespace: str) -> bool:
    return namespace == model_domain or model_domain.startswith(namespace + ".")


def _pack_key(pack: Any | None) -> tuple[str, str] | None:
    if pack is None:
        return None
    return str(pack.pack_id).strip(), str(pack.pack_version).strip()


@dataclass(frozen=True)
class DomainExtension:
    """One explicit package of model, realization and solver declarations.

    ``external_models`` is load-bearing: an extension may add a realization for
    a model defined elsewhere, but that dependency must be written down. A
    realization that merely happens to point outside the extension's own model
    set is otherwise indistinguishable from a typo.

    ``domain_pack`` is optional for compatibility with low-level extensions,
    but when present it is a load-bearing semantic declaration, not metadata.
    It must satisfy SRIA's DomainPack contract and its ``pack_id``/version must
    equal this runtime package's extension identity. That gives an installed
    plugin one identity from semantic scope through registry contributions.
    """

    extension_id: str
    version: str
    namespace: str
    models: tuple[ScientificModelDefinition, ...] = ()
    realizations: tuple[ModelRealizationDefinition, ...] = ()
    solver_factories: tuple[SolverFactory, ...] = ()
    external_models: tuple[ModelReference, ...] = ()
    domain_pack: Any | None = None
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "extension_id",
            _identity(self.extension_id, label="extension_id"),
        )
        object.__setattr__(self, "version", _identity(self.version, label="version"))
        object.__setattr__(self, "namespace", _namespace(self.namespace))
        object.__setattr__(self, "models", tuple(self.models))
        object.__setattr__(self, "realizations", tuple(self.realizations))
        object.__setattr__(self, "solver_factories", tuple(self.solver_factories))
        object.__setattr__(self, "external_models", tuple(self.external_models))
        object.__setattr__(self, "description", str(self.description))

        if self.domain_pack is not None:
            # Structural/semantic validation happens during construction, long
            # before DomainRuntime.install has any registries to mutate.
            validate_domain_pack(self.domain_pack)
            pack_key = _pack_key(self.domain_pack)
            if pack_key != self.key:
                raise ScientificCoreError(
                    f"domain extension {self.extension_id!r}@{self.version} carries "
                    f"DomainPack {pack_key[0]!r}@{pack_key[1]}; semantic pack and "
                    "runtime extension must have the same identity/version"
                )

        if not (self.models or self.realizations or self.solver_factories):
            raise ScientificCoreError(
                f"domain extension {self.extension_id!r} contributes nothing"
            )
        if any(not isinstance(model, ScientificModelDefinition) for model in self.models):
            raise ScientificCoreError(
                "domain extension models must be ScientificModelDefinition records"
            )
        if any(
            not isinstance(realization, ModelRealizationDefinition)
            for realization in self.realizations
        ):
            raise ScientificCoreError(
                "domain extension realizations must be ModelRealizationDefinition records"
            )
        if any(not callable(factory) for factory in self.solver_factories):
            raise ScientificCoreError(
                "domain extension solver_factories must be callable"
            )
        if any(
            not isinstance(reference, ModelReference)
            for reference in self.external_models
        ):
            raise ScientificCoreError(
                "external_models must contain ModelReference records"
            )

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
            model_domain = str(model.domain).strip()
            if not model_domain:
                raise ScientificCoreError(
                    f"extension model {model.model_id!r} declares no domain; a plugin "
                    "cannot prove namespace ownership without one"
                )
            if not _inside_namespace(model_domain, self.namespace):
                raise ScientificCoreError(
                    f"extension {self.extension_id!r} owns namespace {self.namespace!r}, "
                    f"but model {model.model_id!r} declares domain {model_domain!r}"
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
    def domain_pack_key(self) -> tuple[str, str] | None:
        return _pack_key(self.domain_pack)

    @property
    def model_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(model.key for model in self.models))

    @property
    def realization_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(realization.key for realization in self.realizations))


@dataclass(frozen=True)
class InstalledExtension:
    """Exact contributions from one successful install."""

    extension_id: str
    version: str
    model_keys: tuple[tuple[str, str], ...] = ()
    realization_keys: tuple[tuple[str, str], ...] = ()
    solver_keys: tuple[tuple[str, str], ...] = ()
    domain_pack_key: tuple[str, str] | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.extension_id, self.version


@dataclass
class DomainRuntime:
    """Caller-owned registries plus transactional extension installation."""

    models: ModelRegistry = field(default_factory=ModelRegistry)
    realizations: RealizationRegistry = field(default_factory=RealizationRegistry)
    solvers: SolverRegistry = field(default_factory=SolverRegistry)
    _installed: dict[tuple[str, str], InstalledExtension] = field(
        default_factory=dict,
        init=False,
        repr=False,
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

        # A DomainExtension validates its pack at construction. Revalidate at
        # the mutation boundary as defense against deliberately mutable pack
        # objects changing after the extension was created.
        if extension.domain_pack is not None:
            validate_domain_pack(extension.domain_pack)
            if extension.domain_pack_key != extension.key:
                raise ScientificCoreError(
                    "domain pack identity changed after extension construction; "
                    "refusing installation before registry mutation"
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
            domain_pack_key=extension.domain_pack_key,
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
