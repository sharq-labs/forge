# Independent provenance review disposition

Reviewed final scanner/test implementation in `codex/domain-inventory-reviewed-2026-10-20`; implementation subsequently committed unchanged through `0047321df0522cbc78bb0a7160aace434699c093`.

Overall read-only reviewer Halley: PASS, no remaining material scientific-boundary findings. Read the executed 33-test receipt, did not execute tests. Confirmed 433 unique declarations and all local artifact/source SHA256 bindings. Historical dataset/report bytes unchanged. Declaration origin classification is not applicability, validation or certification.

Benchmark slice reviewer Hegel: PASS, 245 artifacts and 111 distinct supporting paths checked. Existing battery closure acceptance can retain FAIL outside applicability; declarations preserve the artifact but expressly do not endorse such a verdict as admissible contradiction. No acceptance-rule change made.

Other slice reviewer Feynman: confirmed five authored analytical metadata files must be DERIVED, superseding the earlier REFERENCE_ONLY disposition. They contain empty source_digest/data and declare derived rather than copied origin. Final manifest applies this correction while retaining all historical bytes and scientific limits.

Final totals: 405 DERIVED, 22 SYNTHETIC, 3 REFERENCE_ONLY, 3 REAL_MEASURED.

Fixed hostile-review findings:

- NUL-delimited enumeration includes Unicode Git paths.
- Historical classification requires original pinned scanner and matching historical/index/raw bytes, including assume-unchanged cases.
- Explicit current declarations bind artifact and current source SHA256 plus Git index identity.
- The review manifest must itself match its stage-0 regular-file Git blob.
- Immutable archived source references are checked against their Git object rather than a current working file.
- Five locally authored metadata classes corrected to DERIVED.

Final targeted execution: 33 passed in 13.00s. Integration FAST still running when this record was prepared; review PASS does not claim gate PASS.

Post-execution independent evidence review: PASS. Reviewer independently verified raw-log hashes, all12114shared/33added/0removed nodes and exact failure/error labels, including parameter strings containing delimiters. Zero unmatched/ambiguous summary lines; zero differences. Both gates exit1. Matching labels does not prove identical failure causes or scientific correctness. Only Markdown changed after0047321d.
