"""MODEL0-R — Universal Model / Realization Foundation.

These tests pin the separation the milestone exists to establish:

    scientific capability -> scientific model -> computational realization
    -> solver capability -> scientific solver

and the invariants that keep it from collapsing back into one blob. They also
assert that the milestone was *additive*: every legacy
``ScientificModelDefinition`` behaviour and serialized form is unchanged, and
a domain that never declares a realization keeps working.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from src.engcore.scientific import (
    DuplicateRegistrationError,
    ImplementationReference,
    InvalidModelRealization,
    InvalidScientificCapability,
    ModelFormulation,
    ModelReference,
    ModelRealizationDefinition,
    ModelRegistry,
    ModelType,
    ModelValidationStatus,
    RealizationNotFoundError,
    RealizationRegistry,
    ScientificCapability,
    ScientificModelDefinition,
    SolverCapability,
    SolverCapabilityId,
    capability_identifiers,
    scientific_capabilities,
    to_json,
)
from src.engcore.scientific.capabilities import SCIENTIFIC_CAPABILITY_SCHEMA
from src.engcore.scientific.solvers.capability import CoreCapabilities

SCIENTIFIC_ROOT = (
    pathlib.Path(__file__).resolve().parents[1] / "src" / "engcore" / "scientific"
)

# Capability identifiers used only as test fixtures. They are never registered
# anywhere and the core knows nothing about them — which is the point.
ELASTICITY = ScientificCapability("mechanics", "linear_elasticity")
CONDUCTION = ScientificCapability("thermal", "heat_conduction")
WAVES = ScientificCapability("electromagnetics", "wave_propagation")


def _model_reference() -> ModelReference:
    return ModelReference("example.model", "1.0.0")


def _realization(**overrides) -> ModelRealizationDefinition:
    payload = dict(
        realization_id="example.model.analytical",
        version="1.0.0",
        model=_model_reference(),
        formulation=ModelFormulation.ALGEBRAIC,
        provided_capabilities={ELASTICITY},
        required_solver_capabilities={CoreCapabilities.ALGEBRAIC},
    )
    payload.update(overrides)
    return ModelRealizationDefinition(**payload)


# =====================================================================
# 1. ScientificCapability — identity, validation, namespace handling
# =====================================================================

def test_capability_parses_and_renders_its_canonical_identifier():
    capability = ScientificCapability.parse("mechanics:linear_elasticity")
    assert capability.namespace == "mechanics"
    assert capability.name == "linear_elasticity"
    assert capability.identifier == "mechanics:linear_elasticity"


def test_capability_accepts_dotted_sub_namespaces():
    capability = ScientificCapability.parse("mechanics:solid.linear_elasticity")
    assert capability.name == "solid.linear_elasticity"


@pytest.mark.parametrize(
    "identifier",
    [
        "linear_elasticity",          # no namespace at all
        "mechanics:solid:elasticity",  # two separators
        ":linear_elasticity",          # empty namespace
        "mechanics:",                  # empty name
        "Mechanics:linear_elasticity",  # not canonical lowercase
        "mechanics:linear elasticity",  # whitespace inside a segment
        "mechanics:1_elasticity",      # segment must start with a letter
        "mechanics:linear-elasticity",  # hyphen is not in the grammar
        "mechanics:.elasticity",       # empty dotted sub-segment
    ],
)
def test_capability_rejects_malformed_identifiers(identifier):
    with pytest.raises(InvalidScientificCapability):
        ScientificCapability.parse(identifier)


def test_capability_never_defaults_a_missing_namespace():
    """An unnamespaced name is refused, not filed under some ``core:``.

    Guessing which science a bare name belongs to is inference, and the
    failure-semantics contract requires "unknown" to stay distinguishable.
    """
    with pytest.raises(InvalidScientificCapability) as excinfo:
        ScientificCapability.parse("heat_conduction")
    assert "namespace" in str(excinfo.value)


def test_capability_rejects_empty_segments_when_constructed_directly():
    with pytest.raises(InvalidScientificCapability):
        ScientificCapability(namespace="  ", name="heat_conduction")
    with pytest.raises(InvalidScientificCapability):
        ScientificCapability(namespace="thermal", name="")


def test_capability_equality_and_hashing_are_value_based():
    a = ScientificCapability("thermal", "heat_conduction")
    b = ScientificCapability.parse("thermal:heat_conduction")
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1
    assert a != ScientificCapability("thermal", "heat_convection")


def test_capability_is_immutable():
    capability = ScientificCapability("thermal", "heat_conduction")
    with pytest.raises(Exception):
        capability.name = "heat_convection"  # type: ignore[misc]


def test_capability_serialization_round_trips_deterministically():
    capability = ScientificCapability("electromagnetics", "wave_propagation")
    payload = capability.to_dict()
    assert payload["schema"] == SCIENTIFIC_CAPABILITY_SCHEMA
    assert ScientificCapability.from_dict(payload) == capability
    assert to_json(capability) == to_json(capability)
    assert json.loads(to_json(capability)) == payload


def test_capability_helpers_normalize_and_sort():
    mixed = ["thermal:heat_conduction", CONDUCTION, WAVES]
    normalized = scientific_capabilities(mixed)
    assert normalized == {CONDUCTION, WAVES}
    assert capability_identifiers(normalized) == (
        "electromagnetics:wave_propagation",
        "thermal:heat_conduction",
    )


def test_coerce_refuses_a_solver_capability():
    """The two capability types must never be silently interchangeable."""
    with pytest.raises(InvalidScientificCapability):
        ScientificCapability.coerce(CoreCapabilities.ALGEBRAIC)  # type: ignore[arg-type]


def test_scientific_capability_is_not_a_solver_capability():
    assert not isinstance(ELASTICITY, SolverCapability)
    assert not isinstance(CoreCapabilities.PDE, ScientificCapability)
    # A same-spelled name in each type is still two different things.
    assert ScientificCapability("core", "pde") != SolverCapability("core:pde")


def test_capability_has_no_global_registry():
    import src.engcore.scientific.capabilities as module

    assert not [
        name
        for name, value in vars(module).items()
        if isinstance(value, (dict, set, list)) and not name.startswith("__")
    ]


# =====================================================================
# 1b. SolverCapability identity
#
# Identity is the canonical name. ``description`` is documentation *about* a
# capability and was never part of it; that it participated in equality and
# hashing was a defect, corrected at its source rather than worked around by
# storing bare strings downstream.
# =====================================================================

def test_solver_capability_identity_is_its_name_not_its_description():
    reworded = SolverCapability("core:pde", "reworded in a later release")
    assert reworded == CoreCapabilities.PDE
    assert hash(reworded) == hash(CoreCapabilities.PDE)
    assert len({reworded, CoreCapabilities.PDE}) == 1
    assert {CoreCapabilities.PDE: "found"}[reworded] == "found"


def test_solver_capability_description_survives_serialization():
    """Identity changed; the stored schema did not."""
    payload = SolverCapability("core:pde", "kept for humans").to_dict()
    assert payload == {
        "schema": "solver_capability/1",
        "name": "core:pde",
        "description": "kept for humans",
    }
    assert SolverCapability.from_dict(payload).description == "kept for humans"


def test_solver_capability_exposes_its_identity_separately():
    assert CoreCapabilities.PDE.id == SolverCapabilityId("core:pde")
    assert SolverCapabilityId.coerce(CoreCapabilities.PDE).name == "core:pde"
    assert SolverCapabilityId.coerce("core:pde") == CoreCapabilities.PDE.id
    assert str(SolverCapabilityId("core:pde")) == "core:pde"


def test_solver_capability_id_validates_and_canonicalizes():
    from src.engcore.scientific.errors import ScientificCoreError

    assert SolverCapabilityId("  core:pde  ").name == "core:pde"
    for bad in ("", "   ", "core pde", "core\tpde"):
        with pytest.raises(ScientificCoreError):
            SolverCapabilityId(bad)
    with pytest.raises(ScientificCoreError):
        SolverCapabilityId.coerce(object())  # type: ignore[arg-type]


def test_solver_capability_id_is_immutable():
    identity = SolverCapabilityId("core:pde")
    with pytest.raises(Exception):
        identity.name = "core:ode"  # type: ignore[misc]


def test_solver_capability_id_is_not_a_scientific_capability():
    """Two capability vocabularies that must never be interchangeable."""
    assert not isinstance(SolverCapabilityId("core:pde"), ScientificCapability)
    assert not isinstance(ScientificCapability("core", "pde"), SolverCapabilityId)
    assert SolverCapabilityId("core:pde") != ScientificCapability("core", "pde")
    with pytest.raises(InvalidScientificCapability):
        ScientificCapability.coerce(
            SolverCapabilityId("core:pde")  # type: ignore[arg-type]
        )


def test_solver_capability_id_does_not_widen_what_the_core_accepts():
    """Namespacing stays a convention, deliberately not a new hard rule.

    ``SolverCapability`` has always accepted any non-empty, whitespace-free
    name. Tightening that to a ``namespace:name`` grammar here would
    retroactively invalidate historical records whose capability names were
    unnamespaced, and migrating frozen records is out of scope for this pass.
    """
    assert SolverCapability("legacy_unnamespaced").name == "legacy_unnamespaced"
    assert SolverCapabilityId("legacy_unnamespaced").name == "legacy_unnamespaced"


def test_solver_registry_deduplicates_identically_named_capabilities():
    """A visible consequence of the identity fix, and the intended one."""
    from src.engcore.scientific.solvers import SolverIdentity, SolverRegistry

    class _Solver:
        def __init__(self, solver_id, capabilities):
            self.identity = SolverIdentity(solver_id, "1.0.0")
            self._capabilities = frozenset(capabilities)

        @property
        def capabilities(self):
            return self._capabilities

        def supports(self, problem):
            return True

        def prepare(self, problem):  # pragma: no cover - unused here
            raise NotImplementedError

        def solve(self, prepared):  # pragma: no cover - unused here
            raise NotImplementedError

    registry = SolverRegistry(
        [
            _Solver("a", {SolverCapability("core:pde", "one wording")}),
            _Solver("b", {SolverCapability("core:pde", "another wording")}),
        ]
    )
    assert registry.capabilities() == frozenset({SolverCapability("core:pde")})
    assert registry.capability_names() == ("core:pde",)


# =====================================================================
# 2. Formulation, and the deliberate absence of a fidelity classification
# =====================================================================

def test_formulation_members_and_serialized_values():
    assert {member.value for member in ModelFormulation} == {
        "algebraic", "ode", "dae", "pde", "discrete",
    }
    for member in ModelFormulation:
        assert ModelFormulation(member.value) is member


def test_formulation_carries_no_realization_strategy_member():
    """``SURROGATE`` named a strategy, not a mathematical form.

    A surrogate is itself posed in one of these forms — a response surface is
    algebraic, a learned latent-dynamics model is an ODE — so the member made
    a caller discard the form in order to record the strategy. It is deferred,
    and no member, field or flag replaces it.
    """
    assert not hasattr(ModelFormulation, "SURROGATE")
    for strategy in ("surrogate", "emulator", "reduced_order", "data_driven"):
        with pytest.raises(ValueError):
            ModelFormulation(strategy)

    fields = set(ModelRealizationDefinition.__dataclass_fields__)
    for smuggled in ("strategy", "surrogate", "is_surrogate", "emulates"):
        assert smuggled not in fields


def test_no_universal_fidelity_classification_is_declared_anywhere():
    """MODEL0-R records no absolute fidelity category, and nothing replaces it.

    The rejected enum had the members ANALYTICAL, REDUCED_ORDER, ENGINEERING,
    NUMERICAL and HIGH_FIDELITY. Those are not one semantic axis: solution
    character (analytical vs numerical), order reduction, provenance and
    *relative* resolution are four independent things, and a single-valued
    field spanning four axes cannot record any of them honestly.
    """
    import src.engcore.scientific as scientific
    import src.engcore.scientific.realizations as realizations
    from src.engcore.scientific.realizations import definition

    for module in (scientific, realizations, definition):
        assert not hasattr(module, "RealizationFidelity")
        assert "RealizationFidelity" not in getattr(module, "__all__", ())

    assert "fidelity" not in ModelRealizationDefinition.__dataclass_fields__
    assert "fidelity" not in _realization().to_dict()


def test_no_speculative_enum_was_substituted_for_the_removed_one():
    """The field is deferred, not renamed. No synonym, flag or open bag of
    metadata may reintroduce the same unevidenced claim under a new spelling.
    """
    fields = set(ModelRealizationDefinition.__dataclass_fields__)
    for smuggled in (
        "fidelity", "realization_fidelity", "accuracy", "resolution",
        "approximation", "approximation_class", "fidelity_class",
        "fidelity_level", "rank", "level", "tier", "grade", "quality",
        "cost", "cost_class", "reduced_order", "is_high_fidelity",
        "metadata", "extra", "attributes", "tags",
        # Calibration is epistemic evidence, and has its own evidenced home.
        "calibrated", "calibration", "calibration_data", "fitted",
        "fit_residual", "tuning", "evidence",
    ):
        assert smuggled not in fields

    assert set(_realization().to_dict()) == {
        "schema", "realization_id", "version", "model", "formulation",
        "name", "description", "provided_capabilities",
        "required_capabilities", "required_solver_capabilities",
        "assumptions", "implementation",
    }


def test_the_combinations_that_killed_the_fidelity_enum_now_cost_nothing():
    """``numerical + reduced_order`` and ``numerical + high_fidelity``.

    These are the ordinary cases — nearly every reduced-order and every
    high-fidelity realization in practice is also numerical — and under a
    single-valued enum each one forced the author to delete one true fact to
    record the other. Both facts now survive, and survive a round trip: the
    computational form in ``formulation``, the approximation stated as the
    falsifiable claim it actually is in ``assumptions``.
    """
    rom = _realization(
        realization_id="example.model.rom",
        formulation=ModelFormulation.ODE,
        assumptions=("POD-Galerkin reduction to 12 modes",),
    )
    hifi = _realization(
        realization_id="example.model.dns",
        formulation=ModelFormulation.PDE,
        assumptions=("direct numerical simulation; no turbulence closure",),
    )

    # Neither record had to choose between "numerical" and its other claim.
    for realization in (rom, hifi):
        restored = ModelRealizationDefinition.from_dict(realization.to_dict())
        assert restored == realization
        assert restored.formulation is realization.formulation
        assert restored.assumptions == realization.assumptions

    assert rom.formulation is not hifi.formulation
    assert rom.assumptions != hifi.assumptions


def test_deserialization_rejects_rather_than_ignores_a_fidelity_key():
    """A payload written against the rejected design must fail loudly.

    Ignoring the key would let a caller believe a claim round-tripped that
    was in fact discarded — the precise failure the removal exists to stop.
    """
    payload = _realization().to_dict()
    payload["fidelity"] = "high_fidelity"
    with pytest.raises(InvalidModelRealization):
        ModelRealizationDefinition.from_dict(payload)


def test_calibration_keeps_its_existing_evidence_backed_home():
    """The rejected enum once carried a ``CALIBRATED`` member too.

    The package already answers "is this calibrated?", and answers it better:
    a calibrated twin fails closed without calibration evidence, whereas a
    fidelity member would have let any record claim it with none. Removing
    the enum does not orphan the question — it never owned it.
    """
    from src.engcore.scientific.twins.definition import ScientificTwin, TwinKind

    assert TwinKind.CALIBRATED.value == "calibrated"
    assert "calibration_evidence_refs" in ScientificTwin.__dataclass_fields__


def test_formulation_is_independent_of_model_type():
    """Epistemic character and computational form are separate axes."""
    assert {m.value for m in ModelFormulation} & {m.value for m in ModelType} == set()


def test_relative_fidelity_keeps_its_existing_study_scoped_home():
    """Ordering fidelity is answerable only against a stated study, and the
    repository already has the contract for it. MODEL0-R neither duplicates
    nor perturbs it, and adds no core-level competitor to it.
    """
    from src.engcore.design.fidelity import FidelityLadder, FidelityRung

    ladder = FidelityLadder(
        ladder_id="example",
        version="1.0.0",
        rungs=(FidelityRung("cheap", 0), FidelityRung("fine", 1)),
    )
    assert ladder.next_after("cheap").rung_id == "fine"
    assert ladder.rung("fine").rank > ladder.rung("cheap").rank


# =====================================================================
# 3. ModelRealizationDefinition — construction and reference integrity
# =====================================================================

def test_realization_construction_records_every_declared_field():
    realization = _realization(
        name="Analytical realization",
        description="Closed-form evaluation.",
        required_capabilities={CONDUCTION},
        assumptions=("small strain", "isotropic"),
        implementation=ImplementationReference(
            "example.impl", "0.2.0", reference="internal note"
        ),
    )
    assert realization.key == ("example.model.analytical", "1.0.0")
    assert realization.model_key == ("example.model", "1.0.0")
    assert realization.formulation is ModelFormulation.ALGEBRAIC
    assert realization.provides(ELASTICITY)
    assert realization.requires(CONDUCTION)
    assert realization.requires_solver_capability(CoreCapabilities.ALGEBRAIC)
    assert realization.assumptions == ("small strain", "isotropic")
    assert realization.implementation.key == ("example.impl", "0.2.0")


def test_realization_references_a_model_without_embedding_it():
    model = ScientificModelDefinition(
        model_id="example.model",
        version="1.0.0",
        model_type=ModelType.FUNDAMENTAL_RELATION,
    )
    realization = _realization(model=ModelReference(*model.key))
    assert realization.model_key == model.key
    # The realization carries the identity and nothing else about the model.
    payload = realization.to_dict()
    assert payload["model"] == {
        "schema": "model_reference/1",
        "model_id": "example.model",
        "version": "1.0.0",
    }
    for forked in ("assumptions_of_model", "validity", "inputs", "outputs"):
        assert forked not in payload


def test_realization_refuses_an_embedded_model_definition():
    model = ScientificModelDefinition(model_id="example.model", version="1.0.0")
    with pytest.raises(InvalidModelRealization) as excinfo:
        _realization(model=model)
    assert "ModelReference" in str(excinfo.value)


def test_realization_refuses_a_duck_typed_model_stand_in():
    class Pretender:
        model_id = "example.model"
        version = "1.0.0"
        key = ("example.model", "1.0.0")

    with pytest.raises(InvalidModelRealization):
        _realization(model=Pretender())


@pytest.mark.parametrize("field", ["realization_id", "version"])
def test_realization_requires_non_empty_identity(field):
    with pytest.raises(InvalidModelRealization):
        _realization(**{field: "   "})


def test_realization_requires_at_least_one_provided_capability():
    with pytest.raises(InvalidModelRealization) as excinfo:
        _realization(provided_capabilities=frozenset())
    assert "provides nothing" in str(excinfo.value)


def test_realization_refuses_to_require_what_it_provides():
    with pytest.raises(InvalidModelRealization) as excinfo:
        _realization(
            provided_capabilities={ELASTICITY},
            required_capabilities={ELASTICITY},
        )
    assert "cannot depend on itself" in str(excinfo.value)


def test_realization_accepts_capability_identifier_strings():
    realization = _realization(
        provided_capabilities={"mechanics:linear_elasticity"},
        required_capabilities=("thermal:heat_conduction",),
    )
    assert realization.provided_capabilities == {ELASTICITY}
    assert realization.required_capabilities == {CONDUCTION}


def test_realization_rejects_a_malformed_capability_string():
    with pytest.raises(InvalidScientificCapability):
        _realization(provided_capabilities={"linear_elasticity"})


def test_realization_stores_typed_solver_capability_identities():
    """Declarations, names and identities all normalize to one typed identity.

    The stored value is a ``SolverCapabilityId``, not a bare string and not a
    ``SolverCapability``: a requirement references a capability, so it must
    hold exactly what it can serialize and reload unchanged. A stored
    declaration would come back from ``from_dict`` with its description
    silently emptied.
    """
    realization = _realization(
        required_solver_capabilities={
            CoreCapabilities.PDE,
            "core:linear_system",
            SolverCapabilityId("core:ode"),
        }
    )
    assert realization.required_solver_capabilities == {
        SolverCapabilityId("core:pde"),
        SolverCapabilityId("core:linear_system"),
        SolverCapabilityId("core:ode"),
    }
    assert all(
        isinstance(c, SolverCapabilityId)
        for c in realization.required_solver_capabilities
    )
    assert not any(
        isinstance(c, SolverCapability)
        for c in realization.required_solver_capabilities
    )
    assert realization.requires_solver_capability("core:pde")
    assert realization.requires_solver_capability(CoreCapabilities.LINEAR_SYSTEM)
    assert realization.requires_solver_capability(SolverCapabilityId("core:ode"))
    assert not realization.requires_solver_capability(CoreCapabilities.STOCHASTIC)


def test_realization_solver_requirement_ignores_declaration_prose():
    """Requiring ``core:pde`` must match a solver's ``core:pde`` regardless of
    how either side worded its description."""
    reworded = SolverCapability("core:pde", "reworded in a later release")
    realization = _realization(required_solver_capabilities={CoreCapabilities.PDE})
    assert realization.requires_solver_capability(reworded)
    assert realization.solver_capability_gap([reworded]) == frozenset()


def test_realization_rejects_an_empty_solver_capability_name():
    with pytest.raises(InvalidModelRealization):
        _realization(required_solver_capabilities={"  "})


def test_realization_rejects_a_whitespace_bearing_solver_capability_name():
    """A typed identity validates on construction; a bare string never did."""
    with pytest.raises(InvalidModelRealization):
        _realization(required_solver_capabilities={"core pde"})


def test_realization_canonicalizes_solver_capability_names():
    """Surrounding whitespace must not create a second, distinct requirement."""
    realization = _realization(
        required_solver_capabilities={"  core:pde  ", "core:pde"}
    )
    assert realization.required_solver_capabilities == {
        SolverCapabilityId("core:pde")
    }
    assert realization.to_dict()["required_solver_capabilities"] == ["core:pde"]


def test_realization_rejects_an_unknown_formulation():
    with pytest.raises(ValueError):
        _realization(formulation="finite_volume")


def test_realization_has_no_fidelity_parameter_to_pass():
    with pytest.raises(TypeError):
        _realization(fidelity="high_fidelity")


def test_realization_rejects_a_non_reference_implementation():
    with pytest.raises(InvalidModelRealization):
        _realization(implementation={"implementation_id": "x", "version": "1"})


def test_implementation_reference_requires_identity():
    with pytest.raises(InvalidModelRealization):
        ImplementationReference("", "1.0.0")
    with pytest.raises(InvalidModelRealization):
        ImplementationReference("example.impl", "  ")


def test_realization_has_no_metadata_escape_hatch():
    """Deferred concepts must be deferred, not smuggled through a dict."""
    assert "metadata" not in _realization().to_dict()
    with pytest.raises(TypeError):
        _realization(metadata={"mesh": "unstructured"})


def test_realization_carries_no_deferred_structures():
    payload = _realization().to_dict()
    for deferred in (
        "material", "materials", "geometry", "mesh", "field", "fields",
        "state", "history", "coupling",
    ):
        assert deferred not in payload


def test_realization_is_immutable():
    realization = _realization()
    with pytest.raises(Exception):
        realization.version = "2.0.0"  # type: ignore[misc]


def test_solver_capability_gap_reports_without_deciding():
    realization = _realization(
        required_solver_capabilities={"core:pde", "core:linear_system"}
    )
    assert realization.solver_capability_gap([CoreCapabilities.PDE]) == frozenset(
        {SolverCapabilityId("core:linear_system")}
    )
    assert realization.solver_capability_gap(
        [CoreCapabilities.PDE, "core:linear_system"]
    ) == frozenset()


# =====================================================================
# 4. Realization serialization
# =====================================================================

def test_realization_serialization_round_trips():
    realization = _realization(
        name="Analytical realization",
        description="Closed form.",
        required_capabilities={CONDUCTION, WAVES},
        required_solver_capabilities={"core:algebraic", "core:linear_system"},
        assumptions=("isotropic",),
        implementation=ImplementationReference("example.impl", "0.2.0"),
    )
    restored = ModelRealizationDefinition.from_dict(realization.to_dict())
    assert restored == realization


def test_realization_serialization_is_byte_stable_across_declaration_order():
    """Set ordering must never leak into the record."""
    first = _realization(
        provided_capabilities=[ELASTICITY, CONDUCTION, WAVES],
        required_solver_capabilities=["core:pde", "core:algebraic"],
    )
    second = _realization(
        provided_capabilities=[WAVES, ELASTICITY, CONDUCTION],
        required_solver_capabilities=["core:algebraic", "core:pde"],
    )
    assert to_json(first) == to_json(second)
    assert to_json(first) == to_json(first)


def test_realization_serializes_capabilities_as_sorted_identifiers():
    payload = _realization(
        provided_capabilities={ELASTICITY, CONDUCTION}
    ).to_dict()
    assert payload["provided_capabilities"] == [
        "mechanics:linear_elasticity",
        "thermal:heat_conduction",
    ]


def test_realization_load_rejects_a_foreign_schema():
    payload = _realization().to_dict()
    payload["schema"] = "model_realization_definition/2"
    with pytest.raises(Exception):
        ModelRealizationDefinition.from_dict(payload)


def test_realization_schema_is_its_own_and_not_the_models_schema():
    from src.engcore.scientific.models.definition import MODEL_SCHEMA
    from src.engcore.scientific.realizations.definition import REALIZATION_SCHEMA

    assert REALIZATION_SCHEMA == "model_realization_definition/1"
    assert REALIZATION_SCHEMA != MODEL_SCHEMA


# =====================================================================
# 5. RealizationRegistry
# =====================================================================

def _registry() -> RealizationRegistry:
    return RealizationRegistry(
        [
            _realization(),
            _realization(
                realization_id="example.model.numerical",
                formulation=ModelFormulation.PDE,
                provided_capabilities={ELASTICITY, CONDUCTION},
                required_solver_capabilities={"core:pde"},
            ),
            _realization(
                realization_id="other.model.discrete",
                model=ModelReference("other.model", "2.0.0"),
                formulation=ModelFormulation.DISCRETE,
                provided_capabilities={WAVES},
                required_solver_capabilities={"core:algebraic"},
            ),
        ]
    )


def test_registry_registers_and_looks_up_by_exact_identity():
    registry = _registry()
    assert len(registry) == 3
    assert registry.contains("example.model.analytical", "1.0.0")
    found = registry.get("example.model.analytical", "1.0.0")
    assert found.formulation is ModelFormulation.ALGEBRAIC


def test_registry_rejects_a_duplicate_identity():
    registry = RealizationRegistry([_realization()])
    with pytest.raises(DuplicateRegistrationError):
        registry.register(_realization())


def test_registry_allows_a_second_version_of_the_same_realization():
    registry = RealizationRegistry([_realization()])
    registry.register(_realization(version="2.0.0"))
    assert registry.versions("example.model.analytical") == ("1.0.0", "2.0.0")


def test_registry_rejects_a_non_realization():
    registry = RealizationRegistry()
    with pytest.raises(TypeError):
        registry.register(ScientificModelDefinition("m", "1.0.0"))


def test_registry_missing_identity_raises_its_own_error():
    registry = _registry()
    with pytest.raises(RealizationNotFoundError):
        registry.get("nope", "1.0.0")
    with pytest.raises(RealizationNotFoundError):
        registry.unregister("nope", "1.0.0")


def test_registry_unregisters():
    registry = _registry()
    registry.unregister("example.model.analytical", "1.0.0")
    assert not registry.contains("example.model.analytical", "1.0.0")
    assert len(registry) == 2


def test_registry_lists_realizations_for_one_scientific_model():
    registry = _registry()
    found = registry.for_model("example.model", "1.0.0")
    assert [r.realization_id for r in found] == [
        "example.model.analytical",
        "example.model.numerical",
    ]


def test_registry_distinguishes_a_model_version_it_has_no_realization_for():
    """Model known, realization absent — an empty tuple, never an exception."""
    registry = _registry()
    assert registry.for_model("example.model", "9.9.9") == ()


def test_registry_filters_by_provided_scientific_capability():
    registry = _registry()
    assert [r.realization_id for r in registry.providing(ELASTICITY)] == [
        "example.model.analytical",
        "example.model.numerical",
    ]
    assert [
        r.realization_id
        for r in registry.providing("electromagnetics:wave_propagation")
    ] == ["other.model.discrete"]
    assert registry.providing("thermal:heat_convection") == ()


def test_registry_filters_by_required_solver_capability():
    registry = _registry()
    found = registry.list(requires_solver_capability=CoreCapabilities.PDE)
    assert [r.realization_id for r in found] == ["example.model.numerical"]
    found = registry.list(requires_solver_capability="core:algebraic")
    assert [r.realization_id for r in found] == [
        "example.model.analytical",
        "other.model.discrete",
    ]


def test_registry_filters_by_formulation():
    registry = _registry()
    assert [
        r.realization_id
        for r in registry.list(formulation=ModelFormulation.DISCRETE)
    ] == ["other.model.discrete"]
    assert [
        r.realization_id
        for r in registry.list(formulation=ModelFormulation.PDE)
    ] == ["example.model.numerical"]
    assert registry.list(formulation=ModelFormulation.DAE) == ()


def test_registry_offers_no_fidelity_filter_to_match_the_absent_field():
    """A filter over a fact no record declares could only ever lie."""
    import inspect

    parameters = inspect.signature(RealizationRegistry.list).parameters
    assert "formulation" in parameters
    assert "fidelity" not in parameters
    with pytest.raises(TypeError):
        _registry().list(fidelity="high_fidelity")


def test_registry_filters_by_model_id():
    registry = _registry()
    assert [
        r.realization_id for r in registry.list(model_id="other.model")
    ] == ["other.model.discrete"]


def test_registry_iteration_and_listing_are_deterministic():
    forward = [_realization(), _realization(realization_id="a.b.c")]
    backward = list(reversed(forward))
    assert [r.key for r in RealizationRegistry(forward)] == [
        r.key for r in RealizationRegistry(backward)
    ]


def test_registry_introspection_supports_unknown_versus_unsupported():
    """The contract that keeps two different failures distinguishable later."""
    registry = _registry()
    provided = registry.provided_capabilities()
    assert provided == {ELASTICITY, CONDUCTION, WAVES}
    # Provided by something, but no realization satisfies the extra filter:
    # "unsupported here", not "never heard of it".
    assert ELASTICITY in provided
    assert registry.list(
        provides=ELASTICITY, formulation=ModelFormulation.DISCRETE
    ) == ()
    # Genuinely unknown to this registry.
    assert ScientificCapability("thermal", "radiation") not in provided


def test_registry_reports_required_solver_capabilities_and_model_keys():
    registry = _registry()
    assert registry.required_solver_capabilities() == (
        SolverCapabilityId("core:algebraic"),
        SolverCapabilityId("core:pde"),
    )
    assert registry.model_keys() == (
        ("example.model", "1.0.0"),
        ("other.model", "2.0.0"),
    )


def test_registry_serialization_round_trips_deterministically():
    registry = _registry()
    payload = registry.to_dict()
    restored = RealizationRegistry.from_dict(payload)
    assert restored.to_dict() == payload
    assert to_json(registry) == to_json(restored)


def test_registry_has_no_module_level_singleton():
    import src.engcore.scientific.realizations.registry as module

    assert not [
        name
        for name, value in vars(module).items()
        if isinstance(value, RealizationRegistry)
    ]


def test_registry_never_selects_or_ranks():
    """No resolve/select/rank/best surface exists yet, by design."""
    forbidden = {"resolve", "select", "rank", "best", "choose", "prefer"}
    assert forbidden & set(dir(RealizationRegistry)) == set()


# =====================================================================
# 6. Backward compatibility
# =====================================================================

LEGACY_MODEL_JSON = {
    "schema": "scientific_model_definition/1",
    "model_id": "legacy.model",
    "version": "0.1.0",
    "name": "Legacy model",
    "domain": "example",
    "model_type": "empirical_correlation",
    "description": "A record written before MODEL0-R existed.",
    "inputs": [],
    "outputs": [],
    "assumptions": ["steady state"],
    "validity": {
        "schema": "validity_domain/1",
        "conditions": [],
        "description": "",
    },
    "references": [],
    "required_capabilities": ["core:algebraic"],
    "validation_status": "self_consistent",
    "metadata": {},
}


def test_legacy_model_record_still_loads_unchanged():
    model = ScientificModelDefinition.from_dict(LEGACY_MODEL_JSON)
    assert model.key == ("legacy.model", "0.1.0")
    assert model.model_type is ModelType.EMPIRICAL_CORRELATION
    assert model.validation_status is ModelValidationStatus.SELF_CONSISTENT
    assert model.required_capabilities == frozenset({"core:algebraic"})


def test_legacy_model_record_re_serializes_byte_identically():
    """MODEL0-R must not perturb one byte of a frozen scientific record."""
    model = ScientificModelDefinition.from_dict(LEGACY_MODEL_JSON)
    assert model.to_dict() == LEGACY_MODEL_JSON
    assert to_json(model) == json.dumps(LEGACY_MODEL_JSON, sort_keys=True)


def test_model_definition_gained_no_realization_fields():
    fields = set(ScientificModelDefinition.__dataclass_fields__)
    assert fields == {
        "model_id", "version", "name", "domain", "model_type", "description",
        "inputs", "outputs", "assumptions", "validity", "references",
        "required_capabilities", "validation_status", "metadata",
    }
    for added in ("realization", "formulation", "fidelity", "realizations"):
        assert added not in fields


def test_a_model_without_any_realization_remains_fully_usable():
    """Existing domains declared no realization and must keep working."""
    model = ScientificModelDefinition.from_dict(LEGACY_MODEL_JSON)
    models = ModelRegistry([model])
    realizations = RealizationRegistry()

    assert models.get("legacy.model", "0.1.0") is model
    assert models.list(capability="core:algebraic") == (model,)
    # The realization registry simply has nothing to say about it, and says so
    # without raising.
    assert realizations.for_model(*model.key) == ()


def test_existing_domain_models_still_construct_and_serialize():
    from src.engcore.domains.electrical.dc.models import build_dc_model_registry

    registry = build_dc_model_registry()
    assert len(registry) >= 1
    for model in registry:
        assert ScientificModelDefinition.from_dict(model.to_dict()) == model


def test_model_and_realization_are_distinct_types():
    assert ScientificModelDefinition is not ModelRealizationDefinition
    assert not issubclass(ModelRealizationDefinition, ScientificModelDefinition)
    assert not issubclass(ScientificModelDefinition, ModelRealizationDefinition)


def test_model_registry_and_realization_registry_do_not_accept_each_other():
    models = ModelRegistry()
    realizations = RealizationRegistry()
    with pytest.raises(TypeError):
        models.register(_realization())
    with pytest.raises(TypeError):
        realizations.register(ScientificModelDefinition("m", "1.0.0"))


# =====================================================================
# 7. Architectural guardrails for the new contracts
# =====================================================================

NEW_MODULES = (
    SCIENTIFIC_ROOT / "capabilities.py",
    SCIENTIFIC_ROOT / "realizations" / "definition.py",
    SCIENTIFIC_ROOT / "realizations" / "registry.py",
    SCIENTIFIC_ROOT / "realizations" / "__init__.py",
)


def test_new_modules_import_no_llm_provider_or_platform():
    banned = (
        "openai", "anthropic", "google.generativeai", "gemini", "cohere",
        "langchain", "fastapi", "flask", "django", "sqlalchemy", "torch",
        "requests", "httpx",
    )
    offenders = []
    for path in NEW_MODULES:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                offenders += [
                    f"{path.name}: {stripped}" for name in banned if name in stripped
                ]
    assert not offenders, offenders


def test_universal_core_imports_no_domain_package():
    """Dependency direction: domains depend on the core, never the reverse."""
    offenders = []
    for path in SCIENTIFIC_ROOT.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            for banned in ("domains", "engcore.design", "engcore.sria", "systems"):
                if banned in stripped:
                    offenders.append(f"{path.name}: {stripped}")
    assert not offenders, f"core reached down into a higher layer: {offenders}"


def test_new_contracts_hard_code_no_domain_name():
    """The universal core must name no physics, product or vendor.

    Docstrings are scanned too: a core that *explains itself* in terms of one
    domain has already started to belong to that domain.
    """
    banned = (
        "openfoam", "ansys", "abaqus", "comsol", "fluent", "starccm",
        "navier", "reynolds", "maxwell", "radar", "cfd", "fem", "fvm",
        "circuit", "kinetics", "combustion", "aerodynamic",
    )
    offenders = []
    for path in NEW_MODULES:
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            lowered = line.lower()
            for name in banned:
                if name in lowered:
                    offenders.append(f"{path.name}:{number}: {name}")
    assert not offenders, f"domain-specific names in the universal core: {offenders}"


def test_new_contracts_contain_no_domain_conditional_logic():
    """No ``if <domain> ==`` branching may exist in the universal contracts."""
    for path in NEW_MODULES:
        text = path.read_text(encoding="utf-8")
        assert "implementation_id ==" not in text
        assert "namespace ==" not in text
        assert ".model_id ==" not in text


def test_realizations_do_not_import_the_model_definition():
    """A realization references a model; it must not depend on its internals."""
    path = SCIENTIFIC_ROOT / "realizations" / "definition.py"
    imports = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not [line for line in imports if "models" in line]
    assert not [line for line in imports if "ScientificModelDefinition" in line]


def test_failure_states_are_distinguishable_error_types():
    """Section 11: five future planner outcomes must stay tellable apart."""
    from src.engcore.scientific.errors import (
        InvalidScientificCapability,
        ModelNotFoundError,
        RealizationNotFoundError,
        ScientificCoreError,
        SolverNotFoundError,
    )

    distinct = {
        InvalidScientificCapability,
        ModelNotFoundError,
        RealizationNotFoundError,
        SolverNotFoundError,
    }
    assert len(distinct) == 4
    for error in distinct:
        assert issubclass(error, ScientificCoreError)
        assert not any(
            other is not error and issubclass(error, other) for other in distinct
        )


# =====================================================================
# 8. Revalidation against the architecture-study synthesis
#
# `docs/architecture-study/07_CRAFTY_ARCHITECTURE_SYNTHESIS_V1.md` §3 lists
# the identities that must not collapse into one object, and §15/§16 list what
# a realization must not presuppose. These tests pin the ones MODEL0-R is in a
# position to violate. Layers that do not exist yet (equation IR,
# discretization, execution policy) are pinned negatively: nothing here may
# already stand in for them.
# =====================================================================

def test_realization_does_not_stand_in_for_a_future_layer():
    """§3: model / realization / equation IR / discretization / solver
    capability / concrete solver / execution policy are seven identities."""
    fields = set(ModelRealizationDefinition.__dataclass_fields__)

    # Equation / residual IR and discretization: not represented, not implied.
    for absent in (
        "equation", "equations", "residual", "jacobian", "weak_form",
        "discretization", "basis", "element_order", "quadrature", "scheme",
    ):
        assert absent not in fields

    # Execution policy is a runtime property, never model identity.
    for absent in (
        "tolerance", "tolerances", "time_step", "stepping", "max_iterations",
        "backend", "device", "parallelism", "resources", "execution_policy",
    ):
        assert absent not in fields

    # A concrete solver is not named, only capabilities are required.
    for absent in ("solver", "solver_id", "solvers", "preferred_solver"):
        assert absent not in fields


def test_realization_names_capabilities_never_a_concrete_solver():
    """§16.A: a realization requests solver *capabilities*, not a brand.

    ``ImplementationReference`` records which code computes the realization,
    for provenance only — it is not a solver selection, and the core must
    never branch on it.
    """
    realization = _realization(
        implementation=ImplementationReference("some.package", "3.1.4")
    )
    assert realization.implementation is not None
    assert all(
        isinstance(c, SolverCapabilityId)
        for c in realization.required_solver_capabilities
    )
    source = (
        SCIENTIFIC_ROOT / "realizations" / "definition.py"
    ).read_text(encoding="utf-8")
    assert "implementation_id ==" not in source
    assert "implementation.implementation_id ==" not in source


def test_realization_assumes_no_discretization_family():
    """§16.B/C: no discretization family, mesh or assembled-matrix assumption.

    The formulation axis stays at the level of mathematical form. Nothing in
    it, or anywhere in the record, commits to a discretization family or to
    matrices being assembled at all — matrix-free operators must remain
    expressible.
    """
    assert {member.value for member in ModelFormulation} == {
        "algebraic", "ode", "dae", "pde", "discrete",
    }
    payload = _realization(formulation=ModelFormulation.PDE).to_dict()
    for absent in (
        "matrix", "matrices", "assembled", "sparsity", "stencil",
        "cells", "nodes", "elements", "dof", "topology",
    ):
        assert absent not in payload


def test_realization_assumes_nothing_about_output_shape_or_causality():
    """Outputs are not declared here at all, so nothing constrains them to
    scalars; and no direction/port/input-output structure is presupposed, so
    acausal physical composition stays reachable (§9)."""
    fields = set(ModelRealizationDefinition.__dataclass_fields__)
    for absent in (
        "outputs", "output", "returns", "result_shape", "scalar",
        "inputs", "ports", "connectors", "direction", "causal",
    ):
        assert absent not in fields


def test_realization_declares_no_execution_or_runtime_dependency():
    """A realization is a record. It cannot run, be run, or reach a runtime."""
    for attribute in ("run", "solve", "evaluate", "execute", "compile"):
        assert not hasattr(ModelRealizationDefinition, attribute)
    assert not callable(_realization())

    source = (
        SCIENTIFIC_ROOT / "realizations" / "definition.py"
    ).read_text(encoding="utf-8")
    imports = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not [line for line in imports if "numpy" in line or "scipy" in line]


def test_capability_declaration_is_not_proof_of_availability():
    """§16.D: declaring a capability proves nothing about executability.

    A realization may provide a capability while requiring solver
    capabilities nothing available can satisfy. The registry reports both
    facts and reconciles neither — reconciling them is a planner's job, and
    the planner does not exist.
    """
    realization = _realization(
        provided_capabilities={CONDUCTION},
        required_solver_capabilities={"core:pde"},
    )
    registry = RealizationRegistry([realization])
    assert CONDUCTION in registry.provided_capabilities()
    assert realization.solver_capability_gap([]) == frozenset(
        {SolverCapabilityId("core:pde")}
    )
    assert not hasattr(registry, "resolve")
    assert not hasattr(registry, "select")
    assert not hasattr(registry, "plan")


def test_two_realizations_of_one_model_stay_attributable():
    """§16.E: same science, different implementations, distinguishable."""
    model = _model_reference()
    native = _realization(
        realization_id="example.model.native",
        model=model,
        formulation=ModelFormulation.PDE,
        implementation=ImplementationReference("native.stack", "1.0.0"),
    )
    external = _realization(
        realization_id="example.model.external",
        model=model,
        formulation=ModelFormulation.PDE,
        assumptions=("resolves the boundary layer directly",),
        implementation=ImplementationReference("optional.provider", "9.9.9"),
    )
    registry = RealizationRegistry([native, external])
    found = registry.for_model(*model.key)
    assert {r.realization_id for r in found} == {
        "example.model.native", "example.model.external",
    }
    assert native.model_key == external.model_key
    assert native.key != external.key
    assert native.implementation != external.implementation
