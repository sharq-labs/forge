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

**Status: DONE in the recommendations round**, as that round's one authorised
core change.

**What was built, and where it differs from the proposal above.** The field is
a **mapping** — `validity: Mapping[str, ValidityAssessment]`, keyed by model id
— and not the single optional assessment proposed here. The proposal was
written from the single-model case and does not survive a coupled result: a run
whose thermal model is in domain and whose material model is not has two
answers, and one field would have had to report one of them, wrongly, half the
time. Empty is the default, so no existing construction site moved.

**Not assessed is not UNKNOWN, structurally rather than by documentation.** The
proposal named the distinction; keeping it needed four things, and all four are
in place:

* a `None` value in the mapping is refused, so there is no representation of
  "listed, but not assessed" — a model is either a key with a real assessment
  or it is not a key;
* `validity_of()` raises for an unassessed model rather than returning `None`
  or synthesizing an `UNKNOWN`, because either would put a caller one `or` away
  from confusing the two;
* `is_assessed()` is the total counterpart, and asking it is the point at which
  the difference becomes visible at a call site;
* `unassessed_models` enumerates declared models with no assessment, so the gap
  is countable rather than implicit.

Nothing in `results/result.py` writes a status of its own. An assessment must
also name a model the result declares, and a result carrying assessments while
declaring no models is refused: a verdict that cannot be attributed to a model
at a version is not a verdict about this result.

**Serialization.** `scientific_result/3`, on this repository's own precedent for
`data_references`: whether the model applied is scientific content, so a reader
that accepted the payload and dropped the field would report a result while
losing the answer to *may I rely on this* — most dangerously for a result
recorded as `OUTSIDE_VALIDATED_DOMAIN`. `/1` and `/2` still load, as not
assessed, which is the truth about writers that could not carry one. Four tests
pinned the old string and each was updated with the reason rather than deleted.

**The consumer side.** `CredibilityEvidenceReport.from_result` reads
`result.validity` and turns each entry into a `ModelValidityRecord`, which
remains the transport — `derive_verdict` still reads this report's own field and
none of its rules changed. The caller's `validity=` argument is still accepted,
because a producer that does not hold the operating point carries nothing. The
two sources are **merged, not ranked**: a model named by both must carry the
identical assessment, and two different verdicts for one model raise rather than
being resolved by precedence, since silently preferring either would let one
verdict replace another with nothing in the record to say so.

**What is still worked around.** §1.9 is untouched: `ValidityAssessment` still
has no `__post_init__`, so `results/result.py` re-runs `ValidityStatus(...)`
over every assessment it is handed and refuses an unrecognised one — the same
local guard `ModelValidityRecord` already carries, now in a second place. That
is two consumers protecting themselves where the record should protect all of
them, and it is the argument for doing §1.9.

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

**What flipped.** Two solvers in this repository produced a fully successful
report whose `attained_levels` was empty, so every package built on either
became `INSUFFICIENT_EVIDENCE`:

* `LumpedThermalSolver` (`src/engcore/domains/thermal_models/lumped.py`)
  — the known case, and the one the IN_DOMAIN electrothermal real-run tests in
  `tests/mcp/test_evidence.py` are built on. **Resolved in the recommendations
  round:** the solver now emits a second check, `analytic_reference_agreement`,
  comparing the closed form against
  `domains/thermal_models/lumped_reference.py` — a reconstruction of the
  solution from the governing equation's coefficients by series recurrence,
  sharing no code and no derived quantity with it. That check earns
  `ANALYTICALLY_VERIFIED`, and those tests now assert `SUPPORTED`.
  `lumped_balance_residual` still establishes nothing; the level came from new
  evidence, not from relabelling the check that had none.
* `ResistancePropertySolver`
  (`src/engcore/domains/electrical/material.py:1358`) — **not previously
  named anywhere**, and a second casualty found only when the change was made.
  Still attains nothing.

**The gap, as a finding.** Twenty-one passing checks across eight solvers
establish nothing. That is now visible in the verdict rather than absorbed by
it, which is the point. What each would need to earn a level:

| Solver | Passing checks with `establishes=None` | Report attains a level? | What it would need |
|---|---|---|---|
| `LumpedThermalSolver` — `lumped.py` | `lumped_balance_residual` | **Yes, since the recommendations round** — from `analytic_reference_agreement`, not from this check | This check stays level-free and should. The level came from a *second* check with an independent reference behind it, and the earlier note here was half wrong: a march of the same ODE does **not** earn `NUMERICALLY_CONVERGED`, because the lumped solver has no discretization to converge — refining the reference refines the reference. The reference module's docstring argues that at length. Still outstanding: a `metric_dimensions` check on the pattern `battery/solver.py:492` already uses, comparing the three emitted metrics against the model record's `ModelOutputSpec` unit exemplars → `DIMENSIONALLY_VALID`. |
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

**Audited in the recommendations round.** Every check above in
`domains/battery/**` and `domains/electrical/**` (excluding `ngspice.py`) is
now classified in `docs/domains/evidentiary-levels.md`: 1 earnable now and
built, 3 earnable later with their costs, 7 never earnable by the check that
raised them. Two of this table's own suggestions were found to be wrong and are
corrected there — an independent integration of the battery's `dz/dt` earns
nothing, because the trajectory is affine and the solver has no discretization;
and the `rint` cross-check is blocked by an architecture decision (it would be
the first domain-to-domain import in `src/engcore/domains/`) rather than by
effort.

### 1.8c `linear_system_residual` awards a level the lumped and conduction solvers refuse

**Where** `src/engcore/domains/electrical/dc/validation.py:157-165`.

**What was found.** `check_linear_residual` awards `NUMERICALLY_CONVERGED` when
`||A x - z||` is at round-off. The frozen conduction validation opens by
refusing exactly that move, on the grounds that a direct factorization's
residual sits at round-off in every run and so certifies a coarse solve as
confidently as a fine one.

**Why the DC case is not identical, and why that does not rescue it.** The MNA
system is the exact statement of the circuit's Kirchhoff laws, not a
discretization of a continuum, so there is no discretization error a refined
solve would reveal. But with nothing to refine there is no sequence whose limit
could be examined, and the level is *not applicable* rather than *attained* —
the same conclusion the lumped model reached this round about its own closed
form, where `NUMERICALLY_CONVERGED` is explicitly declared unearnable for a
solver that never discretized.

**Proposal.** Move it to `establishes=None`, with a detail string saying the
system is solved exactly and there is nothing to converge. The report still
attains `DIMENSIONALLY_VALID` from `check_dimensions`, so no verdict moves and
no existing package downgrades.

**Not done.** Un-awarding a level from the most widely used solver in the
repository is a decision to take deliberately. Recorded here for that decision
rather than made inside an audit.

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

---

# NEEDS — problem-builder round (STEP 8)

Owned paths this round: `src/engcore/mcp/**`, `tests/mcp/**`, and this file.
Everything below was hit while building `engcore.mcp.problem`, the boundary
that turns a JSON case description into posed problems. Nothing here has been
done; each item is a proposal or a limitation, stated where it can be argued
with. Items already recorded above are referenced rather than repeated.

## 1. Changes wanted outside the owned paths — not made

### 1.1 `ModelInputSpec` cannot say which condition an input unlocks

**Where** `src/engcore/scientific/models/definition.py` — `ModelInputSpec`,
`ValidityDomain`.

**What was hit.** The brief for this round asked the capability description to
report, for each optional field, *which validity conditions it feeds*, derived
from the registries so it cannot drift. It is not derivable by reading them.
`ModelInputSpec` carries `name`, `source_kind`, `unit_exemplar`, `value_kind`,
`role`, `required` and a prose `description`. A `RangeCondition` carries a
`name` and bounds. Nothing connects the two: the condition names a *derived*
quantity (`biot_number`), the input names a *declaration*
(`body_conductivity`), and the function that turns one into the other lives in
the domain's `context.py` as ordinary Python.

`lumped.py` states, at the head of its optional inputs, that declaring them on
the record is "what makes 'which declaration unlocks which condition'
recoverable from the model record alone". That is true of *whether* an input is
optional. It is not true of the mapping: the record says `body_conductivity` is
optional, and says nothing about `biot_number` going UNKNOWN without it.

**Worked around, not papered over.** `describe_electrothermal_case` measures
the mapping instead of reading it: it builds a fully-declared probe
declaration, assesses the model's own `ValidityDomain` at a fixed operating
point, then drops one field at a time and reports which conditions moved into
`unknown`. The answer is exact and cannot drift, because it is the domain
answering about itself. Three costs, all real:

* **It needs an operating point.** Which condition reads which declaration is
  a static fact about the model, and measuring it requires inventing numbers
  (`_PROBE_TEMPERATURE`, `_PROBE_AMBIENT`, `_PROBE_HEAT`). They are documented
  as a measuring instrument and never as defaults, but a static fact should not
  need a temperature to discover.
* **It costs an assessment per optional field**, plus one per pair — see §1.2.
* **A condition that is UNKNOWN for an unrelated reason has to cancel out**,
  which it does only because the comparison is against the same operating point
  with and without the field. That is a correctness argument a reader has to
  reconstruct rather than read.

**Proposal.** An optional `unlocks: tuple[str, ...]` on `ModelInputSpec`,
naming the conditions that become decidable when the input is supplied, plus a
`ValidityDomain` check that every named condition exists. It is a declaration
the domain author already knows and currently writes in prose — the
descriptions on those eight lumped inputs each say which group they are for.
The check is what stops it from becoming another comment that drifts.

**Not done because** hard rule 2 forbids touching `src/engcore/scientific/`,
and adding a field to the record every domain writes is exactly the kind of
change that should be argued before it is made.

### 1.2 Nothing can express that two declarations are alternatives

**Where** `src/engcore/scientific/models/definition.py` — `ModelInputSpec`.

**What was hit.** The lumped model accepts a characteristic length either
directly (`characteristic_length`) or as `body_volume / surface_area`. Both are
`required=False` and nothing relates them, so a caller reading the record sees
two independent optional fields and no hint that supplying neither loses the
Biot number while supplying either keeps it.

The omission probe in §1.1 reports this *correctly and uselessly*: dropping
either one alone changes nothing, so each measures as unlocking nothing — the
same answer the probe gives for `convection_regime`, which genuinely is read by
nothing. Two very different facts, one indistinguishable measurement.

**Worked around.** A second pass drops each such field *together with* each
other such field and reports the pair when the joint omission bites, so the
description distinguishes "interchangeable with `body_volume`, and between them
they unlock the Biot and Fourier numbers" from "inert". It is quadratic in the
number of silent fields and it only finds **pairs**: a three-way alternative
would show up as a group of fields all reporting nothing. This domain has no
three-way group, so the limitation is currently theoretical — and it is a
limitation of the workaround, not of the domain.

**Proposal.** A `requires_one_of: tuple[tuple[str, ...], ...]` on
`ValidityDomain`, or an `alternatives` group id on `ModelInputSpec`. Either
makes the relationship a fact of the record instead of something a consumer
rediscovers by search.

### 1.3 A declared field with no model input is invisible to a registry-derived description

**Where** `src/engcore/domains/thermal_models/context.py` —
`LumpedApplicabilityDeclaration.convection_regime`; the model record in
`lumped.py`.

**What was hit.** The declaration record has nine fields. The lumped model
declares eight of them as inputs. `convection_regime` is the ninth: it is
validated against `CONVECTION_REGIME_VOCABULARY`, serialized with the record,
carried into the report as caller-asserted context — and it is not a
`ModelInputSpec`, because no condition reads it and the model would otherwise
be claiming an input it does not use.

That is the right call for the model record and it leaves a hole for a
consumer. A boundary that derived its accepted field set from the registry
alone would refuse `convection_regime` as an unknown field, and a caller who
declared it — which the declaration record invites — would be told their
payload was wrong.

**Worked around.** `engcore.mcp.problem` derives the *facts* about each field
from the registry but takes the field *list* from a binding table that also
carries the categorical, marked as declared-but-not-modelled and described as
unlocking nothing. `_audit_bindings` checks the other direction at import: any
model input not bound and not listed as coupling-supplied is a loud failure, so
the table cannot fall behind the models. It can still fall behind a
*declaration record* that grows a tenth field, which is the residual gap.

**This is not §1.2 of the applicability round.** That entry is about a
categorical parameter being unable to cross `ProvenanceRecord`, which admits
only Quantity inputs. This one is about the *model record* not naming the
categorical at all, so a registry-derived description cannot see it. The two
have the same root — categoricals are second-class — and different remedies.

**Proposal.** Let `ModelInputSpec` carry a non-quantity input with
`value_kind=ValueKind.CATEGORY`, `required=False` and no `unit_exemplar`, and
let a model declare an input it does not read as long as it says so. The record
then describes what a caller may state, rather than only what the mathematics
consumes.

## 2. Deliberately not built this round

**No inverse of the builder.** There is no `problem_to_payload`. A round trip in
that direction would have to invent a payload for a `ScientificProblem` this
boundary did not build, and the honest answer for such a problem is that it has
no payload — not a reconstructed one that happens to run.

**No defaults for any optional declaration.** The one design pressure worth
recording: an agent writing a payload from a natural description will omit
fields it was not told about, and every omission costs it a condition. That is
uncomfortable and it is correct. The alternative is a boundary that fills in a
conductivity and reports IN_DOMAIN for a body nobody characterised.

**`coupling.seed_temperature`, `tolerance` and `max_iterations` are accepted
but are not physics.** They are execution properties, and `ThermalBody`'s own
docstring argues that a body carrying one would have made changing an
integrator into a change of physical identity. They live in a separate
`coupling` block for that reason, feed no condition, and are reported by the
description as unlocking nothing.

**No second system pack.** The boundary is electro-thermal only. The binding
table and the audit are written so that a second pack would add a second table
and a second description function rather than a flag on this one, but nothing
here has been generalised on the strength of one case.
