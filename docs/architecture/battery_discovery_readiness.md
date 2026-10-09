# Battery degradation discovery — readiness assessment (Roadmap V2)

Status: **READINESS ONLY.** No experiment was run, re-run, re-fitted or pre-registered for this assessment, and nothing
here changes the BIG 14 record: the Kirkaldy 2024 throughput-Arrhenius fade study stays **NOT MET** (activation energy NOT
ESTABLISHED, model discrepancy NOT QUANTIFIED; `docs/flagships/README.md`, PROGRESS 2026-10-09). The observed Expt 4
holdout is exploratory evidence for a next fade law at most; any confirmatory test needs a FRESH pre-registration and a
fresh holdout.

## What Roadmap V2 now provides for such a campaign

| need | V2 component | ready? |
|---|---|---|
| a candidate fade law as a typed claim | `sria.decision.Hypothesis` (kind EQUATION / MECHANISM, claim digest, PROPOSED) | yes |
| proposers that cannot decide (symbolic regression, BO) | `claims.discovery_providers` (PySINDy proposals, BoTorch suggestions) | yes (providers executed; not qualified) |
| pre-registered, sealed falsifiers on NOVEL predictions | `claims.falsification` (owner ticket, sealed prediction/k/resolution, novel-condition rule) | yes, in-process |
| measurement records as the only evidence clock | `ExposureAuthority` (acquisition ids; HMAC; first exposure) | needs an adapter from the dataset loader (DEFERRED) |
| "selected from N fits" stated with every result | `claims.multiplicity` (ledger, close(), verify_promoted with the registry) | yes |
| is the law new? | `claims.novelty` (sealed prior-art snapshot, registered canonicalizer) | needs a frozen prior-art snapshot of fade laws (Arrhenius throughput, sqrt-time SEI, power-law calendar ageing, ...) — NOT BUILT |
| cheap physics screening | `design.fidelity_graph` (SPM -> SPMe -> DFN links) | PyBaMM is NOT installed in this container; links would have to be MEASURED, not declared |
| credibility for a decision | `claims.credibility_vector` (registered risk policy, projection of ValidationLevel) | yes |
| adversarial check of a fitted law | `claims.redteam` (temperature / C-rate / DoD attack space, cross-family confirmation) | yes, needs routes |

## Blocking items before any confirmatory battery experiment

1. A new hypothesis (non-monotone temperature dependence or another form) proposed and REGISTERED before any new data at
   its test conditions is released (the novel-prediction rule refuses falsifiers at already-released conditions).
2. A fresh pre-registration: thresholds, splits, holdout cells/rigs/profiles, complexity control, the leave-one-cell-out
   treatment of parameter uncertainty (the open item from the BIG 14 close-out).
3. An ExposureAuthority adapter over the dataset loader so that holdout data is released ONLY after the seal.
4. A frozen prior-art snapshot of fade-law structures (with expressions, so the canonicalizer is self-tested).
5. The Kirkaldy data lives outside this container (`D:/forge-data/kirkaldy2024`); it was not copied or downloaded.

Readiness verdict: **NOT READY for a confirmatory experiment; READY to draft the pre-registration** with the V2
authority components above. AM-Bench comes later, per the owner's ordering.
