# Scientific core re-audit — 2026-09-16

Audited: `claude/core-scientific-audit` at `294c129` (after batches 1-5 of `CORE_SCIENTIFIC_AUDIT_2026-09-16.md`).
Full machine-readable record, with every finding's evidence, reproduction, fix direction and verifier output:
`benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json`.

## Method

Nine code readers, one per core subsystem, read the implementation and ran reproductions. Every finding was adversarially verified: two independent lenses (reproduce; scope/reachability) for P0/P1, one otherwise; a finding survives with a majority of real votes. 109 found, 106 survived, 3 refuted. The 106 were deduplicated into 75 problems (R-01..R-75) and 30 improvements (I-01..I-31, I-17 absorbed into I-08) by a synthesis agent over all 106, checked by a completeness critic: every finding maps to exactly one problem, every problem is addressed, risk and gain shares sum to 100. R-01, R-03 and R-10 were additionally reproduced by hand at the audited commit.

## How production reaches the core

The MCP server is the main production entry point. It exposes describe_capabilities, run_electrothermal and run_battery, which go through problem and battery case runners into CredibilityEvidenceReport and derive_verdict, so the results, validation and credibility guards are reached there. On that path the verdict block never shows evidence_basis, and the report ignores convergence, uncertainty and declared validity requirements. record_values is never passed, so the CORE-014 operating-point binding does not fire (R-04, R-09, R-10, R-72). Domain runners reach conduction2d boundary handling (R-56), the electrothermal coupling with bare-value transfers (R-58), and multirotor design archives that rank unassessed candidates (R-44). The only production calibration route is studies/calibration_study and the battery B1-B3 tables. They run through frozen V1 gaussian_grid_posterior, posterior_predictive_uq and assess_predictive_observation, so no V2 goodness-of-fit, containment, uniqueness or prediction-domain gate runs (R-02, R-35, R-36, R-38). engcore.hybrid_uq, adequacy comparison, TrustedConsensusGate, Experiment.best, the oracles and uq admission have no production caller; benchmarks, audits and certification tools reach them only as a library. The certification tools themselves are latent: they certify the live API with no additive-only comparator, accept self-asserted assurance, and leave the batch guards outside the pinned mutation population (R-65 to R-70). Until I-03, I-11 and I-16 land, most V2 fixes lower library risk without sitting between a production entry point and a published number.

## Problems (R-xx)

Stars: 5 = P0, 4 = P1, 3 = P2, 2 = bounded P3, 1 = hygiene. `risk %` = share of total remaining trust risk (sums to 100).

| ID | Sev | Stars | risk % | Reached | Area | Problem | Findings |
|---|---|---|---|---|---|---|---|
| R-01 | P0 | ★★★★★ | 7.3 | library-only | hybrid_uq router (rebuild step) | **A grid rebuild turns an unassessed or incomplete uniqueness search into a SUPPORTED one-mode grid**. With the default multistart=None, the local route is DOWNGRADED for GLOBAL_UNIQUENESS_NOT_ASSESSED, but step 3 rebuilds a SUPPORTED grid around that one estimate anyway. It misses a mode holding 63% of the posterior (sd 42x too small in the prior repro). | 5, 14 |
| R-03 | P1 | ★★★★☆ | 2.7 | library-only | hybrid_uq local_gaussian goodness of fit | **Observations that carry no information dilute the pooled goodness-of-fit gate (CORE-001)**. The chi2 test pools every residual on n-p dof. A REFUSED misfit (chi2/dof 9) becomes SUPPORTED once 60-1000 uninformative observations are added, and its covariance does not change. | 2 |
| R-06 | P1 | ★★★★☆ | 2.7 | library-only | hybrid_uq router (supplied-grid step) | **A supplied grid over one of two equal modes is SUPPORTED, and a caller's MultistartPolicy is never run**. Step 1 returns GRID_AS_SUPPLIED SUPPORTED before multistart runs, and it tests only the box faces. The same request through local_gaussian_posterior with MultistartPolicy() is REFUSED with SECOND_MODE_FOUND. | 17 |
| R-05 | P1 | ★★★★☆ | 2.2 | library-only | inference/calibration grid resolution | **The V1 grid resolution check fits one quadratic about the top node, so an unresolved second mode inside the box passes**. _fitted_lattice_covariance fits only at the argmax, with no residual test. A narrow second mode (local sd 0.00065 at step 0.005) is SUPPORTED with an sd about 14x too small. | 15 |
| R-07 | P1 | ★★★★☆ | 2.2 | library-only | hybrid_uq local_gaussian multistart | **Multistart dismisses a converged refit in another basin as WORSE_LOCAL_OPTIMUM on peak height alone**. A separated optimum is classified by objective value only, and the verdict ignores WORSE_LOCAL_OPTIMUM. A broad basin holding most of the mass is dropped, and the SUPPORTED 95% interval holds 17.7% of the posterior. | 1 |
| R-24 | P1 | ★★★★☆ | 2.2 | library-only | adequacy/predictive content binding and comparison | **Adequacy content binding omits split identity, likelihood sigma and twin, so compare pairs assessments that do not belong together**. compare_log_predictive_scores pairs identical models calibrated on different data under one dataset-id label and gives a decisive preference (delta -5.8, se 0.86). A caller-chosen sigma (0.05 K vs declared 0.5 K) creates a preference, and a twin mismatch still reads content_bound=True. | 29, 30, 40 |
| R-04 | P2 | ★★★☆☆ | 2.9 | yes | mcp server verdict block / results validation | **A verification-only SUPPORTED reads bare in the MCP verdict block, and verification levels need no issuer**. Every SUPPORTED MCP verdict is VERIFICATION_ONLY, but evidence_basis appears only in the nested report and the block shows no reasons. A hand-written ANALYTICALLY_VERIFIED check with evidence 'trust me' turns INSUFFICIENT_EVIDENCE into SUPPORTED and survives from_dict. | 43, 50, 82 |
| R-09 | P2 | ★★★☆☆ | 2.9 | yes | models validity / results / mcp evidence | **The CORE-014 operating-point binding never fires in production and is bypassable when enabled**. record_values has no caller, assess_validity cannot forward it, and the MCP report path merges validity without comparing. An IN_DOMAIN assessment made at one operating point is accepted for a result at another (alpha -1e-5 vs 1e-5 reads SUPPORTED). When enabled, it matches by name only and drops evaluated on read. | 45, 46, 62, 80 |
| R-02 | P2 | ★★★☆☆ | 2.5 | yes | studies/calibration_study, uq/predictive, adequacy | **The production calibration study predicts and validates through frozen V1 functions, so no V2 evidence gate runs**. posterior_predictive_uq and assess_predictive_observation apply no goodness-of-fit, containment, prior or domain check. A box of mean +/-0.6 sd truncates the posterior sd to 0.34x and is still content-bound and usable for a decisive comparison. | 33, 81 |
| R-10 | P2 | ★★★☆☆ | 2.5 | yes | mcp evidence from_result | **The credibility report never reads result convergence**. A DIVERGED, MAX_ITERATIONS or FAILED result with a passing check derives SUPPORTED, and convergence is absent from the report JSON, even though is_usable is False. | 44 |
| R-72 | P2 | ★★★☆☆ | 2.5 | yes | scientific/ir problem | **ScientificProblem validation_requirements and UncertaintySpecification are declared but enforced nowhere**. The DC, CSTR and conduction problems declare required checks that nothing reads. from_dict silently drops misspelled keys, so a requirement like 'numerically_convergd' is accepted and never checked. | 103 |
| R-08 | P2 | ★★★☆☆ | 2.1 | library-only | hybrid_uq local_gaussian multistart | **The minimum-search rule ignores max_evaluations and maximum_retractions, and failed refits are dropped**. A refit budget of 12 evaluations turns REFUSED SECOND_MODE_FOUND into SUPPORTED, as long as half the starts converge. The committed K2 kinetics evidence relies on this search. | 7 |
| R-39 | P2 | ★★★☆☆ | 2 | library-only | results validation / consensus | **evidence_basis labels agreement between two solvers of the same declared model as VALIDATED**. CROSS_SOLVER_VALIDATED is in VALIDATION_LEVELS, so native plus ngspice agreement on one DCCircuit declaration reads VALIDATED. That is verification of one model, not validation against reality. | 42, 83 |
| R-56 | P2 | ★★★☆☆ | 2 | yes | fields conditions / conduction2d | **require_complete_boundary checks one condition per region id, not per edge**. If two conditions share a region id, the last one wins in conduction2d. A declared Dirichlet edge is silently dropped while every completeness and Dirichlet check passes. | 68 |
| R-11 | P2 | ★★★☆☆ | 1.6 | library-only | hybrid_uq router rebuild truncation | **A posterior cut at the declared upper bound, with data bounding only the lower side, is SUPPORTED**. Domination is refused only when both sides truncate. Moving the upper bound from 20 to 40 to 80 changes the reported sd from 1.74 to 2.04 to 3.47, all SUPPORTED, so the bound sets the answer. | 16 |
| R-12 | P2 | ★★★☆☆ | 1.6 | library-only | hybrid_uq predictive domain gate | **calibration_observations for a routed prediction are bound to nothing**. Passing another dataset's observations, rescaled conditions or a predictor evaluated elsewhere silences PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS. A far extrapolation (x=1e4) reads SUPPORTED although the posterior carries its own dataset_id. | 21, 27, 85 |
| R-16 | P2 | ★★★☆☆ | 1.6 | library-only | hybrid_uq local_gaussian probes | **Probe directions come from eigh(cov) in declared units, so a unit change moves the tested directions**. The same model and data are SUPPORTED with a parameter in volts and REFUSED (TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN) in millivolts. | 10 |
| R-21 | P2 | ★★★☆☆ | 1.6 | library-only | consensus / results validation / execution gate | **CROSS_SOLVER_VALIDATED is guarded only by string checks, and non-independent disagreement is absorbed as WARNING**. Hand-written consensus evidence lines earn the level and survive a result round trip, and TrustedConsensusGate has no caller. Routes 33% apart that are not verified independent give WARNING, and the verdict stays SUPPORTED. | 56, 57, 60 |
| R-31 | P2 | ★★★☆☆ | 1.6 | library-only | hybrid_uq predictive domain gate | **The prediction-domain gate compares only the conditions the prediction chooses to declare**. Calibration held T=300 K. A prediction at T=900 K is DOWNGRADED, but the same prediction with T omitted is SUPPORTED. Joint-support departures (0.71 off the calibrated line) also pass. | 28 |
| R-32 | P2 | ★★★☆☆ | 1.6 | library-only | inference/split and adequacy comparison | **Split duplicate handling: replicates within a half inflate n, and near-duplicates cross into held-out**. One held-out reading listed four times gives n=4, se=0 and a decisive preference. A calibration reading re-imported at 4-8 significant digits, with a re-declared sigma or a renamed observable, is accepted as held-out. | 31, 38 |
| R-33 | P2 | ★★★☆☆ | 1.6 | library-only | adequacy/predictive compare | **The decisive-comparison gate uses a normal 2 SE critical value with an SE from n-1 dof**. Between mirror-image models, a preferred model is named in 27.5% of runs at n=2 and 19.3% at n=3. | 32 |
| R-37 | P2 | ★★★☆☆ | 1.6 | library-only | hybrid_uq predictive linearized | **Linearized predictive nonlinearity is never refused and is pooled across specs**. A prediction with nonlinearity=inf and parameter sd 0 is still emitted, only DOWNGRADED. One quadratic output also downgrades an exactly affine prediction in the same call and records inf as its nonlinearity. | 37, 39 |
| R-41 | P2 | ★★★☆☆ | 1.6 | library-only | scientific experiments | **Experiment.best judges feasibility from whatever checks a candidate carries**. Declared constraints need not be checked, and checks are not tied to the result's numbers. A candidate that checks one of two constraints is feasible, and from_dict without a constraints key drops them, changing best from eval-1 to eval-2. | 48, 100 |
| R-43 | P2 | ★★★☆☆ | 1.6 | library-only | results uncertainty / sria budget | **UncertaintySource never reaches a verdict or report, and SRIA budgets accept NUMERICAL as model-form**. source_kind has no producer, and the report has no uncertainty field. The SRIA budget marks aleatoric and model_form 'known' from a numerical-only record. | 51, 86 |
| R-48 | P2 | ★★★☆☆ | 1.6 | library-only | units in oracles, constraints, grid, split | **Spreads on offset temperature scales convert as absolute temperatures**. A '0.5 degC' tolerance becomes 273.65 K, so a prediction of 573 K passes against 300 K. Sigmas and tolerances in degC become about 274 K, while the correct delta_degC form crashes. | 58, 99 |
| R-57 | P2 | ★★★☆☆ | 1.6 | library-only | fields conditions | **The corner-agreement guard compares magnitudes in each law's own unit**. 300 K meeting 300 degC (573 K) is accepted, a 273 K conflict at the corner. 300 K meeting 26.85 degC, the same temperature, is refused. | 69 |
| R-71 | P2 | ★★★☆☆ | 1.6 | library-only | inference admissibility / grid | **Forward-model admission is not bound to the source result, and tables bind observations by key label only**. The analytic admission route skips convergence and the source result's validation, so a 2-cell, 1-step solve is admitted. AdmittedForwardTable accepts any strings as admission refs and compares data in the observation's own unit (1500 milliohm against a 1.5 ohm table). | 98, 102 |
| R-14 | P2 | ★★★☆☆ | 1.3 | library-only | hybrid_uq local_gaussian tail probes | **The 3 and 6 sd tail probes run only along principal axes**. A posterior flat along the diagonals beyond 3 sd is SUPPORTED, and its 95% intervals hold 76.8% of the marginal (mass beyond radius 3 is 0.20, against 0.011 for a Gaussian). | 4 |
| R-15 | P2 | ★★★☆☆ | 1.3 | library-only | hybrid_uq local_gaussian tail probes | **A tail probe beyond a declared bound is skipped without being counted**. The same flat-tailed posterior is REFUSED with bounds at 6.01 sd and SUPPORTED at 5.99 sd. | 9 |
| R-17 | P2 | ★★★☆☆ | 1.3 | library-only | hybrid_uq grid evidence containment | **A posterior cut by forward-model inadmissibility counts as contained**. Faces with no admissible node read as empty, so supplied grids cut at an inadmissibility boundary are SUPPORTED with means off by up to 0.57 sd. | 19 |
| R-28 | P2 | ★★★☆☆ | 1.3 | library-only | hybrid_uq identifiability | **assess_routed_identifiability accepts loosened thresholds on the local route**. The INF-10 declared-or-tighter guard runs only for grids. Canonical NOT_IDENTIFIABLE (correlation 0.9999985) becomes WEAKLY_IDENTIFIABLE under caller thresholds, and the record reads back. | 23 |
| R-40 | P2 | ★★★☆☆ | 1.3 | library-only | mcp evidence from_result | **A provenance override in from_result drops declared but unassessed models**. Passing a provenance that names only one of the result's two models turns INSUFFICIENT_EVIDENCE into SUPPORTED, with unassessed=(). | 47 |
| R-42 | P2 | ★★★☆☆ | 1.3 | library-only | scientific experiments evaluation | **The objective-versus-result check is keyed by objective name, not metric**. When the name differs from the metric, the check is skipped. best() ranks on objective 0.001 W while the result carries load = 50 W. | 49 |
| R-59 | P2 | ★★★☆☆ | 1.3 | library-only | uq/admission | **Predictive-admission conditioning accepts any budget and returns an unmarked PosteriorGrid**. With budget 1.0 it conditions away 99.9997% of the posterior (factor 3.4e5). The result reuses the original dataset_id and mask, so nothing downstream can tell. | 72 |
| R-13 | P2 | ★★★☆☆ | 1 | library-only | hybrid_uq local_gaussian probes | **The pairwise +/-2 sd probes cannot see a curvature error spread over many pairs**. Each axis and diagonal is checked alone within 0.1. At p=10 the claim is SUPPORTED while one direction's true sd is 2.24x the reported sd. | 3 |
| R-18 | P2 | ★★★☆☆ | 1 | library-only | hybrid_uq local_gaussian multistart | **Retracted multistart starts count as full-span starts**. Starts the forward model refuses are halved toward the estimate (for example 12 becomes 0.75). With 5 of 6 retracted into one basin, the search reads MULTISTART_NO_SECOND_MODE, SUPPORTED, and misses an equal second mode. | 8 |
| R-19 | P2 | ★★★☆☆ | 1 | library-only | hybrid_uq grid evidence binding | **Evidence binding spot-checks 8 nodes, 4 of them seeded from the supplier's bytes**. A grid with 5022 of 19881 nodes sharpened 4x passes after 2 grinding attempts and reports sd halved (0.0136 against 0.0272). | 18 |
| R-22 | P2 | ★★★☆☆ | 1 | library-only | hybrid_uq local_gaussian read-back | **Local RouteDiagnostics read-back trusts carried fields**. Editing the observation count turns DOWNGRADED into SUPPORTED. A relabelled SECOND_MODE refit, stripped policy keys, or a record with no tail probe evaluated (NaN ratio) also reads SUPPORTED. | 12 |
| R-58 | P3 | ★★☆☆☆ | 1.5 | yes | composition transfer / uq cross_domain | **Cross-domain crossings carry bare point values, and UncertaintyTransfer binds nothing**. Production electrothermal coupling passes values with no uncertainty, validity or validation state. The unused UncertaintyTransfer accepts any same-dimension uncertainty, intervals that do not contain the value (350 K with 10-11 K), and overwritten attribution. | 71, 79 |
| R-35 | P3 | ★★☆☆☆ | 1.2 | yes | studies/calibration_study held-out verdict | **HELD_OUT_VALIDATION_PASS is issued for any n>=1 with no power floor**. Only PASS and FAIL exist, with FAIL at p<0.01. A misspecified model with one held-out point (residual 2.1 sd) passes in 24 of 40 seeds. | 35 |
| R-38 | P3 | ★★☆☆☆ | 1.2 | yes | studies/calibration_study | **The TCR held-out study refuses heterogeneous declared sigmas, and coverage repetitions claim CONVERGED without a calibration run**. Held-out sigmas [0.002, 0.002, 0.003] can never be validated, because either observation_sigma is refused. Coverage records say CONVERGED although no calibration ran. | 41 |
| R-51 | P3 | ★★☆☆☆ | 1.2 | yes | models definition / domains repair | **CrossLimitCondition reports a missing declaration as a core gap**. When one operand is supplied, RATED_LINEAR_TCR_MODEL reads UNREADABLE_SHAPE. Repair guidance tells the user that declaring it again will not help, which is wrong. | 63 |
| R-75 | P3 | ★★☆☆☆ | 1.2 | yes | units quantity / mcp problem | **Quantity.parse evaluates unit expressions, magnitudes accept bool or str, and delta units pass as absolute**. At the MCP boundary, '5 volt 2' is accepted as 10 V and '2 volt + 3 volt' as 5 V. An ambient of '27 delta_degC' passes the dimension-only check as an absolute temperature. | 106 |
| R-67 | P3 | ★★☆☆☆ | 1.1 | latent | certification mutation harness | **Batch-guard mutation evidence sits outside the pinned harness and counts any failure as a kill**. None of the 44 batch guards is in MUTATIONS, two recorded kills (B1j, B1k) no longer apply, and several fix guards have no mutation. The runners mutate the shared checkout in place and treat any non-zero exit as KILLED. | 92, 97 |
| R-29 | P3 | ★★☆☆☆ | 1 | library-only | hybrid_uq grid evidence prior uniformity | **The uniform-prior step tolerance refuses a grid that is effectively uniform**. A natural linspace grid on a LOG axis (step deviation 2%) is PASSED_OVER, although its mean and sd match the accepted log-linspace grid to 6 digits. | 25 |
| R-36 | P3 | ★★☆☆☆ | 1 | yes | studies/calibration_study coverage | **The coverage verdict pools correlated intervals as independent trials**. With ICC 0.37 (design effect 2.09), the Wilson interval is about 1.45x too narrow, and UNCERTAINTY_CALIBRATED verdicts flip near the band edges. | 36 |
| R-44 | P3 | ★★☆☆☆ | 1 | library-only | experiments / design archives | **Unassessed candidates are ranked: best() admits NOT_RUN validation and design archives lack the CORE-015 rule**. best() picks a candidate with validation NOT_RUN and nothing attained. The multirotor Pareto and elite archives rank validity_not_assessed candidates as ELIGIBLE, and best() has no caller. | 52, 84 |
| R-65 | P3 | ★★☆☆☆ | 1 | latent | certification core freeze | **The branch descends from no Core Freeze, and recertification is blocked**. The V1 and V2 frozen digests moved (c80e6418 to 7a481264) and 4 API snapshot tests fail. The certificate-child self-check list makes recertification impossible without a V4 control-plane change. | 89 |
| R-20 | P3 | ★★☆☆☆ | 0.8 | library-only | hybrid_uq local_gaussian goodness of fit | **With 1 or 2 residual dof the variance-ratio refusal can never fire**. The p>=0.01 check returns before the ratio test, so chi2/dof of 6.6 (dof 1) and 4.57 (dof 2) read SUPPORTED. | 6 |
| R-26 | P3 | ★★☆☆☆ | 0.8 | library-only | hybrid_uq local_gaussian | **POORLY_SCALED_PARAMETERIZATION is judged on the unit-dependent raw condition number**. Declaring a slope in nanovolts instead of volts (raw condition 3.2e9, equilibrated 3.47) downgrades an exactly Gaussian result. | 13 |
| R-45 | P3 | ★★☆☆☆ | 0.8 | library-only | results validation serialization | **The CORE-013 status precedence changed without a schema bump**. Older validation_report/1 records with a NOT_RUN check are refused as tampered. SRIA reports 'validation never run' when a check simply did not apply, and older readers silently drop new bindings (evaluated, source_kind). | 53, 87, 90 |
| R-46 | P3 | ★★☆☆☆ | 0.8 | library-only | results validation | **GUARD 21 compares signed residual and tolerance**. A PASS with residual -10 against tolerance 1e-6, or with a negative tolerance, is constructed and earns NUMERICALLY_CONVERGED. | 54 |
| R-54 | P3 | ★★☆☆☆ | 0.8 | library-only | models definition conditions | **Validity condition primitives accept declarations whose meaning silently inverts**. allowed='laminar' becomes the letter set, so 'laminar' is outside the domain and 'a' is in it. Ratio bounds with a > b still read in_domain. | 66 |
| R-62 | P3 | ★★☆☆☆ | 0.8 | library-only | fields mesh / transfer | **Mesh identity depends on unit-conversion float rounding and a 1e-12 m floor**. 7 mm and 0.7 cm get different fingerprints, and 10 nm against 10.0005 nm reads as the same geometry at two resolutions, so transfers wrongly require projection. | 76 |
| R-64 | P3 | ★★☆☆☆ | 0.8 | library-only | composition dependency / conversion | **The energy-crossing guard matches only exact energy or power dimensions**. W/m^2, W/m, J/kg and W/m^3 cross with no declared EnergyConversion, while plain watt is refused. | 78 |
| R-69 | P3 | ★★☆☆☆ | 0.8 | latent | certification api snapshot | **The frozen API snapshot cannot see method-level contracts or additive-only violations**. Removing record_values or evidence_basis leaves the V1 and V2 digests unchanged. v1_entries_byte_identical_in_v2 compares live to live, and 13 RouteReason members changed position without detection. | 94, 95 |
| R-30 | P3 | ★★☆☆☆ | 0.7 | library-only | hybrid_uq router | **An evidence-binding mismatch raises instead of passing over**. A grid off only at solver-tolerance level (chi-square 1064.66 on both sides) aborts route_uncertainty with HybridUQError. The same request without the grid is LOCAL_GAUSSIAN SUPPORTED. | 26 |
| R-52 | P3 | ★★☆☆☆ | 0.7 | library-only | scientific consensus | **The consensus verdict depends on route order through the first route's unit**. Relative difference is taken on offset-scale magnitudes in the first route's unit. Swapping route order changes 3.7e-9 (disagree) to 3.3e-10 (CROSS_SOLVER_VALIDATED). | 64, 101 |
| R-55 | P3 | ★★☆☆☆ | 0.7 | library-only | fields result / structured validity | **Field validity decides from an unbound self-declared summary and a component envelope**. FieldSummary is never checked against the bytes or unit, so a forged summary reads in_domain with the same reference digest. A 3-component field with /u/=1.73 passes a 1.2 m/s maximum. | 67, 70 |
| R-60 | P3 | ★★☆☆☆ | 0.7 | library-only | composition transfer | **The QuantityTransfer conversion budget check has a 1.0 absolute floor**. Small crossings in large exemplar units (1 mW with gigawatt) report 100% arrival against a declared 50% efficiency and are accepted. | 73 |
| R-34 | P3 | ★★☆☆☆ | 0.5 | library-only | adequacy/predictive | **content_bound is a caller-settable flag that the decisive comparison treats as proof**. from_dict or replace with content_bound=True yields a decisive preference (15.9 nats), even with fabricated log densities. The comparison has no production caller. | 34, 88 |
| R-49 | P3 | ★★☆☆☆ | 0.5 | library-only | scientific oracles | **Oracle operating-point conditions are the caller's word, partial and optional**. compare never checks where the prediction was computed. Observations without conditions pass at a stated T=9999 K. | 59 |
| R-50 | P3 | ★★☆☆☆ | 0.5 | library-only | models validity / results | **A result accepts an IN_DOMAIN assessment over conditions its model does not have**. Condition names are checked only at the MCP boundary. Core consumers (experiments, admissibility) trust satisfied=('anything_at_all',). | 61 |
| R-53 | P3 | ★★☆☆☆ | 0.5 | library-only | scientific oracles | **Oracle comparison fails an unpredicted metric and cannot compare multi-point evidence**. A missing metric scores FAIL rather than NOT_RUN. An evidence set at T=300 K and 400 K is NOT_RUN for every stated point. | 65 |
| R-73 | P3 | ★★☆☆☆ | 0.5 | latent | inference field_observation | **FieldObservationOperator binds its region by label and snaps out-of-support probes to an edge**. Any region with a matching id is applied, and the digest excludes region content. A probe outside the mesh silently reads the nearest edge node. | 104 |
| R-23 | P3 | ★★☆☆☆ | 0.4 | library-only | hybrid_uq router predictive | **Grid-route predictions ignore predict and never check the predictive table's values**. A table of twice the model, passed with the correct predict(), gives a SUPPORTED mean of 3.949 against the honest 1.975. | 20 |
| R-25 | P3 | ★★☆☆☆ | 0.3 | library-only | hybrid_uq local_gaussian read-back | **Renaming the parameterization or moving recorded bounds escapes the HUQ-12 bound-distance check**. A forged 'linear_map:' record, or bounds moved with the covariance, lets a 100x narrower covariance read back SUPPORTED, alone and inside a HybridUQResult. | 11 |
| R-27 | P3 | ★★☆☆☆ | 0.3 | library-only | hybrid_uq router read-back / identifiability | **Grid HybridUQResult read-back and prediction trust hand-built records**. Variance divided by 5 to 7, or covariance /100 with widths /10, an identifiability flip and an impossible rebuild record all read back SUPPORTED. A hand-built result around a grid that failed evidence predicts a SUPPORTED mean of 2.47 against 1.97. | 22, 24 |
| R-66 | P3 | ★★☆☆☆ | 0.3 | latent | certification core freeze | **The V2 and V3 freeze verifiers accept a self-asserted assurance record**. A fabricated record with green flags and a copied population sha passes every assurance check. No evidence digest, commit or figure is re-derived, which V1 did. | 91 |
| R-68 | P3 | ★☆☆☆☆ | 0.8 | latent | certification core certificate | **The certificate harness area does not pin the helper modules its suites import**. hybrid_synthetic.py (used by 10 targets) and three other helpers are unpinned. The branch changed hybrid_synthetic.py by 12 lines without moving the certificate. | 93 |
| R-61 | P3 | ★☆☆☆☆ | 0.5 | library-only | composition transfer / provenance | **Transfer records compare unit strings and bind neither source record nor instant order**. 300 K and 26.85 degC make the provenance unconstructible, which fails closed. Stale and final crossings coexist, and sorting puts iteration 10 before 9, although no production path reaches the stale case. | 74, 75 |
| R-70 | P3 | ★☆☆☆☆ | 0.5 | latent | certification core freeze v3 | **The V3 supersession check passes on any exception**. v2_fixtures_still_refused passes even when the rule is removed and an ImportError is raised instead. | 96 |
| R-74 | P3 | ★☆☆☆☆ | 0.5 | library-only | inference parameters | **Parameter identity: the digest and differences() disagree, and unit restatement changes identity**. -0.0 and 0.0 show no difference but have different digests. The same bound stated in mV or V is a different identity in 282 of 2000 cases, and the grid-binding helpers have no caller. | 105 |
| R-47 | P3 | ★☆☆☆☆ | 0.4 | library-only | mcp evidence | **The exported derive_verdict trusts any object's passed/establishes**. A duck-typed check that ValidationReport refuses yields verdict SUPPORTED when passed directly to derive_verdict. | 55 |
| R-63 | P3 | ★☆☆☆☆ | 0.3 | latent | fields transfer | **FieldTransferContract accepts any verdict**. The verdict is never re-derived, so a forged payload or invented fingerprints read COMPATIBLE and may_cross_directly for a 1-to-3 component or kelvin-to-pascal pair. | 77 |

## Improvements (I-xx), in execution order

`gain %` = share of the remaining gap to the goal this closes (sums to 100). Phase: now / next / later / defer.

| Order | ID | Stars | gain % | Effort | Phase | Addresses | Improvement |
|---|---|---|---|---|---|---|---|
| 1 | I-01 | ★★★★★ | 10.5 | M | now | R-01, R-06 | **Router uniqueness contract: no SUPPORTED grid past an unresolved uniqueness caveat, and supplied grids need a uniqueness basis**. Stage 1, now: GLOBAL_UNIQUENESS_NOT_ASSESSED and MULTISTART_INCOMPLETE make step 3 PASSED_OVER, and a GRID_REBUILT record read back with unresolved uniqueness is refused. Stage 2: run any caller MultistartPolicy before accepting a supplied grid, and pass the grid over with GRID_MISSES_A_FOUND_MODE or GRID_UNIQUENESS_NOT_ASSESSED unless it spans the declared bounds. Default to a canonical multistart. This is a V2-symbol behaviour change, so it is additive for V4 on V1. |
| 2 | I-15 | ★★★★☆ | 3 | M | now | R-01, R-03, R-05, R-06, R-07, R-08, R-11, R-13, R-14, R-15, R-16, R-17, R-18, R-20, R-26 | **Adversarial false-confidence conformance suite with pinned reference posteriors**. Turn each verified repro into a case with a dense reference posterior pinned as bytes. Assert invariants: a SUPPORTED 95% interval holds at least 0.90 of the reference mass, the result is equivariant under unit rescaling, and neither zero-information observations nor one-field record edits ever improve the claim. Mark each case xfail and make it strict when its fix lands. Run single-process, and use the suite to select preregistered thresholds. |
| 3 | I-10 | ★★★★☆ | 5 | M | now | R-10, R-40, R-43 | **The credibility report reads the whole result: convergence, declared models and uncertainty**. Serialize ConvergenceState into the report. Any non-converged state yields INSUFFICIENT_EVIDENCE through the rule solver_did_not_converge. A provenance override may add models but never drop a result's declared models. Add an uncertainty field that carries source_kind, have uq/predictive produce it, and make the SRIA budget refuse a NUMERICAL record as aleatoric or model_form. |
| 4 | I-09 | ★★★★☆ | 4.5 | M | now | R-04, R-47 | **Qualify SUPPORTED where agents read it, and give every verification level an issuer**. Put evidence_basis, warning_checks and levels_withheld in the verdict block, key the guidance by (verdict, basis), and add an optional required_evidence_basis. Require a registered reference id and digest for ANALYTICALLY_VERIFIED, as oracle and consensus levels already do. Make the exported derive_verdict accept only ValidationReport, or re-run the level and issuer rules. The response schema is pinned in three places, and the hard benchmark must be re-scored with --workers 4. |
| 5 | I-02 | ★★★★☆ | 5 | M | now | R-07, R-08, R-18 | **Honest multistart: count the search actually performed and classify separated optima by Laplace mass**. Bring max_evaluations and maximum_retractions into the minimum search. Require _minimum_starts(p) converged refits, retrying a failure at the canonical budget. Replace a retracted start with the next Halton point instead of counting it as a full start. A separated converged refit is SECOND_MODE when its Laplace mass ratio exceeds a preregistered floor. Re-check the committed K2 kinetics evidence. |
| 6 | I-04 | ★★★★☆ | 3.5 | M | now | R-03, R-20 | **Information-weighted goodness of fit next to the pooled test, plus a small-dof rule**. Add a leverage-weighted residual statistic with a three-moment null. Run it and the pooled test at alpha/2 each and take the worse result. Apply the variance-ratio refusal regardless of p, and give DOWNGRADED GOODNESS_OF_FIT_UNDERPOWERED at dof 1-2. Both need a new preregistered protocol version. |
| 7 | I-05 | ★★★★☆ | 3.5 | M | now | R-05, R-17 | **Per-mode grid resolution and admissibility cuts as truncation faces (additive checks, V1 digest unmoved)**. Label basins. Every maximum within ln 1e6 of the peak needs enough nodes, a quadratic fit that passes a residual test, and the aliasing bound, or it gets GRID_MODE_UNRESOLVED. Treat an admissible high-mass node next to an inadmissible one as a truncation face: refuse it on supplied grids and refine there on rebuilds. Also re-apply these checks in routed prediction. |
| 8 | I-18 | ★★★☆☆ | 4 | M | now | R-24, R-32, R-33, R-34 | **Sound adequacy comparison: full content binding, within-half duplicates, small-n critical values**. Bind split identity, likelihood sigma and twin into content binding, and make content_bound a derived property, not a caller-settable flag. Collapse replicates within a half. Refuse held-out points that match calibration points after unit normalization and rounding. Use a t critical value with n-1 dof and a minimum n before naming a preferred model. |
| 9 | I-11 | ★★★☆☆ | 4 | M | now | R-09, R-50 | **Make the CORE-014 operating-point binding load-bearing by default and bound to the model's conditions**. Add a keyword-only record_values to assess_validity, which is additive on a V1 symbol. Pass it on the DerivedValidityContext, battery, conduction and MCP report paths. Compare evaluated values, including derived conditions, with a tolerance, and keep evaluated in ModelValidityRecord. Refuse an assessment whose satisfied or violated conditions are not the model's, in ScientificResult itself as well as at MCP. Regenerate SHA-pinned fixtures by writing bytes. |
| 10 | I-19 | ★★★☆☆ | 2.5 | M | now | R-72 | **Enforce declared validation requirements and uncertainty specs, and parse problems strictly**. from_dict refuses unknown or misspelled keys. Validation requirements must name registered check kinds. When a declared requirement or UncertaintySpecification is unmet, the boundary yields INSUFFICIENT_EVIDENCE under a named rule. The DC, CSTR and conduction problems then gain real enforcement. |
| 11 | I-24 | ★★★☆☆ | 2 | S | now | R-56 | **Boundary completeness per edge, not per region id**. Refuse two conditions that share a region id, or key completeness and Dirichlet presence by resolved edge set, so conduction2d cannot silently let the last condition win. Add a production conduction case that declares a duplicate as a regression. |
| 12 | I-03 | ★★★★★ | 7.5 | L | next | R-02, R-35, R-36, R-38 | **Admit posteriors once: route the production calibration study through the V2 evidence gates**. Add admit_grid plus routed study entry points, record the grid decision per repetition, and deprecate the raw-PosteriorGrid consumers. Add a power floor, giving HELD_OUT_UNDERPOWERED instead of PASS, and cluster-aware coverage intervals. Accept heterogeneous declared sigmas, and record coverage repetitions honestly when no calibration ran. Migrate the TCR and battery B1-B3 audits. Run this after the gates above are sound. |
| 13 | I-16 | ★★★★☆ | 3.5 | M | next | R-02, R-09, R-21, R-43, R-58 | **Guard reach ledger with a static bypass check**. Map every guard to the production entry points that reach it, marked REACHED, LIBRARY_ONLY or LATENT with a reason. Fail CI when a REACHED guard loses its path or production calls a known bypass: raw PosteriorGrid consumers, assess_validity without record_values, to_check outside the gate, or route_uncertainty with no multistart plus a rebuild. Audit rows marked FIXED must cite REACHED or LATENT. |
| 14 | I-08 | ★★★★☆ | 5 | L | next | R-13, R-14, R-15, R-16, R-26 | **Probe redesign: matrix curvature, tails in every relevant direction, unit-invariant basis, counted clipped probes (absorbs former I-17)**. Rebuild the whitened curvature matrix from the existing ±2 sd probes and gate on its extreme eigenvalues. Run tail probes along diagonals and extreme eigenvectors. Build directions from the correlation eigenbasis scaled by marginal sds. Clip probes at bounds, compare with r_clip^2, and count what is skipped. Emit POORLY_SCALED_PARAMETERIZATION only from the equilibrated condition number. Preregister the thresholds. |
| 15 | I-13 | ★★★☆☆ | 4 | M | next | R-12, R-23, R-31, R-37 | **Bind routed predictions to the calibration content and conditions**. Add one canonical observation-content digest, and store it with calibrated_conditions on the posterior. Refuse calibration_observations that do not match it. Take conditions from the posterior when the prediction omits them, and test joint support, not per-condition ranges. Spot-check grid predictive tables against predict. Keep nonlinearity per spec, and refuse non-finite values. |
| 16 | I-12 | ★★★☆☆ | 3 | M | next | R-21, R-39 | **CROSS_SOLVER_VALIDATED requires artifact independence and is labelled verification**. Grant the level only with the TrustedConsensusGate strongly_independent line, and route dc_consensus through the gate. Move agreement between solvers of one declared model out of VALIDATION_LEVELS into verification. The added basis is additive. Make a disagreement between non-independent routes block SUPPORTED rather than just warn. |
| 17 | I-22 | ★★★☆☆ | 3.5 | L | next | R-48, R-52, R-57, R-75 | **Delta and absolute semantics for offset-scale quantities at every comparison and boundary**. Convert tolerances, sigmas and spreads as deltas and make delta_degC work. Compare corner values, and compute consensus relative difference, in one canonical absolute unit so route order cannot matter. At the MCP boundary, Quantity.parse accepts only 'magnitude unit' with a real number, and refuses delta units where an absolute temperature is required. |
| 18 | I-06 | ★★★☆☆ | 1.5 | S | next | R-11 | **Diagnose bound domination one side at a time**. Replace the both-sides rule with a per-side profile test. If the profile stays within ln 1e6 of the peak out to a declared bound over more than k local sd, pass over with GRID_POSTERIOR_BOUND_DOMINATED naming the side. |
| 19 | I-07 | ★★☆☆☆ | 2 | S | next | R-19, R-29, R-30 | **Grid evidence binding the supplier cannot steer, with graded mismatch and prior-uniformity tolerance**. Seed spot-checks from a verifier-side nonce. Sample by posterior weight, sized for a stated detection probability, and include face nodes. A mismatch within solver tolerance passes the grid over instead of raising HybridUQError. Judge prior uniformity from the implied moment error, not the raw step deviation. |
| 20 | I-14 | ★★☆☆☆ | 2 | M | next | R-22, R-25, R-27, R-28 | **Close read-back re-derivation gaps and add a record-forgery fuzzer**. Derive the observation count from the content digest. Put bounds and parameterization into the digest, require a finite tail ratio, and re-derive grid moments and identifiability on read. Apply the declared-or-tighter threshold guard on the local route. Add a fuzzer that perturbs carried fields and asserts the claim never improves. Batch everything into one route_diagnostics schema bump. |
| 21 | I-20 | ★★☆☆☆ | 1.5 | S | next | R-45, R-46 | **ValidationCheck record integrity: absolute residuals and an explicit schema bump for CORE-013**. GUARD 21 compares /residual/ with a positive tolerance. Bump validation_report to /2 for the new status precedence and the evaluated and source_kind bindings, read /1 records under the old rules, and have SRIA distinguish not-applicable from never-run. |
| 22 | I-21 | ★★★☆☆ | 2.5 | M | later | R-41, R-42, R-44 | **Selection ranks only established, fully checked candidates**. best() requires a check for every declared constraint, bound to the result's numbers. from_dict refuses a payload with the constraints key missing. Objective checks are keyed by metric, and candidates with validation NOT_RUN are excluded. Apply the same CORE-015 rule to the design Pareto and elite archives that multirotor uses. |
| 23 | I-28 | ★★★☆☆ | 2 | M | later | R-59, R-71 | **Bind forward-model admission and predictive conditioning to their sources**. The analytic admission route requires the source result's convergence and validation. AdmittedForwardTable takes typed admission records and compares data in canonical units. Admission conditioning caps its budget, and marks the returned grid with a new dataset identity and the conditioned mass. |
| 24 | I-27 | ★★☆☆☆ | 2.2 | M | later | R-58, R-60, R-61, R-64 | **Cross-domain transfers carry uncertainty and validity, with physically bound checks**. Electrothermal crossings carry uncertainty, validity and validation state. UncertaintyTransfer checks that intervals contain the value and keeps its attribution. The conversion budget becomes relative with no 1.0 floor. The energy guard matches every dimension derived from energy. Transfer records bind the source record id and a numeric instant order, and compare values in canonical units. |
| 25 | I-31 | ★★☆☆☆ | 1.5 | S | later | R-51, R-54 | **Validity condition declarations that cannot invert, and a correct missing-declaration diagnosis**. Refuse a bare string for allowed sets and ratio bounds with a > b at construction. CrossLimitCondition reports a missing operand declaration as a user-repairable gap, not UNREADABLE_SHAPE, and repair guidance follows. |
| 26 | I-26 | ★★☆☆☆ | 0.8 | S | later | R-49, R-53 | **Oracle comparison checks where the prediction was computed and handles multi-point evidence**. Require the prediction's operating-point conditions to match each evidence point's full declared conditions. Score an unpredicted metric NOT_RUN, and compare multi-point evidence point by point. |
| 27 | I-25 | ★★☆☆☆ | 1 | M | later | R-55, R-63, R-73 | **Field records, transfer contracts and observation operators re-derive what they claim**. Re-derive FieldSummary from the bytes and unit, and apply envelopes to the vector magnitude. FieldTransferContract re-derives its verdict from the fingerprints. FieldObservationOperator binds region content into its digest and refuses probes outside the support. |
| 28 | I-30 | ★★★★☆ | 3 | XL | later | R-66, R-67, R-68 | **Re-derived assurance evidence: batch guards in the mutation population, isolated runners, pinned helpers**. Bring the batch and fix guards into a V4 mutation population, drop the stale B1j and B1k kills, and run each mutant in a worktree on D:. A mutant counts as KILLED only when the named target test fails. Pin the helper modules (hybrid_synthetic.py and others) in the harness area. Make the V4 verifier re-derive the evidence digests, measured commit and figures, as V1 did. |
| 29 | I-29 | ★★★★★ | 5 | L | later | R-65, R-69, R-70 | **Core Freeze V4 control plane with a real additive-only comparator**. Base V4 on a commit that descends from V3, and change the certificate-child self-check list so recertification is possible. Extend the snapshot to method signatures and enum member order. Compare against the stored V1 manifest bytes rather than the live API. The supersession check must assert the specific refusal rule, not any exception. |
| 30 | I-23 | ★☆☆☆☆ | 1 | S | defer | R-62, R-74 | **Canonical identity for meshes and parameters**. Fingerprint geometry from canonical SI values with a relative tolerance. Normalize parameter bounds to canonical units and -0.0 to 0.0, so the digest and differences() agree. |

## Progress

Batches follow the per-batch protocol of `CORE_SCIENTIFIC_AUDIT_2026-09-16.md`: preregister the rules and
thresholds, commit each audited reproduction as a strict xfail and watch it fail, implement, verify against
the targeted files and the FAST tier, mutate every new guard, and record what moved. Each batch's rules are
in `benchmarks/core_v4_false_confidence/BATCH<k>_THRESHOLD_PROTOCOL.json` and its guard mutations in
`BATCH<k>_MUTATIONS.log`.

The FAST tier (`python -m pytest -m "not expensive" -q -n 4 --dist loadfile`) has 18 failures BY DESIGN
throughout, all in the Core Freeze V4 list of `docs/CORE_FREEZE_POLICY.md`
(`test_core_api_snapshot`, `test_core_freeze_manifest`, `test_core_freeze_policy`, `test_core_freeze_v2_manifest`,
`test_core_freeze_v3_manifest`, `test_core_v2_api_snapshot`, `test_core_v2_compatibility`, `test_core_certificate`).
Each batch below reports that count so a 19th failure would be visible.

### Batch 6 — I-01, I-15

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-01 | **DONE** | `5a08eef` (preregistration + xfails), this commit | the canonical multistart's own resolution; a supplied grid whose local route raises has no basis; a grid routed without a calibration can no longer be SUPPORTED |
| I-15 | **PARTIAL** | `5a08eef`, this commit | the suite exists with 17 cases over 15 problems; only the R-01 and R-06 cases are live, the other 15 are `xfail(strict=True)` until their own improvement lands, which is I-15's design |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-01 | **FIXED** | `route_uncertainty` does not rebuild a grid from a local posterior whose uniqueness word is `NOT_ASSESSED`, `MULTISTART_INCOMPLETE` or `MULTISTART_BELOW_MINIMUM_SEARCH`: the rebuild is passed over under `GLOBAL_UNIQUENESS_NOT_ASSESSED` or `MULTISTART_INCOMPLETE`, the same way and in the same place a misfit already passes it over. `HybridUQResult._require_one_truth` refuses such a record on read, so the router's write rule is its read rule. And where a grid route is in play with no caller multistart, the router now runs the canonical `MultistartPolicy()` itself rather than recording that nobody looked: the audited case returns the honest bimodal grid (sd 1.0220 on theta1, against the reference's 1.0220) where it returned sd 0.02428 SUPPORTED. |
| R-06 | **FIXED** | A supplied grid is accepted only with a uniqueness basis: either it spans the declared bounds of every axis, or a search at or above the minimum ran and every separated mode it found lies inside its box. Otherwise it is passed over `GRID_MISSES_A_FOUND_MODE` or `GRID_UNIQUENESS_NOT_ASSESSED`. The basis is the LAST check of the supplied-grid route and the bounds-spanning half costs nothing, so the search is only paid for on a grid that would otherwise be accepted. The basis the accepted grid stood on is recorded in the `considered` log's `detail`. |

**Compatibility.** Additive on V2: two `RouteReason` members appended after the last existing one
(`GRID_MISSES_A_FOUND_MODE`, `GRID_UNIQUENESS_NOT_ASSESSED`), and one keyword-only argument with a default
(`route_uncertainty(canonical_uniqueness_search=True)`). No field, member or default is removed, renamed,
reordered or changed. No schema is bumped and no serialized field is added. The V1 surface is untouched. The
V1/V2 API snapshots move by the two added members and are regenerated in the V4 round (I-29), not here.

The V2 behaviour change I-01 asks for is real and intended: with a grid route in play and `multistart=None`,
`route_uncertainty` now runs the canonical search, so a call that used to return a wrong SUPPORTED grid may
now return the honest grid, a REFUSED, or a pass-over. With neither a grid nor a rebuild policy,
`multistart=None` keeps its exact V2 meaning and no search is run.

**Blast radius, and what was done about it.** A supplied grid routed with observations and a forward model but
no calibration has no declared bounds and no search, so it can no longer be SUPPORTED. Five test call sites
and one evidence generator did that:

* `tests/hybrid_uq/test_hybrid_uq_trust_boundary.py::_grid_result`,
  `tests/hybrid_uq/test_audit_hybrid_records.py::grid`,
  `tests/hybrid_uq/test_hybrid_uq_router.py::test_routed_predictive_uses_the_route_that_was_chosen` and
  `tests/hybrid_uq/test_hybrid_uq_tcr.py::test_the_local_route_agrees_with_the_resolved_grid` were each given
  the calibration they already had in hand, with a comment in place saying why. Not one assertion was
  weakened or removed: these are record-integrity and agreement tests, and what they do to the record they
  get is unchanged.
* `benchmarks/core_v2_hybrid_uq/audit/tcr.py` needed the same change and was re-run. Every claim
  `TCR.json` makes reproduces: both designs still `GRID_AS_SUPPLIED`, the same means, standard deviations,
  identifiability statuses and agreement verdicts. The only change to the record is an added `detail` on the
  WIDE 41-node grid's `USED` entry naming its uniqueness basis, plus float-level drift from this environment's
  optimizer (relative 1e-8, and a forward-evaluation count of 192 against the recorded 190). So no committed
  claim moved and `TCR.json`'s bytes are left pinned; re-pinning belongs to the V4 round, where I-30 re-derives
  the assurance digests and the whole evidence set is re-run in one environment. `FAILURE_CASES.json` and
  `PERFORMANCE.json` were re-run too: every case still meets its declared expectation, and their only
  differences are the same environment drift, so their bytes are untouched.
  `tests/hybrid_uq/test_hybrid_uq_committed_evidence.py` gained the guard that both TCR grids are still
  `GRID_AS_SUPPLIED` under the new rule and that both stand on `MULTISTART_NO_SECOND_MODE`.

**Guard mutations.** `benchmarks/core_v4_false_confidence/BATCH6_MUTATIONS.log`, from
`benchmarks/core_v4_false_confidence/audit/batch6_mutations.py`. Nine of ten mutations KILLED. The tenth,
B6b, SURVIVED **on purpose and is recorded as such**: I-01 gives R-01 two independent rules — resolve
uniqueness, or withhold the grid — so removing either one alone leaves the conformance invariant standing.
B6a and B6d kill each rule separately through the contract tests, and B6b2 removes both at once, which is
exactly the audited behaviour, and kills the conformance mass floor. Without that compound mutation the mass
floor would have been reported as load-bearing on no evidence.

This batch also fixes **R-67** for its own runners, in
`benchmarks/core_v4_false_confidence/audit/isolated_mutations.py`, which every later batch uses: each mutation
is applied in a fresh copy of `src`, `tests`, `pyproject.toml` and the JSON evidence, never in the checkout;
KILLED requires the named test to be collectable in the mutated copy AND pytest to exit 1 AND its summary to
report a `failed` and no `error`, so a collection or import error the mutation caused is reported
`COLLECTION_BROKEN` or `NOT_A_TEST_FAILURE` rather than counted as a kill; each mutation declares whether it
must be killed or must survive; and an unmutated control runs last. (R-67 is not yet closed: the batch guards
still sit outside the pinned population, which is I-30's.) The 12 pinned mutations that target the files this
batch changed were re-run under the same runner and all 12 are still KILLED:
`benchmarks/core_v4_false_confidence/BATCH6_PINNED_MUTATIONS.log`.

**Verification.** `tests/hybrid_uq/` 275 passed, 15 xfailed. FAST tier 6436 passed, 15 xfailed, 18 failed (the
by-design 18, unchanged). `tests/test_mutation_harness.py` 6 passed, every pinned anchor still matching exactly
once; `tests/mutation_guards.py` was not touched.

**Open decisions.** None in this batch.

### The expensive tier's baseline in this environment

Recorded once here so every batch below can tell an environmental failure from one of its own. At batch 7's
preregistration commit `5b8d036`, before any of that batch's code, the expensive tier
(`python -m pytest -m expensive -q -n 4 --dist loadfile`) reports **18 failed, 527 passed, 14 errors**. It was
run in a `git worktree` at that commit and diffed against the same run after batch 7's implementation: the two
failure lists are identical. The causes:

* 12 failures and all 14 errors in `tests/test_heterogeneous_ngspice.py`, plus
  `tests/test_cross_solver_consensus.py::test_the_dc_routes_earn_the_level_on_a_real_circuit` and
  `tests/mcp/test_problem.py::test_the_second_route_actually_runs_and_the_level_is_withheld`: this environment
  invokes the ngspice provider as `('wsl.exe', '-e', 'ngspice')` and cannot launch it (`NgspiceUnavailable`);
* 2 in `tests/domains/kinetics/test_cstr_domain.py`, where the benign regime's `validation_status` is NOT_RUN
  under this environment's solver numerics;
* 2 gate rebuilds under `benchmarks/empirical_validation` and `benchmarks/model_measurement_validation`, the
  two the per-batch protocol restores with `git checkout --`.

### Batch 7 — I-10

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-10 | **DONE** | `5b8d036` (preregistration + 25 strict xfails), this commit | the battery MCP tool assembles its report without a `ScientificResult`, so the convergence rule does not reach it; a hand-assembled payload with the new field deleted relies on the NOT_RUN check; UNSPECIFIED source kinds are named rather than refused |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-10 | **FIXED** | `CredibilityEvidenceReport` carries the result's `ConvergenceState` in a new trailing field, `from_result` sets it, and `derive_verdict` takes it as a keyword and returns INSUFFICIENT_EVIDENCE for any state that is neither CONVERGED nor NOT_APPLICABLE — the same verdict and the same reasoning as the `coupling` rule it sits beside: a solver that stopped early produced an iterate, and the fix is to finish it. The state is serialized, and read back, only when there is one; the downgrade does not depend on that, because `from_result` also appends a NOT_RUN check `solver_did_not_converge`, so it survives a reader written before the field and a payload with the key deleted. All four unfinished states now report INSUFFICIENT_EVIDENCE where they reported SUPPORTED. |
| R-40 | **FIXED** | `from_result` adds the result's own declared models, and the ones named in `validity_not_assessed`, to `contributing_models` whatever provenance is passed. The override — the documented path for coupled runs, and what production passes — can still widen the inventory and can no longer narrow it. The audited case now reports INSUFFICIENT_EVIDENCE with the declared-but-unassessed model named, with the override as with the result's own provenance. |
| R-43 | **PARTIAL** | The report now carries per-value `uncertainty` including `source_kind`, serialized when non-empty, with the declared sources in `verdict_qualifiers.uncertainty_sources` for a reader who never opens the field. `posterior_predictive_uq` declares PARAMETER on its epistemic interval and COMBINED on its total, which is what their notes already said in prose. `UncertaintyDeclaration` and the budget's `ChannelEntry` refuse a record whose declared source names another channel, under one map stated once in `CHANNEL_ACCEPTS_SOURCE`; COMBINED is accepted by no channel, because root-sum-squaring a mixture with one of its own parts counts it twice. **PARTIAL and not FIXED**: every domain solver still emits UNSPECIFIED, so the map has something true to check only for the two V1 intervals; UNSPECIFIED is named through a new `unattributed_channels` rather than refused, because refusing it would fall on every existing declaration and no wrong one; and nothing yet carries a V1 interval into an `UncertaintyDeclaration`, so the producer and the budget are still two unconnected halves. That connection is I-16's reach ledger. |

**Compatibility.** Additive: two trailing dataclass fields with defaults on `CredibilityEvidenceReport`
(`convergence`, `uncertainty`), one keyword-only argument with a default on `derive_verdict` (`convergence`),
one derived property on each of `CredibilityEvidenceReport` (`uncertainty_sources`) and
`UncertaintyDeclaration` (`unattributed_channels`), and one new module-level name in each of
`mcp.evidence` (`SOLVER_CONVERGENCE_CHECK`) and `sria.uncertainty` (`CHANNEL_ACCEPTS_SOURCE`,
`require_source_fits_channel`). No field, member or default is removed, renamed, reordered or changed, and no
schema is bumped: `mcp_evidence_package` gains two top-level keys and one qualifier, each written only when it
carries information, so a record written before this reads back byte-identically. `posterior_predictive_uq`
is V1-frozen and its signature and return type are untouched; one already-existing field of a record it
returns moves off its default, and `Uncertainty` serializes `source_kind` only when declared.

The verdict WORD is unchanged. Non-convergence uses the existing INSUFFICIENT_EVIDENCE.

**Production effect.** The MCP electrothermal report carries `convergence: not_applicable` and stays
SUPPORTED; the battery report's is `None`, because the battery march returns steps rather than a
`ScientificResult` and there is no state to read — its own fixed point is gated by `CouplingEvidence`, which
`derive_verdict` already reads. No production verdict moved.

**Guard mutations.** `benchmarks/core_v4_false_confidence/BATCH7_MUTATIONS.log`, from
`audit/batch7_mutations.py`, through the isolated runner: **12 of 12 KILLED**, unmutated control green. B7c is
a compound mutation that removes the verdict rule and the check together, which is the audited behaviour
exactly; B7a and B7b kill each half separately. The 10 pinned mutations that target the four files this batch
changed were re-run under the same runner and all 10 are still KILLED
(`BATCH7_PINNED_MUTATIONS.log`).

**Verification.** FAST tier 6463 passed, 15 xfailed, 18 failed (the by-design 18, unchanged; 27 more passing
than batch 6). Expensive tier identical to the recorded baseline above. `tests/test_mutation_harness.py` 6
passed, every anchor intact; `tests/mutation_guards.py` untouched. No committed evidence claim moved: the only
evidence generator whose output changes is `tcr.py`, and that is batch 6's already-recorded `detail`.

**Open decisions.** None in this batch.

### Batch 8 — I-09, part A of two

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-09 | **PARTIAL** | `03da331` (preregistration + 15 strict xfails), this commit | the issuer half — a registered reference id and digest for ANALYTICALLY_VERIFIED — is batch 9; DIMENSIONALLY_VALID and NUMERICALLY_CONVERGED still need no issuer; the bundle manifest is still unkeyed |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-04 | **PARTIAL** | The adoption half is closed. The verdict block an agent reads first carries `evidence_basis`, `evidence_basis_means`, `attained_levels`, `levels_withheld` and `warning_checks`, and its `means`, `does_not_mean` and `action` come from a table keyed by **(verdict, evidence basis)**: a SUPPORTED report on verification alone now says that every level attained says the declared model was solved correctly and that the report contains no comparison of the model with the world — where it used to say "nothing in this report argues against relying on the result". A non-deciding `verification_only` rule fires in `other_findings`, so the reader who scans rules sees it too. `describe_capabilities` lists all three readings per verdict under `verdicts[].by_evidence_basis`. A caller can demand a kind of evidence with `required_evidence_basis`, which is `required_levels` for the kind rather than the level, reported under the rule `required_evidence_basis_not_attained`. `_withhold_level` records the level it strips as a structured `level-withheld:` line, so `levels_withheld` names it instead of leaving it inside a prose `detail`. And the qualifiers block, with `evidence_basis` in it, is now REQUIRED on read — deleting the block, or just that one key, was a way past the comparison. **PARTIAL**: the issuer half is batch 9, and the two residuals above stay open. |
| R-47 | **FIXED** | `derive_verdict` builds its attained set through the new `attained_levels_of`, which re-applies the core's own field-level rules — GUARD 2 (`level_is_earned`), GUARD 21 (`outcome_is_earned`) and VAL-01 (`_issuer_gap`) — over each check's `outcome`, `establishes`, `residual`, `tolerance` and `evidence`, instead of reading `check.passed` and `check.establishes`. Fields rather than `isinstance`, for `level_is_earned`'s own stated reason: a method can be overridden and a property shadowed. A check missing a field the rule reads is refused rather than read past, because "this object has no residual" must not resolve to "nothing argues against this result". The duck-typed object claiming EXPERIMENTALLY_VALIDATED is now refused, as `ValidationReport` already refused it. Every genuine `ValidationCheck` gives the same answer as before, which the FAST tier confirms across 6479 tests. |

**The verdict WORD is unchanged and no benchmark was re-scored.** What changed is the sentence beside it and
the keys around it.

**Compatibility.** Additive: one trailing dataclass field with a default (`required_evidence_basis`), three
derived properties (`evidence_basis`, `missing_evidence_basis`, `levels_withheld`), one keyword-only argument
with a default on `derive_verdict`, two new exported functions (`attained_levels_of`, `evidence_basis_of`),
two new module-level constants (`EVIDENCE_BASIS_ORDER`, `WITHHELD_LEVEL_EVIDENCE_PREFIX`). The MCP response
schema gains five keys in the verdict block and one in each `describe_capabilities` verdict entry; every
existing key keeps its name and place. `docs/mcp/README.md` is updated with the new section. One correction to
the preregistered compatibility note is recorded in the protocol's amendment log: a pre-CORE-008 payload with
no `verdict_qualifiers` block at all is now refused, which the note wrongly said would be unaffected.

**Two implementation corrections**, both in the protocol's amendment log rather than glossed:

1. The level rules are scoped to PASS **and** WARNING, while the core's `attained_levels` counts only
   PASSING checks. A WARNING check is therefore held to the rules and still attains nothing. The first
   implementation admitted a WARNING check's level, and the existing
   `tests/mcp/test_evidence.py::test_a_level_established_by_a_check_that_did_not_pass_does_not_count`
   caught it — which is what that test is for.
2. Pinned mutations `G31x` and `G31y` anchor the verdict-requirement statements and the qualifier comparison
   as contiguous code. `tests/mutation_guards.py` may not be edited before the I-30 round, so the new
   qualifiers-present refusal was moved above the verdict's own rather than between it and the comparison it
   guards. The `if stated is not None` guard still does real work: a present key with a `null` value, which
   the `in payload` check does not cover.

**Guard mutations.** `BATCH8_MUTATIONS.log`, from `audit/batch8_mutations.py`: **14 of 14 KILLED**, control
green. B8j..B8l were first written as string renames and were correctly refused by the harness's own
`MUTATION CHANGED NO CODE` check — `_code_digest` ignores string tokens on purpose — and were rewritten to
mutate the code behind each key. The 13 pinned mutations that target the three files this batch changed were
re-run isolated and all 13 are still KILLED (`BATCH8_PINNED_MUTATIONS.log`).

**Verification.** FAST tier 6479 passed, 15 xfailed, 18 failed (the by-design 18, unchanged).
`tests/test_mutation_harness.py` 6 passed, every anchor intact; `tests/mutation_guards.py` untouched. Two
existing test fixtures were updated, both because a stub of a report must carry what the transport reads off
one: `tests/mcp/test_server.py`'s `SimpleNamespace` gained `evidence_basis`, `levels_withheld`,
`missing_evidence_basis` and `convergence`, and its `attained_levels` became a real `ValidationLevel` member.
No assertion was weakened.

**Open decisions.** None in this batch.

### Batch 9 — I-09, part B of two

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-09 | **DONE** | `03da331`, `b71d878` (part A), `d66a7fe` (preregistration + 14 strict xfails), this commit | DIMENSIONALLY_VALID and NUMERICALLY_CONVERGED still need no issuer; the bundle manifest is still unkeyed; the rule has the oracle rule's strength and no more; `thresholds.award` is not load-bearing in lumped |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-04 | **FIXED** | The issuer half closes here. A check that PASSes or WARNs and declares ANALYTICALLY_VERIFIED must now name **exactly one registered analytic reference**, as `"<id>: <expression>"` with the expression equal to the registered one byte for byte, and carry **exactly one threshold record** equal to the awarding gate's declared identity and fingerprint — or, for the level's other legitimate issuer, a pinned ANALYTIC_REFERENCE oracle's record, which the existing `_oracle_issuer_gap` already verifies. `engcore.domains` gains `SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS`, pinning the three closed forms this layer stands behind with their expressions and digests, recomputed at import so the table and the constants cannot drift. `thermal_models.lumped` gains a declared gate, `thermal_models.lumped.analytic_reference@0.1.0`, so the tolerance its analytic check is judged against has an owner; `SOLVER_ROUNDING_ULPS` keeps its name and value and is read from it. `ValidationCheck(PASS, establishes=ANALYTICALLY_VERIFIED, evidence=("trust me",))` is refused, as the same construction claiming BENCHMARK_VALIDATED already was. The two remaining parts of R-04 — an issuer for DIMENSIONALLY_VALID and NUMERICALLY_CONVERGED, and a keyed bundle manifest — are **OPEN**, recorded as such, and neither is in I-09's text. |

**The production verdict did not move, and the hard benchmark was re-scored to check.**
`python benchmarks/hard/score_hard.py --src $PWD/src --cases benchmarks/hard/cases_hard --split dev
--workers 4`, on the dev partition the tracked `results_hard.json` holds. The sealed hold-out was not
opened, no case file was read or written by hand, and no truth or adjudication file was touched. Every
number is identical: 1400 scored, 243 sound, 1157 unsound, exact verdict match 1362/1400 (97.3%), catch rate
1157/1157 (100.0%), false accept 0/1157, false reject 0/243. The only difference in the regenerated file is
its `generated` timestamp, so no committed claim moved and the file's bytes are left as the 2026-09-09 run
wrote them. Both production producers — the lumped analytic check the one SUPPORTED MCP report rests on, and
the conduction1d refinement gate — keep the level, through their issuers.

**Three things the implementation had to change from the preregistration**, all in the protocol's amendment
log rather than glossed:

1. **The rule reads the line the producers already wrote.** The preregistration asked for three new evidence
   lines. `src/engcore/domains/thermal/` is SHA-256 pinned by the frozen thermal_t1/t2/t3 experiments, whose
   claim is that their measured bias is a property of *that* solver, and
   `test_frozen_thermal_solver_digests_match` caught the edit immediately. That pin is evidence this work has
   no authority to spend. The stronger reason is the second one: **a digest of a public value carries no more
   authority than the value.** The oracle rule needs a content digest because an oracle's evidence is data
   the caller does not hold; an analytic reference's expression is in the source. So the two carried lines
   were ceremony, the expression is compared in full instead, and the authority is where it always was — the
   registry and the declared threshold set. **What that costs:** the rule has exactly the strength of the
   oracle rule the audit named as the model, and no more. Every line it requires is reproducible from public
   data, so it refuses a careless or invented claim and not a determined forgery. The core already states
   that residual in `_issuer_gap` and it is unchanged. The *consensus* rule is stronger, because its binding
   lines carry a digest over the run's own numbers — data nobody has who did not run it. An analytic
   reference has no equivalent.
2. **Three checks became one, because two were dead code.** The first implementation compared the gate name,
   the version and the values fingerprint separately, and the mutation run showed two of the three could be
   removed with every test still green: all three compared against the gate the *registry* names rather than
   the one the record names, so each was subsumed by the fingerprint. One comparison now, of the whole
   `<gate>@<version>#<fingerprint>` line. A survivor that buys the removal of dead code from a guard is a
   survivor doing its job.
3. **`thresholds.award(...)` is not load-bearing in the lumped check, and B9h is recorded as an expected
   survivor.** Mutating it to award the level beside its gate leaves the level in place, because the check
   still writes a valid threshold record and the issuer gap is what enforces it. `LumpedThermalSolver` takes
   no caller-facing `thresholds=` argument, so there is no override for `award` to withhold from. It is kept
   because it is the one place such an argument would be judged and because every other gate reads this way,
   but the log says SURVIVED rather than counting it.

**Blast radius, and what was done about it.** 14 hand-built ANALYTICALLY_VERIFIED checks in 9 test files lost
their level. Nothing was weakened:

* three sites in `tests/mcp/` moved to `DIMENSIONALLY_VALID`, which is the same evidence *basis* —
  verification — and needs no issuer. Their subject is a verdict, a record or a basis, not that level;
* the rest build the check through a new support module, `tests/issued_levels.py`, which resolves the
  issuer's record from the two registries so a fixture cannot drift from the rule it satisfies;
* `tests/test_core_guards.py::_guarded_level` moved from ANALYTICALLY_VERIFIED to DIMENSIONALLY_VALID. That
  helper exists to name "a level sentence-evidence can still legitimately carry" and has now moved twice for
  exactly that reason; its docstring records both moves and what would move it again;
* `tests/test_audit_consensus_level_issuers.py::test_weaker_levels_are_unchanged` asserted that this level
  needed no issuer. That statement is what this batch changed, so the test now names the two levels that
  still need none and points at the new batch-9 suite for the one that does not;
* `tests/test_trust_boundary_threshold_authority.py`'s `CANONICAL` list gained the new gate, which is what
  that file's test G exists to force.

**Guard mutations.** `BATCH9_MUTATIONS.log`: **9 of 10 KILLED**, the tenth an expected survivor documented
above, control green. The 9 pinned mutations on the three files this batch changed were re-run isolated and
all 9 are still KILLED (`BATCH9_PINNED_MUTATIONS.log`).

**Verification.** FAST tier 6506 passed, 15 xfailed, 18 failed (the by-design 18, unchanged). Expensive tier
identical to the recorded baseline. `tests/test_mutation_harness.py` 6 passed, every anchor intact;
`tests/mutation_guards.py` untouched. Nothing under `src/engcore/domains/thermal/` was edited.

**Open decisions.** None in this batch.

### Batch 10 — I-02

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-02 | **DONE** | `8f094f04` (preregistration + 11 strict xfails), this commit | the Laplace mass ratio is a Laplace approximation, used only against a floor 50x inside the value that would matter; a pre-batch record carrying no `laplace_mass_ratio` is exempt from the mass rule (it is gated on the policy record, which postdates such bytes) but not from the converged-count rule, so a pre-batch record whose refits failed no longer re-derives its own uniqueness word and is refused on read; replacement still cannot reach a mode the Halton sequence does not land near (that residual is I-01's); a search under a small budget costs up to `starts` extra calibrations at the canonical one |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-08 | **FIXED** | `_search_shortfalls` now compares the recorded `multistart_max_evaluations` and `multistart_maximum_retractions` with the canonical policy's, so a budget or a replacement allowance below canonical is a recorded shortfall like a narrower span — the start that travels to a distant mode is the slow one, so a small budget removes exactly that refit. `_multistart_verdict`'s completeness rule became `converged < _minimum_starts(p)`, replacing `converged * 2 < len(entries)` under which half the starts could fail silently. And a refit that does not converge under a budget below canonical is retried exactly once at the canonical budget, so the audited case reaches the true answer (REFUSED `SECOND_MODE_FOUND`) rather than the honest withholding (DOWNGRADED). The audited record — `max_evaluations=12` giving SUPPORTED `MULTISTART_NO_SECOND_MODE` with `recorded policy shortfalls: []` and sd 1.0 against a reference sd of 9.72 — now refuses. |
| R-18 | **FIXED** | A start the forward model refuses is REPLACED by the next unused point of the same Halton sequence, from one counter shared by every start so no two take the same one, instead of being halved toward the calibrated estimate. Each entry records `replacements` and no longer records `retractions`. The audited islands case (`proposed [-12.0] used [-0.75] retractions 4`, five of six starts pulled into the estimate's own basin, SUPPORTED `MULTISTART_NO_SECOND_MODE` over a posterior whose 95% interval holds 0.4748) now reaches the far island and refuses `SECOND_MODE_FOUND`. |
| R-07 | **FIXED** | A converged refit beyond the separation radius that is not a `BETTER_OPTIMUM` is classified by its Laplace mass ratio `exp(-(chi - chi_min) / 2) * sqrt(det(Sigma) / det(Sigma_min))` against `MULTISTART_MASS_FLOOR = 1e-3`: above it `SECOND_MODE`, below it `WORSE_LOCAL_OPTIMUM`. The ratio is recorded per entry and `_require_reasons_follow_measurements` holds the word to it, so the classification cannot be carried without the number it follows from. A mode whose mass cannot be bounded — no curvature at the refit, an information matrix that is not positive definite, or a ratio that overflows a float — records `laplace_mass_unavailable` and counts as a second mode. The audited case (six starts at chi-square 10 above the estimate and m2 = 2.5e5, all `WORSE_LOCAL_OPTIMUM`, SUPPORTED, while 0.792 of the posterior sits in that basin) now refuses. `BETTER_OPTIMUM` is unchanged and its mass is never consulted. |

**The conformance suite.** I-15's R-07, R-08 and R-18 cases came off `xfail`: three more of the seventeen
are live (five in total, with R-01 and R-06).

**Compatibility.** Additive. No V1 symbol is touched. On V2: `MultistartPolicy` gains no field — the
`maximum_retractions` name and its default of 12 are kept and it is now the REPLACEMENT budget, which is the
behaviour change I-02 asks for — and one private method (`_point`) that `start_points` is now written in
terms of. `RouteDiagnostics` gains no field: the multistart entries are free-form mappings inside an existing
one, and there each separated entry gains `laplace_mass_ratio` (or `laplace_mass_unavailable`) and
`replacements` takes the place of `retractions`. `route_diagnostics/2` is NOT bumped, because the keys change
inside an existing field; a record written before this batch is refused on read where the converged-count
rule now bites, which the residual above states. `local_gaussian_posterior`'s signature is unchanged.

**One correction to the preregistered rules**, recorded in the protocol's `amendment_log` and repeated here:
making the completeness rule count converged refits meant a policy below the minimum search and a refit that
failed were both `incomplete`, and the more specific word (`MULTISTART_BELOW_MINIMUM_SEARCH`) was being
masked by the more general one. The uniqueness expression now names `below` before `incomplete`. Both add
`MULTISTART_INCOMPLETE` to the downgrades either way, so no claim moves; only the word a record states does,
and it states the more specific fact.

**Existing tests edited (no assertion weakened).**

* `tests/hybrid_uq/test_hybrid_uq_local_route.py`'s retraction test is now
  `test_an_inadmissible_multistart_start_is_replaced_by_another_halton_point_and_recorded`: it reads
  `replacements` instead of `retractions` and gained two assertions (nothing retracts, and a replaced start
  is a different point from the one the model refused);
* nothing else. `test_audit_hybrid_local_route.py::test_huq01_the_one_start_mirror_mode_is_no_longer_supported_and_says_why`
  keeps its expected word because of the ordering correction above, which is why that correction was made
  rather than the test edited.

**Committed evidence.** No claim in the cheap records moves: `TCR.json` records no multistart,
`FAILURE_CASES.json` records `"multistart": null`, and `PERFORMANCE.json`'s five V2 claims turn on the
goodness of fit (p = 2, 5, 10 REFUSED) and on the 6-start default being below `max(6, 2p + 2)` (p = 20, 41
DOWNGRADED with `MULTISTART_INCOMPLETE`) — both untouched by this batch, and all ten committed-evidence
guards pass unchanged. So those records' bytes stay as their runs wrote them rather than absorbing this
container's wall-time drift. The two SUPERSEDED markers gained an `R-08 / I-02`, an `R-18 / I-02` and an
`R-07 / I-02` entry each, in the JSON and the companion Markdown, and `KINETICS_K2`'s `now_would_say.MULTI_v2`
moved from SUPPORTED to DOWNGRADED (`MULTISTART_INCOMPLETE`): its policy is 6 starts at p = 2 with
`max_evaluations=400` against a canonical 2000, and 2 of its 6 committed refits failed, so 4 converged where
6 are required — either shortfall alone caps it. Its one separated refit sits at chi-square 2699.72 against
5.4446, a height ratio of `exp(-1347.1)`, so no covariance could lift it above the floor and
`WORSE_LOCAL_OPTIMUM` is projected unchanged. `BATTERY_T41`'s thirty refits are all `SAME_OPTIMUM` and all 6
of 6 converged in every model, so its table does not move; what its marker now records is that P1..P5
retracted between one and three starts each, so the committed "no second mode" rests on a narrower search
than the record implies. Neither multistart was re-run, as the protocol requires. The two generators
(`audit/battery.py`, `audit/kinetics.py`) now project `replacements` and `laplace_mass_ratio` instead of
`retractions`, so a future regeneration records the keys that exist.

**Guard mutations.** `BATCH10_MUTATIONS.log`: **15 of 15 KILLED**, control green. Three of the fifteen were
rewritten after a first run, and what they bought is the point of running them:

* the entry-key mutation was refused as MUTATION CHANGED NO CODE, because it renamed a string literal and
  `_code_digest` ignores STRING tokens; it now mutates the code that chooses the key;
* zeroing the shared Halton counter SURVIVED against the replacement test, so the R-18 basin test was
  strengthened from "does not claim a single mode" to "refuses `SECOND_MODE_FOUND`" — with the counter frozen,
  five of six starts find no admissible point at all and the far island is never visited;
* dropping the VOLUME term from the mass ratio SURVIVED, because R-07's own basin clears the floor on peak
  height alone (`exp(-10 / 2) = 6.7e-3`). The rule's volume half was therefore unmeasured, so the batch
  gained `test_a_separated_mode_is_weighed_by_its_volume_and_not_only_its_height`: the same basin made a tenth
  as wide, where the height still clears the floor and the mass ratio 6.7e-4 does not. Two further tests were
  added for the branch the audited cases do not reach (a mass that cannot be bounded, and the read-back
  taking a recorded reason in place of the number for `SECOND_MODE` and for nothing else).

The 10 pinned mutations on `local_gaussian.py` were re-run isolated and all 10 are still KILLED
(`BATCH10_PINNED_MUTATIONS.log`).

**Verification.** FAST tier 6525 passed, 12 xfailed, 18 failed (the by-design 18, unchanged; the three
xfails that became passes are I-15's R-07, R-08 and R-18 cases). Expensive tier 528 passed, 18 failed, 14
errors — the recorded baseline's failure and error lists exactly, with the one extra pass being batch 9's
added expensive test. `tests/test_mutation_harness.py` 6 passed, every anchor intact; `tests/mutation_guards.py`
untouched. Two anchors constrained the implementation and were honoured rather than edited: `G33a` pins
`    if incomplete or below:` (so the completeness rule changed in the line above it) and `G33d` pins the
`elif refit.objective_value < chi_min - lower_tolerance:` line at its indentation (so the mass classification
stayed inline in the loop instead of moving to a helper). Nothing under `src/engcore/domains/thermal/` was
edited.

**Open decisions.** None in this batch.

### Batch 11 — I-04

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-04 | **DONE** | `e33e1be3` (preregistration + 15 strict xfails), this commit | the three-moment match is an approximation to a quadratic form's distribution, exact at equal weights and used only against α/2 = 0.005 and an exact null mean; dof 3 and dof 4 are underpowered by the same even-odds criterion (they miss a true factor-4 misfit with probability 0.608 and 0.554) and are not flagged, because the owner's declared limit is 2; a systematic error confined to the observations with NO leverage is seen by the pooled test only, which is why both run and the worse stands; the hat diagonal is computed at ONE point, inheriting the route's own local-linearity assumption; a supplied grid with n − p ≤ 2 is still SUPPORTED with nothing recording that its noise model was untestable, because a grid claim is SUPPORTED or absent; over-declared σ on the INFORMATIVE points is under-dispersion and stays deliberately ungated |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-03 | **FIXED** | Beside the pooled χ² on n − p degrees of freedom, the route computes the leverage-weighted statistic `T = Σᵢ Hᵢᵢ rᵢ²`, where `Hᵢᵢ` is the hat-matrix diagonal of the whitened Jacobian — observation i's share of the Fisher information that builds the reported covariance. Under the route's own premise the fitted residuals satisfy `r = (I − H)e`, so `T` is a quadratic form whose cumulants `c_k = tr(((I − H) diag(H))ᵏ)` are computed in closed form (`Σd^k`, `Σh d^k` and traces of two rank×rank matrices — nothing of size n×n is built) and matched to a shifted, scaled χ² on three moments. Both tests run at α/2 and the worse stands. The audited record — ten precise points at χ²/dof 9 REFUSED alone, SUPPORTED with 60 over-declared or 1000 honestly low-precision points appended and a covariance identical to 4 digits — now refuses in both dilutions: the pooled ratio is diluted to 0.071 with a p-value of 1.0, and the leverage ratio is 4.5. For the local route the whole statistic is **free**: the hat diagonal is the row norms of the orthonormal basis of the same column space the rank and conditioning already came from. The grid route runs the same two tests at its best admissible node, with a convergence-checked Jacobian there. |
| R-20 | **FIXED** | The variance-ratio refusal fires whatever the p-value says: `_one_fit_test` tests the ratio first, so χ²/dof 6.6 at one degree of freedom and 4.57 at two — scatter 2.6× and 2.1× the declared σ, which had read SUPPORTED with no reason at all — refuse `MODEL_MISFIT_BEYOND_DECLARED_NOISE`. And `n − p ≤ 2` adds the downgrade `GOODNESS_OF_FIT_UNDERPOWERED`: with the ratio rule now unconditional, a true variance ratio of 4 is still missed with probability 0.683 at dof 1 and 0.632 at dof 2, so the record says the declared noise model was essentially untestable instead of reading "tested and adequate". |

**The identity that makes the null checkable.** At `d = 1` for every observation, `c₁ = c₂ = c₃ = n − p`, so the
three-moment match has `b = 1`, `dof = n − p` and shift `0`: the leverage test IS the pooled χ² test. The
reduction is asserted to 1e-12 over three statistics, and a second assertion at unequal weights checks that
the match reproduces the statistic's mean — which is what the shift carries, and what a mutation showed no
test was measuring.

**Two problems that stopped reproducing and are NOT closed.** The strict-xfail ratchet took the markers off
two conformance cases for other problems, and both stay OPEN:

* **R-14** (a posterior flat along its diagonals, I-08's): its case has 4 observations and 2 parameters, so
  `GOODNESS_OF_FIT_UNDERPOWERED` caps it at DOWNGRADED and the mass floor is satisfied without any tail probe
  looking off-axis. I-08 must add a case with more than 2 residual degrees of freedom, so that what carries
  it is the probe and not the cap.
* **R-22** (editing one carried field, I-14's): the record now carries a SECOND goodness-of-fit number that
  the edit does not touch, so the edited record is refused because its two statistics disagree — not because
  the observation count is bound to anything. I-14 must fuzz every carried field rather than this one.

Both are recorded in the conformance file beside the cases, and in the protocol's `amendment_log`.

**Compatibility.** Additive. No V1 symbol is touched. On V2: two `RouteReason` members appended after the last
existing one (`GOODNESS_OF_FIT_UNDERPOWERED`, a downgrade; `GOODNESS_OF_FIT_NOT_MEASURABLE`, a refusal);
two trailing `RouteDiagnostics` fields with defaults (`leverage_weighted_chi_square` = NaN,
`leverage_null_cumulants` = ()); two keyword arguments with defaults on the private
`_grid_evidence.grid_goodness_of_fit`. `route_diagnostics/2` is NOT bumped: the two keys are written only when
a leverage test ran, and a record without them is accepted and held to the pooled test alone.

**The claims that move**, in both directions, as the protocol stated in advance: a variance ratio above 4 with
a p-value at or above α/2 now refuses (was: nothing); `n − p ≤ 2` is at most DOWNGRADED (was: SUPPORTED); a
mixed-precision dataset whose informative subset misfits refuses or downgrades (was: SUPPORTED); and in the
other direction a fit whose POOLED p-value lies in [0.005, 0.01) loses `RESIDUALS_EXCEED_DECLARED_NOISE`
unless the leverage test flags it too, because each test now runs at α/2 to hold the family-wise
false-refusal rate at the level batch 1 declared. No committed record sits in that band.

**Blast radius, measured.** The underpowered cap was the widest change in the batch and it moved exactly one
existing expectation: nothing in the FAST tier broke except the five items below. The cap reaches every
reproduction built on 3 or 4 observations, but those cases assert mass floors and refusals, which a DOWNGRADED
claim satisfies.

**Existing tests edited (no assertion weakened).**

* `tests/hybrid_uq/test_core_scientific_audit_batch1.py::test_a_record_that_understates_its_chi_square_is_refused_on_read`
  keeps its assertion — the record is refused — and its `match` now names the check that refuses it. With two
  goodness-of-fit numbers in the record, editing the χ² minimum alone leaves the other one still implying the
  recorded reason, so the record is consistent as a set of REASONS while being impossible as a set of
  NUMBERS: every leverage weight is a hat-matrix diagonal in [0, 1], so `T ≤ Σrᵢ²`. That inequality (and
  `c₁ ≤ p`) is now a read-back check, and it is what refuses the edit. The reason is commented in place;
* the four conformance markers above (R-03, R-20 closed by this batch; R-14, R-22 not closed);
* `R-03`'s padding builder moved from the conformance module into `false_confidence_cases.py` beside the case
  it dilutes, in the preregistration commit.

**Committed evidence.** `PERFORMANCE.json` is the one cheap record whose V2 claims turn on this rule, and its
pooled half can be re-derived from the bytes while its leverage half cannot — the record carries no residuals
and no Jacobian. So `benchmarks/core_v4_false_confidence/audit/batch11_performance_probe.py` re-runs the same
five routes and prints verdicts only, never writing the record (regenerating it would replace its measured
wall times with this container's, which is drift and not evidence). **All five claims are identical, reasons
included**: the measured leverage ratios are 22.28 at p = 2, 20.59 at p = 5, 8.449 at p = 10, 0.8564 at
p = 20 and 0.0056 at p = 41, so the three refusals the pooled test already made are made by the leverage test
too and the two downgrades stay downgrades. The two SUPERSEDED markers gained an `R-03 / R-20 / I-04` entry
each, in the JSON and the companion Markdown: K2's MULTI is 6 observations at p = 2 (4 residual dof, not
underpowered) with χ² 5.4446 — ratio 1.36, pooled p-value 0.2447, and since every weight is at most 1 a
leverage ratio above 4 would need `T > 8` against a total χ² of 5.44 and a null mean of at most 2, which is
impossible, so no refusal can arise there; T41's models have 26 to 65 residual dof and the p = 41 leverage
ratio was measured by the probe above at 0.0056. Neither multistart was re-run.

**Guard mutations.** `BATCH11_MUTATIONS.log`: **17 of 17 KILLED**, control green. Five survived a first run,
and each purchase is recorded in the protocol's `amendment_log`: the rank cut in `_leverage_weights` (the test
used a full-rank Jacobian, so the cut was a no-op — it now also checks that a collinear design's weights sum
to its RANK); the three-moment SHIFT (zero by construction in the equal-weight reduction — the test now also
checks at unequal weights that the match reproduces the statistic's mean); re-deriving only the pooled half on
read (the tamper was caught one check earlier by the new `T ≤ χ²` inequality — the test now first asserts that
the DILUTED record, whose refusal follows from the leverage half alone, reads back as written); reading the
grid's statistics at its FIRST admissible node (every grid in the suite refused either way — added
`test_a_well_fitting_supplied_grid_is_still_used`, since a grid's first node is a corner of its box); and
passing a grid over on ANY goodness-of-fit reason rather than only the misfit ones (added
`test_a_supplied_grid_over_one_residual_degree_of_freedom_is_still_used`). The 31 pinned mutations on the
files this batch changed were re-run isolated and all 31 are still KILLED (`BATCH11_PINNED_MUTATIONS.log`).

**Verification.** FAST tier 6548 passed, 7 xfailed, 18 failed (the by-design 18, unchanged; four more xfails
became passes, two of them this batch's closures and two the not-closed cases above). Expensive tier 528
passed, 18 failed, 14 errors — the recorded baseline's lists exactly. `tests/test_mutation_harness.py` 6
passed, every anchor intact; `tests/mutation_guards.py` untouched. Nothing under `src/engcore/domains/thermal/`
was edited.

**Open decisions.** None in this batch.

### Batch 12 — I-05

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-05 | **DONE** | `556ad8e0` (preregistration + 14 strict xfails), this commit | mode finding is a property of the NODES, so a mode that falls entirely between nodes is not a local maximum of the node function and is not checked — the rule is a necessary and not a sufficient condition for resolution; a mode on a FACE is not interior and is the containment check's business; the per-mode fit inherits the quadratic assumption, so a genuinely resolved but badly non-quadratic mode can fail its residual test (the measured margin on real grids is a factor of 9); the scan is O(N·3^p) plus one small fit per mode, bounded on the fitting half by `MODE_FIT_LIMIT`; a cut that is not axis-aligned is seen wherever it separates axis neighbours but only those axes are refined (the verifier measured that a diagonal cut mostly averages the moment error out, < 0.02 sd); the rebuild halves across a cut rather than moving the box to it, so the O(step) error there is bounded by `TRUNCATION_CONVERGENCE_SD` rather than removed |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-05 | **FIXED** | A new additive V2 check, `grid_mode_resolution`. V1's `_fitted_lattice_covariance` fits ONE quadratic about the global argmax over a window of 50 nats or more, so a second mode in the box pollutes it (the fitted lattice variance came out at 285 to 7e3, which switched the aliasing check off). Now every INTERIOR lattice node within ln 1e6 of the peak that is at least as high as all `3^p − 1` of its lattice neighbours gets its own quadratic, in V1's lattice units, on the smallest box holding V1's own node count, with V1's own flat-direction floors; the fit must describe its own nodes to `MODE_FIT_RESIDUAL_NATS` = `_ALIASING_NUMBER_MINIMUM / 2` = ln 100, and its curvature must pass V1's own aliasing bound. On the audited case at a step of 0.008 the narrow mode's own fit gives a lattice sd of 0.109 steps, an aliasing number of 0.470 and a residual of 17.7 nats — against the pooled fit's 285 to 7e3 — and the grid is passed over. The same grid at a step of 0.0005 passes. `src/engcore/inference/calibration.py` is unchanged: the check imports its constants and its exact enumeration. |
| R-17 | **FIXED** | A new additive V2 check, `grid_admissibility_truncation`. `grid_containment` takes each face's peak over ADMISSIBLE nodes only, so a face with no admissible node scores −inf and passes, and a posterior cut off inside the box never reaches a face at all. Now an admissible node the posterior reaches within ln 1e6 of the peak that has an inadmissible lattice neighbour is a truncation face: a supplied grid is passed over with `GRID_CUT_BY_INADMISSIBILITY`, and in a rebuild that axis joins the truncation halving so steps across the cut are halved until the moments move less than `TRUNCATION_CONVERGENCE_SD`. The audited rebuild read "0 truncation halving(s)" with a mean error of −0.144 sd, about 3× the router's own tolerance. |

**The two halves are independent, and each is measured by a case the other does not cover.** That is what two
surviving mutations bought:

* only the RESIDUAL test sees a broad shoulder with a narrow spike at its centre — the least-squares quadratic
  follows the six shoulder nodes, so its curvature is wide and V1's aliasing bound PASSES, while the centre
  node sits 6.67 nats below the fit;
* only the ALIASING bound sees a thin tilted ridge — the log-likelihood is exactly quadratic, so the fit's
  residual is 1e-10 nats, and the ridge is narrower perpendicular to itself than the lattice can sample.

**Why mode finding does not have to be exact.** Over the `2p` AXIS neighbours alone, an exactly Gaussian
TILTED ridge staircases into spurious maxima (3 and 4 on `hybrid_synthetic.affine` at 41 and 61 nodes per
axis). Over the full `3^p − 1` stencil those grids have exactly one. A thin tilted ridge can still staircase
when its crest passes between nodes — `bimodal_two_parameter` at 41 nodes per axis has 11 maxima on a grid
whose moments are stable to 6 digits from 41 to 321 nodes per axis — and each of those 11 yields the RIDGE's
own curvature, so each passes both tests with a factor-9 margin on the residual. So the scan only has to MISS
nothing, which is why maximality is non-strict and the band is the one the containment check already uses.
Both facts were measured before the rules were written and are recorded in the protocol.

**Compatibility.** Additive. V1 untouched: `src/engcore/inference/calibration.py` is not edited, and the new
checks import `_tensor_lattice_steps`, `_minimum_aliasing_number`, `_ALIASING_NUMBER_MINIMUM` and the two
flat-direction floors from it. On V2: two `RouteReason` members appended after the last existing one
(`GRID_MODE_UNRESOLVED`, `GRID_CUT_BY_INADMISSIBILITY`, both refusals); two module-level functions in the
private `_grid_evidence`; no record field and no schema is touched, because both checks are router-side
verdicts on a grid object like the containment and uniformity checks beside them.

**Blast radius, measured: none.** The FAST tier gained no failure. That is the design choices paying off — the
full stencil rather than the axes, and tolerating spurious maxima rather than trying to eliminate them.

**Existing tests edited (no assertion weakened).** Only the two conformance markers (R-05 and R-17, closed by
this batch). Nothing else in the suite moved.

**Committed evidence.** Nothing was regenerated, because nothing moved. `TCR.json`'s two supplied grids are
the cheap records these rules could move, and they are re-derived LIVE by
`tests/hybrid_uq/test_hybrid_uq_tcr.py::test_the_local_route_agrees_with_the_resolved_grid`, which asserts
`GRID_AS_SUPPLIED` and still passes — so both resolve every mode in their band and neither is cut by
admissibility. `PERFORMANCE.json`'s grid half is V1-only. The two SUPERSEDED markers gained an
`R-05 / R-17 / I-05` entry each: K2's grids are V1 REFERENCES with nested refinement and no route decision in
that record rests on a V2 grid check, and every T41 model is routed LOCAL_GAUSSIAN with no grid, so neither
rule reaches a claim in either. Neither was re-run.

**Guard mutations.** `BATCH12_MUTATIONS.log`: **16 of 17 KILLED**, the seventeenth an expected survivor,
control green. The survivor is instructive: appending the admissibility-cut axes to the list the
bound-domination rule counts changes nothing, because the guard against reporting the model's own domain as
the declared range dominating a width is the ORDER of two statements — the domination check reads the
truncation list above the line where the cuts are merged in. The mutation that moves the domination check's
own expression to read them is KILLED. The 21 pinned mutations on the files this batch changed were re-run
isolated and all 21 are still KILLED (`BATCH12_PINNED_MUTATIONS.log`).

**Verification.** FAST tier 6565 passed, 5 xfailed, 18 failed (the by-design 18, unchanged; the two xfails
that became passes are I-15's R-05 and R-17 cases). Expensive tier 528 passed, 18 failed, 14 errors — the
recorded baseline's lists exactly. `tests/test_mutation_harness.py` 6 passed, every anchor intact;
`tests/mutation_guards.py` untouched. Nothing under `src/engcore/domains/thermal/` was edited.

**Open decisions.** None in this batch.

### Batch 13 — I-18

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-18 | **DONE** | `28ae62ad` (preregistration + 16 strict xfails), this commit | a re-import that rewrites the number AND the provenance is indistinguishable from a new measurement by any rule this layer can state (this replaces the preregistered claim that 1e-3 σ on the value would catch it — see the amendment log); the in-process registry means a comparison over records from an EARLIER process names no preferred model, which needs `compare` to take the split and tables to fix and the V1 freeze has no room for that until V4; the split content digest binds the two halves' content, not the forward model or the parameterization; the t correction fixes the level of ONE comparison and nothing records how many were run on one held-out set (that is I-21's); the minimum n of 10 is a precision floor on the standard error, not a strong level — the elpd literature's own advice is nearer a hundred points; and declaring `allow_exact_replicates()` now declares more than it did, because it also switches off the within-half test |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-24 | **FIXED** | Three holes, one idea: content binding now binds the content. The split branch requires `spec.observation_sigma` to be the matched held-out observation's declared sigma, to the same tolerance the branch already holds the VALUE to — the declared noise is what makes a log density a likelihood rather than a distance, and a caller-chosen sigma created a decisive preference (0.05 K against a declared 0.5 K) and erased a genuine 11.5-nat one (5 K). It requires `twin == split.twin`, which `ObservationSplit`'s own docstring already said. And `PredictiveEvidenceIdentity` gained a trailing `split_content_digest` over the split's twin, both dataset ids and the canonical content digest of every observation in BOTH halves — so the pairing loop that already refuses two assessments assessed against different evidence now refuses two bound to different SPLIT CONTENT, and names the field. Two campaigns under the same id strings no longer pair as one evidence. |
| R-32 | **FIXED** | The copy detectors run WITHIN each half as well as across it, unless the study declared replicates: the detector's own argument ("same observable, same value, same sigma, different condition_id — for a continuous quantity that is a copy, not a coincidence") never depended on which side the rows are on, and inside the held-out half the consequence is worse than leakage — the paired differences become identical, the sample variance is exactly 0 and the standard-error test is vacuous. A second, LINEAGE route catches the re-import the old rule admitted: the same non-empty `source_ref` and base unit, values within a thousandth of the declared sigma, with the observable NAME and the declared SIGMA both ignored. `compare` withholds a preference when two paired positions carry the same held-out content, and `ModelScoreComparison` records the independence its standard error assumes. |
| R-33 | **FIXED** | The SE multiple is the two-sided Student-t quantile on `n − 1` degrees of freedom at `COMPARISON_ALPHA` — which is the level the existing multiple of 2 already declared, so the threshold's preregistered false-refusal rate is kept and only the missing small-sample correction is new. `COMPARISON_MINIMUM_N` rose from 2 to 10: the relative standard error of a sample sd on `n − 1` degrees of freedom is `1/sqrt(2(n−1))`, and 10 is the smallest n at which that is below a quarter. **Measured** (`audit/batch13_false_decisive_rate.py`, 40 000 trials): the old gate gives 0.0742 at n = 10, 0.0619 at n = 20 and 0.0515 at n = 50 against a declared α of 0.0455; the new gate gives 0.0443, 0.0467 and 0.0459, and below n = 10 the rate is 0 because no preference is named at all. |
| R-34 | **FIXED** | `content_bound` is V1-frozen and stays exactly as it is — a recorded claim, integrity-only on read. What changed is who believes it: a module-private registry holds the RECORD DIGESTS this process bound, written only at the end of the split branch, and `compare` gates the preferred model on the derived `content_binding_verified` instead. A flipped flag, a `replace` with a fabricated log density, and a record this process never produced are all unverified; a faithful same-process round-trip is verified, and that is the honest answer — the binding it claims is true of exactly those numbers. |

**A preregistered rule corrected by real evidence.** The protocol preregistered "a copy is decided on the
VALUE, at a thousandth of the declared sigma, with the sigma-equality requirement dropped" — the audit's own
suggested rule. It **refuses real evidence**: `benchmarks/battery_flagship_b3` stopped building, because its
split holds two cross-half pairs (DCHG r142/r143 and r145/r146) whose recorded open-circuit voltages are
BIT-IDENTICAL — the instrument quantizes — and whose combined standard uncertainties differ by 4.842e-6 of a
sigma, at distinct rows, distinct rested conditions and distinct `source_ref`s. Those are two measurements.
On the value alone, at any tolerance, they are indistinguishable from the re-import the audit asks to catch,
so the sigma was doing real work and LINEAGE is the discriminator. The numeric route therefore keeps both
conditions at the preregistered 1e-6, and the looser tolerance with no sigma condition moved to the lineage
route, where the false-match exposure is a handful of pairs instead of `n_cal × n_held`. The arithmetic that
settles it: the expected number of false matches on value alone is about `0.7979 · t · pairs`, which for B3's
2211 pairs is **1.76 at t = 1e-3** — and exactly 2 were found — against 0.0018 at 1e-6. The full reasoning and
the numbers are the first entry of the protocol's `amendment_log`.

**Compatibility.** Additive on every V1-frozen symbol: `PredictiveEvidenceIdentity` gained one trailing field
with a default, `ModelScoreComparison` one trailing field with a default, `PredictiveObservationAssessment`
no field and two derived properties (`record_digest`, `content_binding_verified`). No field is removed,
renamed or reordered, and no existing default changed. `EVIDENCE_IDENTITY_FIELDS` grew from 7 entries to 8,
which the V1 snapshot records as a SIZE — the same additive category as a new enum member. The two module
constants that changed (`COMPARISON_MINIMUM_N` 2 → 10, and the new
`NEAR_DUPLICATE_LINEAGE_RELATIVE_TO_SIGMA`) are not in the frozen snapshot, which records constants by kind
and container size rather than by value. `predictive_evidence_identity` is NOT bumped: the new key is written
only when non-empty and enters the identity digest only when non-empty, and a pinned digest test computed by
hand from the pre-batch canonical form proves a stored record keeps the digest it had.

**Existing tests edited (no assertion weakened).**

* `tests/test_evidence_pairing_integrity.py::test_the_identity_covers_exactly_the_declared_fields` asserts the
  field list in full, as before, with the appended name and a comment saying why it joined;
* `tests/hybrid_uq/test_core_scientific_audit_batch4.py`'s two CORE-011 comparisons grew their split from 3 to
  12 held-out points, because the gate they are about now needs 10. Both assertions are unchanged — one still
  says a negligible difference names no model and names the 4-nat reason, the other still says a decisive
  difference on content-bound evidence names the better model.

**Committed evidence.** Nothing moved: no committed record in the repository carries a predictive assessment
or a model comparison. The B3 benchmark is the evidence this batch was corrected BY, and it builds and passes
unchanged.

**Guard mutations.** `BATCH13_MUTATIONS.log`: **18 of 18 KILLED**, control green. Four survived a first run,
and all four purchases are recorded in the protocol's `amendment_log`: a gate for "bound to the same split"
was dead code (the pairing loop already refuses it and names the field) and was removed — which then made the
mutation that reads the caller-settable flag instead of the in-process verification killable, because the two
gates had been covering each other; the decisive gate was extracted into a pure function
`_decisive_preference(delta, n, standard_error)` and is read at its own boundary, because the window between
2 SE and the t quantile is a fixture search through data and a measurement through the function; and the
within-half exact-content detector needed the one case only it sees (at a value of 1e20 the digest's twelve
significant digits make two rows one content while their difference is 1e9 declared sigmas). The 5 pinned
mutations on the two files this batch changed were re-run isolated and all 5 are still KILLED
(`BATCH13_PINNED_MUTATIONS.log`).

**Verification.** FAST tier 6593 passed, 5 xfailed, 18 failed (the by-design 18, unchanged). Expensive tier
528 passed, 18 failed, 14 errors — the recorded baseline's lists exactly. `tests/test_mutation_harness.py` 6
passed, every anchor intact; `tests/mutation_guards.py` untouched. Nothing under
`src/engcore/domains/thermal/` was edited.

**Open decisions.** None in this batch.
