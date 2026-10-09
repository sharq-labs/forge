# Forge flagship engineering demonstrations (BIG 13)

Four recognizable engineering systems, each entered as one BIG 12 `SystemRunRequest`, executed by the **same generic**
`SystemExecutor`, and left as a `SystemRunResult` plus an engineering summary and a verifiable run bundle. There is no
flagship-specific runtime (`flagships/tests/test_flagship_portfolio.py` checks this from the source).

| Flagship | Domain | Providers executed | Multiphysics? | Lifecycle? | Independent comparison? | Reference benchmark? | Experimental validation? | Final scientific status |
|---|---|---|---|---|---|---|---|---|
| [A - Battery + cooling + lifecycle](battery_cooling_lifecycle.md) | electrochemistry / thermal-fluid | PyBaMM 26.8, TESPy 0.11.2 (BIG 9 coupling, BIG 10 multi-timescale) | yes (cell <-> cold plate, two-way, implicit) | yes (56 represented days, fade feeds later physics) | none available (single battery provider) | analytic only (first-law); NASA PCoE considered, applicability UNKNOWN, not compared | no | `insufficient_evidence` |
| [B - Thermo-mechanical structure](thermo_mechanical_structure.md) | thermal + structural mechanics | CalculiX 2.23, Code_Aster 18.1.7, FEniCSx 0.11 | one-way (temperature field -> thermal strain) | no | **yes - corroboration reached, implementations only** (three structural implementations, one shared mesh and one shared temperature field; FEniCSx and Code_Aster share a formulation; pre-registered 1 % tolerances) | analytic only (exact uniform-temperature limits, bar theory); no numerical benchmark integrated | no | `insufficient_evidence` |
| [C - Lid-driven cavity CFD](cavity_cfd_benchmark.md) | incompressible CFD | OpenFOAM v2412, SU2 8.5.0 (fluid records: CoolProp 8.0.0) | no | no | attempted, **NOT reached - the codes disagree by 24-26 % of lid speed in the cell layer next to the lid, at every mesh; preserved** (part of it may be an artifact of the declared corner-mean mapping; that was not tested) | **yes - Ghia et al. 1982, Re = 100 (numerical benchmark), pre-registered 2 %: met by both codes at 80x80** | no | `insufficient_evidence` |
| [D - Chemical / thermal-fluid system](chemical_thermal_system.md) | combustion chemistry + heat transfer | Cantera 3.2.0 (GRI-Mech 3.0), TESPy 0.11.2 | energy-balance interface, one-way | no | none available (single chemistry provider) | analytic relation (Hess's law) with evaluated NIST data, a data-consistency check (LHV at 300 K with a bounded 298.15 K offset): met | no | `insufficient_evidence` |

The "final scientific status" is the verdict the **existing credibility authority** derives (`trust_handoff` ->
`CredibilityVerdict`). It is `insufficient_evidence` for every flagship because the runtime supplies no validity record and no
validation check, and none of the four has experimental validation. A verification ladder (levels 1-7) is reported per flagship as a
**report vocabulary** that records where evidence stops; it is not a validation grant and not a trust verdict; the ladder property `reference_level_reached` is `none` for A, B and D and `published_numerical_benchmark` for C (a numerical-benchmark comparison, reported as such, never as experimental validation). Providers are listed
alphabetically within a row; none is ranked or preferred.

## What each flagship stops at

| | L1 contract | L2 conservation | L3 analytic limit | L4 convergence | L5 independent providers | L6 published numerical benchmark | L7 experiment |
|---|---|---|---|---|---|---|---|
| A | reached | reached (**interface consistency** only: TESPy is handed the cell heat, so closure shows the solver honoured the duty) | reached (**first-law restatement** of the same interface, verifies the heat -> temperature implementation only) | **attempted, not reached** (window-size study: tolerances met, but successive differences grow as the window shrinks) | not available | not available | not available |
| B | reached | reached (thermal balance is near-tautological for a linear profile; the informative diagnostic is the axial force, read only where a force exists) | reached (exact uniform-temperature limits and bar theory; analytic references) | **attempted, not reached** (pre-registered order criterion; the mid-plate stress is at solver noise; peak von Mises converges slowly and is not claimed converged) | **reached** (corroboration of the three IMPLEMENTATIONS on one mesh and one shared temperature field; not of the discretisation or the thermal solution) | not available | not available |
| C | reached | **attempted, not reached** (SU2 mid-plane flux) | not available | **attempted, not reached** (OpenFOAM error against the benchmark is not monotone) | **attempted, not reached** (the codes disagree near the lid; preserved) | **reached** (Ghia et al. Re = 100, a numerical benchmark, both codes at 80x80; not experimental validation) | not available |
| D | reached | reached (element balance is a genuine check; the duty balance is interface consistency) | reached (Hess's law with evaluated NIST data at 300 K, plus kinetic-vs-equilibrium; BOTH checks must run and be met) | **attempted, not reached** (pre-registered ignition criterion below the sampling spacing) | not available | not available | not available |

Negative results are deliberate and visible: six criteria failed or could not be met as written (A the monotone-decrease requirement of the window study, added
after the first review together with its third level, so it is not a strictly pre-first-run criterion; B the convergence order of a quantity already converged to
solver noise; C the whole-field OpenFOAM/SU2 comparison, the monotone benchmark-error criterion and SU2's mid-plane flux; D the discrete ignition-time criterion whose
sampling spacing exceeds its tolerance). Each report states the pre-registered outcome, and where a later
reading was added it is labelled **post hoc** and sits beside, never in place of, the original outcome.

## BIG 14 status

The owner selected flagship A for BIG 14 closure work on 2026-09-27, with no backup. **B, C and D are DEFERRED** (recorded
2026-10-09): their BIG 13 bundles, reports, verdicts (`insufficient_evidence`) and recorded gaps stay exactly as above, and no
new evidence-bearing work is done on them in BIG 14. Their open questions, carried unchanged into the deferral:

- B: peak-stress convergence, the CalculiX difference, and no independent thermo-structural numerical benchmark;
- C: near-lid mapping/discretisation effects, SU2's mid-plane flux miss, and authoritative verification of the Ghia transcription;
- D: GRI-Mech applicability, and no ignition-delay or flame experimental comparison.

Deferral is not a disposition of those questions; reopening any of them needs a new pre-registration.

Flagship A's fade law was tested against LG M50T ageing data (Kirkaldy 2024) in the pre-registered study
`big14-a-kirkaldy-fade` (`flagships/forge_flagships/data/big14_a_kirkaldy_fade_preregistration.json`, record
`docs/flagships/big14/kirkaldy_fade_study.json`). Outcome **NOT MET**, closed as a justified negative result:

- C1 pooled holdout RMSE 0.037 > 0.015, NOT MET. C2 |mean signed residual| <= 0.010 per temperature: 10 degC 0.006 met,
  25 degC 0.027 NOT MET, 40 degC 0.007 met. `met_if` is C1 and C2, so the study is NOT MET.
- Activation energy NOT ESTABLISHED: the fit sits at its lower bound (0) in all eight leave-one-cell-out refits. The ~1e-13
  J/mol spread of those refits is optimizer noise at the bound, not a parameter uncertainty.
- Model discrepancy NOT QUANTIFIED (unknown, not zero): the pre-registration allowed it only if C1 and C2 were met.
  Measurement uncertainty UNKNOWN (no repeated capacity check of an unaged cell in the summaries; not zero).
- No threshold or split changed after the results. Five deviations are recorded in the study record's
  `deviations_from_preregistration` (one, skipping each cell's last RPT, biases toward MET), and the outcome is NOT MET with
  or without the reference RPT. The bound-pinned activation-energy spread is not carried as parameter uncertainty, under the
  pre-registration's "a fit at the bound is reported as at the bound"; that departure from its uncertainty rule is stated
  here and is not yet in the record's deviations list.
- Independence of the holdout: different cells on disjoint rig channels (`experiment_metadata.xlsx`; the dataset carries no
  serials) and a different discharge profile (drive cycle vs constant current). Shared with calibration: laboratory, dataset
  programme, the same two test rigs (2 and 5, on disjoint channels), RPT procedure and cell type; the pre-registration claims
  no batch independence either. This is not
  independent-laboratory validation.
- Flagship A's declared fade parameters on the same holdout are reported, not judged: they overpredict at every temperature
  and 38 of 64 predictions fall outside the model's declared state range. Kirkaldy measured LG M50T; flagship A uses the LG M50
  (Chen2020) parameter set. The study neither validates nor invalidates flagship A's battery model, and its parameters are not
  "corrected" from it. The registered NOT MET is evidence against this throughput-Arrhenius law for LG M50T fade under these
  conditions; the declared-parameter comparison is an observation only (temperature = setpoint, not flagship A's mean cell
  temperature), and carrying this law or parameterization to another cell still needs an applicability argument.
- A non-monotone or otherwise new temperature law would be a separate, newly pre-registered study with a fresh confirmatory
  holdout. It is not started.

## Reproducing a flagship

The providers run in WSL conda environments (see `docs/work/PROGRESS.md`, BIG 11 "Provider environments"); `tools/wsl_env.sh` sets
`FORGE_PROVIDER_ENVS`, `PYTHONPATH` and the environment `PATH` (`FORGE_PY_ENV` chooses the Python environment).

```bash
# A (env: battery)     DFN cell since BIG 14: ~3 min per case; --extras adds the window-refinement study (three more coupled days); the report run is ~15 min
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c 'export FORGE_PY_ENV=battery; source /mnt/d/forge-b13/tools/wsl_env.sh; cd /mnt/d/forge-b13 && python -m forge_flagships battery normal --out /mnt/d/ftmp/battery_normal --extras'
# B (env: fenicsx)     ~20 s
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c 'export FORGE_PY_ENV=fenicsx; source /mnt/d/forge-b13/tools/wsl_env.sh; cd /mnt/d/forge-b13 && python -m forge_flagships structure flagship --out /mnt/d/ftmp/structure --extras'
# C (env: sci)         ~1 min
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c 'export FORGE_PY_ENV=sci; source /mnt/d/forge-b13/tools/wsl_env.sh; cd /mnt/d/forge-b13 && python -m forge_flagships cavity --out /mnt/d/ftmp/cavity'
# D (env: sci)         ~10 s
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c 'export FORGE_PY_ENV=sci; source /mnt/d/forge-b13/tools/wsl_env.sh; cd /mnt/d/forge-b13 && python -m forge_flagships chemistry --out /mnt/d/ftmp/chemistry'
```

Each command runs the flagship through BIG 12, writes a run bundle (`request.json`, `plan.json`, `result.json`, `summary.json`,
`summary.txt`, `references/*.json`, `artifacts/*`, `manifest.json`), **re-verifies it** (every file re-hashed, the result re-derived
through `SystemRunResult.from_dict`), and prints the engineering summary. The reports in this directory are generated from real runs by
`python -m forge_flagships.reports <flagship> --docs docs/flagships`; the section list is enforced by
`engcore.engineering.render_report`. "Pre-registered" in the reports means listed in `flagships/forge_flagships/data/predeclared_criteria.json` and pinned by a test; git cannot show that a criterion preceded the first run (the first commit was made after it), so that ordering rests on `docs/work/PROGRESS.md`. `verify_bundle` re-derives much of what a bundle holds (result, request, plan, scientific status, summary text, key outputs, level 1, every reference comparison, each provider comparison's outcome and providers, the ladder's guards); it cannot re-derive the level 2-4 studies, the constraint lines or the completeness of the provider comparisons, and the manifest is unkeyed, so a passing `verify_bundle` means self-consistent, not authentic (see `docs/architecture/engineering.md`).

The committed `runs/` directories hold the complete bundles (including VTU field files and CSV histories, ~10 MB in total; a nested `.gitattributes` keeps them byte-exact) of the runs each report was generated from: `battery_normal`, `battery_hot`, `battery_overload`, `battery_outside_window`, `structure_flagship`, `structure_over_range`, `cavity_re100`, `chemistry_nominal`. `flagships/tests/test_flagship_portfolio.py` re-verifies every committed bundle (`verify_bundle`), pins each bundle's full `bundle_digest` and `summary_digest`, and checks that each report names its own bundle's request / plan / result digests, so a stale report, an edited file or a consistently rewritten bundle fails a test. VTU files are presentation artifacts, not evidence; their digests are in each manifest, and run-to-run byte stability is asserted by the tests for flagship B's field files only.

Replay identity: the request and plan digests are stable across runs and the observed values replay through `compare_runs` (`identity_replay`, `numerical_reproducibility`). The whole-result digest is NOT expected to be equal between runs: two regenerations of flagship B gave different result digests (the result records operational data such as provider wall time), so a report's `result` digest identifies that run, not a reproduction target.

Tests: `python -m pytest flagships/tests/<file> --import-mode=importlib` in the matching environment
(`test_flagship_battery.py` in `battery`, `test_flagship_thermo_mechanical.py` in `fenicsx`, `test_flagship_cavity.py` and
`test_flagship_chemistry.py` in `sci`); `test_flagship_portfolio.py` and `test_thermoelastic_adapters.py` need no provider.

## Reference data used

| Reference | Kind (never mislabelled) | Provenance | Used by |
|---|---|---|---|
| Ghia, Ghia & Shin (1982), Tables I and II, Re = 100 columns | **numerical benchmark** (129 x 129 multigrid), not an experiment | transcription digests + a second independent public transcription (NOT checked against the printed paper); excerpt only, attribution kept | C |
| NIST Chemistry WebBook (SRD 69) gas-phase formation enthalpies of CH4, CO2, H2O (Chase 1998; CODATA; Manion 2002) | **analytic** relation (Hess's law) with evaluated data | three page digests; excerpt file digest | D |
| First-law heat balance; uniform-temperature thermoelastic limits; bar theory | **analytic** | derived, nothing copied | A, B |
| NASA PCoE Li-ion aging dataset | experimental dataset, **considered and not compared** (applicability UNKNOWN) | repository-pinned manifest identity; no data copied | A |

## Scope of this milestone

BIG 13 is a demonstration milestone. Full FAST, full SCIENTIFIC, mutation and hardened recertification runs were **NOT RUN**
(reserved for BIG 14-15); see `docs/work/PROGRESS.md` for the exact focused commands that were executed.
