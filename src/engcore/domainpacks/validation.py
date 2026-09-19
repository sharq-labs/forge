"""Fail-closed validation of a Domain Pack before registration."""

from __future__ import annotations

from dataclasses import dataclass

from ..scientific.models.definition import ScientificModelDefinition
from ..scientific.realizations.definition import ModelRealizationDefinition
from ..scientific.solvers.registry import SolverRegistry
from .errors import InvalidDomainPackProvider
from .manifest import ArtifactRef, DOMAIN_PACK_API, DomainPackManifest
from .provider import DomainPackProvider, ProvidedArtifact


@dataclass(frozen=True)
class DomainPackValidationReport:
    pack_id: str
    pack_version: str
    errors: tuple[str, ...]
    checks: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> None:
        if self.errors:
            raise InvalidDomainPackProvider(
                f"domain pack {self.pack_id}@{self.pack_version} is invalid: "
                + "; ".join(self.errors)
            )


def _aux_refs(items: tuple[ProvidedArtifact, ...], label: str, errors: list[str]) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    for item in items:
        if not isinstance(item, ProvidedArtifact):
            errors.append(f"{label} returned {type(item).__name__}, expected ProvidedArtifact")
            continue
        refs.append(item.ref)
    if len(set(refs)) != len(refs):
        errors.append(f"{label} returned duplicate artifact identities")
    return tuple(sorted(refs))


def validate_domain_pack(provider: DomainPackProvider) -> DomainPackValidationReport:
    """Validate declaration/runtime agreement without enabling the pack."""

    errors: list[str] = []
    checks: list[str] = []

    manifest = getattr(provider, "manifest", None)
    if not isinstance(manifest, DomainPackManifest):
        raise InvalidDomainPackProvider(
            f"provider manifest must be DomainPackManifest, got {type(manifest).__name__}"
        )

    if DOMAIN_PACK_API not in manifest.compatible_core_apis:
        errors.append(
            f"pack does not declare compatibility with current API {DOMAIN_PACK_API!r}"
        )
    else:
        checks.append("core API compatibility declared")

    try:
        models = tuple(provider.models())
    except Exception as exc:
        raise InvalidDomainPackProvider("provider.models() failed during validation") from exc
    if any(not isinstance(model, ScientificModelDefinition) for model in models):
        errors.append("models() must return ScientificModelDefinition records only")
    model_refs = tuple(sorted(
        ArtifactRef(model.model_id, model.version)
        for model in models
        if isinstance(model, ScientificModelDefinition)
    ))
    if len(set(model_refs)) != len(model_refs):
        errors.append("models() returned duplicate scientific model identities")
    if model_refs != manifest.models:
        errors.append(
            f"manifest models {manifest.models!r} do not match provider models {model_refs!r}"
        )
    else:
        checks.append("model manifest matches provider")

    wrong_domains = sorted(
        f"{model.model_id}@{model.version}:{model.domain}"
        for model in models
        if isinstance(model, ScientificModelDefinition) and model.domain != manifest.domain
    )
    if wrong_domains:
        errors.append(
            f"models outside declared domain {manifest.domain!r}: {wrong_domains}"
        )

    try:
        realizations = tuple(provider.realizations())
    except Exception as exc:
        raise InvalidDomainPackProvider("provider.realizations() failed during validation") from exc
    if any(not isinstance(item, ModelRealizationDefinition) for item in realizations):
        errors.append("realizations() must return ModelRealizationDefinition records only")
    realization_refs = tuple(sorted(
        ArtifactRef(item.realization_id, item.version)
        for item in realizations
        if isinstance(item, ModelRealizationDefinition)
    ))
    if len(set(realization_refs)) != len(realization_refs):
        errors.append("realizations() returned duplicate realization identities")
    if realization_refs != manifest.realizations:
        errors.append(
            f"manifest realizations {manifest.realizations!r} do not match provider realizations {realization_refs!r}"
        )
    else:
        checks.append("realization manifest matches provider")

    model_keys = {
        (model.model_id, model.version)
        for model in models
        if isinstance(model, ScientificModelDefinition)
    }
    dangling = sorted(
        f"{item.realization_id}@{item.version}->{item.model.model_id}@{item.model.version}"
        for item in realizations
        if isinstance(item, ModelRealizationDefinition)
        and item.model_key not in model_keys
    )
    if dangling:
        errors.append(f"realizations reference models outside this atomic pack: {dangling}")
    else:
        checks.append("all realizations resolve to pack models")

    provided_capabilities = tuple(sorted({
        capability.identifier
        for item in realizations
        if isinstance(item, ModelRealizationDefinition)
        for capability in item.provided_capabilities
    }))
    if provided_capabilities != manifest.capabilities:
        errors.append(
            f"manifest capabilities {manifest.capabilities!r} do not match realization-provided capabilities "
            f"{provided_capabilities!r}"
        )
    else:
        checks.append("capability manifest matches realizations")

    solvers = ()
    try:
        factories = tuple(provider.solver_factories())
        solver_registry = SolverRegistry(factories)
        solvers = tuple(solver_registry.list())
        solver_refs = tuple(sorted(
            ArtifactRef(solver.identity.solver_id, solver.identity.version)
            for solver in solvers
        ))
    except Exception as exc:
        errors.append(f"solver factories violate the Scientific Core solver contract: {exc}")
        solver_refs = ()
    if solver_refs != manifest.solvers:
        errors.append(
            f"manifest solvers {manifest.solvers!r} do not match provider solvers {solver_refs!r}"
        )
    else:
        checks.append("solver manifest matches validated factories")

    uncovered_realizations: list[str] = []
    for realization in realizations:
        if not isinstance(realization, ModelRealizationDefinition):
            continue
        required = {item.name for item in realization.required_solver_capabilities}
        served = False
        for solver in solvers:
            declared = {item.name for item in solver.capabilities}
            solver_models = {model.key for model in solver.served_models}
            model_ok = not solver_models or realization.model_key in solver_models
            if model_ok and required <= declared:
                served = True
                break
        if not served:
            uncovered_realizations.append(
                f"{realization.realization_id}@{realization.version}"
            )
    if uncovered_realizations:
        errors.append(
            "realizations have no in-pack solver covering their exact model and required "
            f"solver capabilities: {sorted(uncovered_realizations)}"
        )
    else:
        checks.append("every realization is executable by an in-pack solver declaration")

    aux = (
        ("calibration_protocols", provider.calibration_protocols, manifest.calibration_protocols),
        ("validation_protocols", provider.validation_protocols, manifest.validation_protocols),
        ("uq_producers", provider.uq_producers, manifest.uq_producers),
        ("measurement_adapters", provider.measurement_adapters, manifest.measurement_adapters),
        ("transformations", provider.transformations, manifest.transformations),
        ("benchmarks", provider.benchmarks, manifest.benchmarks),
    )
    for label, getter, declared in aux:
        try:
            actual = _aux_refs(tuple(getter()), label, errors)
        except Exception as exc:
            errors.append(f"{label} failed during validation: {exc}")
            continue
        if actual != declared:
            errors.append(f"manifest {label} {declared!r} do not match provider {actual!r}")
        else:
            checks.append(f"{label} manifest matches provider")

    return DomainPackValidationReport(
        manifest.pack_id,
        manifest.pack_version,
        tuple(errors),
        tuple(checks),
    )
