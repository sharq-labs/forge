# Active Plan

Purpose: keep long-running implementation sessions bounded and resumable.

## Current objective

Finish PR #65 as a semantics-preserving repository/agent-workflow cleanup.

## Task tree

- [x] Remove scientific reasoning dependency on MCP transport.
- [x] Introduce canonical `engcore.credibility` layer.
- [x] Group low-coupling claim modules with compatibility shims.
- [x] Add repository architecture guards.
- [x] Add canonical architecture documentation entry point.
- [x] Add root `CLAUDE.md` working contract.
- [x] Add independent read-only scientific reviewer skill.
- [x] Add persistent progress/dead-end memory.
- [x] Add fixed scientific regression manifest.
- [x] Add changed-file fast gate.
- [ ] Run `python tools/forge_check.py --changed`.
- [ ] Run FAST tier.
- [ ] Run SCIENTIFIC tier.
- [ ] Resolve any regression without weakening scientific invariants.
- [ ] Merge PR #65 only after the requested manual verification is green.

## Stop conditions

Stop implementation and surface a blocker if any proposed fix would require:

- weakening UNKNOWN/fail-closed semantics;
- changing a frozen serialized contract without an explicit version decision;
- regenerating certification merely to silence drift;
- allowing claims to depend on MCP;
- inventing scientific inputs, uncertainty or evidence.

## After PR #65

Next structural slice: split `mcp/problem.py` by case/system responsibility,
then reassess whether more claim modules should move. Do not combine that
migration into PR #65.
