# Reviews

External and adversarial reviews of this repository, one file per review, dated.

**These are documents, not the project's record.** `NEEDS.md` is the record: it is
written by whoever did the work, in the order the work happened, and it assumes you
have been following. A review is written by someone attacking the claims from
outside, and it has to stand on its own — a reader evaluating this runtime should be
able to read one of these end to end without opening `NEEDS.md` first.

## What a review here must contain

Three sections, and the middle one is the one that is usually missing.

1. **Findings**, by severity, each with the exact snippet that produced it and the
   exact output it produced. A finding without a reproduction is a hypothesis and
   belongs in the section labelled that way.

2. **What was attacked and held.** Every attack that failed, naming the mechanism
   that stopped it. This is the half that tells a reader which claims are real:
   a list of defects says what is broken, and only this says what was tried and
   did not break. A review with no such section has not established that it looked.

3. **Claims that did not survive**, including the reviewer's own. A report that
   lists findings is indistinguishable from one that found them until somebody runs
   the reproduction — so a claim that was made, checked and refuted is evidence
   about the review process and is kept, not deleted.

Each finding carries a status (`open` / `fixed`) and a smallest-fix sentence. When
a finding is later closed, the entry stays and its status changes; a review is a
record of what was true on its date, not a live issue tracker.

## Relationship to `NEEDS.md`

A review may *originate* a rule, but the rule lives in `NEEDS.md` once the project
adopts it — that is where the standing rules are, and splitting them would let the
two drift. A review states the rule and points at it; `NEEDS.md` owns it.

## Index

| Date | Target | Findings | Verdict |
|---|---|---|---|
| [2026-09-07](2026-09-07-adversarial-review.md) | `d23f7ae`, whole verification path (`sria/` excluded) | 10 reproduced, 4 hypotheses, 9 attacks held, 3 relayed claims refuted | Published metrics reproduce exactly; two claims (coupling tolerance, hold-out seal default) bend a central guarantee and are open |
