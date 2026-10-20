# Reviewed publication and merge inventory — 2026-10-20

Owner authorized publication and reviewed merges, excluding preserve/* and wip/*. This does not waive scientific decisions, tests or certification. Main at inventory: eb113ab7e74580d47e6aa1210d02e45a49124724.29distinct unmerged tips after alias deduplication;4contained in others,25maximal candidates. This is a safety disposition, not a claim of complete source validation.

| Branch | Disposition |
|---|---|
| `ci/local-only-assurance` | HOLD:17 conflicts with newer CI/assurance controls; no rollback of automatic gates. |
| `ci/self-hosted-heavy-runner` | CONTAINED in origin/ci/self-hosted-heavy-runner |
| `claude/battery-thermal-flagship-sprint-3` | CONTAINED in claude/battery-voltage-s3-recovery, claude/provider-architecture-pybamm-pybop |
| `claude/battery-voltage-s3-recovery` | CONTAINED in claude/provider-architecture-pybamm-pybop |
| `claude/domain-real-data` | HOLD: trial merged cleanly but test_repository_scan_is_current fails (1 failed/12 passed); aborted trial without rewriting historical snapshot. |
| `claude/provider-architecture-pybamm-pybop` | HOLD:8 conflicts including frozen policy, multiphysics runtime and providers; semantic reconciliation and current gates required. |
| `codex/m1d-adaptive-transient` | HOLD: independent review P1; port new continuation into main without restoring datum-dependent energy allowance; current gates/OD3 outstanding. |
| `codex/multidomain-science-hardening` | HOLD: residual WIP adds local AGENTS/config/skills; ignored agent entrypoint must not be silently tracked. |
| `evidence-v11` | HOLD: competing historical bisect edits conflict in needs document; no new measured history manufactured. |
| `feat/battery-real-data-identifiability` | HOLD: historical claim/evidence code plus tests require current merged-tree review and certification; progress conflict. |
| `feat/br-mind-01-minimal-mind` | PUBLISHED; HOLD SOURCE MERGE: original source tested only developmentally; test-suite certification trigger. Identical candidate code preserved in PR175. |
| `feat/genesis-lite-v03-amendment-draft` | CONTAINED in feat/genesis-lite-v03-escrow-fda05 |
| `feat/genesis-lite-v03-escrow-fda05` | HOLD: PR174 remains draft; CP2 94failed/28passed, certified escrow addition requires OD3. No formal/freeze approval inferred. |
| `fix-bisect-table` | HOLD: conflict with newer historical evidence account; do not delete measured history blindly. |
| `fix/active-plan-epic-line` | PREPARED FOR NORMAL PR: documentation paragraph move;28targeted passed; exact gate comparison removes1main failure and adds0. |
| `fix/final-assurance-blockers` | SUPERSEDED/HOLD: prior scanner replaced by repository ownership design;3current conflicts, stale empirical re-pin. |
| `governance/od-cap-0-quantitative-scope` | PUBLISHED; CONDITIONAL: scope-only amendment keeps capabilities MISSING; tests trigger current assurance; pending design decisions remain pending. |
| `origin/chatgpt/core-v2-trust-repair-1-4` | HOLD:8conflicts in current certified trust sources; no current merged-tree certification. |
| `origin/ci/self-hosted-heavy-runner` | HOLD:closed unmerged PR107,6conflicts incl workflow/certificate; no implicit runner/deployment change. |
| `origin/codex/critical-production-closure` | PATCHES_ALREADY_PRESENT: git cherry reports4equivalent/0unique; no need to overwrite newer MCP code. |
| `origin/core/p0-trust-boundaries-v2` | HOLD:5conflicts with current scientific/SRIA boundaries; no current certification. |
| `origin/docs/assurance-performance-investigation` | SUPERSEDED HISTORY: closed PR147; current main already contains reconciled investigation with integration note;2conflicts. |
| `origin/docs/blind-rediscovery-benchmark-v1` | SUPERSEDED CONTRACT: closed PR127/151; independent review P1 old tip drops strengthened baseline/budget/evaluator requirements. |
| `origin/docs/main-check-2026-10-13` | HOLD HISTORICAL RECONCILIATION:progress-only conflict; current test evidence cannot be replaced by old main snapshot. |
| `origin/feat/big-13-flagship-demonstrations` | HOLD SELECTIVE DOCS: independent review P2; old phases/queues must not replace live strategy;5conflicts. |
| `origin/feat/multiphysics-lifecycle-foundation` | PATCH_ALREADY_PRESENT: git cherry1equivalent/0unique. |
| `origin/fix/p0-1-scientific-correctness-hardening` | STALE CERTIFICATE ONLY: not a certificate for current main; do not replace current certificate. |
| `origin/fix/p0-trust-boundaries` | STALE CERTIFICATE ONLY: not a certificate for current main; do not replace current certificate. |
| `origin/fix/p0-v4-assurance-descendants` | STALE CERTIFICATE ONLY: not a certificate for current main; do not replace current certificate. |

## Published work

All251files of this chat were preserved byte-identically in1b90f94c, PR175 (draft, stacked on174). Also pushed previously local Mind, M1D, OD-CAP-0 and active-plan-fix refs. No force-push, branch deletion or shared-checkout switch. Other dirty worktrees are listed and untouched; generated scratch and excluded preservation branches were not bulk-added.

## Verification

Exact commands/results are in receipts and PROGRESS. Documentation-only active-epic repair:28passed; selected219nodes show2failed/217passed vs pristine main3failed/216passed; new failures0, removed governance epic-location failure1. This is not a green full gate. Domain-data trial:1failed/12passed; aborted. Independent scientific review:CHANGES REQUIRED for batch scientific integration; blockers above. Full assurance/recertification/formal campaigns NOT RUN.

The original broad staged whitespace scan reported whitespace in pinned historic logs/patches. These bytes were preserved; authored source/docs whitespace check passed. GitHub CLI account returned404; authorized GitHub connector and SSH publication worked.

See final main PR for actual merge status; publication of drafts must never be described as all source merged.

## Final remote disposition

PR176 remains OPEN and UNMERGED at 1e109c667018be219f6da1df8bc7049caa11ebb9. Remote main remains eb113ab7e74580d47e6aa1210d02e45a49124724. No remote merge attempted: BRANCH_PROTECTION.md requires at least one approving review; the live reviews endpoint returned an empty list. The rulesets endpoint returned HTTP403 (plan feature unavailable); this does not waive the repository contract.

Tests run39471205748 and Recertify Hardened Core run39471205812 failed in initial classifier/layout jobs; downstream tests were skipped. Job logs returned404 BlobNotFound; the connector rejected annotation endpoints. Root cause UNKNOWN; no billing claim. CI is not the local scientific attestation. See github-status.json for the exact observed state.

Next integration action: obtain an approving review on documentation-only PR176. Scientific PR174/175 remain drafts pending CP2 isolation closure and applicable OD3/current assurance. Conflicting older branches require selective reconciliation; no bulk merge or historical certificate replacement is justified. This report is evidence, not a new executable queue.
