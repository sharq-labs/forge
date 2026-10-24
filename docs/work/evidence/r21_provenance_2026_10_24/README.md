# R21 provenance repair review

Examined source: `41663479890a656a9a0e62bd8334e5e59510218a`.
Scope is inventory bookkeeping only. No scanner, tests, scientific source, historical artifact bytes, recorded failures, dataset admission, uncertainty or assurance gates changed.

The scanner correctly refused undeclared files. Immutable-tree reconstruction found 456 unknown entries at `1202ea6c`, 1,202 at `b4bbee0f` (+746, none removed), and 1,211 at closure/reconciled source (+9 curated closure artifacts). The 746 are exhaustively listed in [additional-746.md](additional-746.md): six generated results, 149 audit metadata files and 591 historical logs. There are zero raw scientific datasets, benchmark inputs or production source files among those 746. No entry is deleted as temporary or redundant; duplicate-byte retention is a separate scope audit.

The full repair handles the older debt as well: 1,210 new explicit rows and the stale DOCSET declaration, giving 1,643 records. All 432 other prior records are preserved exactly, including their original evidence. Original review_base remains historical; every new/replaced record pins supporting files to full immutable commit `41663479890a656a9a0e62bd8334e5e59510218a` and SHA-256. Support consists of identified generators, benchmark reports, session custody/report documents or the contemporary PROGRESS history. No new report is used as its own scientific authority.

Classification details:

- Thirty-nine battery v0/v1/v2/v3 problem packs are DERIVED reductions of measured trajectories plus declared protocol metadata. Builders and per-pack provenance retain recorded ancestry; all 39 current pack hashes match their existing pack manifests. Raw external data were not reacquired, reconstructed or authenticated by this review. UNKNOWN uncertainty remains UNKNOWN. These packs must not be called synthetic or raw measured bytes.
- `mind_gen2_world_v1/results/CASES.json` is SYNTHETIC: generated contract cases with expected outcomes. Other model/benchmark result files are DERIVED computations, not measurements.
- Evaluator TRUTH files are computed reference judgments, not physical truth. Plans, seals, identity maps, access audits and Gen1 seals are derived metadata; neither caller declarations nor policy become evidence.
- Archived session logs and reviewer records are attributed by the pinned session history/reports; exact same-stem probes and specific check generators are additionally cited where retained. This is historical custody classification, not new independent attestation that every invocation ran, every result is correct, or a reviewer assertion is admissible scientific evidence. Interrupted runs and failures remain recorded. No archival log supplies the forthcoming local-assurance receipt.
- DOCSET is a changed authored navigation list consumed by check_docs.py; updating its exact digest does not assign authority to its referenced documents.

All JSON candidates decoded successfully; text candidates were read as UTF-8 and hashed. Artifact/source bindings are explicit per path, not a new scanner prefix allowance. Structural provenance tests and an independent review are required before this repair is accepted. Full assurance, physical-model validation, scientific certification and formal proof are not claimed by this document.
