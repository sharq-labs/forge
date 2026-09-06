"""Repo-wide guards: properties every model, solver and record must hold.

These tests are written over what the repository *contains*, not over a list
somebody maintains. Every model is discovered by walking ``engcore``, so a
domain added tomorrow is covered on the day it lands, and a domain that opts
out of a guard fails here rather than in a report six months later.

That is the point of the round these tests came from. Each finding they encode
was first found in one domain and then found again in a second, because the
guard was a convention four domains happened to follow rather than a rule the
core enforced. A convention has a fifth domain; a rule does not.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

from src import engcore
from src.engcore.scientific.errors import (
    InvalidScientificProblem,
    ModelValidityError,
)
from src.engcore.scientific.ir.problem import ScientificProblem
from src.engcore.scientific.ir.variables import ScientificParameter
from src.engcore.scientific.models.definition import ScientificModelDefinition
from src.engcore.scientific.models.registry import ModelRegistry
from src.engcore.scientific.units.quantity import Quantity


# =====================================================================
# Discovery
# =====================================================================

def _every_model() -> tuple[ScientificModelDefinition, ...]:
    """Every model record reachable from ``engcore``, by import rather than list.

    A module-level constant in a package nobody imported here would be missed,
    so this walks the package rather than reading a registry: the registries are
    built by functions, one per domain, and a domain that forgot to write one
    would be exactly the domain worth testing.
    """
    found: dict[tuple[str, str], ScientificModelDefinition] = {}
    for module_info in pkgutil.walk_packages(engcore.__path__, "src.engcore."):
        try:
            module = importlib.import_module(module_info.name)
        except Exception:  # pragma: no cover - an unimportable module is a
            continue       # different test's failure, not this one's
        for attribute in dir(module):
            try:
                value = getattr(module, attribute)
            except Exception:  # pragma: no cover
                continue
            if isinstance(value, ScientificModelDefinition):
                found.setdefault(value.key, value)
    return tuple(found[key] for key in sorted(found))


MODELS = _every_model()
MODEL_IDS = [f"{m.model_id}@{m.version}" for m in MODELS]
RESERVING = [m for m in MODELS if m.derived_quantities]
RESERVING_IDS = [f"{m.model_id}@{m.version}" for m in RESERVING]


def test_the_discovery_actually_found_the_repository():
    """A guard over an empty set passes and proves nothing."""
    assert len(MODELS) >= 14
    domains = {m.domain for m in MODELS}
    assert {"electrical", "thermal", "battery"} <= domains
    # And most of them reserve something, so the guards below are not vacuous.
    assert len(RESERVING) >= 12


# =====================================================================
# GUARD 1 — a caller parameter cannot occupy a derived quantity's name
# =====================================================================

@pytest.mark.parametrize("model", MODELS, ids=MODEL_IDS)
def test_every_condition_name_is_either_declared_or_reserved(model):
    """The classification the core refuses to construct a model without.

    A validity condition reads a context key by name. That key is filled either
    by a caller declaration -- in which case the model must declare it as an
    input, so a reader can see the caller is meant to supply it -- or by the
    domain's assembler, in which case it must be reserved so no caller can. A
    name in neither category is filled by whatever happens to occupy it, which
    is the forgery.
    """
    declared = {spec.name for spec in model.inputs}
    unclassified = model.validity.context_keys - declared - model.derived_quantities
    assert not unclassified, (model.model_id, sorted(unclassified))


@pytest.mark.parametrize("model", RESERVING, ids=RESERVING_IDS)
def test_no_model_reserves_a_name_nothing_reads(model):
    """A reserved name that decides nothing is a claim of protection, not one."""
    assert model.derived_quantities <= model.validity.context_keys


@pytest.mark.parametrize("model", RESERVING, ids=RESERVING_IDS)
def test_a_caller_parameter_named_after_a_derived_quantity_is_refused(model):
    """The round's central test, over every model in the repository.

    For each name a model derives, a problem declaring a parameter of that name
    cannot produce a caller-declared context at all. Not "the value is ignored"
    and not "the verdict is the same": the assessment does not happen, because
    a caller asking for a verdict over a derived quantity they supplied is
    asking a question they are not entitled to ask.

    The property the round asked for -- *a caller parameter named after a
    derived quantity changes no verdict* -- follows and is stronger here: there
    is no verdict for it to change.
    """
    for name in sorted(model.derived_quantities):
        problem = ScientificProblem(
            problem_id=f"forge:{model.model_id}:{name}",
            parameters=(
                ScientificParameter(
                    name=name, value=Quantity(0.5, "dimensionless")
                ),
            ),
        )
        with pytest.raises(InvalidScientificProblem, match="derives"):
            problem.validity_context(reserved=model.derived_quantities)


@pytest.mark.parametrize("model", RESERVING, ids=RESERVING_IDS)
def test_a_reserved_name_is_refused_in_the_declared_half_of_an_assessment(model):
    """The second door: assembly, rather than problem construction.

    A context can be built by hand, deserialized from a payload or produced by
    a builder nobody has written yet. Whatever route it took, ``assess`` refuses
    to read a reserved name out of the caller's half.
    """
    for name in sorted(model.derived_quantities):
        with pytest.raises(ModelValidityError, match="reserved name"):
            model.assess_validity(declared={name: Quantity(0.5, "dimensionless")})
        # And the same mapping handed in as the single-argument form, which is
        # what a domain merging the two namespaces would produce.
        with pytest.raises(ModelValidityError, match="reserved name"):
            model.assess_validity({name: Quantity(0.5, "dimensionless")})


@pytest.mark.parametrize("model", MODELS, ids=MODEL_IDS)
def test_a_domain_cannot_assemble_a_name_it_did_not_reserve(model):
    """The third door: the assembler's own output.

    A derived quantity added to a domain's assembly without being reserved
    would be impersonable from the day it landed. It is refused at the
    assessment that would have read it.
    """
    with pytest.raises(ModelValidityError, match="does not reserve"):
        model.assess_validity(
            assembled={"a_name_no_model_reserves": Quantity(1.0, "dimensionless")}
        )


@pytest.mark.parametrize("model", RESERVING, ids=RESERVING_IDS)
def test_the_reserved_namespace_survives_serialization(model):
    """A guard that stopped at a process boundary would not be one.

    A model record crosses a boundary as JSON. If the reserved set did not
    travel with it, the receiving side would assess the same conditions with
    nothing protected -- and would not know that it was.
    """
    restored = ScientificModelDefinition.from_dict(model.to_dict())
    assert restored.derived_quantities == model.derived_quantities
    assert restored == model


def test_a_registry_can_enumerate_every_reserved_name_in_the_repository():
    """Why the set lives on the record rather than beside it.

    This is the test that could not be written while each domain kept its
    reserved names in a module-level constant: nothing could reach them without
    importing five specific modules and remembering the sixth.
    """
    registry = ModelRegistry(MODELS)
    reserved: set[str] = set()
    for model in registry:
        reserved |= model.derived_quantities
    assert {
        "biot_number",
        "damkohler_number",
        "dissipated_power_utilization",
        "peukert_capacity_ratio",
        "reduced_debye_temperature",
    } <= reserved
