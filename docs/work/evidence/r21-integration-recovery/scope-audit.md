# R21 integration scope audit (2026-10-24)

Inspected source: `41663479890a656a9a0e62bd8334e5e59510218a`.
Comparison: main `5ac5267781b9310fa205e9f2c1d12b34aa86e235`.
This report concerns repository retention and integration risk, not scientific validation.

The proposed integration contains 1,812 changed files totaling 121,624,072 current
uncompressed bytes. The prior branch-side count was 4,500,952 added lines.
The merge of main preserved both PROGRESS histories and changed no source or tests.
No existing evidence was deleted, relocated or rewritten.

## Retention disposition

Source, tests and benchmark drivers belong in the implementation history. Plans,
seals, manifests, frozen benchmark inputs and evaluator reference records preserve
experiment identity and replay context. Generated outputs and historical review,
mutation and test logs are retained as the record of this development campaign;
they are not automatically current evidence for the integration SHA.

Battery rediscovery packs include reductions of measured datasets. The previous
integration audit's blanket description as synthetic was incorrect. Their recorded
ancestry must remain distinct from synthetic authority-contract fixtures, and neither
classification grants measurement admission, known uncertainty or model validation.

There are 173 groups of byte-identical changed files. Some are copied benchmark
inputs and results across separately sealed campaigns; others are repeated control
logs. Byte identity alone does not establish that a path is safely disposable.
The largest file is round15/changed.log (7,593,340 bytes, 146,685 lines).
Future compaction or external archival requires an owner-approved retention design
that preserves content hashes, experiment paths and retrievable evidence. No such
migration is required or performed in R21; the current ~122 MB footprint is disclosed.

## Credential inspection

Executed a byte scan over all 1,812 changed current files and separately over all
692 unpublished historical blobs (32,864,740 bytes). Seven pattern families covered
private keys, GitHub tokens, AWS access IDs, Google API keys, Slack tokens,
credential-bearing HTTP URLs and long quoted secret assignments. Also inspected
credential-like filenames and NUL-bearing files. All candidate counts were zero.
No secret values were printed. This is a bounded heuristic scan, not a guarantee:
unknown formats, encrypted data, low-entropy passwords and credentials outside the
inspected integration/history ranges remain outside its coverage.

Raw inventories and duplicate groups are preserved outside the checkout at
`/home/dev_kaeem/br11-r21/scope-audit.json` and `history-secret-audit.json`.

## Publication boundary

No push or merge is authorized by this audit. The documented assurance runner must
produce a genuine source receipt and certificate-only child, and verification must
say `SAFE_TO_PUSH: YES`. Branch protection and independent human approval remain
mandatory. The protection API returned HTTP 403 requiring a supported private-repo
plan; the collaborator list contained only PR author `sharq-labs`. No plan, visibility,
review, protection or repository governance setting was changed.
