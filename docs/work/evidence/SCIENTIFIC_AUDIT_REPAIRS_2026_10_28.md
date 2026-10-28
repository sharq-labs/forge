# Scientific audit repairs on local main — 2026-10-28

Scope: the owner's explicit request to repair S-01 through S-05 on `main`.
Starting commit: `dd567d53d2444950f57ffaeb9903c74d7c38f04d`, with pre-existing
local MVP, ordering, scoring and isolation work. Other concurrent timing and
documentation changes were preserved. This is a development repair report,
not a certificate, formal evaluation or measured scientific lift.

## Corrected boundaries

1. **S-01, equation/data identity.** `DiscoveryFeature` now evaluates its typed
   expression against snapshotted typed sample bindings and rejects a mismatched
   column. Symbols with declared binding units work; constant placeholders for
   unrelated varying columns no longer do. Dimensionless feature/target scope is
   unchanged. Dataset fingerprints bind expressions, bindings, values, targets,
   calibration/selection partitions, lineage and evidence. Generated candidate
   identities also bind search policy, implementation bytes and NumPy version.
   Historical manually constructed candidate fingerprints remain unchanged.
2. **S-02, pair recovery.** Development `score_v3.score_universe` requires at
   least one accurate law for recovery. Bracketing alone remains explicitly
   unresolved, with no positive recovery credit and existing control penalties
   retained. All six task kinds and both potentially accurate members are tested.
3. **S-03, statistical inference.** `analysis_v3.bounded_paired_test` uses a
   conservative one-sided Hoeffding bound for paired independent-unit means.
   `compare_paired_scores` requires a complete predeclared arm/unit/repeat grid,
   averages repeated settings within each independent physical unit, compares
   every baseline, applies Holm, and reports separate simultaneous lower bounds
   with Bonferroni coverage. No uncentered bootstrap tail is passed as a p-value.
   The v3 compatibility diagnostic never promotes the legacy lift result.
4. **S-04, selection versus final testing.** Generated candidates explicitly
   carry `evaluation_role="selection"`; review cannot promote them using a
   verification object. `FrozenDiscoverySelection` freezes the selected winning
   candidate and a finite final threshold before a final dataset is supplied.
   `evaluate_final_test` neither refits nor ranks alternatives. It checks feature
   expressions, context and disjoint declared sample/physical-group identities,
   and binds the final result to the frozen selection and exact final data.
   Closed-loop campaigns stay at HOLDOUT_REVIEW for selection-only reviews;
   the new CANDIDATE decision cannot accidentally complete a campaign.
5. **S-05, zero.** Development v3 scores exact prediction/truth zero as correct.
   A nonzero prediction at zero truth fails. The relative criterion away from
   zero and PASS_FRACTION are retained; no absolute tolerance was invented.
   Missing/nonfinite truth never passes. Pair inbox agreement handles zero too.

## Current entry points and compatibility

Use `benchmarks.genesis_lite.evaluator.score_v3` and
`benchmarks.genesis_lite.analysis_v3` for the corrected development evaluation.
The frozen `score.py`, `analysis.py`, old preregistrations and historical outputs
remain byte-identical to HEAD. Their old numerical decisions are historical
replay, not v3 decisions. No v3 formal campaign identity has been frozen.

Use `engcore.scientific.discovery.final_test.FrozenDiscoverySelection` and
`evaluate_final_test` after `discover_sparse_equations`. The legacy field name
`holdout_indices` remains for compatibility but denotes selection rows during
search. Final data are supplied separately, only after freezing the winner.

Physical lineage IDs and independence are declarations, not authenticated
custody. This API does not prevent a malicious caller relabeling leaked data.
Final model testing is numerical testing, not independent experimental validation.
Statistical superiority is conditional on independent units, bounded scores and
a plan fixed before outcomes. `lift_claimed` stays false in v3 pending formal
campaign qualification, per-kind noninferiority and independent evaluation.

The conservative bound is deliberately allowed to be inconclusive at modest
sample sizes; no power or useful lift is fabricated. Its reference is
[Hoeffding (1963), Probability Inequalities for Sums of Bounded Random Variables](https://doi.org/10.1080/01621459.1963.10500830).
The synthetic null control enumerates all 1,024 independent ten-unit two-point
null samples and verifies conservativeness at alpha .01, .05 and .10. This is a
bounded implementation control, not a formal application campaign.

## Validation and failed approach

Python 3.11.15 on native Windows, using `.venv/Scripts/python.exe`.
All new scientific fixtures are synthetic; no hidden/final evaluation data read.

- Initial direct edit of legacy `analysis.py` caused 8 integration failures
  because its bytes are preregistration-pinned. The edit was reverted exactly;
  the safe boundary was moved into `analysis_v3.py`. No pin or guard was relaxed.
- Integration including historical analysis/replay, discovery hardening and
  corrected scoring: **153 passed**, `.forge/scientific-repairs-integration.log`.
- Official regression pack: **279 passed**, command
  `python tools/forge_check.py --regression --workers 2`, log
  `.forge/scientific-repairs-regression.log`.
- Final directly affected modules after the last implementation identity and
  tolerance-input and campaign-stage checks: **85 passed**, `.forge/scientific-repairs-final-targeted.log`.
- Wider changed-file gate uses `python tools/forge_check.py --changed --base HEAD
  --workers 2`: **2,799 passed, 29 failed, 54 skipped in 474.10 seconds**,
  `.forge/scientific-repairs-changed.log`. This gate is RED, not a release gate
  PASS. Its selection/run began before the final implementation-metadata and
  campaign-stage follow-ups; the 85-test final run covers those updates.

The 29 failed nodes are retained in `.forge/scientific-repairs-failure-ids.json`.
Observed mechanisms, not an assertion of baseline equivalence:

- Change impact (1) and repository ownership symlink (1): Windows privilege
  error 1314. The other repository ownership failure (1) sees the local
  environment in the checkout graph.
- Authority integrity (4), escrow boundary (15): POSIX `geteuid`/`fcntl`
  unavailable on native Windows, or the corresponding child handshake fails.
- Mutation startup (3): Windows interpreter executable-file/symlink assumptions.
- Certificate (2): modified Core bytes (including this repair) and dirty tree;
  an old certificate cannot be made current by editing its hashes.
- Data inventory (2): `certification/current_core_v2.json` and `docs/ai/DOCSET.txt`
  remain UNKNOWN_PROVENANCE (confirmed by the live scanner). The synthetic-data
  test fails on unknown count, not on an observed synthetic-as-measured label.

`git diff --check` and `docs/ai/check_docs.py` pass. Source hashes for the final
repair are in `.forge/scientific-repairs-source.json`. These are local receipts,
not certification manifests. Existing frozen evaluator and analysis source bytes
were separately checked identical to HEAD.

Full FAST/SCIENTIFIC, hardened recertification, independent evaluation, commit,
push and merge are not claimed by these focused development results.
