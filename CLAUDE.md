# Forge — Claude Working Contract

Forge is a scientific simulation, reasoning and assurance runtime. The Python
distribution is still named `crafty` for compatibility; do not rename package
identity as part of ordinary work.

## Read before changing code

1. `docs/project/FORGE_MASTER_PLAN.md` — long-term technical direction and resume protocol.
2. `docs/architecture/README.md` — current repository/layer map.
3. `docs/scientific-core/README.md` — Scientific Core ownership and limits.
4. `docs/CORE_FREEZE_POLICY.md` — frozen API / certification rules.
5. `docs/scientific-core/scientific-intelligence-layer.md` — claim runtime.
6. `docs/work/ACTIVE_PLAN.md` and `docs/work/PROGRESS.md` — current bounded work state.

Historical audits are evidence about a past tree, not current architecture truth.

## Scientific authority rules

These are load-bearing invariants, not style preferences:

- UNKNOWN never improves an answer.
- Missing uncertainty never becomes zero.
- Missing model discrepancy never becomes zero.
- Missing boundary conditions are never silently defaulted.
- Model applicability precedes evidence-bearing execution.
- Verification does not become validation.
- Solver agreement does not prove physical truth.
- Caller assertions and planner output are not scientific evidence.
- Contradiction requires admissible evidence.
- Evidence must remain bound to the exact context / decision it was produced for.
- Removing evidence must not increase assurance.
- Risk policy sets the evidence bar; it never becomes evidence.
- Diagnostic hypotheses are not evidence; sensitivity is not causality; a proposed corrective action never guarantees support.
- A language model may propose structured inputs; it has no authority to select
  an applicable model, invent measurements, grant validation, quantify unknown
  uncertainty, or issue a scientific verdict.

If a change weakens one of these, stop and treat it as a scientific-design
decision, not a convenience refactor.

## Layer direction

```text
Scientific Core -> domains/systems -> credibility -> claims/SRIA -> MCP
```

MCP is transport. Scientific reasoning must never depend on MCP. In particular,
`engcore.claims` must not import `engcore.mcp`.

Old compatibility shims may remain while callers migrate, but new internal code
uses the canonical implementation path.

## Implementation discipline

- Prefer production code and adversarial tests over long progress prose.
- Reuse existing scientific records; do not create parallel Evidence,
  ValidationLevel, ScientificResult, uncertainty vocabularies, or provenance
  systems.
- Do not edit frozen/certified artifacts merely to silence a test.
- Preserve serialization identity and old import identity during structural
  refactors unless an explicit version/deprecation decision says otherwise.
- Keep domain-specific conditionals out of the generic Scientific Core.
- Keep a task small enough that its scientific claim can be tested directly.
- Record failed approaches in `docs/work/PROGRESS.md` so later sessions do not
  repeat them.

## Fast local gate

For a normal code change, start with:

```bash
python tools/forge_check.py --changed
```

For the fixed scientific regression pack:

```bash
python tools/forge_check.py --regression
```

Then, when the change is ready for integration, use the repository tiers:

```bash
python -m pytest -m "not expensive" -q -n 4
python -m pytest -m "not campaign" -q -n 4
```

Certification / hardened recertification is a separate manual operation.

## Truthfulness about verification

Never write "tests passed", "verified", "validated", "green", or equivalent
unless the command was actually executed in this session or a trusted workflow
result was read.

When tests are run, append the exact command, result, and relevant failure names
to `docs/work/PROGRESS.md`. If execution is unavailable, write **NOT RUN**.

A code review is not test execution. Static inspection is not a scientific
validation result.

## Reviewer separation

After changing claim/evidence/UQ/assurance behavior, invoke the
`forge-scientific-review` skill. The reviewer is read-only and should try to
find false support, authority leaks, hidden defaults, context mismatches and
verification/validation confusion. The builder does not silently overrule a
review finding; either fix it or record why it is not applicable.

## Long-running sessions

Treat `docs/project/FORGE_MASTER_PLAN.md` as the persistent strategic contract.
Use `docs/work/ACTIVE_PLAN.md` as the bounded executable task tree and update
`docs/work/PROGRESS.md` after meaningful milestones, failures or test runs.

If a chat/session is lost, recover from those files and the actual repository
HEAD/branch/PR. Do not require the previous chat transcript to continue.

Do not stop merely because one subtask or PR is complete if the active plan
contains the next executable task and no scientific/architectural blocker
exists.

## CI policy

GitHub test and hardened-core recertification workflows are part of the
repository's scientific control plane.

- Pull requests must be classified automatically.
- Ordinary changes run the normal Tests gate.
- Certified/trust-sensitive changes run hardened-core recertification.
- Pushes to `main` rerun the normal merged-tree checks.
- Branch/ruleset policy is checked after updates to `main`.
- Manual dispatch may remain as an explicit fallback, not as the only path.

Do not weaken or bypass these gates merely to make a change mergeable.
