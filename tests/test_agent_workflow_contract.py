from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_root_claude_contract_names_the_scientific_guardrails_and_manual_ci():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for required in (
        "UNKNOWN never improves an answer",
        "Verification does not become validation",
        "claims",
        "mcp",
        "python tools/forge_check.py --changed",
        "PROGRESS.md",
        "manual-only",
    ):
        assert required in text


def test_scientific_reviewer_and_persistent_work_memory_exist():
    required = (
        ".claude/agents/forge-scientific-reviewer.md",
        ".claude/skills/forge-scientific-review/SKILL.md",
        "docs/work/PROGRESS.md",
        "docs/work/ACTIVE_PLAN.md",
    )
    for relative in required:
        assert (ROOT / relative).is_file(), relative

    progress = (ROOT / "docs/work/PROGRESS.md").read_text(encoding="utf-8")
    assert "Status: **NOT RUN**" in progress
    assert "Failed approaches / dead ends" in progress
