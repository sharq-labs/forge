# R21 bounded portability review

Independent read-only reviewer `/root/r21_integration_review`: PASS. This technical
review does not supply a human GitHub approval, scientific validation or assurance.

The first official FAST311 run exposed two test assumptions that differ between
the required runtimes. Production correctly refuses an unreadable owner history;
CPython3.11 cannot encode depth2000 even on a fresh thread, whereas3.12 can. The
revised test independently checks owner round-trip readability, requires rollback
refusal and exactly one execution in either case, and requires permanent divergence
for unreadable history. Depth3/600 positive controls and100000 overflow remain.

The declared dependency range installs Pint0.25.3 on3.11 and0.26.2 on3.12. Full unit
registry fingerprints differ. An additive frozen reference records the former
runtime; originalAUTHORITY.json remains byte-identical. Only six world_revision
fields differ; all decisions and other recorded fields match. This is not proof
that all registry declarations are semantically equivalent. The test requires the
full registry fingerprint, exact Pint version, exact frozen file digest and exact
computed matrix bytes. Unknown combinations fail. No expected output is generated
by the test, and no Core fingerprint is normalized. The existing producer and its
original-reference CLI are unchanged; this bounded repair qualifies the integrity
test, not every CLI invocation across runtimes.

Reviewed SHA-256 values:

| Path | SHA-256 |
|---|---|
| tests/mind/test_authority_review_r11.py | 91b9045fd12ec99b6f264fa6c69c97ad1f8e5ebb993c1eed6bf3d0ac2ef83dce |
| benchmarks/mind_gen2_authority_v1/tests/test_mind_gen2_authority_v1.py | b2af08f8472067c1e778806691161be9cac33a537c8d570bbf23fdb909d56548 |
| results/runtime/AUTHORITY_pint_0_25_3.json | b7f09d39028bf5d0d4b7c3ce45c1789c5aeeacb193028c1320906f213d4e8651 |
| benchmarks/domain_real_data/CURRENT_PROVENANCE.json | 6f0476cb7b034a15151bd6a08934f64eff8514a1102f7a02c5459579e1ee1bd9 |

The reviewer read focused logs:44passed,1deselected in5.51s on3.11 and5.57s on3.12.
No production/Core files, old records, uncertainty, thresholds or skips changed.
The59 failure IDs shared with Round20 remain a separate integration blocker;
this repair does not claim their causes are equivalent or that assurance passed.
