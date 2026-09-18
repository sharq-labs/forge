# Forge Work Progress

This file is persistent engineering memory for long-running AI-assisted work.
Keep it concise and factual. Do not use it as a release note or marketing log.

## Current branch / PR

- Branch: `refactor/repository-architecture-cleanup`
- PR: #65 — repository architecture and layer boundaries
- Base: `main`

## Completed in this line of work

- Extracted credibility/V&V implementation from MCP transport into
  `engcore.credibility`.
- Removed the `claims -> mcp` implementation dependency.
- Added compatibility shims for old MCP credibility imports.
- Grouped claim analysis, governance, replay and NL adapter implementations
  under subpackages while preserving old import identity.
- Added a current architecture entry point and historical-audit index.
- Added persistent Claude/agent working contract, scientific reviewer,
  regression manifest and fast changed-file gate.

## Verification log

No test command is recorded here yet for the latest agent-workflow additions.

Status: **NOT RUN**

When a command is executed, append entries in this exact shape:

```text
YYYY-MM-DD HH:MM TZ
command: <exact command>
result: PASS | FAIL | BLOCKED
summary: <counts or first relevant failures>
commit: <sha>
```

Never convert NOT RUN into PASS based on code inspection.

## Failed approaches / dead ends

- None recorded for the current agent-workflow slice.

Record failed experiments here with the reason they failed before trying a new
approach. Do not delete old failed approaches merely because a later approach
works.

## Open structural follow-ups

- Manually run `python tools/forge_check.py --changed` on PR #65.
- Run FAST and SCIENTIFIC tiers before merge.
- Split the still-large `mcp/problem.py` in a separate structural slice.
- Continue reducing the remaining flat claim modules only after PR #65 is
  verified.
- Do not expand the frozen Scientific Core for repository-layout aesthetics.
