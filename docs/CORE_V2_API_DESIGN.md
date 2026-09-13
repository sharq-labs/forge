# Core V2 API design: scalable hybrid uncertainty quantification

**Status:** design, written and committed **before** any implementation.

**What this is:** the complete additive surface of Core V2 and the compatibility argument for it. The implementation must match this document. Where it cannot, the document is changed first and the change is recorded.

**Baseline** (`V2_BASELINE`): `7519aee559750f51bfc58aea12ab29ec199743f4`.

This is Core V1 with the certified thin-ridge repair applied. At the baseline:

- the frozen API digest is `c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929`;
- there are 194 frozen symbols, 205 public symbols in total;
- `core_certificate --verify` and `core_freeze --verify` are OK.

---

## 1. Compatibility strategy: a new canonical module, not new names in old ones

The V1 contract is the snapshot of seven canonical modules (`api_snapshot.CANONICAL_MODULES`). The V1 freeze verifier binds on four things in DESCENDANT mode:

- that snapshot's frozen digest, frozen count, total count and experimental set;
- the pinned snapshot files;
- the serialization inventory derived from those modules;
- the certificate.

Adding even one name to `engcore.inference.__all__` or `engcore.uq.__all__` would move the V1 frozen digest. It would then fail `contract.api` and `bytes.pinned_contract_files`, and make every later commit a non-descendant of Core Freeze V1. That is a rewrite of V1's meaning.

**V2 therefore adds exactly one new Core package, `src/engcore/hybrid_uq/`, and nothing to any V1 module's `__all__`.**

| surface | modules | digest |
|---|---|---|
| **V1** (unchanged) | the seven V1 canonical modules | `c80e6418…` (must not move) |
| **V2** | the seven V1 modules **plus** `engcore.hybrid_uq` | new V2 frozen digest, pinned in `tests/api/v2_frozen_api_snapshot.json` |

Consequences:

- `api_snapshot.build()` with no argument keeps producing the V1 snapshot byte-for-byte. The V1 reproduction probe, the V1 wheel parity script and the V1 verifier all call it that way.
- A new entry point, `api_snapshot.build(modules=api_snapshot.V2_CANONICAL_MODULES)`, produces the V2 snapshot. `modules` is a keyword-only argument with a default. `api_snapshot` is not a canonical module, so this is not a frozen-API event.
- Every V1 frozen snapshot entry must appear **byte-identical** inside the V2 frozen snapshot. This is a test.
- The V1 freeze verifier keeps passing on every V2 commit: V2 is also a V1 descendant. This is part of the V2 freeze manifest.
- The layering test gains one layer, `hybrid_uq`, directly above `uq`: it imports `scientific`, `inference` and `uq` and nothing above. The canonical-module equality test becomes "V2 canonical modules == layers".

**V1 files that change:**

- **`src/engcore/api_snapshot.py`:** the V2 module tuple and the `modules=` keyword.
- **Tests:**
  - `tests/test_core_api_layering.py`: the new layer;
  - `tests/test_core_freeze_policy.py`: V2 modules may be named in policy prose.
- **Docs:** `docs/CORE_FREEZE_POLICY.md` gains a §12 pointer.
- **Certification tooling** (at freeze): `tools/certification/core_certificate.py` gains the new certified area.

No file under `src/engcore/{scientific,data,inference,uq,adequacy,execution,studies}` changes. No V1 record, schema, digest, signature, default or enum changes.

## 2. What V2 adds, conceptually

| approximation class | what it is | never |
|---|---|---|
| `POSTERIOR_GRID` | V1's discrete posterior on a tensor lattice, **used only after the repaired V1 resolution checks pass** | called exact for the continuous posterior |
| `LOCAL_GAUSSIAN_APPROXIMATION` | N(ẑ, (J_wᵀJ_w)⁻¹) in the declared inference coordinates z at the calibrated estimate: Gauss–Newton / Fisher information, flat prior inside the bounds | called a posterior grid, called exact, or used when its validity diagnostics refuse |
| `LINEARIZED_PREDICTIVE_UQ` | predictive mean g(ẑ), parameter variance diag(G Σ Gᵀ), measurement variance σ², total = sum | called exact, or merged into one undifferentiated number |

Every V2 record carries its `approximation_class`. `ApproximationClass.exact_posterior` is `False` for **every** member, and no V2 record has a field that can say otherwise.

**Route validity and identifiability are separate records**, `RouteDiagnostics` and `RoutedIdentifiability`. A valid route can report NOT_IDENTIFIABLE; a refused route reports no identifiability at all.

## 3. The public symbols of `engcore.hybrid_uq` (27)

### 3.1 Vocabulary (11)

| symbol | kind | definition |
|---|---|---|
| `ApproximationClass` | str Enum | `POSTERIOR_GRID`, `LOCAL_GAUSSIAN_APPROXIMATION`, `LINEARIZED_PREDICTIVE_UQ`; properties `exact_posterior` (always False) and `describes` (`"parameters"` / `"predictions"`) |
| `RouteClaim` | str Enum | `SUPPORTED`, `DOWNGRADED`, `REFUSED` |
| `RouteReason` | str Enum | every refusal and downgrade code (§4); property `severity` → `RouteClaim.REFUSED` or `RouteClaim.DOWNGRADED` |
| `RouteDecision` | str Enum | `GRID_AS_SUPPLIED`, `LOCAL_GAUSSIAN`, `GRID_REBUILT_FROM_LOCAL_COVARIANCE`, `REFUSED` |
| `HybridUQError` | exception | subclass of `engcore.uq.UQProblemError`, so no new exception root |
| `RouteRefusedError` | exception | subclass of `HybridUQError`; raised when a caller asks a refused route for numbers |
| `PARAMETER_UNCERTAINTY` | str constant | `"PARAMETER_UNCERTAINTY"` |
| `MEASUREMENT_UNCERTAINTY` | str constant | `"MEASUREMENT_UNCERTAINTY"` |
| `MODEL_DISCREPANCY_NOT_MODELLED` | str constant | `"MODEL_DISCREPANCY_NOT_MODELLED"` |
| `UNCERTAINTY_SOURCES` | tuple constant | the three above, in that order |
| `GRID_ROUTE_MAXIMUM_PARAMETERS` | int constant | `5`, the dimension the repaired V1 grid route was validated at (B3 P4/T5) |

### 3.2 Jacobian retention (2)

`calibrate` returns no Jacobian, and its return contract is frozen. V2 does not modify it. It gives the local sensitivity its own record, which can be built two ways:

- **reconstructed** from the calibrated estimate with the caller's own forward evaluator: 2p + 1 evaluations, central differences;
- **preserved**, by constructing the record directly from a domain's analytic or retained Jacobian.

```python
@dataclass(frozen=True)
class LocalSensitivity:
    parameter_set_digest: str
    parameter_names: tuple[str, ...]
    inference_transforms: tuple[str, ...]      # ParameterTransform values, per parameter
    estimate: tuple[float, ...]                # natural units, the declared parameter units
    observation_keys: tuple[str, ...]
    observation_units: tuple[str, ...]
    observed: tuple[float, ...]
    sigma: tuple[float, ...]
    predicted: tuple[float, ...]               # at the estimate, observation units
    jacobian: tuple[tuple[float, ...], ...]    # d predicted / d inference coordinate, n x p
    steps: tuple[float, ...]                   # inference-coordinate steps (0.0 when supplied)
    one_sided: tuple[bool, ...]
    dataset_id: str
    evaluation_count: int
    method: str = "central_difference"         # or "supplied"
    # to_dict / from_dict / digest; properties weighted_jacobian, standardized_residuals, chi_square

def reconstruct_local_sensitivity(
    calibration: CalibrationResult, observations: ObservationSet, forward: ForwardEvaluator,
    *, relative_step: float = 1.0e-5,
) -> LocalSensitivity
```

**Inference coordinates.** A parameter declared `ParameterTransform.LOG` is differentiated, probed and given a covariance in log space; one declared `IDENTITY` in its natural unit. The transform is part of the parameterization identity (§6).

### 3.3 The local route (5)

```python
@dataclass(frozen=True)
class MultistartPolicy:
    starts: int = 6
    scheme: str = "halton_in_inference_bounds"
    interior_fraction: float = 0.8            # starts lie in the central 80% of the inference-space box
    max_evaluations: int = 2000
    mode_separation_quantile: float = 0.999   # Mahalanobis^2 beyond chi2(p) quantile = a different optimum
    comparable_fit_quantile: float = 0.99     # chi-square within chi2(p) quantile of the best = comparable
    # start_points(parameter_set) -> tuple[tuple[float, ...], ...]  (deterministic, natural units)
    # to_dict / from_dict / digest

@dataclass(frozen=True)
class RouteDiagnostics:
    parameters: int
    observations: int
    jacobian_rank: int
    jacobian_condition: float                  # after column equilibration (scale-free)
    raw_jacobian_condition: float              # in the declared coordinates
    newton_step_in_sd: tuple[float, ...]       # stationarity: Gauss-Newton step from the estimate
    at_bound: tuple[str, ...]
    near_bound: tuple[str, ...]
    minimum_bound_distance_sd: float
    nonlinearity_index: float                  # max |rise/4 - 1| over +/-2 sd principal-axis probes
    nonlinearity_probes_skipped: int
    minimum_chi_square_rise: float
    multistart: tuple[dict, ...]               # per start: start, status, estimate, chi_square, mahalanobis_sq
    uniqueness: str                            # MULTISTART_NO_SECOND_MODE / SECOND_MODE_FOUND /
                                               #   BETTER_OPTIMUM_FOUND / NOT_ASSESSED / MULTISTART_INCOMPLETE
    thresholds: Mapping[str, float]
    evaluation_count: int
    claim: RouteClaim
    refusals: tuple[RouteReason, ...]
    downgrades: tuple[RouteReason, ...]
    # to_dict / from_dict / digest

@dataclass(frozen=True)
class ParameterInterval:
    name: str
    unit: str
    inference_transform: str
    estimate: float                            # natural units
    inference_standard_uncertainty: float      # in inference coordinates
    lower: float                               # natural units (mapped back through the transform)
    upper: float
    confidence_level: float
    approximation_class: ApproximationClass
    # to_dict / from_dict

@dataclass(frozen=True)
class LocalGaussianPosterior:
    approximation_class: ApproximationClass    # must be LOCAL_GAUSSIAN_APPROXIMATION
    parameter_names: tuple[str, ...]
    parameter_units: tuple[str, ...]
    inference_transforms: tuple[str, ...]
    parameterization: str                      # "declared" or "linear_map:<label>"
    parameterization_digest: str
    estimate: tuple[float, ...]                # natural units
    inference_point: tuple[float, ...]         # inference coordinates
    covariance: tuple[tuple[float, ...], ...] | None   # None when REFUSED: a refused route emits no numbers
    lower_bounds: tuple[float, ...]            # inference coordinates
    upper_bounds: tuple[float, ...]
    diagnostics: RouteDiagnostics
    sensitivity_digest: str
    dataset_id: str
    # properties: claim, reasons, exact_posterior (False), standard_deviations, correlation
    # intervals(confidence_level=0.95) -> tuple[ParameterInterval, ...]   (raises RouteRefusedError if REFUSED)
    # reparameterized(matrix, names, units, label) -> LocalGaussianPosterior   (linear map; new parameterization identity)
    # to_dict / from_dict / digest

def local_gaussian_posterior(
    calibration: CalibrationResult, observations: ObservationSet, forward: ForwardEvaluator,
    *, multistart: MultistartPolicy | None, sensitivity: LocalSensitivity | None = None,
) -> LocalGaussianPosterior
```

`multistart` is **required**. Passing `None` is allowed, but it is recorded as `GLOBAL_UNIQUENESS_NOT_ASSESSED`, which caps the claim at DOWNGRADED. No SUPPORTED claim assumes a single mode without a multistart that looked for another.

### 3.4 Identifiability (2)

```python
@dataclass(frozen=True)
class RoutedIdentifiability:
    approximation_class: ApproximationClass
    parameterization_digest: str
    route_claim: RouteClaim                    # of the route it was read from, kept beside it and never merged
    report: IdentifiabilityReport              # the V1 record, V1 thresholds, V1 classification rule
    # to_dict / from_dict / digest

def assess_routed_identifiability(
    posterior: LocalGaussianPosterior | PosteriorGrid, *,
    correlation_threshold: float = 0.95, condition_threshold: float = 1.0e6,
    width_threshold: float = 1.0, confidence_level: float = 0.95,
) -> RoutedIdentifiability
```

- **Grid:** delegates to the frozen `assess_identifiability`, with its refusals intact.
- **Local route:** applies the frozen thresholds and the **same** classification rule to the Gaussian covariance, with Gaussian marginal intervals (±z·sd in inference coordinates) in place of discrete ones.
- **Defaults** equal the frozen function's defaults. A test reads them from its signature.
- **Refused local posterior:** raises `RouteRefusedError`.

### 3.5 Predictive UQ (3)

```python
@dataclass(frozen=True)
class RoutedPredictiveUncertainty:
    observation_key: str
    unit: str
    approximation_class: ApproximationClass    # LINEARIZED_PREDICTIVE_UQ or POSTERIOR_GRID
    mean: float
    parameter_standard_uncertainty: float
    measurement_standard_uncertainty: float | None   # None when no sigma was declared
    total_standard_uncertainty: float
    parameter_interval: tuple[float, float]
    total_interval: tuple[float, float]
    confidence_level: float
    sources: tuple[str, ...]                   # == UNCERTAINTY_SOURCES
    model_discrepancy: str                     # == MODEL_DISCREPANCY_NOT_MODELLED
    posterior_digest: str
    route_claim: RouteClaim
    reasons: tuple[RouteReason, ...]
    predictive_nonlinearity: float | None
    # to_dict / from_dict / digest

def linearized_predictive_uq(
    posterior: LocalGaussianPosterior, predict: ForwardEvaluator,
    specs: Sequence[PredictiveObservableSpec], *,
    confidence_level: float = 0.95, check_nonlinearity: bool = True,
) -> tuple[RoutedPredictiveUncertainty, ...]

def grid_predictive_uncertainty(
    posterior: PosteriorGrid, predictive_table: AdmittedForwardTable, spec: PredictiveObservableSpec, *,
    twin: TwinReference, model: ModelReference, source_ref: str, confidence_level: float = 0.95,
) -> RoutedPredictiveUncertainty
```

- **Linearized:** G by central differences in inference coordinates, 2p + 1 calls. With `check_nonlinearity`, the ±2 sd principal-axis probes (another 2p calls) compare g with its linear extrapolation. A deviation above 0.10 total sd adds `PREDICTIVE_NONLINEAR`, a downgrade.
- **Refused posterior:** raises `RouteRefusedError`.
- **Grid:** wraps the frozen `posterior_predictive_uq`, including its grid-resolution refusal. The epistemic part becomes `parameter_standard_uncertainty`, the declared sigma becomes `measurement_standard_uncertainty`, and V1's exact mixture interval is kept as `total_interval`.
- **Model discrepancy:** never estimated; every record names `MODEL_DISCREPANCY_NOT_MODELLED`.

### 3.6 The router (4)

```python
@dataclass(frozen=True)
class GridRebuildPolicy:
    table_builder: Callable[[Sequence[Sequence[float]]], AdmittedForwardTable]
    sigma_span: float = 6.0
    maximum_points: int = 250_000
    aliasing_margin: float = 4.0               # design for aliasing number >= margin x the V1 minimum
    # export-only (holds a callable): no from_dict

@dataclass(frozen=True)
class HybridUQResult:
    decision: RouteDecision
    approximation_class: ApproximationClass | None
    claim: RouteClaim
    parameter_names: tuple[str, ...]
    coordinates: str                           # "natural" (grid routes), "inference" (local route), "none" (refused)
    mean: tuple[float, ...] | None
    covariance: tuple[tuple[float, ...], ...] | None
    local_posterior: LocalGaussianPosterior | None
    grid_summary: Mapping[str, Any] | None     # dataset id, points, digest of points+weights, grid refusal text
    considered: tuple[Mapping[str, str], ...]  # every route tried, in order, with its outcome and reason
    identifiability: RoutedIdentifiability | None
    # the PosteriorGrid itself is data-plane: held on the instance (compare=False), not serialized
    # to_dict / from_dict / digest

def route_uncertainty(
    *, grid: PosteriorGrid | None = None,
    calibration: CalibrationResult | None = None, observations: ObservationSet | None = None,
    forward: ForwardEvaluator | None = None, multistart: MultistartPolicy | None = None,
    rebuild: GridRebuildPolicy | None = None,
    maximum_grid_parameters: int = GRID_ROUTE_MAXIMUM_PARAMETERS,
) -> HybridUQResult

def routed_predictive_uncertainty(
    result: HybridUQResult, specs: Sequence[PredictiveObservableSpec], *,
    predict: ForwardEvaluator | None = None, predictive_table: AdmittedForwardTable | None = None,
    twin: TwinReference | None = None, model: ModelReference | None = None,
    source_ref: str | None = None, confidence_level: float = 0.95,
) -> tuple[RoutedPredictiveUncertainty, ...]
```

**Routing rule.** It is deterministic, runs in this order, and every step is recorded in `considered`.

1. **Grid as supplied.** A `grid` is supplied, its p ≤ `maximum_grid_parameters`, and the frozen `assess_identifiability` does not raise. That means all of the following pass:
   - the repaired V1 checks (tensor lattice, ESS ≥ p+1, the ESS-and-spacing rule, lattice aliasing number ≥ 2 ln 100);
   - a usable local curvature fit.

   → `GRID_AS_SUPPLIED`, class `POSTERIOR_GRID`, claim SUPPORTED. Otherwise the grid's refusal text is recorded and routing continues. **V1 refusal semantics are never weakened:** the router has no way to accept a grid V1 refuses.
2. **Local Gaussian, supported.** Local inputs are supplied and `local_gaussian_posterior(...)` is SUPPORTED → `LOCAL_GAUSSIAN`, class `LOCAL_GAUSSIAN_APPROXIMATION`.
3. **Verified regrid.** `rebuild` is supplied, p ≤ `maximum_grid_parameters`, and the local posterior has a covariance (not refused for a structural reason). The router then:
   - designs an axis-aligned tensor grid whose box covers ±`sigma_span` sd around the estimate and every mode multistart found, clipped to bounds;
   - picks per-axis node counts so the aliasing number predicted from the local covariance is ≥ `aliasing_margin` × 2 ln 100, within `maximum_points`;
   - builds the table with the caller's builder;
   - **checks containment:** on every face that is not a declared bound, the largest log-likelihood must sit at least ln 10⁶ below the peak. Otherwise the box grows by half its width on that side, at most 6 times. The frozen V1 checks verify resolution, not containment;
   - **checks truncation convergence:** where a declared bound cuts the posterior off, the density is not smooth at the edge and the Poisson-aliasing argument behind the V1 check does not bound the error there. The step on each such axis is halved, nested, until means and sds move by less than 0.05 posterior sd, at most 5 halvings within `maximum_points`;
   - runs the **frozen** V1 checks on the result. If V1 refuses, the aliasing target is raised 4× (steps halved) and the grid rebuilt, at most 3 times.

   If V1 accepts → `GRID_REBUILT_FROM_LOCAL_COVARIANCE`, class `POSTERIOR_GRID`. If not, every refusal is recorded and routing continues.

   *Amendment, made before the tests were written.* Containment and truncation convergence were added after a smoke run showed two failures:
   - a Gaussian-sized box truncated F1's heavy tail: θ₁ mean 3.31 against the dense reference 3.43;
   - a grid at a declared bound was accepted by V1 with θ₂ biased by 0.27 sd.

   With both checks, the rebuilt grids match dense references to ≤ 0.01 sd on F1, F2, F4 and a bimodal case.
4. **Local Gaussian, downgraded.** The local posterior is DOWNGRADED → `LOCAL_GAUSSIAN`, claim DOWNGRADED, with its reasons attached.
5. Otherwise → `REFUSED`: no mean, no covariance, every reason recorded.

## 4. Route reasons and declared thresholds

**Refusals** (claim REFUSED; no covariance is emitted):

| code | condition |
|---|---|
| `CALIBRATION_NOT_CONVERGED` | the supplied `CalibrationResult` is not CONVERGED |
| `FORWARD_INADMISSIBLE_NEAR_ESTIMATE` | the forward evaluator refused a Jacobian point |
| `NO_RESIDUAL_DEGREES_OF_FREEDOM` | p ≥ n |
| `STRUCTURALLY_UNIDENTIFIABLE` | rank(J_w) < p |
| `NUMERICALLY_SINGULAR_JACOBIAN` | equilibrated cond(J_w) > 1/√ε ≈ 6.7e7 |
| `PARAMETER_AT_BOUND` | the Gauss–Newton step from the estimate exceeds 0.05 sd and points through a bound the estimate is within 1e-6 bound-range of |
| `NOT_STATIONARY` | the Gauss–Newton step exceeds 0.05 sd with no bound to explain it |
| `NOT_A_LOCAL_MINIMUM` | a ±2 sd probe lowers χ² |
| `NONLINEAR_BEYOND_LOCAL_GAUSSIAN` | nonlinearity index > 0.50 |
| `SECOND_MODE_FOUND` | a multistart optimum with Mahalanobis² > χ²_p(0.999) and χ² ≤ χ²_min + χ²_p(0.99) |
| `BETTER_OPTIMUM_FOUND` | a multistart optimum with Mahalanobis² > χ²_p(0.999) and χ² lower than the estimate's by more than χ²_p(0.99) |

**Downgrades** (claim DOWNGRADED):

| code | condition |
|---|---|
| `BOUND_WITHIN_3_SD` | a bound within 3 sd of the estimate |
| `NONLINEAR_WITHIN_2_SD` | 0.10 < nonlinearity index ≤ 0.50 |
| `NONLINEARITY_PROBE_INCOMPLETE` | a probe fell outside the bounds or was inadmissible |
| `POORLY_SCALED_PARAMETERIZATION` | raw cond(J_w) > 1/√ε while the equilibrated condition is representable |
| `GLOBAL_UNIQUENESS_NOT_ASSESSED` | `multistart=None` |
| `MULTISTART_INCOMPLETE` | fewer than half the starts converged |
| `PREDICTIVE_NONLINEAR` | predictive only |

**Router-only reasons:** `GRID_NOT_SUPPLIED`, `GRID_BEYOND_VALIDATED_DIMENSION`, `GRID_UNRESOLVED`, `LOCAL_INPUTS_NOT_SUPPLIED`, `GRID_REBUILD_OVER_BUDGET`, `GRID_REBUILD_UNRESOLVED`.

The thresholds are module constants, recorded inside every `RouteDiagnostics.thresholds`. The nonlinearity, bound, condition and multistart thresholds were validated by the HD-UQ review (`benchmarks/core_gap_hd_uq`) on the following:

- B3 P1–P9 and T3–T41;
- TCR wide and narrow;
- K2;
- failure cases F1–F6.

The stationarity threshold is new and must be validated on the same set before freeze.

## 5. Serialization (V2 inventory)

**Schemas:**

| schema string | record | round-trip |
|---|---|---|
| `hybrid_uq.local_sensitivity/1` | `LocalSensitivity` | yes |
| `hybrid_uq.multistart_policy/1` | `MultistartPolicy` | yes |
| `hybrid_uq.route_diagnostics/1` | `RouteDiagnostics` | yes |
| `hybrid_uq.parameter_interval/1` | `ParameterInterval` | yes |
| `hybrid_uq.local_gaussian_posterior/1` | `LocalGaussianPosterior` | yes |
| `hybrid_uq.routed_identifiability/1` | `RoutedIdentifiability` | yes |
| `hybrid_uq.routed_predictive_uncertainty/1` | `RoutedPredictiveUncertainty` | yes |
| `hybrid_uq.hybrid_uq_result/1` | `HybridUQResult` | yes |
| — | `GridRebuildPolicy` | export-only (holds a callable) |

**Rules:**

- **Readers:** every `from_dict` accepts exactly its current schema string. Anything else raises `HybridUQError`.
- **Floats:** stored as JSON numbers with `allow_nan=False`. A non-finite value is written as the string `"inf"`, `"-inf"` or `"nan"` and read back, so a condition number of ∞ survives a round trip.
- **Canonical bytes:** `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`.
- **Tests:** round-trip byte identity for every record; unknown-schema refusal for every reader; fresh-process digest stability (a subprocess computes the same digests).

## 6. Identity

Each record's `digest` is SHA-256 over its canonical dict, restricted to **material** fields.

**Material:**

- approximation class, claim, reasons;
- estimate, covariance, inference transforms;
- parameterization label **and** parameterization digest;
- parameter names and units;
- dataset id, sensitivity digest;
- diagnostics values and thresholds;
- confidence level;
- sources and model-discrepancy marker.

**Non-material** (excluded from digests):

- wall-clock seconds;
- evaluation counts;
- free-text notes.

Every material field is checked by a test that changing it moves the digest, and every non-material field by a test that changing it does not.

**Parameterization identity.** `parameterization_digest` for the declared parameterization is SHA-256 over:

- the parameter set digest (V1 `CalibrationParameterSet.digest`, which already includes transforms);
- the label `declared`.

For `reparameterized(T, names, units, label)` it is SHA-256 over:

- the parent digest;
- the label;
- T in canonical JSON;
- names and units.

Two parameterizations of one posterior therefore never share an identity (HD-9).

**Evidence identity.** V1's `PredictiveEvidenceIdentity` is untouched. V2 predictive records identify the posterior they came from by digest and carry their approximation class. They introduce no new evidence pairing.

## 7. Layering and dependencies

- **Imports:** `engcore.hybrid_uq` imports `engcore.scientific`, `engcore.inference` and `engcore.uq`, plus `numpy` and `scipy` (already Core dependencies).
- **Private V1 helper:** it calls one private V1 helper, `inference.calibration._grid_resolution_refusal`, only to explain a grid refusal in `considered`. The decision itself is always the frozen public `assess_identifiability`.
- **Nothing below imports it.** `adequacy`, `execution` and `studies` do not import it in V2.

## 8. What is deliberately not in V2

- **Changes to `calibrate`, `PosteriorGrid`, `assess_identifiability`, `posterior_predictive_uq`, adequacy scoring or evidence identity.**
- **Other posterior approximations.** Laplace with a full Hessian, MCMC, sparse grids, importance-sampling posteriors, non-Gaussian likelihoods, estimated noise and model-discrepancy models are not added. Importance reweighting stays a benchmark-side verification tier.
- **A claim of global mode uniqueness.** Multistart bounds it; it cannot prove it.
- **Adequacy scoring over the linearized predictive.** Held-out scoring through `engcore.adequacy` remains grid-based in the frozen API. Benchmarks compute χ² and coverage from `RoutedPredictiveUncertainty` explicitly.

## 9. Compatibility proof obligations (tests, written before the implementation)

1. `api_snapshot.frozen_digest()` == `c80e6418…`, and `build()` symbol counts are 194 / 205, unchanged.
2. `tests/api/frozen_api_snapshot.json` and `full_api_snapshot.json` bytes are unchanged, as the existing pinned tests require.
3. Every entry of the V1 frozen snapshot is byte-identical in the V2 frozen snapshot, and V2 − V1 == exactly the `engcore.hybrid_uq` entries.
4. No V1 canonical module's `__all__` gained or lost a name.
5. The V2 surface adds no exception root. Every `hybrid_uq` exception descends from `UQProblemError`.
6. `core_freeze --verify` stays OK on every V2 commit.
7. The V2 frozen digest is pinned in `tests/api/v2_frozen_api_snapshot.json` and in the V2 freeze manifest.
