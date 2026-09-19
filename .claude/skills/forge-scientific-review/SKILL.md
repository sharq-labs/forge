---
name: forge-scientific-review
description: Independent scientific review of Forge code or a proposed change. Use after changes to claims, credibility, SRIA, uncertainty, validation, evidence, policy, replay, routing or scientific model selection. The reviewer is read-only and looks specifically for false scientific confidence.
argument-hint: [files, PR, feature or change to review]
context: fork
agent: forge-scientific-reviewer
background: false
---

# Forge Scientific Review

Review the requested change as a hostile scientific-assurance boundary.

Before reviewing, read:
1. `CLAUDE.md`
2. `docs/architecture/README.md`
3. the changed implementation
4. the closest tests
5. `docs/scientific-core/scientific-intelligence-layer.md` when claims are involved

Do not review style before scientific authority.

Required headings:

```text
A. Scope
B. Authority boundary
C. Applicability and model use
D. Verification / validation
E. Uncertainty
F. Evidence / context / policy
G. Provenance / replay
H. Adversarial test coverage
I. Findings
J. Verdict
```

Under I, every non-trivial finding must include severity, file/symbol, smallest
counterexample and minimal correction.

J contains exactly one of:

PASS
CHANGES REQUIRED
BLOCKER

A PASS is a review result only. Never represent it as executed tests or
scientific validation.
