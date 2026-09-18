# Core Freeze V4 — the scientific core re-audit's contract, with a compatibility proof

**Tag:** `v4.0-core-freeze` (created after merge) · **Candidate:** written into `certification/core_freeze_v4.json`
**Manifest:** `certification/core_freeze_v4.json` · **Assurance:** `certification/core_freeze_v4_assurance.json`
**Verifier:** `python -m tools.certification.core_freeze_v4 --verify` · **Audit:** `docs/audits/CORE_REAUDIT_2026-09-16.md`

## Why a fourth freeze

The 2026-09-16 scientific core re-audit measured **75 problems** in the scientific core and closed them in
**31 improvements** over fifty-six batches. The fixes needed new shapes — new enum members, new trailing
dataclass fields with defaults, new keyword arguments with defaults — and the owner's rule for the round was
**additive only**: nothing removed, renamed, reordered or re-defaulted.

That rule moved the frozen digest, from `c80e6418592e94a0…` to `f18aa806d594016c…`, and the round deliberately
did **not** regenerate a snapshot to hide it: nineteen FAST-tier tests failed by design for fifty-five
batches, because a snapshot regenerated in batch 7 would have been the reference for batch 8 and nothing would
have been left to compare against. The re-audit's own finding 89 names the state that produced: *the branch
descends from no Core Freeze, and recertification is blocked.*

V4 is where the round's result becomes certifiable. **V1's 194 frozen symbols are still 194, in the same seven
modules**, and every difference from the V1 surface **as V1 committed it** is proved additive, one difference
at a time.

## What is new in the control plane

| thing | what it fixes |
|---|---|
| `additive_only_problems(stored, live)` | R-69 (findings 94, 95). The audited check was `v1_entries_byte_identical_in_v2`, which compared the LIVE surface with the LIVE surface and is true by construction. This compares against `tests/api/frozen_api_snapshot.json` **as committed at the V1 baseline**, read out of git and checked against the digest V1's own manifest pinned, and it names every non-additive difference: a removed or renamed symbol, a removed parameter, a changed default, a changed parameter kind, a new required argument, a removed/revalued/reordered enum member, a removed or reordered dataclass field, a new field without a default or not last, a changed exception chain, a changed union, a shrunk frozen container |
| `enum_insertions(stored, live)` | the other half of finding 95 — *13 RouteReason members changed position without detection*. An insertion keeps every existing member's name, value and relative order, so it is additive; it is no longer silent. `RouteReason` went from **24 members to 43**, seven of them inserted before members that already existed, and each is named with the position it took. The owner's decision on insertions is recorded as an open decision in the audit document |
| `tools/certification/api_surface_v4.py` | R-69 (finding 94). `engcore.api_snapshot` describes module-level symbols and not one method, so deleting `ValidityDomain.assess`'s `record_values` argument or `ValidationReport.evidence_basis` moved no digest. The deep surface records **1943 method signatures** and every enum member's **position**, pinned in `certification/core_v4_api_surface.json`. `engcore.api_snapshot` is untouched, so V1, V2 and V3 keep computing what they always computed |
| `is_the_core_refusal` | R-70 (finding 96). The V3 supersession check caught `Exception` and read any of them as the refusal, so it passed with the rule deleted and an `ImportError` raised in its place. V4 requires the exception to be the core's own class **and** the message to name the rule |
| `v4_mutation_problems` | R-66 (finding 91). A fabricated record with green flags and a copied population sha passed every V2/V3 assurance check. V4 recomputes the population's two digests from the tree, each shard's log digest from the transcript's own bytes, each shard's verdicts by parsing that transcript, and the shards' union and disjointness |
| `CERTIFICATE_SELF_CHECKS` | R-65 (finding 89). Every check that compares the tree against a pinned API artifact of the previous freeze is now classified as a certificate self-check: deselected in the source gates, and **required to be reported PASSED in JUnit by the certificate child**, so deferring is not skipping |

## What binds

| check | meaning |
|---|---|
| `v4.descends_from_v3` | the candidate descends from the Core Freeze V3 commit. A freeze that does not is a fork |
| `v1.history_unchanged`, `v2.history_unchanged`, `v3.history_unchanged` | each earlier manifest is recorded by digest and never rewritten: a manifest is a record of its own commit |
| `v1.contract_api_is_superseded_additively`, `api.additive_only` | zero non-additive differences from the stored V1 surface **and** from the stored V2 surface |
| `api.stored_v1_bytes_are_v1s_own` | the snapshot the comparison reads is the one V1 pinned, by digest |
| `api.enum_insertions_are_recorded` | the manifest's insertion list is what the tree says, recomputed |
| `api.pinned_files`, `api.deep_surface_is_the_live_one` | the four snapshots and the deep surface are the bytes this freeze recorded |
| `v4.v3_fixtures_refused_by_the_named_rule` | V3's identity references are `route_diagnostics/1` records with no thresholds and a nan chi-square minimum, and this tree refuses them with `engcore.hybrid_uq.vocabulary.HybridUQError`. Measured on every verify, and it must be THAT rule |
| `certificate.verifies`, `certificate.covers_required_areas`, `certificate.harness_area_covers_what_its_suites_import` | the certificate covers V3's seven areas plus `harness` and `certification_control`, and the harness area covers the closure of what its suites import (R-68) |
| `assurance.v4_mutations_re_derived`, `assurance.required_suites_green`, `assurance.measured_commit_is_this_history` | the 575-mutation V4 population in four shards, every figure recomputed from the tree and the transcripts |

## What V4 supersedes, and why

V3's contract cannot hold on this tree, in the same way V2's could not hold on V3's:

* **R-01/R-20** — a route's goodness of fit is re-derived from the numbers it carries, and a
  `route_diagnostics/1` record naming no thresholds and no chi-square minimum is refused. That is exactly what
  V3's own identity references are, so the V3 serialization inventory cannot be reproduced by a correct tree.
* **R-43** — a quantified uncertainty nobody attributed can no longer be aggregated into a channel total.
* **R-58/R-61** — a recorded transfer states where its value came from and is checked against the result it
  names, so a crossing carrying a bare point value no longer round-trips.
* **R-67/R-68** — the certificate's harness area is derived from what its suites import, so a V3 certificate's
  scope table is not a V4 scope table.

## What V4 does not claim

* No domain solver quantifies its uncertainty: every one still reports UNKNOWN with a stated reason (R-43's
  remaining half).
* The deep surface covers **shape**. Methods are recorded by name and signature; what they do is what the
  575-mutation population and the suites are for.
* A fresh execution. The assurance record states which commit it measured and every figure in it is
  re-derived from the tree and the transcripts; binding that to an execution is the recertify workflow's job.
* Mesh and parameter identity (R-62, R-74) are **not** re-frozen: I-23 is deferred and is recorded as an open
  decision in the audit document.
