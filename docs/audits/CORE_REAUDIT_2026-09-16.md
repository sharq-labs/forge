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

### Batch 14 — I-11

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-11 | **DONE** | `3f957a94` (preregistration + 10 strict xfails), this commit | `record_values` records Quantities only, so a CategoryCondition or FlagCondition verdict ("laminar, steady") still attaches to a result whose provenance says otherwise — `evaluated` is typed `Mapping[str, Quantity]` on a V1-frozen record and widening it is finding 62's remaining half; 59 of the 77 condition names across the 16 registered models are reserved DERIVED quantities and 18 are declared inputs, so most names cannot be bound at all and are REPORTED rather than counted as gaps (D-14-1 below); the production electrothermal report's provenance inputs are namespaced (`resistance-tcr-R1::temperature`), which binds nothing by name on either side; a hand-built assessment can still fabricate its model key and its condition list consistently, which is what the MCP boundary's registry check is for; and an interval verdict records only the values that did not move within the step, so a coupled step binds its state of charge and current and not its temperature |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-09 | **FIXED** | The CORE-014 binding is now enabled on the production paths and applied where the verdict is formed. Three changes, none of them a new rule: `ScientificModelDefinition.assess_validity` gained `record_values` (default False — it is a V1-frozen symbol's method) so a domain *can* opt in, and `DomainValidityContext.assess` gained it with a default of **True**, so battery, electrical and repair record their operating point by construction rather than by memory; every remaining direct assessment site under `src/engcore/domains` passes it (the two conduction1d scheme paths and the four electrical dc paths — `src/engcore/domains/thermal/**` is SHA-256 pinned and untouched); and `ModelValidityRecord`'s rebuild **carries `evaluated`** instead of silently dropping it, which is finding 46 exactly — the credibility boundary erased the operating point immediately before both production MCP tools form their verdict. `CredibilityEvidenceReport` then applies the same comparison to every record it holds, supplied by an assembler or carried from the result, against its own provenance. The audited case — a result whose provenance says `alpha = -1e-5 m^2/s` carrying an IN_DOMAIN assessment made at `+1e-5` — is refused at the result, and its report-shaped twin at the report. |
| R-50 | **FIXED** | `ValidityAssessment` gained three trailing fields with defaults: `model_id`, `model_version` and `declared_conditions`. `ValidityDomain.assess` fills the last with the names it decided, in declaration order; `assess_validity` fills the model key. `ScientificResult` then refuses an assessment whose model id is not the key it is filed under, whose version is not the one the result declares (its own one-version rule already says those are two claims), or whose condition lists are not exactly the names its domain decided, each once. `satisfied=('anything_at_all',)` no longer reaches `Experiment.best`, the inference admission gate or `validity_of`. No registry is involved, which is why the check can live in `engcore.scientific` at all: that package cannot import the domains, and a record needing a registry to be checkable is checkable only where the registry is. The MCP boundary's `_require_conditions_of_the_declared_model` stays and is the stronger of the two, because it reads the model's own domain. |

**What "load-bearing" cost, measured rather than assumed.** Enabling the flag moved exactly one existing
expectation in the tree, and it moved for a real reason. `tests/domains/battery/test_battery_coupling.py`'s
`test_a_coupled_run_and_a_standalone_assessment_agree_at_the_same_point` compared a step's **interval**
verdict with a standalone assessment at one instant. Those now differ, because `_over_the_step` combines two
instants and a step's temperature moves between them by construction — that is what the two instants are for.
The combination therefore carries the model key and the declared conditions (identical at every instant) and
records a value only for a name every instant agreed on: the state of charge and the current, not the
temperature. Recording either end would state an operating point the interval does not have, and a result
carrying the other end would then be refused for agreeing with itself. The test now compares against
`validity_at[STEP_START]`, which is the assessment the march made at exactly that operating point — a
**stronger** equality than the one it replaces, because it now covers the recorded operating point as well as
the condition lists — and asserts separately that the interval verdict agrees on status, conditions, model key
and declared conditions, and holds exactly the names the two instants agreed on. The measured difference is
three names across three of the five battery models (`discharge_temperature_position`,
`internal_resistance_drift_ratio`, `capacity_temperature_drift_ratio`, `peukert_temperature_drift_ratio`) —
every one of them temperature-derived.

**One preregistered enumeration corrected, the rule unchanged.** The protocol's
`the_production_paths_record_their_operating_point` rule is implemented exactly as stated — every site under
`src/engcore/domains` that assesses DIRECTLY passes the flag — but its parenthetical list was written from the
audit's fix direction before the call sites were read, and it named two families that do not assess directly:
the lumped capacity path and the battery cell paths both go through `DomainValidityContext.assess` and are
covered by that method's default of True. The actual direct set is the two conduction1d scheme paths and the
four electrical dc paths. Recorded as the first entry of the protocol's `amendment_log` rather than edited in
place, because a preregistration quietly corrected to match the code is not a preregistration.

**Compatibility.** Additive on every V1-frozen symbol. `ValidityAssessment` gained three TRAILING fields with
defaults; `ScientificModelDefinition.assess_validity` and `DomainValidityContext.assess` gained keyword-only
arguments with defaults; `ValidityDomain.assess` is untouched and its `record_values` default stays False.
`CredibilityEvidenceReport` gained no field and one derived property (`unbound_assessment_values`). No field
or member is removed, renamed or reordered, and no existing default changed. Serialization: the three new
assessment keys are written **only when non-empty**, as `evaluated` already is, so an assessment recorded
before this batch keeps its bytes and its digest; `ModelValidityRecord`'s serialized form gains `evaluated`
where the assessment has it, which is the information finding 46 says it was dropping. No schema string is
bumped, and `from_dict` reads a missing key as the empty value on both records.

**Existing tests edited (no assertion weakened).** One: the battery coupling equality described above, which
became stronger. Nothing else in the FAST or expensive tier changed expectation.

**Committed evidence.** Nothing moved. No committed record in the repository serializes a
`ValidityAssessment` or a `ModelValidityRecord` (`validity_assessment/2` appears in
`benchmarks/core_freeze_v1/REPRODUCTION_OUTPUT.json` and `certification/core_freeze_v1.json` only as the
accepted-schema list of the reader test, not as a stored assessment), so no digest is re-derived here. The
`KINETICS_K2` and `BATTERY_T41` SUPERSEDED markers gain no entry either: every claim in both is a hybrid-UQ
route record, and neither carries a validity assessment for these rules to reach.

**Guard mutations.** `BATCH14_MUTATIONS.log`: **15 of 15 KILLED**, control green. One survived a first run and
the purchase is recorded: B14b (removing the model key `assess_validity` fills) survived because
`test_r50_an_assessment_filed_under_another_model_is_refused` had the result declare BOTH models and was
therefore passing on the unrelated "declares a model and says nothing about whether it applied" rule — it
never read the key it was about. The test now declares only the other model and matches the mismatch message,
so the model key is measured at its own boundary. The 17 pinned mutations on the six files this batch changed
were re-run isolated and all 17 are still KILLED (`BATCH14_PINNED_MUTATIONS.log`), control green.

**Verification.** FAST tier 6611 passed, 5 skipped, 5 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors — the recorded baseline's lists exactly.
`tests/test_mutation_harness.py` 6 passed, every anchor intact; `tests/mutation_guards.py` untouched. Nothing
under `src/engcore/domains/thermal/` was edited.

**Open decisions.**

* **D-14-1 — what an assessment whose condition values cannot be bound to the provenance should count as.**
  **DECISION-NEEDED.** The audit's fix direction says "treat an unbound assessment as a gap, not as a pass".
  Doing that turns every production MCP verdict resting on a derived condition from SUPPORTED into
  INSUFFICIENT_EVIDENCE: 59 of the 77 condition names across the 16 registered models are reserved derived
  quantities, which are never provenance inputs, and the production electrothermal report's inputs are
  namespaced besides. This round's hard constraints say the verdict word moves scored benchmarks and that an
  existing call must not change what it returns by default, so the change is the owner's.
  Options: **(a)** record only, as this batch does — `CredibilityEvidenceReport.unbound_assessment_values`
  names every recorded value the provenance could not bind, the binding is load-bearing wherever a name CAN
  be compared, and the verdict is unchanged; **(b)** treat unbound as a gap, accepting that production
  verdicts move to INSUFFICIENT_EVIDENCE until every domain maps its derived quantities to provenance inputs;
  **(c)** make the binding complete first — each domain's assembler declares, per derived quantity, which
  declared inputs it is computed from, those inputs' values are recorded too, and THEY are compared — after
  which (b) costs nothing. Recommendation: **(a) now, and (c) as its own improvement.** (a) closes every
  audited reproduction without moving a scored verdict; (c) is a real piece of work (a declared
  input-to-derived-quantity map for 16 models) and is the honest way to reach (b). (b) alone would trade a
  silent pass for a blanket INSUFFICIENT_EVIDENCE, which tells a reader less, not more.

### Batch 15 — I-19

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-19 | **DONE** | `350e08e3` (preregistration + 16 strict xfails), this commit | the unknown-key refusal is scoped to `ScientificProblem` and `UncertaintySpecification`; the audit's own verification says the silent drop is a general pattern across every `from_dict` in `engcore.scientific`, and making all of them strict has a much larger blast radius on stored records; `src/engcore/domains/thermal/**` is SHA-256 pinned, so the conduction1d result builder does not append the requirement checks and its declaration is enforced only where a boundary holds both the problem and the result; the uncertainty half has no production reach today, because nothing in src constructs an `UncertaintySpecification` above NONE; a requirement is satisfied by a PASS check of the right NAME and nothing here verifies that the check checked what the name says; the registry records which names are check kinds somewhere in this tree, not which names a particular solver can produce; and `ScientificResult.is_usable` is unchanged, because a NOT_RUN check does not move it and that is the existing rule for every NOT_RUN check in the tree |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-72 | **FIXED** | Three holes, one idea: a declaration is read where it can be read. (1) **Strict parsing.** `ScientificProblem.from_dict` and `UncertaintySpecification.from_dict` refuse a key they do not read, naming the unknown keys and the keys they accept; and a PRESENT `uncertainty` key goes through its own reader rather than a truth test, so a present-but-empty value is refused by that reader's schema requirement instead of silently becoming the default specification. `to_dict` emits exactly the read set on both records, so no payload this tree has ever written is refused. (2) **The rule.** A new additive module `engcore/scientific/results/requirements.py` says what is unmet: a requirement is satisfied only by a check of that exact name whose outcome is PASS (a NOT_RUN check of the right name says the opposite of what the declaration promises); `REPORTED` is met by an Uncertainty record, `QUANTIFIED` is not met by one whose kind is UNKNOWN — the record's own word for *not evaluated* — and a declared confidence level must be the one the record declares. What is unmet becomes at most two NOT_RUN checks, and **nothing at all** when the declaration is met, so a compliant result keeps its bytes. NOT_RUN and not FAIL for the reason the boundary's own `solver_convergence` check is NOT_RUN: nothing found the values false, and the work to recommend is to run the check. (3) **The registry.** `numerically_convergd` was accepted because nothing validated a requirement name and nothing read the field. Every module that emits a check kind now registers it beside the emitter — the DC and CSTR validation modules, the `thermal_models` schemes, 2D and lumped modules, the MCP boundary's own two — and a requirement naming no registered kind is reported as one **no result can ever satisfy**, with the registered kinds named. **Enforced where the enforcement happens, and the three reach points are wired:** `TrustedExecutionRecord.trusted` re-derives the verdict from the prepared problem and the validation report it already carries (the audited case exactly: `validation checks ['dimensional_consistency'] status pass trusted True` against a problem requiring `kirchhoff_current_law` and `power_balance`); `CredibilityEvidenceReport.from_result` gained an optional `problem=` and appends the checks, which lowers a real production SUPPORTED verdict to INSUFFICIENT_EVIDENCE through the existing NOT_RUN rule — measured on the production electrothermal report rather than asserted; and the two editable domain result builders (DC and CSTR) route their validation report through the rule, so the verdict travels with the result rather than only with a report somebody remembered to assemble. |

**Why the registry is read at enforcement time and not at construction.** A refusal in
`ScientificProblem.__post_init__` or `from_dict` would make a problem record's acceptability depend on which
domain modules a process happens to have loaded — the scientific core may not reach down into a domain
package, so the registry is populated only when a domain is itself imported. A guard that switches itself off
with the import graph is worse than no guard. At enforcement time the domain is necessarily loaded: its result
is the thing being judged. The cost is stated rather than hidden: a typo is not refused at the moment it is
written down, and is instead reported as a requirement nothing can ever satisfy the first time a result is
judged against it.

**The pinned tree.** `src/engcore/domains/thermal/**` is SHA-256 pinned by the frozen thermal_t1/t2/t3
experiments, so conduction1d cannot call the registrar beside its own checks. Its five kinds are registered in
`src/engcore/domains/__init__.py` — the domains package root, imported before any domain module can be — for
exactly the reason that file already states a position on behalf of `thermal.conduction1d.solver`. Without it
the frozen slab problem's own declaration would read as naming nothing.

**Compatibility.** Additive in shape on every V1-frozen symbol. `CredibilityEvidenceReport.from_result` gained
a keyword-only `problem=None`; `TrustedExecutionRecord` gained two derived properties and no field;
`ScientificProblem` and `UncertaintySpecification` gained a `READ_KEYS` class attribute, which is not a
dataclass field (it carries no annotation) and so moves no field order. A new module is added. No field or
member is removed, renamed or reordered and no existing default changes. Two behaviours change on purpose:
the two readers refuse a payload carrying a key they do not read — a reader becoming stricter exactly where
its old acceptance was dishonest, and the refused payload is precisely the one whose declaration was silently
dropped — and a trusted execution record whose problem's declared checks did not pass is not trusted, which
is the audited defect. No schema string is bumped and no record gains a key; the only new bytes are the
NOT_RUN checks, and only where a declaration is actually unmet.

**Existing tests edited (no assertion weakened).** None. One production module was RESTRUCTURED rather than
edited in behaviour: `TrustedExecutionRecord.trusted` grew a condition, which would have moved the line
`tests/mutation_guards.py` pins as G30ai. Per the round's rule the code was restructured so the anchor still
matches exactly once — RES-07's own decision moved into
`_attested_run_reached_a_usable_end`, carrying the pinned line unchanged, and `trusted` now reads that
property and the new one. `tests/mutation_guards.py` was not touched, and the G30ai mutation still kills its
named test.

**Committed evidence.** Nothing moved. No committed record in the repository carries a problem payload with
an unread key, and no committed result or report carries an unmet declaration: the DC domain's validation
emits exactly the six names its problem declares and the CSTR's exactly its four, which
`test_r72_the_dc_solve_meets_its_own_declaration` measures live rather than asserting. The `KINETICS_K2` and
`BATTERY_T41` SUPERSEDED markers gain no entry: every claim in both is a hybrid-UQ route record and neither
carries a problem declaration for these rules to reach.

**Two preregistered details corrected, both recorded in the protocol's `amendment_log` rather than edited in
place.** (1) The rule said the battery assembler would append the requirement checks to the checks it already
carries. That report answers TWO sub-problems and `CredibilityEvidenceReport` refuses two checks of one name
— rightly: one name, one finding — so two separate calls would have made the report unconstructible the
moment either problem declared a requirement. A sibling `merged_requirement_checks(problems, ...)` produces
one check per kind naming each problem's unmet items, and the assembler calls that. Nothing about what is
enforced or where moved. (2) The mutation runner's `_COPY_TREES` gained `experiments`: the pinned mutations on
the files this batch changed include a CSTR audit suite whose module fixture imports
`experiments.kinetics_k1.k1_config`, so that file errored in every isolated copy and the first pinned run's
control came back RED at 116 passed, 3 errors. This runner's own doctrine is that a red control says nothing,
so that run's verdicts were discarded and the whole set re-run against a green control.

**Guard mutations.** `BATCH15_MUTATIONS.log`: **21 of 21 KILLED**, control green. One survived a first run
and the purchase is recorded: B15m (removing the rule that a metric the problem does not carry can never be
satisfied) survived because `test_r72_a_metric_the_problem_does_not_carry_can_never_be_satisfied` passed an
EMPTY uncertainty mapping, which the "no record at all" branch catches whatever the problem declares — so the
rule under test was never the one deciding. The test now also supplies a record for that name, which only
this rule can refuse, and asserts that the same record satisfies the same demand over a name the problem does
carry. The 22 pinned mutations on the nine files this batch changed were re-run isolated and all 22 are
KILLED (`BATCH15_PINNED_MUTATIONS.log`), control green at 119 passed.

**Verification.** FAST tier 6635 passed, 5 skipped, 5 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors -- the recorded baseline's lists exactly. `tests/test_mutation_harness.py` 6 passed, every
anchor intact; `tests/mutation_guards.py` untouched. Nothing under `src/engcore/domains/thermal/` was edited.

**Open decisions.** None in this batch.

### Batch 16 — I-24

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-24 | **DONE** | `e0749c17` (preregistration + 6 strict xfails), this commit | the edge set is the four `BoundaryEdge` members, because a structured rectilinear mesh is the only support this layer has; a support with another boundary topology would need the set to come from the mesh, and the refusal names which edges it required; a condition whose region is a PART of an edge is not representable here at all, so a partially conditioned edge cannot be declared and is not checked for; and the corner-agreement check keeps keying its prescribed values by region id, which is safe now that a region id and an edge are in bijection for any declaration that reaches it |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-56 | **FIXED** | `require_complete_boundary` now keys BOTH of its checks by the RESOLVED EDGE. Two conditions on one edge are refused whatever their region ids and whatever their kinds — a Dirichlet edge and a Neumann condition on the same edge is the same contradiction with the same silent winner, and the corner rule only ever compared Dirichlet pairs. Completeness is over the SUPPORT's four edges rather than over the caller's own region list, so a caller who passes one region and one condition is told which edges have no condition instead of being told the boundary is complete and then crashing with a `KeyError` inside assembly. Both refusal sentences are unchanged — `One edge, one condition` and `under-determined` — because the rule they state was always the intended one and only the key was wrong. And `SteadyConductionProblem.edges` refuses a collision instead of keeping the last condition: that dict comprehension is where the winner was actually chosen, and the assembly and `_worst_dirichlet_error` both read it, which is why the dropped 400 K Dirichlet edge was never imposed and never checked. The audited case — a 9x9 plate declaring a 400 K left edge and a 0 W/m² flux on the same edge through two region ids, which solved with `field_finite`, `field_linear_system_residual` and `boundary_conditions_held` all PASS and a field maximum of 300.00000000019827 K — is refused when the problem is constructed, and its honest counterpart (the same plate declared once per edge) is committed beside it and reports its maximum as 400 K. |

**Why both ends.** The core gate is where the contradiction is a declaration error; the consumer is where it
becomes a wrong number. A guard at only one of the two is a guard the other end can be reached without —
`edges` is a public property and a caller may hold a problem built some other way — so both refuse, and the
consumer's message says why keeping either condition would be worse than refusing.

**Compatibility.** No field, member, default or signature changed anywhere, nothing was added to a serialized
record and no schema string is bumped. Three behaviours change on purpose, and each of the three was a state
that produced a wrong number or a crash: two conditions on one edge under two region ids, a region set that
does not cover the support, and a Dirichlet plus a Neumann on one edge. Every in-tree caller of
`require_complete_boundary` passes `boundary_regions(mesh)` — all four edges, one region each, with ids
derived from the support so two regions cannot claim one edge — which this batch's tests measure rather than
assume.

**Existing tests edited (no assertion weakened).** None. The two existing refusal tests in
`tests/test_field_records.py` read the sentences this batch deliberately kept, and both pass unchanged.

**Committed evidence.** Nothing moved: no committed conduction2d record declares a duplicate region or a
partial region set, and the manufactured-solution and convergence suites pass unchanged.

**Guard mutations.** `BATCH16_MUTATIONS.log`: **6 of 6 KILLED**, control green, none survived a first run.
Five remove a new rule; the sixth removes the bookkeeping that records an edge as seen, which is the control
that the completeness check is not vacuously satisfied. No pinned mutation in `tests/mutation_guards.py`
targets either file this batch changed, so the pinned set is empty — and the runner was fixed to say so: an
empty set used to fall through to a control run with an empty test list, which pytest reads as "collect
everything", giving 15 errors and a RED control for a run that measured nothing. Recorded in the protocol's
`amendment_log`; batch 16's own six ran against a green control before that fix and their verdicts stand.

**Verification.** FAST tier 6643 passed, 5 skipped, 5 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors -- the recorded baseline's lists exactly.
`tests/test_mutation_harness.py` 6 passed, every anchor intact;
`tests/mutation_guards.py` untouched. Nothing under `src/engcore/domains/thermal/` was edited.

**Open decisions.** None in this batch.

### Batch 17 — I-03 part A

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-03 | **PARTIAL** (part A of two) | `e512de91` (preregistration + 8 strict xfails), this commit | the prediction-domain check is DECLARED but not yet informative — the TCR observations carry no `conditions`, so every routed record reads `PREDICTION_DOMAIN_NOT_DECLARED`; `assess_predictive_observation` applies containment and prior uniformity but not goodness of fit, which needs the calibration OBSERVATIONS and the forward evaluator where it receives a calibration TABLE; a held-out verdict is still PASS or FAIL, because there is no third word yet; and what a coverage verdict should do about a refused fraction is undecided. All four are part B's (batch 18) |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-02 | **FIXED** | `engcore.hybrid_uq` — every evidence gate the 2026-09-16 audit built — had no caller in `src` outside its own package, so `studies/calibration_study.py`, the only production orchestration that turns a calibration into predictive intervals and a held-out verdict, ran none of them. `predict_held_out` and `validate_held_out` now obtain their predictive quantities from `hybrid_uq.grid_predictive_uncertainty`, which computes the SAME frozen `posterior_predictive_uq` on the same inputs under the router's own judgement: the grid is held to the evidence it describes (CORE-005), the declared noise must explain the calibration residuals (CORE-001), the box must contain the posterior (CORE-002), equal node mass must be the declared prior (CORE-010), every mode must be resolved, and no admissibility cut may truncate it. A grid the router would not route now RAISES where the study answered it with an interval — the audited truncated box (parameter sd 0.34x) and the audited misfit (chi-square 232.824 on 4 dof) among them. `PredictiveDecomposition` and `HeldOutMetrics` carry the claim and the reasons the V2 record leaves. In `adequacy.assess_predictive_observation`'s content-binding branch, prior uniformity and containment are applied and a finding WITHHOLDS the binding rather than raising, with the reason recorded in a new trailing field — so the decisive 6.259-nat preference the narrow box manufactured is gone, because `compare` names no preferred model over an unbound assessment. And the frozen `posterior_predictive_uq` now RECORDS the condition names it cannot check (`conditions_not_checked`) instead of ignoring a spec that says `T = 5000 K` in silence. |

**The numbers did not move; the judgement around them is new.** `grid_predictive_uncertainty` computes the
same frozen call the study always called, so the predictive mean, the parameter sd, the total sd and both
intervals are identical. That is measured rather than asserted:
`test_r02_the_production_wide_design_still_predicts_the_same_numbers` and
`test_r02_the_routed_record_honours_the_declared_credible_mass` read the shape and the declared level off the
routed records, and the whole `tests/inference` and `tests/hybrid_uq` suites (539 tests) pass.

**Four existing expectations moved, every one of them because a check found something real.**

* `tests/inference/test_tcr_heldout_uq.py::test_a_misspecified_model_converges_and_is_rejected` — B4, the
  central proof. The misspecified model is now REFUSED before any held-out statement, because its
  CALIBRATION residuals already exceed the declared noise (chi-square 129.887 on 4 dof). The claim is
  unchanged and made twice over: converged, identifiable, refused. The U-shaped residual pattern — the
  signature of a truncated expansion, and the strongest evidence in that test — is read from the same
  per-observation `assess_predictive_observation` call the study makes, through a new helper that says why.
* the same file's side-by-side contrast, for the same reason.
* `tests/hybrid_uq/test_core_scientific_audit_batch4.py` and `tests/test_core_scientific_audit_batch13.py` —
  the two CORE-011 comparison fixtures. Their grids were `linspace(1.0, 3.0)`, and two of the fixture models
  put their posteriors outside that box: the BIASED model peaks at theta = 1.269 with a posterior sd of 0.0548
  (4.9 sd from the lower edge, 12.0 nats — INSIDE the ln 1e6 window containment watches) in batch 4, and at
  count = 9 in batch 13 the BIASED model peaks at 0.962 and the MIRROR model at 3.264, both outside the box
  entirely. The box, not the data, bounded those posteriors and the new check was right to say so. Both grids
  were widened at the SAME node spacing, so the comparisons are now over boxes that contain what they
  describe — which is what those tests were always about. No assertion was weakened.

**One rule was added after seeing results, and the numbers that forced it are recorded.** Routing
`validate_held_out` through the V2 judgement means the goodness-of-fit gate sees every coverage repetition's
calibration half — and a gate with a declared false-refusal rate refuses that fraction of WELL-SPECIFIED
repetitions by construction. Measured on the study's own reproducibility fixture (4 calibration temperatures,
2 residual degrees of freedom, truth = the fitted law, noise = the declared sigma): seeds 11 and 12 route and
PASS, seed 13 gives chi-square 13.6471 on 2 dof, p = 0.0011, and is refused. The sweep is FAIL_FAST, so one
refusal killed the whole study. `CoverageRepetition` therefore gained a trailing `route_refused_because`: a
refused repetition is RECORDED with its reason and zero intervals, and `CoverageStudy.why` states how many
were refused, which seeds, and that the coverage fraction is conditional on the repetitions that were
routable. What the VERDICT should do about that fraction is deliberately not decided here — a refused
fraction consistent with the gate's declared rate is a different thing from one that says the pipeline is
misspecified, and the threshold between them is a preregistration this batch does not have. It is part B's,
with the cluster-aware interval (R-36). Both entries are in the protocol's `amendment_log`.

**One observation recorded rather than fixed.** The refusal messages this batch newly surfaces read
"chi-square 129.887 on 4 degrees of freedom at the grid's best node, and a leverage-weighted **nan** against a
null mean of **nan**". The pooled half makes the refusal and it is correct; the leverage half (batch 11, I-04)
reports NaN rather than a number on these 2-parameter TCR grids. It changes no verdict measured here, and it
is a defect in another batch's rule — fixing it inside this batch would be an unpreregistered change to a
threshold that batch declared. Recorded in the protocol's `amendment_log` to be carried into I-14.

**Compatibility.** Additive only in shape: `QuantifiedPredictiveResult` gains one trailing field with a
default, `PredictiveObservationAssessment` one, `PredictiveDecomposition` and `HeldOutMetrics` two each, and
`CoverageRepetition` one. No field or member is removed, renamed or reordered and no existing default changes.
Every new key is serialized only when non-empty, so a record written before this batch keeps its bytes and
its digest, and no schema string is bumped. Two behaviours change on purpose and both are the improvement:
the study refuses a grid the router would not route, and an assessment over a truncating grid is not
content-bound.

**Committed evidence.** Nothing moved. `benchmarks/core_v2_hybrid_uq/TCR.json` records the hybrid-UQ route on
the TCR designs rather than the study's outputs, and no committed record in the repository carries a
`PredictiveDecomposition`, a `HeldOutMetrics` or a `PredictiveObservationAssessment`; the committed-evidence
suite passes unchanged. The `KINETICS_K2` and `BATTERY_T41` SUPERSEDED markers gain no entry: both are
hybrid-UQ route records and neither passes through the study.

**Guard mutations.** `BATCH17_MUTATIONS.log`: **12 of 12 KILLED**, control green. Two survived a first run and
the purchase is recorded: B17b and B17c RENAMED `_routed` and its call site together, which changes two
identifiers and no behaviour — the runner's "MUTATION CHANGED NO CODE" refusal does not catch a rename, and
both survived correctly. What each call site actually owns is the EVIDENCE it hands the judgement, so both
were repointed at `calibration=split.calibration, forward=forward`, and the two sites are told apart by
indentation as well as by scope. The 5 pinned mutations on the three files this batch changed were re-run
isolated and all 5 are still KILLED (`BATCH17_PINNED_MUTATIONS.log`), control green.

**Verification.** FAST tier 6652 passed, 5 skipped, 5 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors -- the recorded baseline's lists exactly. `tests/test_mutation_harness.py` 6 passed, every anchor intact;
`tests/mutation_guards.py` untouched. Nothing under `src/engcore/domains/thermal/` was edited.

**Open decisions.** None new. What a coverage verdict should do about a refused fraction is carried to part B
rather than decided here, and is written down in the protocol's `amendment_log` as such.

### Batch 18 — I-03 part B

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-03 | **DONE** | `e512de91`, `8b6360a7` (part A), `90ffb681` (part B preregistration + 15 strict xfails), this commit | the bias test uses the residuals' NOMINAL null, treating them as independent standard normals; they share one posterior, so the true sd of their mean is slightly above 1/√n and the test is slightly anti-conservative — the Mahalanobis statistic with the joint predictive covariance is the complete answer and needs a covariance `posterior_predictive_uq` does not return; the power floor is stated for a COMMON one-sigma bias and says nothing about power against a variance error or a pattern that cancels; the design-effect correction assumes exchangeable clustering within a repetition; the battery B1–B3 observations do not gain declared conditions, so their prediction-domain records stay `PREDICTION_DOMAIN_NOT_DECLARED` (I-13's); and `classify_coverage` still gives the pooled interval to a caller who passes only the two counts, which is what such a caller asked for |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-35 | **FIXED** | `HeldOutValidation` gained `INCONCLUSIVE`, and the rule moved into `held_out_verdict`, stated once and readable at its own boundary. Three answers: **FAIL** when either of two tests rejects; **INCONCLUSIVE** below `HELD_OUT_MINIMUM_N = 7`; **PASS** otherwise, in a sentence that now says NOT REJECTED rather than "consistent with", because that is what a test that did not reject has established. The second test is the one the omnibus chi-square cannot be: a sum of squares is blind to sign, and a truncated expansion leaves a common-sign bias — the audit measured a mean standardized residual of about 2.3 on every point while the model PASSED in 24 of 40 seeds at n = 1. The mean residual is tested directly (`z = √n · mean(r)`), and each test runs at half the declared alpha so the family-wise level is exactly the 0.01 the module already declared. **The floor is derived, not chosen**: the effect size of interest is a common bias of one DECLARED sigma per point — below its own measurement noise a model is not wrong in any way this evidence can speak to — and the bias test finds it at better than even odds exactly when √n ≥ z₁₋α/₂, i.e. n ≥ z² = 6.6349 at α = 0.01. A rejection still outranks the floor: FAIL is issued at any n, because a rejection is evidence whatever the sample size. |
| R-36 | **FIXED** | The coverage interval is computed at an EFFECTIVE sample size. `coverage_design_effect` estimates the intraclass correlation of the per-repetition indicators with the conventional one-way random-effects ANOVA estimator, forms `1 + (m̄ − 1)·max(ICC, 0)`, and divides the pooled count by it; the Wilson interval and the standard error use that, the POINT estimate stays the pooled fraction, and `CoverageStudy` records the intervals per repetition, the ICC, the design effect and the effective size so a reader can see the correction rather than trust it. The `max(ICC, 0)` clamp is the fail-closed direction: the estimator can come out negative, and inflating precision for negative clustering would claim more than the data has. The audited verdict flip reproduces — 1104/1200 reads CALIBRATED pooled and INCONCLUSIVE at an effective size of 574. And the refused fraction now DECIDES: a coverage verdict is INCONCLUSIVE when the fraction of repetitions the V2 judgement refused exceeds the study's own `acceptance_half_width`, because a refused repetition's intervals are unobserved and the selection alone can move the measured coverage by at most that fraction — **derived from a threshold the study already declares, with no new number**. |
| R-38 | **FIXED** | `observation_sigma` is optional on `predict_held_out` and `validate_held_out`. Given, INF-02's check is exactly what it was — that argument is the only thing standing between a caller and a self-chosen noise level, and the audit that added it measured the difference (chi-square 49.3 at the declared 0.002 ohm against 1.81 at a caller's 0.02 ohm). Omitted, each observation's own declared sigma is used, which is what the per-observation loop already did — so a half declaring [0.002, 0.002, 0.003] ohm is validated, where before no single value could validate it. And a coverage repetition records `CALIBRATION_NOT_RUN_GRID_POSTERIOR` instead of `CALIBRATION_CONVERGED`: it builds a grid posterior, no optimizer runs, and there is nothing for CONVERGED to be true of. Not a new `CalibrationStatus` member, because that enum's own docstring is "Did the optimizer find a minimum" and a value meaning none ran would be a legal thing for a `CalibrationResult` to claim. |

**Part A's residual closed too.** The TCR observations now declare the temperature they were measured at
(`GaussianObservation.conditions['temperature']`), and the study's predictive specs carry the condition they
are AT — so CORE-006 compares the prediction with the range the calibration covered instead of saying
`PREDICTION_DOMAIN_NOT_DECLARED` everywhere. The TCR flagship holds out temperatures above its calibration
range by design, and its routed records now read DOWNGRADED / `PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS`,
which is the true statement about an extrapolation. A study inside its calibrated range says nothing about the
domain, which is the other half of the same measurement.

**Both new thresholds are derived from numbers the module already declared.** `HELD_OUT_MINIMUM_N = 7` from
the module's own alpha through the bias test's power, and the refused-fraction limit IS the study's own
acceptance half-width. Neither is a number chosen after looking at a result, and the derivations are in the
protocol with the arithmetic.

**Existing expectations moved, six of them, each because a small held-out set cannot validate a model.**
Four tests asserted `HELD_OUT_VALIDATION_PASS` on 2, 3 or 4 held-out points; each now asserts INCONCLUSIVE
and, where the test's own claim was "this evidence is not against the model", asserts that too (neither test
rejects, p > 0.01). Two batch-17 tests asserted part A's own state — `PREDICTION_DOMAIN_NOT_DECLARED` and a
PASS at n = 2 — and part B supersedes both deliberately; the comments say so. No assertion was weakened: the
claim each test makes is unchanged and the word it reads is the honest one.

**Compatibility.** Additive in shape. `HeldOutValidation` gained one member — the round's first named additive
category. `CoverageStudy` gained five trailing fields with defaults. `observation_sigma` gained a default of
None on two study functions, which no existing call notices; it stays REQUIRED on `run_coverage_study`, which
synthesizes the observations and so needs the noise it draws from. `wilson_interval`'s two parameters are
typed float rather than int so the interval can be computed at a non-integer effective size; the arithmetic is
unchanged and an integer pair gives exactly the interval it always gave, which a no-regression guard measures.
No field or member is removed, renamed or reordered and no existing default changes.

**Committed evidence.** Nothing moved. No committed record in the repository carries a `HeldOutMetrics`, a
`CoverageStudy` or a serialized TCR observation. `benchmarks/calibration_uq/ROUND_REPORT.md` records a
`HELD_OUT_VALIDATION_PASS` in a historical table of a past round; it is pinned by no test and is not
rewritten, and its held-out verdict would now read INCONCLUSIVE for the reason above — 3 held-out points.

**Guard mutations.** `BATCH18_MUTATIONS.log`: **16 of 16 KILLED**, control green. Two needed a purchase on a
first run and both are recorded. B18m matched twice inside `run_coverage_study` -- the refused path and the
normal one carry the same line -- and the runner rightly refuses a mutation that is not one decision; it was
repointed at the constant, which is where the claim lives. B18o survived: dropping the conditions from
`predict_held_out`'s per-observation specs did not break the extrapolation test, because that test reads the
HELD-OUT VERDICT's routed record, which comes from the other spec. The per-observation records needed a guard
of their own, and
`test_r02_each_predictive_record_carries_its_own_conditions_domain_verdict` is it. The 5 pinned mutations on
the two files this batch changed were re-run isolated and all 5 are still KILLED
(`BATCH18_PINNED_MUTATIONS.log`), control green.

**Verification.** FAST tier 6672 passed, 5 skipped, 5 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors -- the recorded baseline's lists exactly. `tests/test_mutation_harness.py` 6 passed, every anchor intact;
`tests/mutation_guards.py` untouched. Nothing under `src/engcore/domains/thermal/` was edited.

**Open decisions.** None. The decision part A deferred — what a coverage verdict should do about a refused
fraction — is decided here, from the study's own acceptance half-width.

### Batch 19 — I-16

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-16 | **DONE** | `ac5099f7` (preregistration), `67aadd85` (12 strict xfails), this commit | the ledger covers the guard families whose reach this round MEASURED by R-xx, not every check in the tree — the inventory is `tests/mutation_guards.py`'s job and I-30's; the four bypass checks are syntactic, so a bypass through a dynamic dispatch, a `getattr` or an alias the checker does not resolve is not caught, and each row says per check what it cannot see; the verifier reads `src/engcore` only, so a bypass in `benchmarks/`, in a script or in a test is not checked; and two of the five rows (R-43, R-58) declare a MISSING producer, which no static check over the tree can measure at all — they are declarations, closed by I-25 and I-27 and by their own tests, not by a scan |

**What this improvement is.** I-16 fixes nothing about the science. It makes the REACH CLAIM checkable, and
that is this round's central finding: the guards were not wrong, they were written where production does not
go. `certification/guard_reach_ledger.json` now carries one row per guard family this round tracks, and
`tools/certification/guard_reach.py` refuses a row that is not checkable and finds the four bypass shapes the
audit named by reading the code. **A status is a declaration and the verifier checks what can be checked
about it; nothing infers reach from a grep**, which is why each row also says what its checks cannot see.

**R-xx recorded.** This batch closes no scientific problem. What it does is make five of them impossible to
mis-state, and it records three of them as unreached for the first time in a machine-readable place.

| ID | Ledger row | Why |
|---|---|---|
| R-01 | **LATENT**, audit status FIXED (I-01, batch 6) | `route_uncertainty` has no caller in `src` at all, so there is nothing for the rebuild rule to reach. LATENT and not LIBRARY_ONLY: LIBRARY_ONLY would say a production path bypasses the rule, and no production path asks for a rebuild. The row says what would create the shape — a production caller, which I-13 and I-07 are where one would arrive — and the `ROUTE_UNCERTAINTY_REBUILD_WITHOUT_MULTISTART` check turns the audited form (a rebuild policy passed together with `multistart=None`) into a build failure on that day. |
| R-02 | **REACHED**, audit status FIXED (I-03, batches 17–18) | `engcore.studies.calibration_study` — the only production consumer of the predictive layer — routes through `grid_predictive_uncertainty`, so every production prediction, held-out verdict and coverage repetition passes CORE-001, CORE-002, CORE-005, CORE-006 and CORE-010 before the frozen V1 interval is formed. Six tests exercise it through the study's own entry points. The residual is stated on the row rather than hidden by the status: the study is the only production path that predicts at all — the MCP tools run solvers and report credibility and form no interval, so there is no second path for this rule to reach. |
| R-09 | **REACHED**, audit status FIXED (I-11, batch 14) | `record_values` defaults to False on a V1-frozen symbol's method and before batch 14 nothing in `src` passed True. `DomainValidityContext.assess` now defaults it to True and the conduction and KCL sites pass it explicitly, so the CORE-014 binding has values to compare on every production path. D-14-1's residual is carried on the row: 59 of the 77 condition names across the 16 registered models are reserved derived quantities and 18 are declared inputs, so most names cannot be bound BY NAME and are reported in `unbound_assessment_values` rather than counted as agreements. |
| R-21 | **LIBRARY_ONLY**, closed by I-12 | `TrustedConsensusGate` has no caller in `src`. The one production consensus check is minted in `engcore.mcp.problem` and reaches `CrossSolverConsensus.to_check` — the scientific comparison and the string-declared independence — never the gate. What keeps that from being a false CROSS_SOLVER_VALIDATED is the `_withhold_level` wrapper, which strips the level: **a real mitigation, and exactly the kind of fact a ledger should record rather than leave to a reader's inference**. The hole is that the gate that WOULD verify the level is unreachable from production. `TO_CHECK_OUTSIDE_THE_GATE` is written so that unwrapping the mcp call fails the build, which is what stops the mitigation being lost quietly while I-12 is outstanding. |
| R-43 | **LIBRARY_ONLY**, closed by I-25 | `UncertaintySource` has no producer in `src`, so `source_kind` is UNSPECIFIED on every uncertainty production makes. Batch 8's I-09 gave the credibility report an `uncertainty` field, so the TRANSPORT reaches production and the DECLARATION does not — and an UNSPECIFIED kind is indistinguishable from a kind nobody was asked for, which is how an SRIA budget accepts NUMERICAL as model-form. |
| R-58 | **LIBRARY_ONLY**, closed by I-27, audit reach `yes` | The one row where LIBRARY_ONLY understates the risk rather than overstating it: the PROBLEM is reached in production — the production electrothermal coupling and the battery coupled step pass bare point values with no uncertainty, validity or validation state — while the GUARD is not, because `UncertaintyTransfer` has no caller. So a crossing that loses its uncertainty loses it silently. The ledger records the audit's own `yes` beside the guard's LIBRARY_ONLY, which is the pair a reader needs. |

**The rule that makes the ledger worth having.** Every problem a row marks `audit_status: FIXED` must have
reach REACHED or LATENT. **A fix to a rule production does not reach is not a fix to a production problem**,
and the verifier refuses to record it as one. Each row also carries the audit's own `reached_in_production`
value and the verifier refuses a row that disagrees with `REAUDIT_2026-09-16.json`, so the ledger cannot
drift from the audit it is about.

**Both directions are enforced.** A row naming a bypass the checker does not implement is a finding, and a
bypass the checker implements that no row names is a finding. A ledger the checker does not enforce is a
comment; a checker with rules the ledger does not name is a guard nobody declared. Either half alone is the
defect this round is about.

**Compatibility.** No production code changed. One JSON artifact, one tool module, one test file, and one
line of the shared mutation runner (`_COPY_TREES` gained `tools` and `certification`, because this batch's
guards live there and a copy without them cannot run the mutation at all). No V1-frozen symbol is touched and
no serialized record gains a field. The deliberate behaviour change is that the FAST tier now fails when
production gains an undeclared bypass of one of the four shapes, or when a ledger row stops being checkable.

**Two amendments, both recorded in the protocol with the numbers.** (1) The preregistered allow-list for
`ASSESS_VALIDITY_WITHOUT_RECORD_VALUES` was `domains/derived_context.py`; the committed list is **empty**.
Over the 233 production modules (52 under `src/engcore/domains`, carrying 7 assess call sites) the checker
finds 0 hits with no allow-list: batch 14 closed every site, and `derived_context.py` forwards
`record_values=record_values`, so the name is in the argument list the checker reads and that site was never a
hit. **An allow-list entry that is not needed is a hole nobody would notice** — if a later edit dropped the
flag from that helper, the entry would have hidden it. The reproduction could not keep its preregistered form
(`... != []`), because that assertion asserts a fixed defect stays broken; it now asserts the tree is clean
AND that the checker finds the shape in an injected source, the construction the `to_check` and rebuild
reproductions already needed. (2) Two refusals were added beyond the written list — an allow-list entry with
no reason, and an allow-list entry naming a path that does not exist. The first is the preregistered rule's
own words (`with a reason per entry`) made enforceable, which nothing had checked; the second catches a stale
entry surviving a rename. Both are strictly stricter and neither was added after seeing a result.

**Guard mutations, and the finding they produced.** `BATCH19_MUTATIONS.log`: **21 of 21 KILLED**, control
green (20 tests). Thirteen of them only kill because of a test this batch added after the fact:
**13 of the verifier's refusals had no reproduction at all**, so removing them left the whole suite green and
those mutations SURVIVED on the first run. That is a finding of exactly the kind I-16 exists to make visible —
a checker whose refusals nobody exercises is the same defect one level up — and
`test_i16_each_refusal_is_exercised` is the guard it asked for: twelve tampered ledgers, one per refusal, so
a rule deleted from `verify` fails a test rather than quietly widening what the ledger may say. The test is
not preregistered and says so in its own comment. The pinned re-run reports **NONE**: no mutation in
`tests/mutation_guards.py` targets `tools/` or `certification/`, which are new to the mutation population
(`BATCH19_PINNED_MUTATIONS.log`).

**Verification.** FAST tier 6697 passed, 5 skipped, 5 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors — the recorded baseline's lists exactly.
`tests/test_mutation_harness.py` 6 passed, every anchor intact; `tests/mutation_guards.py` untouched.
Nothing under `src/engcore/domains/thermal/` was edited.

**Three real failures the new file caused, and the fix.** `tools/certification/*.py` is inside the
`certification_control` scope area, and that area requires a reason for every file it certifies — "a file in
the control plane without a reason is a file nobody decided to trust". `tools/certification/guard_reach.py`
arrived without one, so `tests/test_certification_control_plane.py` failed three ways. The fix is the reason,
declared in `CERTIFICATION_CONTROL_FILES`: the verifier's own bytes are now certified, which is the right
answer for a checker whose weakening would let a guard whose reach nobody states pass as a guard production
runs. These were not by-design failures and were not treated as such.

**Open decisions.** None.

### Batch 20 — I-08 part A

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-08 | **PARTIAL** (part A of two) | `c2976119` (preregistration + 8 strict xfails), this commit | this part does nothing about R-13, R-14 or R-15: each probed direction is still bounded ALONE rather than as a matrix, the tails still run along the p axes only, and a tail probe beyond a declared bound is still dropped uncounted — part B owns all three, and the invariant basis is what its extreme-eigenvector probes will be built from; `POORLY_SCALED_CONDITION_LIMIT` is deliberately NOT in the serialized thresholds map, so a record cannot be checked against the limit that was in force when it was written (every other threshold this route uses is recorded; a schema bump is I-30's if the map is ever reopened); `hybrid_uq/predictive.py` builds its own probe directions and is not part of this part, so whether the PREDICTIVE probes have the same unit dependence is not measured here and is not claimed fixed; and `eps * kappa^2` is an order-of-magnitude bound on a solve's relative error, so the limit is where that bound reaches the module's own accepted tolerance, not a claim that the covariance's error IS 0.10 there |

**One claim, two problems.** The route's verdict must not depend on the units a parameter is declared in.

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-16 | **FIXED** | The probe basis is the CORRELATION eigenbasis scaled by the marginal standard deviations: with `D = diag(sd)` and `R = D⁻¹ cov D⁻¹`, the p unit-Mahalanobis axes are `δ_k = √μ_k · (sd · w_k)` for `μ_k, w_k = eigh(R)`. **It is the same points.** Under `z → S z` for diagonal `S` — a per-parameter unit change — `cov → S cov S` and `D → S D`, so `R` is INVARIANT and `w_k` with it; then `δ_k → S δ_k`, which names the same points in parameter space whatever unit each parameter is declared in. The old `√λ_k · v_k` from `eigh(cov)` also had Mahalanobis length 1, but a covariance's eigenvectors ROTATE under a diagonal rescaling, which is how the same model and data were SUPPORTED with a parameter in volts and REFUSED (`TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN`) in millivolts. **The new basis keeps the length exactly:** `δᵀcov⁻¹δ = μ_k · w_kᵀ R⁻¹ w_k = μ_k · (1/μ_k) = 1`, so `PROBE_SD²` is still what a rise is compared with. **And it changes nothing for an uncorrelated posterior:** `R = I` gives `μ_k = 1`, `w_k = e_k`, `δ_k = sd_k e_k` — exactly what `√cov_kk · e_k` already was. Only a correlated posterior's probes move, and they move to the invariant ones. Both the nonlinearity probes and the tail probes use it. |
| R-26 | **FIXED** | `POORLY_SCALED_PARAMETERIZATION` is emitted from the COLUMN-EQUILIBRATED condition number and never from the raw one, and the raw number stays RECORDED in `raw_jacobian_condition` without lowering a claim. **The limit is derived from two constants this module already declares.** The relative error of a linear solve at condition κ is of order `eps·κ²`; `NUMERICAL_CONDITION_LIMIT = 1/√eps` is exactly where that reaches 1 — where the covariance has no correct digits — and is already the refusal. The downgrade is where the same quantity reaches the tolerance this module already accepts for a wrong chi-square rise, `NONLINEARITY_DOWNGRADE = 0.10`: `κ = √0.10/√eps = √(NONLINEARITY_DOWNGRADE)·NUMERICAL_CONDITION_LIMIT = 21 221 686.1426478`. No number is chosen; it is the two declared constants combined the only way the units allow. **Why the raw number may not lower a claim:** any caller moves it by any factor by restating a parameter in a smaller unit, and nothing about the evidence moves with it — a claim that moves under a unit change is not a claim about the evidence. It is still worth recording, because it tells a reader their parameterization is badly scaled for a solver that does not equilibrate, and this one does. That is the strictness rule applied in the direction it points: what is recorded and not claimed is recorded. **The read-back rule moved with the emission rule**, and a non-refused record whose `raw_jacobian_condition` is NaN is now refused as a record that does not carry a number it claims to record — where before a missing diagnostic FORCED a downgrade, which is a statement about the evidence for a fact about the record. |

**Compatibility.** No V1-frozen symbol touched, no public signature changed, no serialized field added, removed,
renamed or reordered, and `_thresholds()` is unchanged — so every record written under
`hybrid_uq.route_diagnostics/2` still reads back, unless its `POORLY_SCALED_PARAMETERIZATION` came from a raw
condition number, which is the claim this rule corrects. `_probe_directions(lam, vec)` keeps its signature and
its meaning (it is handed the invariant basis instead of `eigh(cov)`'s), which also keeps
`hybrid_uq/predictive.py`'s pinned call site — mutation anchor G33o — byte-identical.
`POORLY_SCALED_CONDITION_LIMIT` is a new module-level name, which is additive.

**Existing expectations moved, four of them, none weakened.**

* `tests/hybrid_uq/test_hybrid_uq_local_route.py::test_a_poorly_scaled_parameterization_is_downgraded_not_silently_trusted`
  asserted the downgrade on R-26's own case, and that assertion WAS the finding: the case is a pure unit
  choice (raw 3.19e9, equilibrated 3.474, exactly Gaussian). It is now
  `test_a_unit_choice_is_recorded_and_never_downgrades_a_well_conditioned_fit`, and it still asserts that the
  raw condition is computed and recorded — a number nobody reads is a number that stops being computed.
* `tests/hybrid_uq/test_audit_hybrid_local_route.py::_tight_nonlinear` put its bounds at ±1.5 posterior sd so
  that every 2 sd probe left the box. With the invariant basis this correlated posterior (r = 0.552) is
  probed CLOSER IN along its per-parameter axes — the smallest per-axis excursion is 0.9468 sd — so the
  fixture's factor moves to 0.9 and every probe still leaves the box. The claim is unchanged: a route whose
  probes all left the bounds emits no covariance. It is the FIXTURE that followed the basis, not the
  assertion. The same fixture carries
  `test_audit_hybrid_records.py::test_huq09_a_legacy_route_with_every_probe_skipped_and_nonlinearity_zero_is_refused`.
* `test_audit_hybrid_records.py`'s `DIAGNOSTIC_EDITS["raw_condition"]` inflated the raw condition to 1e300 and
  expected a refusal. A huge raw condition no longer contradicts anything. The edit now REMOVES the raw
  condition instead, which is still refused — same claim, on the rule that replaced it.
* I-15's two conformance cases for R-16 and R-26 were strict xfails and now pass, so their markers came off
  with a line naming the fix, which is the ratchet I-15 is for.

**Committed evidence regenerated.** `benchmarks/core_v2_hybrid_uq/FAILURE_CASES.json`, all cases met.
`poorly_scaled_parameterization`'s declared expectation is restated from DOWNGRADED /
POORLY_SCALED_PARAMETERIZATION to SUPPORTED: that adversarial case was only ever adversarial about its units,
which is R-26 stated as an artifact rather than as a sentence. So the downgrade would have been left with no
end-to-end case, and one was added — `ill_conditioned_after_equilibration`, a quartic fitted over a 10% range
of x (equilibrated condition 4.36e7, inside the band between the new limit and the refusal), which no unit
change repairs because the monomial basis is nearly collinear on that interval whatever each coefficient is
measured in. Both rows are pinned in `test_hybrid_uq_committed_evidence.py` so neither half of the correction
can be dropped silently. `KINETICS_K2.json` carries `POORLY_SCALED_PARAMETERIZATION` and is NOT regenerated
(its MULTI multistart alone is ~76 min of CSTR solves); its SUPERSEDED marker stands and this rule is one
more reason it is superseded.

**Guard mutations, and the three findings they produced.** `BATCH20_MUTATIONS.log`: **11 of 11 KILLED**,
control green. Three survived on the first run and each survival was informative rather than a mis-aimed test.

* **B20d** (the marginal sds dropped from the scaling) survived the uncorrelated-posterior guard — and
  rightly: for a DIAGONAL covariance the two formulas COINCIDE, which is the property that guard exists to
  pin and exactly the reason it cannot see this mutation. Repointed at the invariance guard, where the
  mutation is the defect.
* **B20e** first sent the tail probes to the declared COORDINATE axes and survived. That is a correct result
  and it corrected the mutation: `sd_k · e_k` is ITSELF invariant under a per-parameter rescaling, so the
  defect is `eigh(cov)`, not being off the eigenbasis. Rewritten to restore `eigh(cov)` for the tails alone.
* **B20h** (the emission rule deleted outright) survived because every other R-26 guard either asserts the
  downgrade is ABSENT on a well-conditioned fit or works on a hand-edited record — nothing ran a genuinely
  ill-conditioned problem through the route and read what it said.
  `test_r26_an_ill_conditioned_parameterization_is_downgraded_end_to_end` is the guard that finding asked for,
  on the same quartic the new FAILURE_CASES row uses. It is not preregistered and says so in its own comment.

The 10 pinned mutations on `local_gaussian.py` were re-run isolated and all 10 are still KILLED
(`BATCH20_PINNED_MUTATIONS.log`), control green.

**Verification.** FAST tier 6711 passed, 5 skipped, 3 xfailed, 18 failed (the by-design 18, unchanged — the
two xfails that became passes are I-15's R-16 and R-26 cases, which is why the xfail count fell from 5 to 3).
Expensive tier 528 passed, 18 failed, 14 errors — the recorded baseline's lists exactly.
`tests/test_mutation_harness.py` 6 passed, every anchor intact; `tests/mutation_guards.py` untouched. Nothing
under `src/engcore/domains/thermal/` was edited.

**Open decisions.** None.

### Batch 21 — I-08 part B

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-08 | **DONE** | `c2976119`, `7d9ae9fa` (part A), `1b1bafae` (part B preregistration + 12 strict xfails), this commit | the curvature matrix is a FINITE-DIFFERENCE second derivative at radius `PROBE_SD`, not the Hessian at the estimate — for a genuinely quadratic chi-square they agree exactly, and for anything else it mixes the curvature with the quartic and higher terms at 2 sd, which is the right thing to threshold here (the claim being checked is that the Gaussian describes the posterior out to 2 sd) but means the index is not an estimate of anything at the optimum; M is built over a complete sub-block when probes are missing, so a posterior with a declared bound inside 2 sd on one parameter gets a gate over the others and the record does not say which indices it covered; the extreme-eigenvector tail probes are chosen by a matrix built from the ±2 sd probes, so the p² fixed directions are what carry R-14 and the two extremes are an addition rather than the mechanism; clipping compares a rise with `r_clip²` under the same Gaussian prediction and is not a claim that the tail beyond the declared box is Gaussian; and `hybrid_uq/predictive.py` still builds its own probe directions, which neither part measured |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-13 | **FIXED** | The whitened curvature matrix is rebuilt from the SAME ±2 sd probes the route already evaluates — no new forward evaluation, because a local quadratic `Q(u) = uᵀMu` is fully determined by the p axes and the p(p−1) diagonals: `M_kk = mean_sign Q(±s e_k)/s²` and `M_ij = (Q̄₊ − Q̄₋)/(2s²)` with `s = PROBE_SD`. **The gate reuses the two declared thresholds and needs no new number**, and the reason is an identity: the per-direction index the route already thresholds is `\|Q(s d)/s² − 1\| = \|dᵀMd − 1\|`, and the supremum of that over ALL unit directions IS `max(\|λ_max − 1\|, \|1 − λ_min\|)`. So the matrix index is the same quantity maximized over every direction instead of evaluated at 2p² of them, it DOMINATES every per-direction index, and `nonlinearity_index` becomes their maximum — so no record's reasons stop following from its numbers. The audited case reproduces the preregistered arithmetic: at p = 10 with `M = I + c(J − I)` and `c = −0.099` the eigenvalues are 1.099 (multiplicity 9) and `1 + 9c = 0.109`, the index is 0.891 against `NONLINEARITY_REFUSE = 0.50`, and the case is REFUSED where every per-direction probe sat at 0.0992 under the 0.10 downgrade. A probe beyond a bound leaves an entry unmeasured, and M is then built over the largest index set whose axis probes and all of whose pairwise diagonals were evaluated — a principal submatrix's extremes still bound the worst direction from below, so the restriction never loosens the gate. `curvature_eigenvalue_bounds` records `(λ_min, λ_max)` and read-back refuses a record whose index is below what its own extremes imply. |
| R-14 | **FIXED** | The 3 and 6 sd tail probes run along every direction the ±2 sd probes cover — the p invariant axes and the p(p−1) diagonals — plus the `λ_min` and `λ_max` eigenvectors of the curvature matrix, mapped back into parameter space and normalized to unit Mahalanobis length. p² + 2 directions where there were p. **Why these and not a sphere sample:** a heavy tail has to be looked for where the local quadratic is least trustworthy — the diagonals are where a cross term lives, which is why the ±2 sd probes already cover them, and the `λ_min` direction is the one the matrix itself says is flattest. A quasi-random sample would be a different rule with a sample size to justify. The audit's own note said I-08 must supply a case with more than two residual degrees of freedom so that what carries it is the probe and not I-04's underpowered cap, and `off_axis_flat_tail_with_residual_dof` is it: 6 observations, 2 parameters, exactly Gaussian along both invariant axes out to 6 sd (rises 4, 9, 36) and a rise of 15.92 against the Gaussian's 36 along either diagonal — a ratio of 0.442, below `TAIL_REFUSE_RATIO`. At the baseline it was SUPPORTED with NO reason at all and a minimum tail rise ratio of 1.0; it is now REFUSED. |
| R-15 | **FIXED** | A tail probe whose point leaves the declared box is CLIPPED to the largest radius the box allows and its rise compared with `r_clip²` — the Gaussian's prediction at the radius actually probed — instead of being dropped. No posterior mass lies outside a declared bound, so the original reasoning was right and the SILENCE was the defect: at 6.01 posterior sd the 6 sd probe ran and refused, at 5.99 it vanished and the claim rose. The two now agree, at ratios 0.2595 and 0.2588. A clipped probe is counted in `tail_probes_clipped`; a probe the box stops below `PROBE_SD` is not used, because the ±2 sd probes already measured that radius against their own rule, and it is counted in `tail_probes_outside_bounds` and downgrades. **The floor IS `PROBE_SD`** — a declared constant, not a choice — because using a clipped probe inside it would threshold the same measurement twice against a different rule. |

**Compatibility.** `RouteDiagnostics` gains three TRAILING fields with defaults (`curvature_eigenvalue_bounds`,
`tail_probes_clipped`, `tail_probes_outside_bounds`), each serialized only when it carries information, and
`RouteReason` gains one APPENDED member. Both are the allowed additive shapes. `_thresholds()` gains no key,
for the same reason as batch 20. The one existing read-back bound that moves is WIDENED — the tail-count
budget from `2·len(TAIL_PROBE_SD)·p` to `2·len(TAIL_PROBE_SD)·(p² + 2)` — and widening an upper bound cannot
refuse a record that satisfied the narrower one. So every record written under
`hybrid_uq.route_diagnostics/2` still reads back. `_probe_directions(lam, vec)` keeps its signature, and the
two pinned diagonal lines inside it are byte-identical: the labelled variant builds the same list and zips the
labels beside it, which is what keeps mutation anchor G33c matching.

**One amendment, with the numbers that forced it.** The preregistration said a probe the box stops inside
`PROBE_SD` "adds the existing NONLINEARITY_PROBE_INCOMPLETE downgrade". It gets an appended member of its own,
`TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS`, because folding the two together made the fact R-15 is ABOUT
unobservable. **Two guard mutations that removed the rule both SURVIVED**, and the reason is structural rather
than a gap in the tests: along any of the p² fixed probe directions the box stops a tail probe inside
`PROBE_SD` only when it also stops that direction's own ±2 sd probe, because both conditions are the same
inequality on the box reach — so `nonlinearity_probes_skipped` is non-zero in every such geometry and already
emits the same word. At a bound of 1.5 posterior sd the audited case records
`nonlinearity_probes_skipped = 2` and `tail_probes_outside_bounds = 4`. A probe the box stopped inside the
radius the ±2 sd probes already cover is a different fact from a ±2 sd probe that left the box, and R-15 is
precisely about that fact being silent. The correction is strictly additive: the member is appended, both
counts default to 0, and no record written before the rule gains a reason.

**Existing expectations moved, three of them, none weakened.**

* `test_the_cost_is_order_p_plus_multistart` pinned `4p + 1 + 2p² + 4p`. The tail term is now
  `4(p² + 2)`: 41 evaluations at p = 2 where there were 25. The ORDER is unchanged — the diagnostics were
  already O(p²) — and the constant goes from `2p² + 4p` to `6p² + 8`, about 3× at large p. The comment carries
  the arithmetic and why.
* `test_hybrid_uq_tcr.py::test_the_local_route_agrees_with_the_resolved_grid[narrow]` asserted SUPPORTED. The
  NARROW TCR design's smallest chi-square rise ratio is 0.8127 — the rise 6 reported sd out along the flattest
  direction of its curvature matrix is 29.3 where a Gaussian predicts 36 — which is below
  `TAIL_DOWNGRADE_RATIO = 0.90`. **That is a real measurement on a model that IS non-quadratic that far out,
  found by directions no axis probe reaches; no threshold moved.** The test now expects DOWNGRADED with
  `TAIL_HEAVIER_WITHIN_6_SD` for that design and SUPPORTED for WIDE, and every numeric agreement assertion
  against the dense grid is unchanged and still holds to within 5%. What moved is the WORD.
* The two I-15 conformance cases for R-13 and R-15 were strict xfails and now pass, so their markers came off
  with a line naming the fix.

**Verification.** FAST tier 6728 passed, 5 skipped, 1 xfailed, 18 failed (the by-design 18, unchanged). The
xfail count is 1 because the four I-15 conformance cases this improvement closed — R-13, R-14's sibling R-15,
R-16 and R-26 — have had their markers removed across batches 20 and 21; the one left is R-11's, waiting for
I-06. Expensive tier 528 passed, 18 failed, 14 errors — the recorded baseline's lists exactly.
`tests/test_mutation_harness.py` 6 passed, every anchor intact (G33c needed the labelled probe list to be
built so that its two pinned diagonal lines stay byte-identical, which is how it is written);
`tests/mutation_guards.py` untouched. Nothing under `src/engcore/domains/thermal/` was edited.

**Committed evidence regenerated.** `FAILURE_CASES.json`, all cases met; `multimodal_two_parameter` gains
`TAIL_HEAVIER_WITHIN_6_SD` beside the refusal it already had, which changes no claim. `TCR.json`: NARROW's
`v2_local.claim` SUPPORTED → DOWNGRADED with `reasons` `['TAIL_HEAVIER_WITHIN_6_SD']`, forward evaluations
250 → 266, nonlinearity index 0.0753 → 0.0709 (the invariant basis from part A, folded in by the same
regeneration); WIDE unchanged but for 190 → 211 evaluations and 0.00523 → 0.00432. The guard in
`test_hybrid_uq_committed_evidence.py` now pins both claims and NARROW's reason, so neither half can be
dropped silently. `PERFORMANCE.json` regenerated for the evaluation counts; its own guard is an inequality
(`forward_evaluations >= 4p + 1 + evaluated_probes`) and still holds. `KINETICS_K2.json` and
`BATTERY_T41.json` are NOT regenerated (their full runs are ~76 min and longer); their SUPERSEDED markers
stand and these rules are two more reasons they are superseded.

**Guard mutations, and the five findings they produced.** `BATCH21_MUTATIONS.log`: **18 of 18 KILLED**,
control green, plus 10 pinned re-runs on `local_gaussian.py` all KILLED. Eight survived the first run and
every survival was informative:

* **B21d** (one sign accepted as the sign-averaged rise) survived the recovery test, which feeds EVERY probe,
  so a rule about a MISSING probe was invisible to it. A new guard deletes one sign and asserts the index is
  left out of the matrix — and that one complete index yields no matrix at all rather than a 1×1 one that
  repeats its own axis probe.
* **B21i** (each extreme eigenvector replaced by an axis already in the set) survived a count and a
  unit-Mahalanobis check, which a duplicate passes. The guard now asserts the last two directions ARE the
  mapped eigenvectors.
* **B21k** (a clipped probe compared with the radius it ASKED for) survived the audited 6.01/5.99 pair, and
  rightly: those radii differ by 0.2%, which no verdict can resolve. At a bound of 2.5 sd the factor is 5.8 —
  0.985 of the radius reached against 0.171 of the radius asked for — and the guard reads that case.
* **B21l** and **B21n** survived `> 0` assertions that half a rule still satisfies. The clipped count is now
  asserted exactly: two, at a bound of 5.99 sd.
* **B21m**, **B21m2** and **B21p** and **B21o** are the amendment and its consequences, above; B21o survived
  because popping a key a record DOES carry says nothing about a record that should not carry it, and the
  guard now reads a p = 1 route, which builds no matrix.

**Open decisions.** None.

### Batch 22 — I-13 part A

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-13 | **PARTIAL** (part A of two) | `dd96dfcc` (preregistration + 10 strict xfails), this commit | the convex hull is the region BETWEEN observed operating points, which is an interpolation claim and not a validity claim — a model can be wrong strictly inside it and nothing here says otherwise; the digest binds the OBSERVATIONS to the posterior and binds the `predict` evaluator to nothing, so a caller can still hand a predictive model the calibration never used (R-23, part B, is where the grid route's half of that closes); a condition declared by some observations and not others is still dropped from the design, which is the existing rule's meaning; the stored design is filled only on a non-refused local route; and part B still owns R-37 (the linearized nonlinearity is pooled across specs and never refused) and R-23 |

**One claim, two problems.** A prediction's domain statement must be bound to the calibration it came from.

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-12 | **FIXED** | ONE canonical digest of the observation CONTENT — `digest_of(observations.to_dict())`, over the existing canonical serialization: the dataset id and, per observation, the condition id, observable, value, sigma, source ref and declared conditions with their units. `LocalGaussianPosterior` carries it, and `linearized_predictive_uq` RAISES when the `calibration_observations` it is handed do not digest to it. **A raise and not a downgrade**, because a caller who supplies them is ASSERTING that these are the observations the posterior was calibrated on: that assertion is true or false, not evidence to be weighed, and a caveat on a false assertion reads as a statement about the science. It is the same shape as CORE-005's refusal for a grid that is not this request's evidence. **The content and not the dataset id**, because two of the three audited reproductions keep the id and change the content — the conditions rescaled, or the values replaced by a predictor evaluated elsewhere. And the posterior now carries the calibration's own condition design, so supplying NO observations applies the check instead of silencing it: an extrapolation to x = 1e4 is measured rather than reported with a caveat. |
| R-31 | **FIXED** | Two things. **Every condition the calibration declares must be declared by the prediction**, or nothing shows where the prediction sits — which is what `PREDICTION_DOMAIN_NOT_DECLARED` says. The gate looped over the PREDICTION's conditions, so a prediction that simply left one out was compared on the rest: a prediction at T = 900 K against a calibration at T = 300 K was DOWNGRADED and the same prediction with T omitted was SUPPORTED. It is deliberately not answered by taking the value from the calibration, which would be inventing the prediction's operating point. **And the domain is the JOINT SUPPORT**: a prediction is inside when its condition vector is a convex combination of the calibration's condition rows, decided by a small linear program on the residual and compared with the tolerance the rule already declared. **At one condition the convex hull of the observed values IS the [min, max] interval it replaces**, so nothing about a single-condition study moves and no new number is introduced; at two or more it describes the region the calibration covered instead of the bounding box around it — with observations on a line in (T, load), a prediction inside both marginal ranges and 0.707 of the scaled spread off that line now reads `PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS`. The hull also degenerates correctly: a calibration at one point admits only that point, and one that varied k conditions independently admits its box. |

**Compatibility.** `LocalGaussianPosterior` gains three TRAILING fields with defaults
(`calibration_content_digest`, `calibrated_conditions`, `calibrated_condition_points`), each serialized only
when it carries information, so every record written under `hybrid_uq.local_gaussian_posterior/1` still reads
back. `ObservationSet` is NOT touched — the digest is a private helper over its existing `to_dict`, so no
V1-frozen symbol gains a member. No function gains a required argument and no predictive record gains a field.

**Two amendments, both recorded with what forced them.** (1) The hull linear program is solved with HiGHS's
feasibility tolerances set to 1e-10. Its DEFAULT is 1e-7, a hundred times coarser than
`PREDICTION_RANGE_RELATIVE_TOLERANCE`: at the default, a departure of 1e-8 of the observed spread — ten times
the declared tolerance — returned an objective of exactly 0.0 and read inside, so the rule would have been
silently a hundred times looser than it says. A rule whose decision the solver cannot resolve is the solver's
tolerance wearing the rule's number; the correction makes the solver meet the declared tolerance rather than
moving the tolerance to suit the solver. (2) The condition lookup and the unit conversion are two statements
rather than one `try`. A single broad catch around both swallowed the `KeyError` a missing name raises and
returned `PREDICTION_DOMAIN_NOT_DECLARED` anyway, which made the explicit missing-name rule unobservable —
a guard mutation removing it survived. The same broad-catch shape hid the condition design's INTERSECTION
rule, and that catch is now by type (`UnitCompatibilityError`).

**Existing expectations moved, three of them, none weakened.**

* `test_core_scientific_audit_batch4.py::test_core006_a_prediction_with_no_declared_domain_is_downgraded`
  asserted that supplying no `calibration_observations` ALSO reads `PREDICTION_DOMAIN_NOT_DECLARED`. That was
  the simplest form of R-12: the gate had nothing to compare, so an extrapolation was reported with a caveat
  instead of being measured. It now asserts the true statement — x = 0.5 is inside the calibrated range and
  the record says nothing about the domain — and the same test now also asserts that x = 1e4 with no
  observations supplied is `PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS`. The half the test is named for is
  unchanged: a prediction that declares NO conditions still has no domain to state.
* `test_hybrid_uq_identifiability_predictive.py` and `test_hybrid_uq_trust_boundary.py` built their
  posteriors on the bare observations and then passed `S.conditioned(...)` — the same observations with the
  conditions declared afterwards — as `calibration_observations`. Both fixtures now CALIBRATE on the
  conditioned set. A rule that accepted the same observations with conditions ADDED could not tell that apart
  from the same observations with their conditions RESCALED, which is one of R-12's three reproductions; the
  conditions are part of the evidence and belong on the observations the fit used. The fit itself is
  unchanged, because a declared condition enters no residual, and both fixtures still assert SUPPORTED with
  no reasons.

**Verification.** FAST tier 6744 passed, 5 skipped, 1 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors — the recorded baseline's lists exactly.
`tests/test_mutation_harness.py` 6 passed, every anchor intact; `tests/mutation_guards.py` untouched. Nothing
under `src/engcore/domains/thermal/` was edited.

**Committed evidence.** Nothing moved. The production TCR study declares one condition, where the hull rule
and the interval rule agree exactly, and no committed record carries a `calibration_observations` mismatch or
a prediction that declares a strict subset of its calibration's conditions — so `FAILURE_CASES.json`,
`TCR.json` and `PERFORMANCE.json` are unchanged and were not regenerated. `KINETICS_K2.json` and
`BATTERY_T41.json` keep their SUPERSEDED markers.

**Guard mutations, and the five findings they produced.** `BATCH22_MUTATIONS.log`: **12 of 12 KILLED**,
control green, plus 18 pinned re-runs on the two changed files all KILLED. Five survived the first run:

* **B22f** (the missing-name rule deleted) and **B22e** (the design's intersection turned into a union) both
  survived because a broad `except Exception` caught the `KeyError` each mutation then raises and answered
  with the same reason. Both catches are now by type, and the amendment above records it.
* **B22i** (hull weights allowed to go negative, which makes the region the affine SPAN) survived the off-line
  point, which is off the span as well. The case added for it is an extrapolation ALONG the calibrated line,
  20 K past its last observation, where the span and the hull differ.
* **B22k** (the per-condition scaling replaced by ones) survived every reproduction, which were all far
  outside or exactly inside. The case added for it sits a tenth of the tolerance inside and ten times it
  outside — and that case is what exposed the solver tolerance.
* **B22l** (a condition the calibration never declared silently ignored) survived because every reproduction
  declared exactly the design's names.

**Open decisions.** None.

### Batch 23 — I-13 part B

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-13 | **DONE** | `dd96dfcc`, `2fff3b4f` (part A), `49e0b2f2` (part B preregistration + 9 strict xfails), this commit | the spot-check is three nodes, so a table wrong only at low-weight interior nodes is not caught — the bound is each such node's weight times its deviation on the mean, and nothing tighter is claimed; a FINITE nonlinearity is still only a downgrade however large, which is what the improvement's brief asks for (a finite refusal threshold would be a separate rule with its own consequences for committed evidence); `PREDICTIVE_TABLE_NOT_CHECKED` is not re-derived on read, because a record does not carry whether a `predict` was available when it was built, which is the limit every build-time-only reason in this module has; the check compares the table with `predict` in the SPEC's unit, so a table built in another unit of the same dimension disagrees at roundoff and reads as a disagreement rather than a unit mismatch; and nothing here binds `predict` to the calibration's own forward model, which is the limit part A already stated |

**Two problems about the prediction's numbers.** Part A bound the domain statement; part B is what the record
says about its own uncertainty and where its numbers came from.

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-37 | **FIXED** | The probe deviations were already a vector over the specs and the maximum was taken over the whole CALL, so an exactly affine prediction in the same call as a quadratic one recorded the quadratic one's number — and its own read-back rule then derived `PREDICTIVE_NONLINEAR` for it from someone else's curvature. Each record now carries the maximum its OWN probes measured. And a spec whose nonlinearity is not finite is REFUSED: `linearized_predictive_uq` raises naming it, and a record carrying an infinity is refused on read. **Why a refusal and not a downgrade:** inf is not a large nonlinearity, it is the absence of a scale to measure one against. The deviation is expressed in units of the PARAMETER standard uncertainty because that is what the reported interval is built from; where that uncertainty is exactly 0 the interval is a point, and a probe that moves the prediction at all says the point is wrong by an amount the interval cannot express. There is no number to downgrade — which is what "a refused route emits no predictive uncertainty" already says everywhere else in this module. NaN keeps exactly the meaning it had: nothing was measured, which is `NONLINEARITY_PROBE_INCOMPLETE`. |
| R-23 | **FIXED** | `grid_predictive_uncertainty` and `routed_predictive_uncertainty` take `predict` on the grid path, and the router used to accept it and apply it only on the LOCAL path — a grid result read its numbers out of the table with the model sitting unused in the same call. The table is now checked against it **at the nodes the reported numbers stand on**: among nodes admissible in both the posterior and the table and carrying non-zero posterior weight, the node of maximum posterior weight and the nodes attaining the table's smallest and largest value for this prediction. **Why those and not a count:** a count would be a threshold with nothing behind it. These are the nodes the answer is made of — the reported mean is dominated by the highest-weight node, and the reported interval's ends cannot lie outside the table's extreme values over the support — so the audited factor-of-two table disagrees at the first of them. The tolerance is roundoff (`64·eps·max(|table|, |predict|)`, the form this module already uses), because `predict` is deterministic and the table is supposed to BE its values; a disagreement RAISES, the same shape as part A's digest refusal. And a grid prediction made with no `predict` carries a new appended downgrade, `PREDICTIVE_TABLE_NOT_CHECKED` — without it the check would be silenced by omitting an optional argument, which is R-12 one layer down, and R-12 is the problem part A of this same improvement closed. |

**The reach half.** `engcore.studies.calibration_study` — the one production path to a predictive interval —
BUILDS its predictive table from its own production forward model, so it now hands that model to the check on
every prediction and its records are checked rather than downgraded. A production record reading
`PREDICTIVE_TABLE_NOT_CHECKED` would mean the study had the model and did not use it, and
`test_core_scientific_audit_batch17.py::test_r02_a_predictive_decomposition_carries_its_route_claim_and_reasons`
now asserts it does not.

**Compatibility.** `RouteReason` gains one APPENDED member. `grid_predictive_uncertainty`,
`routed_predictive_uncertainty` and the study's private `_routed` gain one keyword argument;
`predictive_nonlinearity` already existed and only its VALUE becomes per-spec. No record gains a field. A
record written before this batch still reads back: `PREDICTIVE_TABLE_NOT_CHECKED` is derived at BUILD time
from the absence of an argument and is never re-derived on read, so an old grid record without it is not
refused. The non-finite refusal is a new read-back rule and no committed record carries a non-finite
nonlinearity — the audit found that shape in a constructed case, not in evidence.

**Existing expectations moved, two of them, neither weakened.**
`test_audit_hybrid_grid_route.py::test_huq02_a_resolved_grid_is_still_supported_through_the_same_judgement`
now passes a one-output `predict` for its SUPPORTED case — the claim it asserts is unchanged, and the test
gained two new assertions: the same grid with no `predict` carries exactly
`PREDICTIVE_TABLE_NOT_CHECKED`, and the unbound case's reason list grows by it. One test in batch 17 gained
the production assertion above.

**Verification.** FAST tier 6754 passed, 5 skipped, 1 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors — the recorded baseline's lists exactly.
`tests/test_mutation_harness.py` 6 passed, every anchor intact; `tests/mutation_guards.py` untouched. Nothing
under `src/engcore/domains/thermal/` was edited.

**Committed evidence.** Nothing moved, and nothing was regenerated. `TCR.json`, `FAILURE_CASES.json`,
`PERFORMANCE.json` and `WHEEL_V2.json` build their predictive numbers through the frozen
`posterior_predictive_uq` directly, not through `grid_predictive_uncertainty`, so neither the table check nor
the new downgrade reaches them. `KINETICS_K2.json` is the one record built through the routed grid path and
it is NOT regenerated (its MULTI multistart alone is ~76 min of CSTR solves); its SUPERSEDED marker stands
and these two rules are two more reasons it is superseded.

**Guard mutations.** `BATCH23_MUTATIONS.log`: **12 of 12 KILLED on the first run**, both controls green, plus
25 pinned re-runs on the three changed files all KILLED. Nothing survived, which is the first batch in this
round where that happened — the guards were written from the reproductions rather than around them, and two
of the twelve (B23d and B23h) exist precisely because the obvious mutation of a rule is not the only one: a
per-spec array can be computed and then overwritten by its own maximum, and a roundoff tolerance can be
turned into a threshold without removing a line.

**Open decisions.** None.

### Batch 24 — I-12 part A

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-12 | **PARTIAL** (part A of two) | `23609299` (preregistration + 6 strict xfails), this commit | after the reclassification **VALIDATED is unreachable in production** — `oracles._TRUSTED_ORACLE_DECLARATIONS` is empty, so BENCHMARK_VALIDATED and EXPERIMENTALLY_VALIDATED cannot be awarded, and cross-solver agreement no longer counts. That is the honest state of the tree: nothing in production compares a result with anything outside the model that produced it, and it is recorded rather than papered over by keeping the label reachable; `evidence_basis` still covers the WHOLE report rather than each value (CORE-009/VAL-01's residual, I-20's to close); part B still owns R-21 — the level earned from hand-written independence, the gate with no caller, and a non-independent disagreement that warns instead of blocking |

**R-xx closed.**

| ID | Status | How |
|---|---|---|
| R-39 | **FIXED** | `ValidationLevel.CROSS_SOLVER_VALIDATED` leaves `VALIDATION_LEVELS`, so `evidence_basis` and `mcp.evidence.evidence_basis_of` return VERIFICATION_ONLY for a report whose validating evidence is agreement between two solvers. The enum member is unchanged — same name, same value, same position — and the level is still ATTAINED and still says what it said; what changed is the KIND of evidence it is counted as. **This removes a contradiction rather than adding a judgement**, and the contradiction is with three statements the tree already makes about itself: `evidence_basis`'s own docstring defines these levels as the ones that "compare it with something outside itself"; `scientific/consensus.py` says two routes may "realize the same mathematical formulation" and still count as independent, because only shared ARITHMETIC is excluded — `SOLVER_INDEPENDENCE_DIMENSIONS` leaves the problem declaration out and that module's docstring says a declaration error "is invisible to every route that reads it"; and each pinned pair of routes shares its declaration (both DC routes declare `DCCircuit`, both CSTR routes declare `ReactorRun`, and the consensus record lists that declaration as a SHARED dependency) while solving the same declared relations, which `domains/electrical/dc/models.py` states are SELF_CONSISTENT — "not BENCHMARK_VALIDATED … certainly not EXPERIMENTALLY_VALIDATED". So a result whose only other levels were dimensional validity and convergence moved from VERIFICATION_ONLY to VALIDATED the moment a cross-solver check was attached, and a circuit declared with a wrong resistor value read VALIDATED because both solvers agree about the wrong model. |

**The other kind is now named too.** A new `VERIFICATION_LEVELS` holds DIMENSIONALLY_VALID,
NUMERICALLY_CONVERGED, ANALYTICALLY_VERIFIED and CROSS_SOLVER_VALIDATED, and `validation.py` refuses to
import while the two sets overlap, while `UNVERIFIED` is in either, or while any other member is in neither.
**That is the structural half of R-39**: one kind was a set and the other was "the rest", so a member added
later was silently verification and nobody had to decide — which is how this level ended up in the wrong
group, and the adjudication records that the classification "was a choice, not an accident". It is the same
discipline `mcp/server.py::_audit_tables` already applies to the verdict tables.

**Compatibility.** No symbol removed, renamed or reordered; no dataclass field, default or signature
changed. `VALIDATION_LEVELS` keeps its name and type and loses one element, which is what the audit's own
`fix_direction` for R-39 asks for. `VERIFICATION_LEVELS` is additive. The deliberate behaviour changes are
stated in the protocol: `required_evidence_basis="VALIDATED"` is no longer satisfied by cross-solver
agreement (so a caller who demanded validation and was being given code-to-code verification now reads
`required_evidence_basis_not_attained`), and a stored report whose `verdict_qualifiers` say VALIDATED on
cross-solver evidence alone stops reading back — the qualifier is re-derived and enforced, which is the
existing rule doing its job on a corrected classification.

**Committed evidence.** Nothing moved. A search over `benchmarks/` and `certification/` found no artifact
carrying `evidence_basis: VALIDATED`; the only hits are this round's own protocol and audit JSON, which are
text about the problem. The audit's own reach note says the one production serialized path withholds the
level.

**One existing expectation moved, and it is a comment.** `tests/test_core_guards.py` and two vertical tests
refuse a domain noun anywhere in the scientific core, including in prose — the first draft of the
`VALIDATION_LEVELS` comment named the resistor and the CSTR routes, and `'resistor' leaked into
validation.py`. The comment now states the same argument abstractly (each pinned pair shares its
declaration; the declaring layer states the relations are SELF_CONSISTENT) and points at this document,
which is where the core is allowed to know the instances. **No test was weakened**: the guard was right and
the comment was wrong.

**Verification.** FAST tier 6761 passed, 5 skipped, 1 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors — the recorded baseline's lists exactly.
`tests/test_mutation_harness.py` 6 passed, every anchor intact; `tests/mutation_guards.py` untouched. Nothing
under `src/engcore/domains/thermal/` was edited.

**Guard mutations, and what they taught about the check itself.** `BATCH24_MUTATIONS.log`: **5 of 5 KILLED**,
both controls green. The first run had two COLLECTION_BROKEN and two SURVIVED, and the reason is worth
recording: `_require_every_level_is_classified` runs at IMPORT, so a mutation that leaves the level in both
sets or in neither does not produce a wrong verdict — it produces a tree that will not import, which
`isolated_mutations` rightly refuses to count as a kill (R-67). And a mutation that removes only the check
leaves the classification correct, so nothing observes it. Each classification mutation is therefore a PAIR
of edits that restores a consistent-but-wrong state, which is what the audited defect actually was. That is
not a way of making them easier to kill; it is the only way to make them observable, and the script says so
where a reader will find it. `_BASIS_MEANS['VERIFICATION_ONLY']` is a string literal and reports MUTATION
CHANGED NO CODE, so it is NOT mutated and the script records that rather than dropping it silently — its
wording is guarded by a test, and `_audit_tables` already refuses to import while any basis word has no
description.

**Open decisions.** None.

### Batch 25 — I-12 part B

| ID | Status | Commits | Residuals |
|---|---|---|---|
| I-12 | **DONE** | `23609299`, `7f6f28c7` (part A), `09e78111` (part B preregistration + 10 strict xfails), this commit | the DECLARED basis remains a basis and is weaker than the bytes — it says the domain layer PINNED these routes' dependencies and the core verified the declaration against the pin, not that the two programs were read and found to share no code; no production route ships artifact digests, so `artifact-verified` is unreachable in production and the production path therefore awards nothing at all, which is what the gate withholding the level means; `_consensus_issuer_gap` still cannot tell an issued record from a faithful COPY of one (a check copied from a genuine consensus onto another result carries a genuine threshold record and a genuine basis line), which needs the check bound to the result it qualifies — the standing CORE-009/VAL-01 residual and I-20's |

**R-xx closed.** R-21 is three separate claims and each is answered separately.

| Claim | Status | How |
|---|---|---|
| (a) hand-written consensus evidence lines earn the level and survive a round trip | **ALREADY CLOSED**, and now pinned | VAL-01's `_consensus_issuer_gap` closed it in an earlier batch. Confirmed at this batch's baseline rather than assumed — `ValidationCheck(PASS, establishes=CROSS_SOLVER_VALIDATED, evidence=("trust me",))` raises — and `test_r21_a_hand_written_check_cannot_carry_the_level` is here so the closure cannot be lost. R-21 names it, so this document records it rather than leaving a reader to discover that one third of a problem was already fixed. |
| (b) `TrustedConsensusGate` has no caller | **FIXED** | `engcore.mcp.problem`'s cross-solver check is built BY the gate. That path ships no artifact digests, so the gate withholds the level, says why in the detail, and records the withholding structurally as a `level-withheld:` line — which is R-04's rule applied one layer up: what a run came within one artifact digest of establishing reaches a reader as data and not as prose. The boundary's own `_withhold_level` still runs, because the two rules are different — **the gate withholds because the ARTIFACTS are not verified; the boundary withholds because the check is about values it does not scope to** — and either alone would leave the level one change away from a report. `_withhold_level` is now IDEMPOTENT, so the two rules do not state one fact twice. |
| (c) a disagreement between non-independent routes warns, and the verdict stays SUPPORTED | **FIXED** | A disagreement beyond tolerance is FAIL whether or not the routes are independent. **The pinned reasoning was that "a comparison denied authority to award cannot be given authority to condemn", and those are not the same authority.** Awarding a level is a claim about what the evidence SHOWS; reporting a disagreement is a MEASUREMENT of what the two routes did. Both routes were asked for the same named quantities under one declared required-output contract and returned numbers 33% apart: at least one is wrong about the thing they were both asked to compute, however much machinery they share — and sharing machinery makes it worse, because then the same arithmetic produced two different answers. The other direction is unchanged and is the sentence this record exists to write: routes that AGREE while sharing a Jacobian produce a PASS that establishes nothing. |

**Every level now says which independence it rests on.** A check carrying CROSS_SOLVER_VALIDATED must carry
exactly one `independence basis:` line — `declared` (verified against the domain layer's pin, written by
`CrossSolverConsensus.to_check`) or `artifact-verified` (the bytes digested and compared, written only by
`TrustedConsensusGate` when `assess_independence_evidence` reports `strongly_independent`) — and
`_consensus_issuer_gap` refuses the level without one, or with both. **The basis is ADDITIVE, which is what
the improvement's brief asks for**: removing the declared basis would delete the only basis any route in this
tree can currently reach and make the level unreachable rather than better founded. What R-21 is about is
that a reader could not tell the two apart.

**The ledger moved with the fix.** `certification/guard_reach_ledger.json`'s R-21 row is REACHED and FIXED,
names the production entry point and the tests that exercise it there, and states the residual. I-16 exists
because a guard whose reach nobody states is a guard whose reach nobody can lose; a fix that reaches
production and leaves the row saying LIBRARY_ONLY is a fix nobody can check. Two of I-16's own tests named
R-21 as LIBRARY_ONLY and were updated with a comment saying why — **that is the ratchet working**, and it is
why those tests name the rows rather than counting them.

**Compatibility.** No symbol removed, renamed or reordered; no enum member, dataclass field, default or
signature changed. `CrossSolverConsensus.to_check` keeps its signature and return type; its `evidence` tuple
gains one line, which that tuple is a list of by design. `engcore.mcp.problem` gains an import of
`engcore.execution.consensus`, which the layer ladder allows (execution is layer 6, mcp above it). The
deliberate behaviour changes are the three above, plus: a stored `ValidationCheck` carrying
CROSS_SOLVER_VALIDATED without a basis line stops reading back, for the same reason VAL-01's threshold record
does — the level is re-verified where it becomes a claim.

**Committed evidence.** Nothing moved. A search found no serialized `ValidationCheck` carrying a cross-solver
level in `benchmarks/` or `certification/`; `benchmarks/perf_runtime_audit/baseline_k1_solver_calls.json`
carries a list of level NAMES (`levels_earned`), which is not a check and is unaffected.
`KINETICS_K2.json` and `BATTERY_T41.json` keep their SUPERSEDED markers.

**One existing expectation moved, and it is the one this part corrects.**
`test_cross_solver_consensus.py::test_dependent_routes_that_disagree_warn_rather_than_fail` asserted the
audited behaviour and stated its reasoning in its own docstring. It is now
`test_dependent_routes_that_disagree_also_fail`, with the corrected argument written out and two assertions
added: the residual is still 1/3, and the check still establishes NOTHING — **a stricter outcome must not
become a claim**, which is the one thing this change could have got wrong.

**Verification.** FAST tier 6774 passed, 5 skipped, 1 xfailed, 18 failed (the by-design 18, unchanged).
Expensive tier 528 passed, 18 failed, 14 errors — the recorded baseline's lists exactly.
`tests/test_mutation_harness.py` 6 passed, every anchor intact; `tests/mutation_guards.py` untouched. Nothing
under `src/engcore/domains/thermal/` was edited.

**Guard mutations.** `BATCH25_MUTATIONS.log`: **9 of 9 KILLED**, both controls green, plus 21 pinned re-runs
on the four changed files all KILLED. One survived first: B25g removed the gate's record of the level it
nearly awarded, and the idempotence guard could not see it because that guard reaches `_withhold_level` with
a check that still CARRIES the level — so the line it counts is the boundary's, not the gate's. The
withheld-line assertion moved onto the gate's own case. One mutation is recorded as NOT MUTATED with its
reason: the ledger row's move is JSON, and `mutation_guards._apply` parses every mutation with `ast`, so a
JSON edit reports MUTATION BROKE THE PARSE — what the ledger says is verified by
`tools/certification/guard_reach.py` and by batch 19's own twelve refusal cases instead.

**Open decisions.** None.
