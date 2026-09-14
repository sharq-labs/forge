# Reviews

External and adversarial reviews of this repository, one file per review.

**These are documents, not executable truth.** The project work record now lives at [`docs/project/needs.md`](../project/needs.md). Reviews attack claims from outside and should stand on their own; readers should not need the project log open beside them to understand a finding.

## What a review here must contain

Three sections, and the middle one is the one that is usually missing.

1. **Findings**, by severity, each with the exact snippet that produced it and the exact output it produced. A finding without a reproduction is a hypothesis and belongs in the section labelled that way.

2. **What was attacked and held.** Every attack that failed, naming the mechanism that stopped it. This is the half that tells a reader which claims are real: a list of defects says what is broken, and only this says what was tried and did not break. A review with no such section has not established that it looked.

3. **Claims that did not survive**, including the reviewer's own. A report that lists findings is indistinguishable from one that found them until somebody runs the reproduction — so a claim that was made, checked and refuted is evidence about the review process and is kept, not deleted.

Each finding should carry a status (`open` / `fixed`) and a smallest-fix sentence. When a finding is later closed, the entry stays and its status changes; a review is a record of what was true on its date, not a live issue tracker.

## Relationship to the project record

A review may originate a rule, but once adopted the standing project rule belongs in [`docs/project/needs.md`](../project/needs.md) or, when it is an executable scientific contract, in the code/tests that enforce it. Review prose must not become a second source of truth for capabilities.

## Index

| Date / record | Target | Purpose |
|---|---|---|
| [2026-09-07 adversarial review](2026-09-07-adversarial-review.md) | `d23f7ae`, whole verification path (`sria/` excluded) | Reproduced findings, attacks that held, and claims that were refuted |
| [Applicability conditions review](applicability-conditions-review.md) | model applicability / validity semantics | Historical review moved from repository root; interpret against current executable contracts |
