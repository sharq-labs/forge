"""F1-G: every MCP tool that takes a STRUCTURED claim says its criteria were authored by the caller.

The MCP client is a language model. It can take an advisory, ungrounded proposal
from prepare_simulation and submit it as a structured claim. The verdict is then
about the criteria as written -- and the response must say nobody grounded them.
"""

from __future__ import annotations

import pytest

from claims_support import t3_claim

pytest.importorskip("mcp")

from engcore.mcp import server  # noqa: E402


@pytest.mark.parametrize("tool", ["assess_scientific_claim", "run_simulation"])
def test_a_structured_claim_tool_marks_its_criteria_caller_authored(tool) -> None:
    result = getattr(server, tool)(t3_claim().to_dict())
    assert result["criteria_authority"]["authority"] == "caller_authored"
    assert result["criteria_authority"]["grounded"] is False


def test_the_marker_never_claims_grounding() -> None:
    assert server.CALLER_AUTHORED_CRITERIA["grounded"] is False
    assert "caller" in server.CALLER_AUTHORED_CRITERIA["meaning"]
