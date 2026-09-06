# NEEDS

Everything this round wanted outside its owned paths, and the conditions it
deliberately did not implement. Nothing here has been done; each item is a
proposal or a limitation, stated where it can be argued with.

Owned paths for the round were `src/engcore/domains/thermal_models/**`,
`src/engcore/domains/electrical/**` (except `ngspice.py` and
`dc_realizations.py`), `tests/domains/thermal_models/**`, new files under
`tests/domains/electrical/**`, `docs/domains/applicability-conditions.md` and
this file.

---

## 1. Changes wanted outside the owned paths — not made

### 1.1 `ScientificResult` cannot carry a validity assessment

**Where** `src/engcore/scientific/results/result.py`.

**What was hit.** `ScientificResult` has `values`, `provenance`, `validation`,
`uncertainty`, `convergence` — and no field for the model-validity verdict the
README describes as one of the four things a result carries. Every applicability
assessment this round produced therefore lives *beside* the result, computed by
whoever holds both the problem and the operating point, and the phrase
"surfaces OUTSIDE_VALIDATED_DOMAIN in the result" cannot be satisfied
literally. The integration tests assert the verdict next to the result instead,
which is honest but weaker: nothing stops a consumer from reading the numbers
and never asking.

**Proposal.** Add an optional `validity: ValidityAssessment | None = None` to
`ScientificResult`, defaulting to `None` and serialized like the other records.
`None` must mean *not assessed* and must not be confused with
`ValidityStatus.UNKNOWN`, which means *assessed, and the context was
insufficient* — two different failures with two different remedies. This is a
core change and is not a domain conditional: `ValidityAssessment` already lives
in the core and names no domain.

**Not done because** hard rule 2 forbids touching `src/engcore/scientific/`,
and this is exactly the kind of change that should be argued before it is made.

**Status after STEP 7: worked around, deliberately, and the workaround is not a
substitute.** `engcore.mcp.CredibilityEvidenceReport` carries validity itself, as a tuple
of `ModelValidityRecord` the assembler supplies. That closes the gap for anyone
holding a *package* and leaves it wide open for anyone holding a *result*: the
assessment still has to be made by whoever has both the problem and the
operating point, and a package assembled without it reports
`INSUFFICIENT_EVIDENCE` rather than pretending. So the consumer-side fix makes
the omission visible instead of making it impossible, which is the best a
consumer can do. The core change above is still the right one.

### 1.2 A categorical parameter cannot cross the provenance boundary

**Where** `src/engcore/scientific/results/provenance.py` (the `Quantity`-only
rule for `ProvenanceRecord.inputs`), `src/engcore/scientific/ir/problem.py`
(`ScientificProblem.parameter_values`), and
`src/engcore/systems/electrothermal/coupled.py` / `resistor_body.py`, which
build a thermal result's provenance from `problem.parameter_values()` wholesale.

**What was hit.** A `CategoricalValue` parameter on the thermal problem is
refused at the provenance boundary: `ProvenanceRecord` requires every recorded
input to be a `Quantity` ("provenance never records unit-stripped values"), and
`parameter_values()` is annotated `dict[str, Quantity]` while in fact returning
whatever the parameter holds. So a categorical parameter type-checks at
construction and blows up several layers later, inside the coupled runner.

**Status: downgraded, and no longer urgent.** The constant-`hA` condition used
to consume the convection regime, which made this a live correctness problem —
a declaration that could decide a verdict while being invisible to provenance.
That branch has since been removed: `conductance_excursion_ratio` takes only
the excursion and the bound, both Quantities, and no condition anywhere reads a
category. `convection_regime` survives on `LumpedApplicabilityDeclaration` as
recorded intent that decides nothing, so its absence from the problem record
now costs a reader context rather than evidence.

The proposal below is still worth doing — a domain that later wants a genuine
categorical condition (a phase, a material class, a flow regime that actually
selects a correlation) will hit this wall properly. It is no longer blocking
anything.

**Proposal, in preference order.**

1. Narrow `ScientificProblem.parameter_values()`'s annotation to the truth, and
   add a sibling `quantity_parameters()` that returns only the
   `Quantity`-valued ones. The electrothermal pack then records provenance from
   the sibling, and a categorical parameter becomes usable without weakening
   the provenance rule at all. **Preferred**: it changes one annotation and adds
   one method, and the provenance rule — which is a good rule — survives intact.
2. Let `ProvenanceRecord.inputs` accept the full `ScientificValue` union.
   Weakens a deliberate constraint for a narrow gain; not recommended.

### 1.3 `RangeCondition` bounds are fixed when the model record is written

**Where** `src/engcore/scientific/models/definition.py`.

**What was hit.** Six of the fourteen conditions added this round have a bound
that belongs to the *material or the component*, not to the relation: a
linearization band, a maximum operating temperature, a Debye temperature, a
rated dissipation, a working voltage, a compliance voltage. A `RangeCondition`
takes its bounds as `Quantity` literals at definition time, so one model record
cannot carry a per-instance bound. Every one of those conditions is therefore
stated over a dimensionless **utilization** — the operating value divided by
the declared limit, bounded by 1 — with the division done in the domain's
computed-context module.

**This is not a complaint.** The workaround is arguably the better design: a
utilization is directly comparable across components, it makes a derating
policy an explicit input rather than a hidden constant, and it keeps the core
free of any notion of a component rating. It is recorded because the pattern
now appears six times and a reader deserves to know it was a decision.

**Proposal, low priority.** If the pattern reaches a dozen instances, consider a
`RatioCondition(numerator_key, denominator_key, maximum)` in the core, which
would let the record name both operands instead of only their quotient. It
names no domain and would remove the need for each domain to pre-divide. Not
worth doing for six.

### 1.4 The coupled runner cannot surface an applicability verdict

**Where** `src/engcore/systems/electrothermal/coupled.py` and
`resistor_body.py`.

**What was hit.** `CoupledRun` and `CoupledIteration` carry results,
convergence and iterate changes. There is nowhere for the per-model
applicability verdicts of a coupled run to live, so the integration tests
compute them from the run's problems and final values after the fact. That is
the correct answer for a test and the wrong one for a caller, who has to know
which three arguments each model's assessment wants.

**Proposal.** Once §1.1 lands, `_property_result` and `_thermal_result` can
attach the verdict to the result they already build, and `CoupledRun` needs no
new field at all. Sequencing matters: doing this before §1.1 would mean
inventing a second place for validity to live.

### 1.5 `docs/TESTING.md` tier counts do not match this checkout

**Where** `docs/TESTING.md`.

**What was hit.** The header table states FAST 1261, SCIENTIFIC 1525, FULL 1529.
FAST is exact — measured 1261 before any edit. SCIENTIFIC and FULL are not: this
checkout collects **1783** tests in FULL and **1779** under `-m "not campaign"`,
with the difference entirely inside the `expensive` tier. The document is
already internally inconsistent about this (its command section quotes 1035,
1526 and 1530 for the same three tiers), so the header table appears to be the
stale part rather than something this round disturbed — no test file outside the
new ones was touched, and collection counts cannot depend on `src/` edits.

**Proposal.** Re-measure and update the three counts, on a machine and pytest
version the document names. Not edited here: it is outside the owned paths, and
a count is only worth writing down alongside the environment that produced it.

### 1.6 `tests/conftest.py` — deliberately not edited, and no edit needed

Hard rule 4 forbids editing it. No edit is needed: every test added this round
evaluates closed-form arithmetic and the three coupled integration tests run the
same ten-iteration fixed point the electro-thermal vertical milestone already
runs in FAST. The four new test modules together add 140 tests and about 1.5 s.

**The rule if one is ever needed.** A module belongs in `EXPENSIVE_MODULES` when
its tests execute scientific work costing seconds — a frozen-experiment
reproduction, a domain solver driven to a tolerance ladder, or a design study.
An applicability test is none of those: it evaluates a validity predicate over
a context, which is a handful of divisions. Should a future applicability test
need a *field* solve to establish a reference Biot profile, that module — not
the individual test — should be added to `EXPENSIVE_MODULES`, with the
static-guard allowlist carrying any test in it that only reads records.

### 1.7 Frozen and byte-pinned trees — untouched, by construction

`src/engcore/domains/thermal/`, `experiments/`,
`tests/test_sria_e1_electrical.py`, `tests/test_sria_e2_model_adequacy.py` and
`tests/test_design_d3_memory.py` were not read for edit and not written. The
lumped model lives in `thermal_models/` precisely because `thermal/` is pinned;
nothing this round changes that arrangement. Two things were wanted and not
taken:

* The frozen `Conduction1DSolver` would be the natural reference against which
  to *measure* the lumped model's Biot criterion rather than assert it — solve
  the same slab as a field and as a lump, and show where the two diverge as Bi
  grows. That requires either extending the frozen tree or a re-freeze.
* `experiments/` is where such a comparison's numbers would be pinned. A new
  experiment directory would need its own preregistration.

### 1.8 STEP 7 wanted three things outside `src/engcore/mcp/` and took none

**`src/engcore/__init__.py` now under-describes the package.** Its docstring
enumerates the sub-packages — `scientific`, `domains`, `systems`, `sria`,
`design`, `inference`, `uq`, `adequacy`, `data` — and `mcp` is missing from
that list because the file is outside the owned paths. One line to add when
somebody is next in there:

```
- ``mcp``         the verification and validation (V&V) layer: assembles a
                  credibility evidence report carrying validity, validation and
                  provenance together, and derives an advisory verdict from them
```

**`docs/TESTING.md` needs no new tier entry, but its counts are now stale
again.** `tests/mcp/` is not in `conftest.py`'s `EXPENSIVE_MODULES`, so it
defaults to FAST, which is correct: the three real-run tests drive the same
ten-iteration closed-form fixed point the electrothermal tests already run in
FAST, and the whole module costs about a second. Left unmarked deliberately —
the brief said to mark them `expensive` only if the existing rule already
covered them, and it does not.

The counts in that document are another matter. It was last corrected to
FAST 1406 / SCIENTIFIC 1924 / FULL 1928; the closeout round then added 5 tests
and this round adds 50, so the true figures measured on this checkout are:

| Tier | In the doc | Measured now |
|---|---|---|
| FAST | 1406 | **1461** |
| SCIENTIFIC | 1924 | **1979** |
| FULL | 1928 | **1983** |

Not edited, because `docs/` is outside this round's owned paths. This is the
second time these counts have gone stale within a few commits, which is the
real finding: a hand-maintained count in prose drifts every time anyone adds a
test. Worth considering whether the tier table should be generated, or the
counts dropped in favour of the commands that produce them.

**`ScientificResult.validity` — see §1.1**, whose status is updated above.

### 1.8b SUPPORTED now requires at least one attained level — DONE, and the gap it exposes

**Status: done in the consolidation round.** `derive_verdict` returns
`INSUFFICIENT_EVIDENCE` unless some check both passed and established a level.
The guard is evidential rather than numeric — it replaced "there are no checks
at all" with "no check both passed and established a level", reusing
`ValidationReport.attained_levels` as the definition of what counts. Precedence
is unchanged: `NOT_SUPPORTED` still wins.

The argument is the one the platform already makes one level down. `NOT_RUN` is
a distinct outcome because a check that did not run is not a check that passed;
absence of a result is not a result. A passing check that establishes nothing
is the same shape of thing one level up — it has failed to object, which is not
the same as having produced evidence — and reading a package of such checks as
`SUPPORTED` reintroduces exactly the substitution `NOT_RUN` exists to prevent.

**What flipped.** Two solvers in this repository produce a fully successful
report whose `attained_levels` is empty, so every package built on either is
now `INSUFFICIENT_EVIDENCE`:

* `LumpedThermalSolver` (`src/engcore/domains/thermal_models/lumped.py:1219`)
  — the known case, and the one the IN_DOMAIN electrothermal real-run tests in
  `tests/mcp/test_evidence.py` are built on. Those tests now assert
  `INSUFFICIENT_EVIDENCE`.
* `ResistancePropertySolver`
  (`src/engcore/domains/electrical/material.py:1358`) — **not previously
  named anywhere**, and a second casualty found only when the change was made.

**The gap, as a finding.** Twenty-one passing checks across eight solvers
establish nothing. That is now visible in the verdict rather than absorbed by
it, which is the point. What each would need to earn a level:

| Solver | Passing checks with `establishes=None` | Report attains a level? | What it would need |
|---|---|---|---|
| `LumpedThermalSolver` — `lumped.py:1219` | `lumped_balance_residual` | **No** | A `metric_dimensions` check on the pattern `battery/solver.py:492` already uses, comparing the three emitted metrics against the model record's `ModelOutputSpec` unit exemplars → `DIMENSIONALLY_VALID`. The record is a reference outside the arithmetic, so the level is earned rather than asserted. A march of the same ODE by an independent scheme would earn `NUMERICALLY_CONVERGED`; `ANALYTICALLY_VERIFIED` was deliberately removed from this check once and should not come back to it. |
| `ResistancePropertySolver` — `material.py:1358` | `resistance_strictly_positive` | **No** | The same `metric_dimensions` move, one metric wide: `RESISTANCE_METRIC` against the `ModelOutputSpec`'s declared unit → `DIMENSIONALLY_VALID`. Its own docstring is right that an admissibility bound verifies nothing against anything; a dimensional check would be the first thing it verifies against something. |
| `BatteryCellSolver` — `battery/solver.py:525`, `:555` | `coulomb_balance_residual`, `rint_terminal_residual` | Yes (`:500`) | Both check a closed form against the relation it was derived from. An independent integration of `dz/dt` sharing no code with the closed form would earn `NUMERICALLY_CONVERGED`; evaluating the same circuit through `electrical/dc`'s MNA path — a genuinely separate implementation — would earn `CROSS_SOLVER_VALIDATED`. |
| `ElectricalDCSolver` / `NgspiceDCSolver` — `dc/validation.py:211`, `:257`, `:297`, `:338` | `kirchhoff_current_law`, `resistor_metric_consistency`, `voltage_source_relation`, `power_balance` | Yes (`:141`, `:160`) | These are the repository's strongest argument for a **new** `ValidationLevel`: there is no member for "independently reconstructed physical consistency", and the code says so at `dc/validation.py:358-365`. Within today's taxonomy, a native-vs-ngspice agreement check would be a defensible `CROSS_SOLVER_VALIDATED` — the two paths share `assemble` but not the solve. |
| `NgspiceDCSolver` — `ngspice.py:845`, `:887` | `realization_precondition_non_singular`, `provider_element_metric_consistency` | Yes (via shared) | The first is a precondition and should stay level-free by design. The second already compares an external provider's numbers against Crafty's declared relations; widened to compare the provider's full solution against Crafty's own solve of the same circuit, it would be `CROSS_SOLVER_VALIDATED`. |
| `CSTRSolver` — `cstr/validation.py:175`, `:200`, `:256`, and `:584` in the gate | `integration_reported_success`, `trajectory_finite`, `state_physically_admissible`, `cross_method_agreement` | Yes (`:284`), but its `NOT_RUN` checks already make single-solve packages `INSUFFICIENT_EVIDENCE` | The first three are a run's honest opinion of itself and no level fits. `cross_method_agreement` is deliberately level-free because BDF and Radau share the RHS, the Jacobian and SciPy's step control; giving the second method an independent RHS and Jacobian would make it `CROSS_SOLVER_VALIDATED`, and that is real work. |
| `Conduction1DSolver` — `thermal/conduction1d/validation.py:133`, `:152`, `:163`, `:179` | `linear_system_residual`, `field_finite`, `boundary_conditions_held`, `amplitude_decay` | Yes (`:200`), and `NOT_RUN` already dominates | **Frozen path — observation only.** The refinement gate is already the intended home for level-earning here and does it. |
| `SchemeSolver` / `ReducedSchemeSolver` — `conduction1d_schemes.py:612`, `:623`, `:643` | `field_finite`, `amplitude_decay`, `boundary_conditions_held` | Yes (`:659`), and `NOT_RUN` already dominates | `amplitude_decay` does the most real work — it is a property of the equation, not the scheme. Compared against the analytic Fourier-mode decay already implemented for the sibling gate, it would be `ANALYTICALLY_VERIFIED`. Separately: `boundary_conditions_held` at `:643` is the only check in the repository emitted with **no `detail` string**, so a reader of the serialized report sees an empty explanation. |

**Not proposed here:** adding a `ValidationLevel` member for "internally
consistent". Four of the checks above want one, and inventing a level so that
more packages clear the bar is the exact move this change exists to refuse. If
the level is real it should be argued on its own merits, not on how many
verdicts it would improve.

### 1.9 `ValidityAssessment` is the one core record that validates nothing

**Where** `src/engcore/scientific/models/definition.py`, the
`ValidityAssessment` dataclass.

**What was hit.** Every neighbouring record in that file has a
`__post_init__` that coerces enums through their constructor and sequences
through `tuple()`. `ValidityAssessment` has none. So
`ValidityAssessment(status="in_domain")` stores a raw `str`,
`ValidityAssessment(status="probably_fine")` stores a string that is no status
at all, and a `list` passed for `violated` stays a list and makes the frozen
record unhashable.

**Why it matters here.** `CredibilityEvidenceReport`'s verdict is decided by set
membership over the statuses it carries. A *correct* string is harmless —
`ValidityStatus` is a `str` enum whose members hash equal to their values — but
an *unrecognised* one matches neither the NOT_SUPPORTED nor the
INSUFFICIENT_EVIDENCE branch and would fall through to SUPPORTED. A malformed
record would earn the most favourable verdict available.

**Worked around, not fixed.** `ModelValidityRecord.__post_init__` re-runs
`ValidityStatus(...)` over the carried assessment's status and refuses an
unrecognised one, with a test
(`test_an_unrecognised_validity_status_is_refused_rather_than_read_as_clean`).
That protects this consumer and nothing else — any other consumer of a
hand-built `ValidityAssessment` has the same hole.

**A second, sharper consequence.** Nothing forces the status to agree with the
record's own condition lists either, so
`ValidityAssessment(status=IN_DOMAIN, violated=("biot_number",))` constructs
happily — a record that would report SUPPORTED on the same line it names the
bound it violated. `ModelValidityRecord.__post_init__` now cross-checks against
exactly the classification `ValidityDomain.assess` performs (violated dominates
unknown dominates satisfied), so every assessment the core actually produced
passes untouched and only a hand-built one is refused. Again: protects this
consumer only.

**Proposal.** Give `ValidityAssessment` the `__post_init__` its neighbours
have: `object.__setattr__(self, "status", ValidityStatus(self.status))` plus
`tuple(...)` over the three name sequences, and the same violated/unknown
cross-check. No behaviour change for any correctly-built instance, and it makes
both workarounds above unnecessary for every consumer rather than one.

---

## 2. Conditions not implemented this round

Listed, not built. Rule 6 excluded new domains, new solvers and convection
correlations, and several of these need one of the three.

**Convection correlations, with their own Re / Nu / Gr / Ra validity ranges.**
The largest gap. This round bounds the *consequences* of a constant `hA` and
never computes an `h`. Each of the following is a correlation with a declared
range, and each range is itself an applicability condition:

* External forced flow over a flat plate — laminar `Nu = 0.664 Re^(1/2) Pr^(1/3)`
  for `Re < 5×10⁵`, `Pr ≳ 0.6`; the transition band; the turbulent branch.
* Cross-flow over a cylinder — Churchill–Bernstein, valid for `Re·Pr > 0.2`.
* Internal pipe flow — Dittus–Boelter, `Re > 10⁴`, `0.7 ≤ Pr ≤ 160`, `L/D ≳ 10`;
  the fully-developed-versus-entry-length condition is a separate one.
* Free convection from a vertical plate — Churchill–Chu, with the laminar
  `Ra < 10⁹` boundary as an explicit condition rather than a footnote.
* Mixed convection — the `Gr/Re²` ~ 1 band where neither pure regime applies,
  which is precisely the case that must not silently pick one.

These need a fluid-properties declaration (ρ, μ, k, c_p, β at a film
temperature) that the domain does not currently have. That is a new record, not
a new domain, but it is more than a round.

**Contact and interface resistance.** `R"_t,c` between a device and its heat
sink, with the condition that it is small compared with the spreading and
convection path. Needs a second exchange path, which the single-`hA` lumped
model does not have — so the honest first step is a condition asserting that
the *declared* parasitic conductance is a small fraction of `hA`, and the
second is a two-path model.

**Fin efficiency.** `η_f = tanh(mL)/mL` for a straight fin, with the condition
that the fin's own Biot number across its thickness is small — the same
criterion as the body's, one level down. Applies to the effective `hA` of a
finned surface, so it belongs with the `hA` declaration rather than with the
body.

**Spreading resistance.** For a small source on a large plate the
one-dimensional path is wrong by a factor that depends on the source-to-plate
area ratio; the condition is on that ratio.

**Temperature-dependent conductivity.** `k(T)` makes the Biot number itself a
function of temperature. The condition is on the variation of `k` across the
body's own temperature drop — a self-referential bound worth stating carefully.

**Radiation view factor.** This round's radiation condition assumes a small
object in large surroundings (view factor 1). A declared view factor and an
enclosure geometry would make it a real condition rather than a bounding one.

**Electrical, beyond DC.** Skin effect — the condition that the conductor
radius is small compared with the skin depth δ = √(2ρ/ωμ), which is what the
`electrical.dc.resistor_ohm` assumption "no parasitics" and the material
model's "no frequency dependence" actually mean. Needs a frequency, which a DC
problem does not have.

**Electrically small circuit.** Kirchhoff's current law holds while the circuit
is small compared with a wavelength — the standard `D < λ/10`. `KCL_MODEL` is
the one model touched this round that still has an empty validity domain, and
this is the condition it wants. It also needs a frequency and a physical size,
neither of which the DC problem carries, so adding it would have meant
inventing inputs rather than deepening existing ones.

**Self-heating separability.** The material model declares "no self-heating
term: T is supplied, never inferred". In a coupled run that assumption is
discharged by the coupling, and the real condition is on the loop gain
`α·P·(∂T/∂P)` — below 1 the fixed point contracts, above it the system runs
away. This is a *coupling* condition rather than a model condition, which is
why it is not on either model, and it needs somewhere in `systems/` to live.
---

# NEEDS — battery domain round

Owned paths for this round were `src/engcore/domains/battery/**`,
`tests/domains/battery/**`, `docs/domains/battery-v0.md`, appended rows in
`docs/domains/applicability-conditions.md`, and this file. Nothing below has
been done; each item is a proposal or a limitation, stated where it can be
argued with.

---

## 1. Changes wanted outside the owned paths — not made

### 1.1 `dimensionality()` compared dimensions as strings — FIXED

**Where** `src/engcore/scientific/units/quantity.py` — `dimensionality()`,
`Quantity.is_compatible_with`; `src/engcore/scientific/units/validation.py` —
`require_same_dimension`.

**Status: done.** Raised here as a proposal by the battery round, and taken in
the consolidation round as the one authorised change to the core.

**What was hit.** `Quantity(2.5, "ampere") * Quantity(0.03, "ohm")` produced a
quantity in `ampere * ohm`, and `.to("volt")` on it **raised**. The two are the
same physical dimension. The units backend renders a composite's exponents in
the order the composite was built, not in the order the named unit renders
them:

```
ampere * ohm  ->  [mass] * [length] ** 2 / [current] / [time] ** 3
volt          ->  [mass] * [length] ** 2 / [time] ** 3 / [current]
```

`dimensionality()` returned that rendering as a `str`, and every compatibility
check in the core was `dimensionality(a) == dimensionality(b)`, so two
dimensionally identical quantities compared unequal and a correct conversion
was refused as a units error.

This was not exotic. `I * R` is the single most ordinary product in electrical
work, and it was the first thing a new domain multiplying two quantities hit.
It was silent until it raised, and when it raised it reported a physics error
for a rendering detail. An exhaustive sweep over the named electrical and
mechanical units finds twenty-one distinct composite→named conversions that
the string comparison refused.

**What was done.** Two functions where there was one:

* `dimension_of(unit)` returns the backend's own `UnitsContainer`, which is a
  mapping from dimension to exponent and compares and hashes by content.
  `Quantity.is_compatible_with` and `require_same_dimension` decide
  compatibility on these objects, so no rendering is involved.
* `dimensionality(unit)` still returns a `str`, for messages, display and
  anything that serializes one — but the rendering is now **canonical**: the
  container is rebuilt with its dimensions sorted before it is rendered.

The string form was kept canonical rather than merely kept, because the
comparison sites are not all inside this subpackage. `composition/dependency.py`,
`ir/problem.py`, `models/definition.py` and
`systems/electrothermal/resistor_body.py` compare `dimensionality()` strings
directly, and those comparisons were wrong for exactly the same reason. Sorting
the rendering fixes them without editing them — which mattered, because the
consolidation round's rules confined the change to
`src/engcore/scientific/units/`.

The rebuild goes through the container's own type rather than joining
`f"{k}:{v}"` by hand, as an earlier sketch of this proposal suggested. That
keeps the rendering the backend's own and changes only its order: `[temperature]`
and `dimensionless` come out exactly as before, and only a multi-dimension
ordering — which was arbitrary — moves.

**Checked before changing.** No dataclass field stores a dimensionality and no
`to_dict()` emits one: `QuantityDependency.dimension` is a property recomputed
from its unit exemplar, not a stored field. The renderings that do reach
persisted artifacts do so inside exception text, and the one committed artifact
that carries such a message (`experiments/kinetics_k1/k1_results.json`) quotes
`pascal` and `kelvin`, whose renderings are order-invariant. No frozen digest
map pins `src/engcore/scientific/units/`.

**The workaround it forced, now removed.** `context._ohmic_drop` composed `I·R`
from magnitudes (`magnitude_in("ampere") * magnitude_in("ohm")`, tagged
`"volt"`) with a docstring explaining why. It is plain quantity arithmetic
again — `(current * resistance).to(VOLTAGE_UNIT)` — and the explanation is
gone with the reason for it. An AST sweep for the same signature (two raw
magnitudes of *different* units multiplied, result re-tagged with a literal
unit) finds no other instance anywhere in `src/`, `tests/`, `benchmarks/` or
`experiments/`.

**One asymmetry left.** `src/engcore/scientific/__init__.py` re-exports
`dimensionality` but not `dimension_of`, because that file is outside the
units subpackage and the round's rules did not authorise editing it. Anything
outside `units/` that wants the object form imports it from
`engcore.scientific.units` directly. One line to add when somebody is next in
there.

### 1.2 `ScientificResult` still cannot carry a validity assessment

**Where** `src/engcore/scientific/results/result.py`.

Already argued at length in §1.1 of the applicability round above, and this
round hits it again unchanged: every verdict this domain produces lives
*beside* the result, computed by whoever holds both the problem and the
operating point. `SelfHeatingStep` carries `validity` as its own field for
exactly that reason — there is nowhere in a `ScientificResult` to put it.

Nothing to add to the earlier proposal except a second data point: with four
models per problem, the field would need to be a *mapping* from model reference
to assessment, or a result would have to be per-model. A single
`validity: ValidityAssessment | None` would force a domain with four
independent claims to pick one, which is the collapse this domain is built to
avoid. Worth settling before the field is added, not after.

### 1.3 A composition helper for one-way coupling has nowhere to live

**Where** `src/engcore/systems/`.

**What was hit.** `domains/battery/coupling.py` marches a cell against the
lumped thermal body. It is a *composition* of two domains and by the layering
argument belongs under `systems/`, beside `electrothermal/`. It is in the
battery package because hard rule 5 makes this round a pure consumer.

**Why it is not simply "electrothermal with a battery in it".** The
electrothermal pack solves a **cyclic** dependency set with a fixed-point plan,
torn endpoints, seeds and a convergence criterion. This coupling is
**acyclic**: with a constant `R_int` the heat does not depend on the
temperature, so no fixed point exists. Running the pack's machinery here would
report `CRITERION_MET` on the first pass and thereby claim a convergence that
was never at issue.

**Proposal.** If a composition layer is wanted for sequential couplings, it
should be a *sibling* of the fixed-point runner, not a mode of it: an acyclic
execution order already has a home in `coupled.execution_order`, and what is
missing is a run record that says "acyclic, nothing to converge" without
borrowing a convergence vocabulary. `CouplingDirection` in this package is a
one-member sketch of what that record's structural field would be. Merging it
into `CouplingOutcome` would be the wrong direction: that enum answers *why the
iteration stopped*, and this one answers *whether there was an iteration*.

---

### 1.4 The cell cannot declare how its `R_int` was characterised

**Where** `src/engcore/domains/battery/context.py` — `CellSpecification` and
its declared limits; the condition is
`polarization_unmodelled_fraction` in `models.py`.

**Raised by the consolidation round**, when that condition was made two-sided.

`polarization_unmodelled_fraction` admits two regimes: the interval is long
enough that the diffusion branch has settled, or short enough that it has
barely developed. Both are defensible, but they are defensible about
*different numbers*. A settled-interval `R_int` measurement contains the
diffusion contribution; a short-pulse `R_int` measurement does not. Using a
settled value on a short pulse over-predicts the drop by roughly `I R_diff`;
using a short-pulse value on a long interval under-predicts it by the same.

The cell declares one `internal_resistance` and says nothing about how it was
obtained, so the condition can screen the *timescale* and cannot check that
the resistance belongs to the regime it is being used in. The one-sided floor
hid this by admitting only the settled regime — it was consistent by
construction with a settled measurement, and wrong about short pulses.

**Proposal.** A declared `internal_resistance_characterisation` — a
categorical, `pulse` or `settled` — and a `CategoryCondition` requiring it to
agree with the regime the interval falls in. That needs the categorical
declaration to reach a validity condition, which is §1.2 of the applicability
round above: a categorical parameter still cannot cross the provenance
boundary, so the condition could be written but the declaration could not be
recorded. **Not done for that reason**, and stated in the constant's own
documentation so a reader of the bound sees the gap at the bound.

## 2. Conditions this round deliberately did not implement

Each is a real condition on a real derived quantity. None is here because it
was hard; each needs an input the domain does not currently declare, and
inventing the input would have been worse than naming the gap.

**`R_int(T)`, and the two-way coupling it would unlock.** The single most
consequential omission. A cell's internal resistance is strongly and
non-linearly temperature dependent (Arrhenius-like, dominated by electrolyte
conductivity and charge-transfer kinetics). Modelling it would make the heat a
function of temperature, make the electro-thermal dependency **cyclic**, and
turn this round's sequential march into a genuine fixed-point problem with a
real convergence question — and a real *loop gain* condition of the same shape
as the self-heating separability item above. It is deliberately not modelled as
a linear TCR: a cell's `R_int(T)` is not metallic conduction, and reusing
`electrical.material.linear_tcr_resistance` for it would be claiming physics
this domain cannot support. It wants its own constitutive record with its own
activation energy.

**Reversible (entropic) heat.** `-I·T·dU/dT`. Not small: of the same order as
the Joule term at low rate, and it changes sign with current direction and with
state of charge, so a real cell can absorb heat while discharging. The
condition that follows is on the *ratio* of the reversible to the irreversible
term — the direct analogue of the thermal domain's
`radiation_to_convection_ratio`, and the exact statement of what dropping it
costs. Needs `dU/dT(z)` for the cell, a measured curve nobody has supplied.

**Tabulated OCV, and a condition on the chord's error.** With a measured
`OCV(z)` curve the affine chord's error is computable rather than merely
bounded by staying inside a declared window: the condition becomes
`max|OCV_chord(z) − OCV_table(z)|` over the traversed span, against a declared
tolerance. That is strictly better than `soc_window_margin` and would likely
replace it. Needs a table, which is a data-boundary question this round did not
open.

**Capacity fade and resistance growth.** A cycle count and a declared
end-of-life criterion would give `cycles_used / rated_cycles ≤ 1` and, more
usefully, a condition on whether the *declared* `Q_nom` and `R_int` still
describe a cell this far into its life. Needs a cycle count on the declaration,
which is a state the problem IR would carry as a parameter — cheap to add, but
it is a new physical claim (a fade law) and not merely a new bound.

**Charge acceptance at low temperature.** The narrow charge-temperature range,
and the lithium-plating boundary that sets its cold end. The domain models
discharge only and says so, in the model records, the docs and a test; adding
the condition means adding charging, which is a sign convention change through
every derivation and a second set of ratings.

**Pack-level: cell-to-cell spread.** A series string is treated as one lumped
cell. The real condition is on the spread of capacity and resistance across the
string against a declared tolerance — a weakest-cell bound, since the string's
usable capacity is the weakest cell's. Needs a population, not a cell, and
therefore a different declaration record.

**Thermal runaway onset.** Deliberately absent and deliberately *not*
approximated. The lumped balance has no exothermic decomposition term, so
nothing in this domain can represent runaway; a condition purporting to bound
it would be the most dangerous kind of unearned claim this repository could
ship. If it is ever wanted it needs its own model, its own kinetics and its own
validation evidence — not a threshold bolted onto a linear balance.

---

## 3. One test-tier note

The 178 tests added this round are all in **FAST**, correctly: they execute
closed-form arithmetic and the whole directory runs in about 4 s. No
`expensive` marker is needed, and `tests/conftest.py` is untouched.

Two collisions with existing suite invariants were hit and avoided rather than
worked around, and both are worth knowing about before the next domain is
added:

- **A second `conftest.py` anywhere under `tests/` shadows the root one.**
  `tests/test_tier_classification.py` does `from conftest import CAMPAIGN_TESTS,
  ...`, and pytest prepends each test file's own directory to `sys.path`, so a
  `tests/domains/<x>/conftest.py` breaks that import for the whole suite. The
  shared builders here live in `battery_cases.py` instead. A note in
  `docs/TESTING.md` would save the next person the same hour.
- **Test module basenames must stay globally unique.** A
  `tests/domains/battery/test_context.py` collides with
  `tests/domains/thermal_models/test_context.py` under the default import mode.
  The modules here are prefixed `test_battery_`. `docs/TESTING.md`'s
  parallel-safety table records "duplicate module basenames: none" as a
  *finding*; it is really a *requirement*, and saying so where a new domain
  author will read it would help.
