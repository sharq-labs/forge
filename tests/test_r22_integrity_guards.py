"""Adversarial controls for R22 guard precision; no producer/schema exemptions."""
import ast
import pytest
from tests.guard_ast_support import canonical_import_names, unconditional_refusal
from tests.test_core_guards import _threshold_offenders
from engcore.scientific.semantics import semantic_extension
from engcore.scientific.errors import ScientificCoreError


@pytest.mark.parametrize("annotation", ["", ": float", ": 'float'", ": float | None", ": Optional[float]", ": Unknown"])
def test_named_thresholds_with_bare_or_unknown_types_remain_offenders(annotation):
    tree = ast.parse(f"def gate(*, residual_atol{annotation}): pass")
    assert list(_threshold_offenders(tree, "engcore.fixture")) == [("gate", ["residual_atol"])]


def test_only_exact_nonawarding_quantity_annotation_is_distinguished():
    tree = ast.parse("from engcore.scientific.units.quantity import Quantity\ndef numerical(*, residual_atol: Quantity): pass")
    assert list(_threshold_offenders(tree, "engcore.fixture")) == []


@pytest.mark.parametrize("extra", [
    "from engcore.scientific.results.validation import ValidationLevel as L",
    "import engcore.scientific.results.validation as v",
    "from engcore.scientific.results.validation import ValidationCheck as C",
    "def issue(): return some_gate.award()",
    "def issue(): return {'establishes': 'analytically_verified'}",
    "Quantity = float",
    "def shadow(Quantity): pass",
    "from other import Quantity",
])
def test_quantity_annotation_cannot_hide_award_authority_or_shadowing(extra):
    tree = ast.parse("from engcore.scientific.units.quantity import Quantity\n" + extra +
                     "\ndef gate(*, residual_atol: Quantity): pass")
    assert ("gate", ["residual_atol"]) in list(_threshold_offenders(tree, "engcore.fixture"))


@pytest.mark.parametrize("body,expected", [
    ("raise RuntimeError('audit only')", True),
    ('"audit record"\nraise RuntimeError()', True),
    ("if payload: raise RuntimeError()\nreturn payload", False),
    ("return payload", False),
])
def test_only_unconditional_refusal_reader_is_nonadmitting(body, expected):
    function = ast.parse("def from_dict(payload):\n" + "\n".join("    " + line for line in body.splitlines())).body[0]
    assert unconditional_refusal(function) is expected


def test_semantic_schema_helper_is_resolved_by_origin_not_spelling():
    trusted = ast.parse("from .semantics import semantic_extension as read_extension")
    assert canonical_import_names(trusted, "engcore.scientific.conservation", "engcore.scientific.semantics",
                                  "semantic_extension") == {"read_extension"}
    for source in ["from other import semantic_extension",
                   "from engcore.scientific.semantics import semantic_extension\nsemantic_extension = lambda *x: None",
                   "from engcore.scientific.semantics import semantic_extension\ndef from_dict(p):\n    from other import semantic_extension\n    return semantic_extension(p)"]:
        assert canonical_import_names(ast.parse(source), "engcore.fixture", "engcore.scientific.semantics",
                                      "semantic_extension") == set()


@pytest.mark.parametrize("payload", [{}, {"schema": "other/1"}, {"schema": "fixture/3"},
    {"schema": "fixture/2"}, {"schema": "fixture/2", "semantics": None},
    {"schema": "fixture/1", "semantics": {}}])
def test_existing_semantic_helper_refuses_missing_wrong_future_and_downgraded_schema(payload):
    with pytest.raises(ScientificCoreError):
        semantic_extension(payload, "fixture/1", "semantics")


def test_semantic_helper_preserves_explicit_legacy_and_typed_payloads():
    assert semantic_extension({"schema": "fixture/1"}, "fixture/1", "semantics") is None
    payload = {"schema": "fixture/2", "semantics": {"declared": True}}
    assert semantic_extension(payload, "fixture/1", "semantics") == {"declared": True}


@pytest.mark.parametrize("shadow", [
    "from other import *",
    "try: pass\nexcept Exception as semantic_extension: pass",
    "match data:\n    case semantic_extension: pass",
    "match data:\n    case [*semantic_extension]: pass",
    "match data:\n    case {**semantic_extension}: pass",
])
def test_non_name_bindings_cannot_shadow_a_trusted_helper(shadow):
    tree = ast.parse("from engcore.scientific.semantics import semantic_extension\n" + shadow)
    assert canonical_import_names(tree, "engcore.fixture", "engcore.scientific.semantics", "semantic_extension") == set()


def test_attribute_spelling_does_not_count_as_a_canonical_helper_call():
    from tests.guard_ast_support import calls_canonical_helper
    assert not calls_canonical_helper(ast.parse("fake.semantic_extension(payload)"), {"semantic_extension"})
    assert calls_canonical_helper(ast.parse("semantic_extension(payload)"), {"semantic_extension"})


def test_every_serialized_validation_level_prevents_the_numerical_exception():
    from engcore.scientific.results.validation import ValidationLevel
    for level in ValidationLevel:
        tree = ast.parse("from engcore.scientific.units.quantity import Quantity\n"
                         "def gate(*, residual_atol: Quantity):\n"
                         f"    return {{'attained_levels': [{level.value!r}]}}")
        assert list(_threshold_offenders(tree, "engcore.fixture")) == [("gate", ["residual_atol"])]


def test_schema_checker_guard_ignores_unrelated_attribute_calls():
    from tests.test_core_semantic_invariants import _calls_canonical_schema_checker
    member = ast.parse("def from_dict(payload):\n    fake.require_schema(payload)\n    return payload\n").body[0]
    assert not _calls_canonical_schema_checker(member, {"require_schema"})


def test_schema_checker_guard_accepts_canonical_aliased_import():
    from tests.test_core_semantic_invariants import _calls_canonical_schema_checker, _canonical_schema_checker_names
    tree = ast.parse("from engcore.scientific.serialization import require_schema as check\ndef from_dict(payload):\n    check(payload, EXPECTED)\n    return payload\n")
    names = _canonical_schema_checker_names(tree, "engcore.fixture")
    assert names == {"check"}
    assert _calls_canonical_schema_checker(tree.body[1], names)
