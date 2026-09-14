"""Domain extension installation is explicit, namespaced and transactional."""

from __future__ import annotations

import pytest

from engcore.extensions import DomainExtension, DomainRuntime
from engcore.scientific.capabilities import ScientificCapability
from engcore.scientific.errors import ScientificCoreError, SolverNotFoundError
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.models.definition import ScientificModelDefinition
from engcore.scientific.realizations.definition import (
    ModelFormulation,
    ModelRealizationDefinition,
)
from engcore.scientific.solvers.capability import SolverCapability, SolverCapabilityId
from engcore.scientific.solvers.protocol import DeclaredSupport, SolverIdentity


MODEL = ScientificModelDefinition(
    model_id="demo.linear",
    version="1",
    domain="demo.physics",
    exclusions=("nonlinear response",),
    required_capabilities=frozenset({"core:algebraic"}),
)
MODEL_REF = ModelReference(MODEL.model_id, MODEL.version)
REALIZATION = ModelRealizationDefinition(
    realization_id="demo.linear.closed_form",
    version="1",
    model=MODEL_REF,
    formulation=ModelFormulation.ALGEBRAIC,
    provided_capabilities=frozenset({ScientificCapability.parse("demo:evaluate")}),
    required_solver_capabilities=frozenset({SolverCapabilityId("core:algebraic")}),
)


class DemoSolver(DeclaredSupport):
    serves_capabilities = frozenset({"core:algebraic"})
    served_models = (MODEL_REF,)

    @property
    def identity(self):
        return SolverIdentity("demo.solver", "1", backend="python")

    @property
    def capabilities(self):
        return frozenset({SolverCapability("core:algebraic")})


class InvalidHandRolledSolver:
    @property
    def identity(self):
        return SolverIdentity("demo.invalid", "1", backend="python")

    @property
    def capabilities(self):
        return frozenset({SolverCapability("core:algebraic")})

    def supports(self, problem):
        return True


def _extension(*, solvers=(DemoSolver,)) -> DomainExtension:
    return DomainExtension(
        extension_id="demo.physics",
        version="1.0.0",
        namespace="demo",
        models=(MODEL,),
        realizations=(REALIZATION,),
        solver_factories=tuple(solvers),
    )


def test_extension_installs_all_three_registry_layers():
    runtime = DomainRuntime()
    receipt = runtime.install(_extension())
    assert runtime.models.get(MODEL.model_id, MODEL.version) == MODEL
    assert runtime.realizations.get(REALIZATION.realization_id, REALIZATION.version) == REALIZATION
    assert runtime.solvers.definition("demo.solver", "1").identity.solver_id == "demo.solver"
    assert receipt.model_keys == (MODEL.key,)
    assert receipt.realization_keys == (REALIZATION.key,)
    assert receipt.solver_keys == (("demo.solver", "1"),)
    assert runtime.installed_extensions == (receipt,)


def test_failed_solver_registration_rolls_models_realizations_and_prior_solvers_back():
    runtime = DomainRuntime()
    extension = _extension(solvers=(DemoSolver, InvalidHandRolledSolver))
    with pytest.raises(TypeError, match="core support contract"):
        runtime.install(extension)

    assert not runtime.models.contains(*MODEL.key)
    assert not runtime.realizations.contains(*REALIZATION.key)
    with pytest.raises(SolverNotFoundError):
        runtime.solvers.definition("demo.solver", "1")
    assert runtime.installed_extensions == ()


def test_uninstall_removes_only_contributions_owned_by_the_extension():
    runtime = DomainRuntime()
    receipt = runtime.install(_extension())
    assert runtime.uninstall(*receipt.key) == receipt
    assert not runtime.models.contains(*MODEL.key)
    assert not runtime.realizations.contains(*REALIZATION.key)
    with pytest.raises(SolverNotFoundError):
        runtime.solvers.definition("demo.solver", "1")
    assert runtime.installed_extensions == ()


def test_model_domain_must_live_inside_the_extension_namespace():
    foreign = ScientificModelDefinition(
        model_id="foreign.model",
        version="1",
        domain="other.physics",
        exclusions=("everything else",),
    )
    with pytest.raises(ScientificCoreError, match="owns namespace"):
        DomainExtension(
            extension_id="demo.foreign",
            version="1",
            namespace="demo",
            models=(foreign,),
        )


def test_realization_of_external_model_requires_explicit_dependency():
    external_model = ScientificModelDefinition(
        model_id="base.model",
        version="1",
        domain="base.physics",
        exclusions=("secondary effects",),
    )
    external_ref = ModelReference("base.model", "1")
    realization = ModelRealizationDefinition(
        realization_id="demo.base.realization",
        version="1",
        model=external_ref,
        formulation=ModelFormulation.ALGEBRAIC,
        provided_capabilities=frozenset({ScientificCapability.parse("demo:evaluate")}),
    )
    with pytest.raises(ScientificCoreError, match="external_models"):
        DomainExtension(
            extension_id="demo.adapter",
            version="1",
            namespace="demo",
            realizations=(realization,),
        )

    runtime = DomainRuntime()
    runtime.models.register(external_model)
    extension = DomainExtension(
        extension_id="demo.adapter",
        version="1",
        namespace="demo",
        realizations=(realization,),
        external_models=(external_ref,),
    )
    receipt = runtime.install(extension)
    assert receipt.model_keys == ()
    assert runtime.models.contains("base.model", "1")
    assert runtime.realizations.contains("demo.base.realization", "1")


def test_missing_external_model_dependency_fails_before_any_mutation():
    realization = ModelRealizationDefinition(
        realization_id="demo.base.realization",
        version="1",
        model=ModelReference("base.model", "1"),
        formulation=ModelFormulation.ALGEBRAIC,
        provided_capabilities=frozenset({ScientificCapability.parse("demo:evaluate")}),
    )
    extension = DomainExtension(
        extension_id="demo.adapter",
        version="1",
        namespace="demo",
        realizations=(realization,),
        external_models=(ModelReference("base.model", "1"),),
    )
    runtime = DomainRuntime()
    with pytest.raises(ScientificCoreError, match="not installed"):
        runtime.install(extension)
    assert len(runtime.models) == 0
    assert len(runtime.realizations) == 0


def test_same_extension_identity_cannot_be_installed_twice():
    runtime = DomainRuntime()
    extension = _extension()
    runtime.install(extension)
    with pytest.raises(ScientificCoreError, match="already installed"):
        runtime.install(extension)
