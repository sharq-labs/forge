# FORGE Build vs Buy — Defect-Driven Opportunities — 2026-10-19

This audits the hand-built inventory in `GENESIS_STEP0_A1_READINESS_REVIEW.md` §8.5 against **actual defects**
found in this audit. No library was installed or replaced, and no performance figure is claimed: every performance
cell is UNMEASURED. Using a package is not assumed to be more correct. Each row states the concrete evidence.

Decision vocabulary: KEEP / WRAP / REPLACE / DEFER / AUDIT.

Benefit tags:
- **SC**: scientific-correctness improvement
- **PERF**: performance
- **MAINT**: maintenance reduction
- **DISC**: discovery-capability expansion
- **BASE**: independent baseline

## 1. Items where an external package removes a verified risk

| Item | Defect | Mature alternative | Decision | Benefit | Identity / certification impact |
|---|---|---|---|---|---|
| `mcp/probabilistic_uq.py` lattice LHS (`:54-59`) | FDA-04: exact ±1 column correlations; zero-width interval | `scipy.stats.qmc.LatinHypercube(d, scramble=True, seed=…)` (SciPy is already a core dependency); or refuse more than n/2 inputs | **REPLACE** | SC | MCP is uncertified; output values change, and the `method` label must change. Also move it out of MCP (O-4). |
| Same file, empirical quantile (`:138-141`) | FDA-14: realised mass 0.95 − 0.95/n | `np.quantile(..., method="hazen")`, consistent with midpoint strata | **REPLACE** (one argument) | SC | Same as above |
| `hybrid_uq/local_gaussian.py:98-119` Halton multistart | FDA-15: collinear high-dimensional starts | `scipy.stats.qmc.Halton(d, scramble=True, seed=…)` or leaped Halton | **WRAP** as a new scheme `/2`; keep `/1` readable | SC | Frozen V2/V3 module → Core Freeze review + OD-3 |
| `design/sampling.py` Halton (duplicate) | Same construction; it only orders candidates | `scipy.stats.qmc` | **DEFER** (consolidate in the OD-3 batch) | MAINT | Certified |

## 2. Items where a package is a test-only oracle (no production swap)

| Item | Risk audited | Oracle | Decision | Benefit |
|---|---|---|---|---|
| `benchmarks/genesis_lite/arms.py:92,:147-150` (`np.std`, ddof=0, constant 3.5 "≈99 % F", \|r\|>0.5) | FDA-21 plus known gate constants: possibly straw-man baselines | `scipy.stats.f.ppf`, `scipy.stats.t`, statsmodels OLS `get_prediction` | **AUDIT**, then fix in v0.3 | SC, BASE |
| `analysis.py` bootstrap "p" → Holm (O-1) | FWER validity | `scipy.stats.bootstrap`, sign-flip / permutation test, statsmodels `multipletests` | **AUDIT** (null-calibration simulation, BVB-0) | SC |
| `execution/multiphysics/mapping.py:208-216` quad point location | FDA-17 non-convex over-coverage | Shapely `Polygon.contains` (test oracle only) | **KEEP** the algorithm and add a convexity precondition; Shapely in tests | SC |
| `blindfold/expression.py:174` structure digest | OBS-07 rounding collisions | SymPy `srepr` / `simplify` (audit oracle) | **KEEP**, with an optional oracle | MAINT |
| `blindfold/universe.py:171` π-groups | Found sound for want=2 | `pint.pi_theorem` | **KEEP**, with an oracle | — |
| Weighted quantiles, log-sum-exp, mixture bisection, Wilson, Fincke-Pohst, lattice Hessian, Pearson three-moment, FD step halving, GCI/Richardson | All re-derived correct (E, B) | NumPy / SciPy / mpmath | **KEEP**; oracles optional | MAINT |

## 3. Items that must stay proprietary FORGE logic

Each of these defects is a contract defect, not an algorithm defect. No library carries FORGE's authority, identity
or refusal semantics, so a repair must be made in FORGE:

| Item | Defects | Why it stays in FORGE |
|---|---|---|
| `assembly/replay.py` comparison and certification replay gate | FDA-01, FDA-23 | Replay equality is an authority contract over FORGE records |
| `system_runtime` state commit / clock | FDA-02 | State transition and receipt semantics |
| `materials/properties.py` arbitration | FDA-03 | Source-arbitration invariant |
| `claims` verify / replay | FDA-07, 08, 09 | Evidence-standing semantics |
| `execution/multiphysics/runtime.py` balance and parameters | FDA-10, 11 | Run-record identity |
| Escrow / evaluator scoring, lift rule, campaign design | FDA-05, 06, 18, 20, 22 | Preregistered benchmark identity. The evaluator must stay stdlib-only, and its independence is enforced by test. |
| `scientific/discovery/symbolic_regression.py` gate | FDA-16 | Gate semantics; a PySINDy/PySR WRAP exists separately as a provider/baseline, not as the gate |

## 4. Independent baselines (Genesis §10.5)

| Candidate | Status | Decision | Note |
|---|---|---|---|
| PySR (Apache-2.0; Julia) | NOT_AVAILABLE; installation unresolved | **WRAP candidate** for v0.3 | Strongest external law-recovery arm. Never substitute it silently. |
| BoTorch (MIT; PyTorch) | Provider runner exists, not qualified | **WRAP candidate** | Needs budget equalisation and identity binding |
| PySINDy (MIT) | No dynamics class in v0.2 | **DEFER** | — |
| Stateful / adversarial scoring arms (vacuous pair, exclusivity) | Absent | **BUILD** (test-only attack arms) | Detects FDA-05 and FDA-18 classes; FORGE-specific |

## 5. Not recommended

- Replacing hand-built exact or deterministic kernels (the Fraction conservation gate, 96-step bisection, Thomas solver) with libraries. They re-derived correctly, a swap would move result digests, and the hand-built versions buy determinism.
- Putting any library in the Genesis-lite evaluator.
- Using emcee, PyMC, chaospy, OpenTURNS or Dakota for any audited defect. None of the defects found here would be removed by them, so: DEFER.

## 6. Licensing note

FORGE is distributed under a proprietary licence. The packages above are SciPy and NumPy (BSD-3, already core
dependencies), Shapely (BSD-3, test-only), and statsmodels and SymPy (BSD). They are permissive. Shapely,
statsmodels and SymPy are not installed in the venv. Counsel decides the final position; this is not legal advice.
