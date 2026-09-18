"""The natural-language OUTER adapter: a language model proposes, the deterministic compiler decides."""

from __future__ import annotations

import copy

import pytest

from claims_support import et_claim, et_inputs
from engcore.claims.nl_adapter import FORBIDDEN_AUTHORITY_FIELDS, compile_natural_language
from engcore.mcp.capabilities import production_registry


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _text_and_spans(claim):
    """Source prose that states every input, with the span each value is quoted from."""
    parts, spans, cursor = [], {}, 0
    for path, value in sorted(claim.to_dict()["known_inputs"].items()):
        shown = value["magnitude"] if isinstance(value, dict) else value
        piece = f"{path} is {shown} {value.get('units', '') if isinstance(value, dict) else ''}. "
        spans[path] = (cursor, cursor + len(piece))
        parts.append(piece)
        cursor += len(piece)
    return "".join(parts), spans


def test_a_faithful_proposal_compiles_to_what_the_compiler_decides(registry) -> None:
    made = et_claim()
    text, spans = _text_and_spans(made)
    result = compile_natural_language(text, made.to_dict(), spans, registry)
    assert result.status == "ready" and result.findings == () and result.moved_to_missing == ()


def test_an_invented_value_is_moved_to_missing_never_defaulted(registry) -> None:
    made = et_claim()
    text, spans = _text_and_spans(made)
    proposal = copy.deepcopy(made.to_dict())
    proposal["known_inputs"]["stages[0].body.heat_capacity"]["magnitude"] = 77.0  # not what the text says
    result = compile_natural_language(text, proposal, spans, registry)
    assert result.moved_to_missing == ("stages[0].body.heat_capacity",)
    assert result.status == "needs_input"
    assert "stages[0].body.heat_capacity" in result.compiled.to_dict()["missing_inputs"]


def test_an_uncited_value_is_moved_to_missing(registry) -> None:
    made = et_claim()
    text, spans = _text_and_spans(made)
    del spans["source_voltage"]
    result = compile_natural_language(text, made.to_dict(), spans, registry)
    assert "source_voltage" in result.moved_to_missing and result.status == "needs_input"


@pytest.mark.parametrize("field", ["verdict", "attained_levels", "selected_model", "uncertainty_values", "evidence_records"])
def test_a_proposal_carrying_authority_is_refused(registry, field) -> None:
    assert field in FORBIDDEN_AUTHORITY_FIELDS
    made = et_claim()
    text, spans = _text_and_spans(made)
    proposal = made.to_dict()
    proposal[field] = "supported"
    result = compile_natural_language(text, proposal, spans, registry)
    assert result.status == "refused" and result.compiled is None


def test_a_proposal_cannot_declare_discrepancy_zero(registry) -> None:
    made = et_claim()
    text, spans = _text_and_spans(made)
    proposal = made.to_dict()
    proposal["discrepancy"]["kind"] = "zero_declared"
    assert compile_natural_language(text, proposal, spans, registry).status == "refused"


def test_the_core_imports_no_language_model() -> None:
    import ast
    import pathlib

    import engcore.claims as claims

    root = pathlib.Path(claims.__file__).parent
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_bytes().decode("utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                assert not any(p in name for p in ("anthropic", "openai", "langchain", "transformers")), (path, name)
