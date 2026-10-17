"""Composition-pack coupling templates may declare BR1 window control (ERT V1, Big Rock 10).

The template carries an optional WindowControlPolicy into every CouplingPlan it
materializes; it is serialized only when declared, so existing templates (and
the built-in packs) keep their identity; what the plan would refuse is refused
at declaration.  NOT YET EXECUTED (build phase): see
docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engcore.compositionpacks import builtin_electrothermal_feedback as pack
from engcore.compositionpacks.blueprint import CouplingPolicyTemplate
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import CouplingScheme, IterationSemantics, WindowControlPolicy
from engcore.scientific.units.quantity import Quantity


def _control(minimum=0.25, divergence=None):
    return WindowControlPolicy(Quantity(minimum, "s"), 0.5, 3, divergence)


def _template(**kw):
    base = dict(template_id="t", version="1", blueprint_id=pack.BLUEPRINT_ID, scheme=CouplingScheme.EXPLICIT,
                iteration_semantics=IterationSemantics.SERIAL, coupling_window=Quantity(1.0, "s"))
    return CouplingPolicyTemplate(**{**base, **kw})


def test_built_in_templates_keep_their_identity():
    assert pack.COUPLING_POLICY.window_control is None
    assert "window_control" not in pack.COUPLING_POLICY.to_dict()


def test_a_declared_window_control_round_trips():
    template = _template(window_control=_control())
    assert CouplingPolicyTemplate.from_dict(template.to_dict()) == template
    assert template.to_dict()["window_control"]["max_subdivisions"] == 3


def test_materialized_plans_carry_the_declared_window_control():
    plan = _template(window_control=_control()).materialize(start=Quantity(0, "s"), end=Quantity(10, "s"))
    assert plan.window_control == _control()
    assert _template().materialize(start=Quantity(0, "s"), end=Quantity(10, "s")).window_control is None


@pytest.mark.parametrize("kw, match", [
    (dict(window_control=_control(divergence=10.0)), "implicit"),
    (dict(window_control=_control(minimum=2.0)), "exceeds"),
    (dict(window_control="halve on failure"), "WindowControlPolicy"),
])
def test_what_the_plan_would_refuse_is_refused_at_declaration(kw, match):
    with pytest.raises(InvalidScientificProblem, match=match):
        _template(**kw)


def test_window_control_against_a_blueprint_without_deterministic_restore_is_refused():
    with pytest.raises(InvalidScientificProblem, match="deterministic checkpoint/restore"):
        _template(window_control=_control()).validate_against_blueprint(pack.BLUEPRINT)
    _template().validate_against_blueprint(pack.BLUEPRINT)  # without window control the blueprint is admitted


def test_window_control_against_a_restorable_blueprint_is_admitted():
    restorable = replace(pack.BLUEPRINT, participants=tuple(
        replace(p, checkpointable=True, deterministic_restore=True) for p in pack.BLUEPRINT.participants))
    _template(window_control=_control()).validate_against_blueprint(restorable)
