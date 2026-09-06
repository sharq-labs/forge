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


---

# NEEDS — recommendations round

Owned paths this round: `src/engcore/domains/thermal_models/**`,
`src/engcore/domains/battery/**`, `src/engcore/domains/electrical/**` (except
`ngspice.py`), `src/engcore/scientific/results/**` as the one authorised core
change, `docs/**`, `README.md`, their tests, and this file.

Three items already recorded above were resolved rather than re-proposed here
and are updated in place: §1.1 (`ScientificResult` cannot carry validity —
**done**), §1.8b (the lumped solver's empty `attained_levels` — **done**, and
its predictions about how corrected), and the new §1.8c below it (a level
awarded from a linear residual — **proposed, not made**).

---

## 5. `scientific/experiments/optimizer_adapter.py` — recommendation: keep, and stop calling it a leftover

**Where** `src/engcore/scientific/experiments/optimizer_adapter.py`, 271 lines,
exported from `scientific/__init__.py`.

**The question asked.** It is a leftover of the Bayesian-optimizer line removed
in September 2026. Is it a general facility or a vestige?

**Finding: the module is two things with different standing, and only one of
them lost a consumer.**

`CandidateCodec` and `ObjectiveEncoder` are **a general facility, and
load-bearing**. They are the unit ↔ unit-cube boundary itself, not the
optimizer that was going to sit behind it. DESIGN-D2's *preregistration* names
this codec as the frozen, continuous-only baseline its mixed-variable sampler
must not widen or rewrite — "D2 must **not** silently widen or rewrite that
frozen adapter" — and its freeze document repeats it twice more. A D2 test
asserts the codec still refuses a mixed design space. A frozen milestone's
reference point is not a vestige.

`NumericSearchBackend` is **a boundary with nothing behind it, which is its
declared shape**. The core is *required* never to import a concrete optimizer;
the protocol exists so it does not have to. Its emptiness is the invariant
working, not the invariant rotting. What was removed in September was a
consumer, and a boundary outlives the consumer that motivated it.

**So the defect is documentary, not structural.** Nothing in the module or in
`docs/scientific-core/README.md` said the backend line had gone, so a reader
found a protocol with no implementation and reasonably concluded the module was
dead. **Done this round:** a history paragraph in the module docstring saying
what was removed, which half is frozen and by whom, and why the empty protocol
is deliberate. No behaviour changed and no export moved.

**What would break if it were removed** — 33 tests, in two places:

* `tests/test_scientific_core.py` — six tests directly:
  `test_codec_round_trip_scientific_to_vector_to_scientific`,
  `test_codec_accepts_compatible_units_and_rejects_bare_numbers`,
  `test_codec_requires_bounded_continuous_variables`,
  `test_optimizer_adapter_encodes_objective_direction`,
  `test_optimizer_adapter_refuses_silent_objective_choice`,
  `test_adapter_drives_a_synthetic_search_backend_end_to_end`. The module also
  imports `OptimizerAdapter` at module level, so collection of all 110 tests
  there would fail until the import was removed.
* `tests/test_design_d2_mixed_generation.py` — imports `CandidateCodec` at
  module level, so **all 27 collected tests in a frozen milestone's suite fail
  at collection**, not just the one that uses it.

`tests/test_heterogeneous_ngspice.py::test_h_universal_core_gained_nothing_and_knows_no_provider`
would keep passing — its assertion is over other names — but its comment, which
names `OptimizerAdapter` and `NumericSearchBackend` as pre-existing design-search
exports so a provider scan does not flag them, would become stale.

**Recommendation: keep, unchanged.** Removing it edits a frozen milestone's
reference point to delete a boundary whose absence of an implementation is the
property the boundary exists to have. If a future round disagrees, the argument
to answer is D2's preregistration, not the line count.

---

## 6. The derived-quantity pattern — a proposal, nothing built

**Where** `domains/thermal_models/context.py` (18 functions) and
`domains/battery/context.py` (29). Both repeat one shape: take problem inputs as
optional `Quantity`, return `None` if any is absent so the condition reads
UNKNOWN, otherwise compute a dimensionless group.

**The abstraction.** A declarative `DerivedQuantity` record — name, required
input names with their expected dimensions, and a pure function over the
resolved values — plus one resolver that reads the inputs, returns `None` on
the first absent one, and checks dimensions on the rest. Each of the 47
functions becomes a record; `_checked(...)` disappears.

**What it would eliminate.** The `_checked` calls and the `if x is None:
return None` chain, which is 60–70% of the lines and the *only* part that is
mechanical. It would also make the input→quantity map data rather than code,
which is exactly what `NEEDS.md` §1.1 of the problem-builder round wants and
cannot get: `ModelInputSpec` cannot name the conditions an input unlocks, and
the builder currently *measures* that mapping by dropping fields and re-asking
the validity domain. A record that named its inputs would make that derivable.

**What it would cost.** The bodies are not the boilerplate. `soc_window_margin`
is asymmetric about the chord, `conductance_excursion_ratio` takes a bound and
an excursion with a sign convention, `peukert_effective_capacity` is a power
law with a reference current, and several return `None` for reasons other than
an absent input — a non-positive denominator, a regime the correlation does not
cover. A resolver whose only `None` is "an input was missing" cannot express
those, so they become an escape hatch, and an abstraction with an escape hatch
used by a third of its callers has not abstracted the hard part.

**What it would make harder.** Two things this repository values. First, the
docstrings: each of these functions carries a definition, a citation, and a
statement of what the group does *not* mean, and those are what make the
conditions auditable. A record-based form pushes them into a string field on a
record, where nothing reads them and they drift. Second, the failure mode: a
resolver that silently returns `None` on any missing input makes it harder to
see which input was missing — and "which one" is precisely what the UNKNOWN
verdict has to report. The explicit chain is verbose and it is legible at the
point of failure.

**Would a fourth domain justify it?** Not on its own. The evidence that would
is different: **two domains needing the same derived group**, at which point
there is a definition to share rather than a shape to share. Today there is
none — Biot and Fourier are thermal, Peukert and the SOC window are
electrochemical, and a shared record would give them a common container and no
common content.

**Recommendation: do not build it now.** Build the *narrow* half if anything:
the input→dimension declaration, which §1.1 of the problem-builder round
already needs for a different reason and which does not touch a single function
body. The full abstraction should wait for a shared derived quantity, not a
third repetition of a shape.


---

# Adversarial fixes round — F01 to F11

Owned paths for this round were, per task: `src/engcore/mcp/**` and
`tests/mcp/**`; `src/engcore/domains/**` except `thermal/`, and their tests;
`src/engcore/scientific/results/validation.py`,
`src/engcore/scientific/results/**`, `src/engcore/scientific/units/**` and
`src/engcore/mcp/evidence.py` for the three authorised core changes;
`src/engcore/domains/electrical/ngspice.py` and
`src/engcore/systems/electrothermal/**`. TASK 7 was given no owned-path line.

Everything below is either a change made **outside** those paths and why, or
something wanted and not done.

---

## A1. Files changed outside a task's stated owned paths

Four, each unavoidable to keep FAST green or to put a function where it belongs.

### A1.1 `systems/electrothermal/coupled.py` — `dependency_closure` (TASK 1)

TASK 1 owns `src/engcore/mcp/**`. The closure walk went into `coupled.py`
instead, beside `execution_order` and `cycle_edges`, which are the same kind of
graph function over the same `QuantityDependency` records. Putting it in the
payload boundary would have made a composition concept private to a module that
poses problems, and unavailable to the next consumer that needs it.

### A1.2 `tests/domains/thermal_models/test_lumped_verification.py` (TASK 1)

`test_a_real_applicable_electrothermal_run_is_supported` asserted the nominal
electrothermal verdict was SUPPORTED. Assembling the report over the dependency
closure makes it INSUFFICIENT_EVIDENCE, because nothing in the payload declares
a resistor's rated dissipation or a source's current limit and
`electrical.dc.kcl` declares no conditions at all.

The test now makes its actual claim — the level is attained, the thermal model
is in domain, and `derive_verdict` over the thermal evidence alone returns
SUPPORTED — and is renamed to `..._earns_its_level`. Its subject, that the
lumped solver's reference comparison establishes something, is unchanged and
still pinned. Nothing was weakened to make a verdict nicer.

### A1.3 `tests/test_model0r_differential.py` (TASK 5)

One line, and then reverted. It `json.dumps`-ed a record's internal metadata
mapping directly. The first `FrozenMapping` implemented `Mapping` rather than
`dict` and broke it; switching to a `dict` subclass made the edit unnecessary
and it was put back. Recorded because the intermediate state is in the branch's
history.

### A1.4 `tests/test_scientific_core.py` (TASK 3)

TASK 3 owns `validation.py`, `mcp/evidence.py` and "tests". The four core-level
F04 tests went into `test_scientific_core.py`, which is where `ValidationCheck`
is already tested. Additions only; no existing test was edited.

---

## A2. Wanted and not done

### A2.1 F09's shared classification cannot live in the core

**Where** `src/engcore/scientific/models/definition.py`.

**What was asked.** "Make core and wrapper share one classification." The ideal
form is a single function in the core, called by `ValidityDomain.assess` and by
`ModelValidityRecord` — literally one implementation, incapable of drifting.

**Why it was not built.** HARD RULE 3 permits `src/engcore/scientific/` to
change only in TASKS 3, 5 and 6, and F09 is TASK 7. The core would have to
import the function, which is a core edit.

**What was built instead.** `classify_assessment` in `mcp/evidence.py`, stating
the rule once on the wrapper side, plus a test that drives every assessment
reachable from `ValidityDomain.assess` — over a family of domains and contexts,
including the empty domain — through the boundary and asserts the statuses
match. That makes the agreement checkable rather than asserted, which is most
of the value; what it does not do is make divergence impossible.

**What it needs.** Move `classify_assessment` into
`scientific/models/definition.py` and have `ValidityDomain.assess` call it.
About ten lines, and it deletes the cross-check test's reason to exist.

### A2.2 `combine_assessments` is implemented twice

**Where** `mcp/evidence.py` (`combine_assessments`) and
`domains/battery/coupling.py` (`_over_the_step`).

**What was hit.** Both reduce several `ValidityAssessment`s to one by the same
rule — violated anywhere wins, then unknown anywhere, then satisfied
everywhere. TASK 1 needs it across the elements one model was applied to; F10
needs it across the instants within a step. They are the same six lines.

**Why not shared.** The natural home is the core beside `ValidityAssessment`,
which HARD RULE 3 puts out of reach for both tasks. `domains/battery` must not
import `mcp`, and `mcp` importing a battery helper would be worse.

**What it needs.** One `combine_assessments` in
`scientific/models/definition.py`, with both call sites importing it. The two
copies are byte-identical in behaviour today and there are tests on both, so
the risk is drift rather than a present defect.

### A2.3 The credibility report still carries only one sub-result's checks

**Where** `mcp/problem.py`, `run_electrothermal_case`.

**What was hit.** TASK 1 assembles `validity` and `contributing_models` over
the dependency closure, and the coupling outcome beside them. It does **not**
merge the `validation` checks of every result in the closure: the report still
carries the thermal sub-result's checks and its `validation_notes`.

That is what the task asked for — it named the coupling outcome, the
participating models and their assessments — and it is not a false statement,
because the checks are labelled as what they are. But a reader of the report
sees provenance for six models and checks for one.

**Why not done.** Check names would collide across stages and across
participants (`dimensional_consistency` exists in more than one solver), and
`ValidationReport` refuses duplicates for a good reason. Namespacing them as
`"{problem_id}:{name}"` would rename a solver's own check inside a record that
claims to carry it unaltered, which is a small forgery of exactly the kind this
layer exists to refuse.

**What it needs.** A decision about whether a report may carry checks from
several producers at all, and if so a record that keeps each check attributed
to the result it came from rather than flattening them into one list. That is a
schema change to `CredibilityEvidenceReport`, not a patch.

### A2.4 The electrical rating declarations have no payload field

**Where** `mcp/problem.py`, `_BINDINGS`.

**What was hit.** Since TASK 1 the report assesses `electrical.dc.resistor_ohm`
and `electrical.dc.ideal_voltage_source`, whose conditions are stated over a
declared rated dissipation, working voltage and source current. The payload has
no field for any of them, so every one is UNKNOWN and the nominal case is
INSUFFICIENT_EVIDENCE.

**This is the correct verdict and was not compensated for.** An unrated part is
not an unlimited part, and the gap was there before — it was invisible only
because the models that ask were not in the report.

**What it needs.** Three optional fields under `stages[].conductor` bound to
`ComponentRating`, and one under the root for the source. Small, and
deliberately not done here: adding payload fields in the same commit that made
the gap visible would have looked like — and partly been — arranging for the
verdict to come out nicer.

### A2.5 `electrical.dc.kcl` declares no validity conditions

**Where** `domains/electrical/dc/models.py`.

**What was hit.** Its `ValidityDomain` carries a description and no conditions,
so `assess` correctly returns UNKNOWN and the report says so. Kirchhoff's
current law is not in doubt; what is undeclared is the lumped-circuit regime it
holds in — no charge accumulation at nodes, which fails at high frequency or
across a distributed structure.

**What it needs.** A condition over something the caller declares. There is no
obvious dimensionless group here that this repository already computes — an
electrical length over a wavelength would need a frequency and a geometry the
DC domain does not model. Recorded rather than invented.

### A2.6 `FrozenMapping` is a `dict` subclass, and that is a weaker guarantee

**Where** `scientific/results/immutable.py`.

**What was hit.** `dict.__setitem__(m, k, v)` reaches past the overridden
mutator. The `Mapping`-based version had no such hole and was tried first; it
broke fifteen multirotor tests, because records' mappings are handed to
`json.dumps` and splatted with `{**m}` throughout the repository.

**What was done about it.** The override list is generated from
`DICT_MUTATORS`, and a test asserts `DICT_MUTATORS | DICT_NON_MUTATORS` is
exactly `set(dir(dict)) - set(dir(Mapping))` against the running interpreter, so
a future CPython dict method fails there rather than opening a hole silently.

**What it needs.** Nothing, unless the platform decides it wants the stronger
guarantee — in which case the work is auditing every consumer that treats a
record's mapping as a `dict`, which is the audit this round declined to do
inside a fix for something else.

### A2.7 Serialization got slower and no consumer was profiled

**Where** `scientific/results/`.

**What was hit.** `ScientificResult.to_dict` is 12.6 → 20.6 us and
`ProvenanceRecord.to_dict` 3.5 → 7.5 us per call (best of 7, this machine). FAST
is unchanged within noise; SCIENTIFIC is up ~4.6% like-for-like, which is inside
the 9–14% spread this suite's own performance audit measured for identical code
and is therefore not resolvable by that instrument.

**What it needs.** The campaign persistence path is where serialization is
actually hot, and it was not profiled — only the suite was timed and the
operations microbenchmarked. If the cost matters there, the next lever is
caching a record's payload, which is only sound *because* the record is now
immutable. That is a real follow-on and is not free: a cached payload has to be
invalidated by `dataclasses.replace`, and nothing today would catch a miss.

### A2.8 TASK 4 refuses at the transfer boundary only

**Where** `systems/electrothermal/coupled.py`, `_transport`.

**What was hit.** The guard fires when a value is *transported* out of a
FAIL-validation result, which is what the task specified. A result that fails
validation and whose values nothing transports is not refused; it lands in
`CoupledIteration.results` and the run continues.

**Whether that is right.** Arguably yes — the run did not rely on it — and
arguably a coupled run containing a rejected sub-result should say so whatever
was read out of it. Since TASK 1, the credibility report would carry it if the
report merged checks across the closure, which A2.3 says it does not.

**What it needs.** The A2.3 decision. The two are the same question asked from
opposite ends.

### A2.9 The resistor assessment named a resistance the circuit had not used — FIXED, and narrower than it reads

**Where** `mcp/problem.py`, `_electrical_assessments`.

> **Scope, before anything else — this entry has been read too broadly once and
> a round of work was planned on the misreading.**
>
> **The resistor *rating* conditions never read the reference resistance.**
> `dissipated_power_utilization` and `working_voltage_utilization` are computed
> from `dissipated_power` and `voltage_across`, which arrive as *arguments* to
> `assess_resistor_validity` out of the **converged** electrical result. They
> have always been at the converged operating point and this entry never said
> otherwise.
>
> **The defect could only ever reach one condition: `resistance > 0`.** It was
> in the *element list* — the one-element `resistor_relation_problem` built from
> `system.circuit_at(...)` — and the only resistor condition that reads the
> element's `resistance` parameter is the positivity check. Both readings are
> strictly positive in any run that reaches the assessment, so **no verdict
> could move, and none did.**
>
> If a benchmark case disagrees with the tool about a rating, **this entry is
> not the explanation.** Look at the operating point the ground truth was
> computed at. See §B.6.

**What was hit.** The element list was built from `system.circuit_at(...)` at
the **nominal** reference resistances, so the one-element
`resistor_relation_problem` carried the conductor's declared reference
resistance rather than the `R(T)` the converged circuit actually used.

**Why it was left, at the time.** It cannot change a verdict, for the reason in
the scope note above. The report names conditions, not values, so its content
is identical either way.

**Why it was still worth changing.** "The element as the run had it" and "the
element as the caller declared it" are different statements, and letting those
blur is how a report comes to name a number nothing computed.

**DONE.** `_electrical_assessments` now builds its element list from
`cp.converged_resistances(system, run)`, which reads each stage's `R(T)` back
out of that stage's own property result rather than evaluating the TCR form a
second time — two implementations agree until one of them does not. It raises
rather than falling back when a stage's result is absent: a rating assessed at
the reference value without saying so is a wrong value read confidently.

The prediction held exactly. **No verdict moved**, on any of the 2000 hard
benchmark cases or anywhere in the suite. Every one of the four benchmark
metrics was byte-identical before and after.

**What this did NOT fix, and what was wrongly attributed to it.** `S00709`, the
hard benchmark's one false reject. §B.6 said the tool "computes 3.5634 W" —
the dissipation at the reference resistance. It does not; it computes 3.5240 W,
the converged value, and 3.5240 W is over the 3.49889 W rating as well. That
case is mislabelled by the generator, not misread by the tool, and §B.6 now
carries the corrected account. The arithmetic is pinned in
`tests/mcp/test_problem.py::test_s00709_is_over_its_rating_at_every_resistance_the_run_can_offer`
so neither entry can drift back into the wrong story.

---

# NEEDS — MCP server round (STEP 9)

`src/engcore/mcp/server.py`, `tests/mcp/test_server.py` and the server section
of `docs/mcp/README.md` were added. Nothing outside those paths was edited.

## 1. Changes wanted outside the owned paths — not made

### 1.1 `pyproject.toml` has no `[mcp]` optional dependency group

**Where** `pyproject.toml`, `[project.optional-dependencies]`.

**What was asked.** Add the MCP SDK as an optional group `[mcp]`.

**Why it was not made.** HARD RULE 4 of this step names the owned paths and
`pyproject.toml` is not among them. The step anticipated this and asked for the
exact stanza here instead.

**The stanza.** Add to `[project.optional-dependencies]`, beside `dev`:

```toml
mcp = [
  # Official Model Context Protocol Python SDK, for engcore.mcp.server.
  # Transport only: no production code outside that module imports it, and
  # the suite must remain runnable — and green — without it, which
  # tests/mcp/test_server.py achieves with pytest.importorskip.
  # Upper bound is deliberate: 2.x renamed FastMCP to MCPServer and moved
  # the wire fields to snake_case, so a 3.x would be a rewrite, not an
  # upgrade.
  "mcp>=2.1,<3",
]
```

**The manual install** until it lands, and what `docs/mcp/README.md` documents:

```
pip install "mcp>=2.1,<3"
```

Developed and tested against `mcp` 2.1.1 on Python 3.14.2.

### 1.2 A payload error carries its field only in the message text

**Where** `src/engcore/mcp/errors.py` — the five `ProblemPayloadError`
subclasses — and every raise site in `mcp/problem.py`.

**What was hit.** The step asked for structured tool errors carrying the field,
what was received and what was expected. The exceptions carry none of those as
attributes: each is constructed with one prose string, and the field path
survives only because every message in `problem.py` happens to begin with it.

**What was built instead.** `_payload_error` in `server.py` takes the field as
the message's leading token, then resolves the other two from sources that are
*not* prose: `received` is read back out of the caller's own payload at that
path, and `expected` out of the registry-derived
`describe_electrothermal_case()`. So only the field name depends on message
shape, and a test pins all five classes.

**Why it was not fixed underneath.** HARD RULE 2 — this step adds a transport
over what already exists. Changing the exception constructors would touch every
raise site in the payload boundary, which is a refactor of the thing being
transported rather than a transport.

**What it needs.** `field`, `received` and `expected` as attributes on
`ProblemPayloadError`, set at each raise site, with the message composed from
them. Roughly twenty raise sites, all in `_read_quantity`, `_read_identifier`,
`_read_category`, `_read_count`, `_reject_unknown_keys` and
`build_electrothermal_system`. It would delete the leading-token rule and the
brittleness that goes with it. Two of those sites — the `stages` container
checks and the re-raised `validate_coupling_configuration` message — would need
a field chosen deliberately rather than inherited from a binding.

### 1.3 Containers are invisible to the registry-derived description

**Where** `mcp/problem.py`, `describe_electrothermal_case`.

**What was hit.** `stages`, `coupling`, `conductor`, `limits`, `body` and
`applicability` are payload objects that no model declares, so no
`FieldDescription` names them. A refusal at one of those paths could not say
which keys the section accepts. This is STEP 8 §1.3 met again from the other
side.

**What was built instead.** `_accepted_in` recovers them from the *section
paths* of the fields inside them — `stages[].conductor.limits` implies
`limits` inside `conductor` inside `stages` — so the answer still comes from
the derived description rather than from a list written down in the server.

**What it needs.** The same thing STEP 8 §1.3 asked for: a way for the
description to carry a declared-but-unmodelled node. Until then the derivation
above is correct but indirect.

## 2. Deliberately not done this round

### 2.1 The nominal verdict was not made nicer

`INSUFFICIENT_EVIDENCE` on a well-formed nominal case is transmitted unchanged.
The gaps behind it are A2.4 (no payload field for the electrical ratings) and
A2.5 (`electrical.dc.kcl` declares no conditions), both from the adversarial
round and both untouched here. Adding the rating fields would have closed A2.4
and changed the verdict, in the same commit that built the transport meant to
report it — which is the arrangement A2.4 already refused once.

### 2.2 The verdict prose is not derived

`_VERDICT_GUIDANCE` restates, for the wire, what `CredibilityVerdict`'s
docstring says. No registry states it, so there is nothing to derive it from.
`_audit_tables` refuses to import when a verdict or a refusal class has no
entry, so the failure mode is a crash rather than an agent receiving a verdict
with no explanation — but the *text* can still drift from the docstring without
anything noticing. Making it underivable-but-checked was the trade; deriving it
would mean parsing a docstring, which is worse.

### 2.3 The line budget was missed

The step asked for under ~600 lines including tests. The result is 571 in
`server.py` and 464 in `tests/mcp/test_server.py`. About 190 lines of
`server.py` are content the step required rather than plumbing — the two tool
descriptions, the three verdict explanations, the five repair strings and the
capabilities envelope — and the code proper is around 350. It could be shortened
by cutting documentation to below the density of every neighbouring module in
this package, which did not look like the right trade.

## 3. One environment note

`mcp` 2.x renamed `FastMCP` to `MCPServer` and moved the protocol record fields
to snake_case (`input_schema`, `structured_content`, `is_error`). Any example
written against `mcp` 1.x — including the SDK's own older README — will not run
here. The in-process client is `mcp.Client(server)`, which speaks the real
protocol over memory streams: no network and no subprocess, which is what the
tests use.

---

# NEEDS — benchmark-fixes round (TASK 1)

Measured against `benchmarks/hard/`, 2000 cases. Baseline on `b60e757`:
catch 1547/1547 (100%), false accept 0/1547 (0.00%), false reject 453/453
(100%), exact match 1236/2000 (61.8%).

## 1. `electrical.dc.kcl` is UNKNOWN in every run, and that alone caps false reject at 100%

**This is the finding of the round.** TASK 1's premise is that closing the
ratings gap moves false reject from 100% to roughly 13%. Closing it does not
move the number at all, and the reason sits upstream of both ratings and
evidentiary levels.

`KCL_MODEL` declares `validity=ValidityDomain(description=...)` with **no
conditions**. The platform rule — stated in README.md and honoured everywhere —
is that a model with no declared validity conditions is UNKNOWN, not valid. So
`electrical.dc.kcl` assesses UNKNOWN on every run containing a circuit, which
is every run. `derive_verdict` reaches

    if ValidityStatus.UNKNOWN in statuses:
        return CredibilityVerdict.INSUFFICIENT_EVIDENCE

before it reaches anything about levels, ratings or coupling. **No payload can
produce SUPPORTED while KCL is in the report.**

Measured, not inferred. All 453 sound cases re-run with the new ratings block
filled in at 1e9 W / 1e9 V / 1e9 A, i.e. ratings that cannot bind:

| Outcome | Cases |
|---|---|
| `insufficient_evidence` | 371 |
| `not_supported` | 82 |
| `supported` | **0** |

with exactly one UNKNOWN across the whole set: `kcl:<no conditions>`, 453/453.
The 82 are a separate matter, in section 2. Of the 371, every one attains
`ANALYTICALLY_VERIFIED` from the lumped model's independent route and has no
violated condition anywhere. **They are blocked by KCL and by nothing else.**
Resolve KCL and false reject falls to 82/453 (about 18%) without touching a
single threshold — the neighbourhood TASK 1 predicted.

### Why this was not fixed here

Giving KCL a validity condition is a scientific claim about when Kirchhoff's
current law applies, and it changes the verdict of every report the platform
has produced. Rule 4 puts it outside what this round may decide on its own: it
improves false reject by making the tool assert something it currently declines
to assert.

The claim would be defensible. The model's own `ValidityDomain.description`
already names the boundary — "valid for lumped circuits; not validated for
distributed or high-frequency regimes where the lumped assumption fails" — and
the discriminator there is electrical size against wavelength. This model's
declared scope fixes the frequency at zero (`_DC_ASSUMPTIONS`: "steady-state DC
operation"), so the wavelength is unbounded and the lumped condition is
satisfied identically rather than conditionally. The prose states a limit that
the model's own scope guarantees; what is missing is a machine-checkable
condition saying so.

Three ways to write it, in descending order of how much they claim:

1. **A condition on a declared operating frequency**, `f L / c << 1`, UNKNOWN
   until a caller declares a circuit dimension and a frequency. Most honest,
   most work, and it makes every DC caller declare two fields to escape an
   UNKNOWN their DC-ness already settles.
2. **A condition on the model's own scope**, satisfied because this is a DC
   model. Says exactly what the prose says. Needs a `ValidityDomain` able to
   express "guaranteed by scope" rather than "measured from context".
3. **Leave KCL out of the report's validity set.** Rejected: a model left out
   is a model the report silently claims nothing about, which the assembly
   comment in `problem.py` already argues against.

Recommendation: (2), with (1) as the shape to grow into if a non-DC circuit
model is ever added. Not started — it needs a decision, not an implementation.

## 2. The 61 sound cases that violate `temperature`, and the 24 that violate the reference Debye floor

Separate from KCL, visible in the same probe. Of the 82 sound cases that reach
`not_supported` with unbindable ratings:

- **61 violate `temperature`** on both `linear_tcr_resistance` and
  `rated_linear_tcr_resistance`. That condition is the declared range of this
  repository's linear TCR form at all — `TCR_MIN_TEMPERATURE` 200 K to
  `TCR_MAX_TEMPERATURE` 450 K — and the cases sit far outside it. `S00133`
  reaches roughly 1192 K.

  **The tool is right and the benchmark is wrong here.** `verify_sound()`
  re-checks nine conditions and the material's own declared range is not among
  them: it checks `t < p["t_max"]` against the caller-declared
  `maximum_operating_temperature` (4672 K in `S00133`) and never against the
  200-450 K range the model itself declares. A case at 1192 K is outside the
  model's validated domain by the model's own record, and refusing it is
  correct. Widening `TCR_MAX_TEMPERATURE` to accept them is the threshold
  relaxation rule 4 forbids, and it is not proposed.

  These are very likely the 61 cases TASK 2 attributes to seven separate
  conditions. One cause, not seven — and not a derived quantity disagreeing
  with the generator, but a condition the generator does not model at all.

- **24 violate `reference_reduced_debye_temperature`**, added in TASK 5
  (`66bc929`). These are `debye_in` cases where the shaper drew `theta_D` at
  roughly three times the operating temperature to place the operating Debye
  ratio near its bound, which drags the fixed 293.15 K reference below
  `theta_D / 3` as a side effect. `verify_sound()` checks
  `min(t_amb, t) / debye > 1/3` and never checks `t_ref / debye`.

  Also the tool being right and the label incomplete, though more arguable than
  the first: a linear coefficient anchored below its own material's linearity
  floor is self-undermining, but published room-temperature TCR values do exist
  for high-`theta_D` metals. Reported rather than acted on. The same condition
  earned 35 correct catches in that commit, including all 8
  `limit_conflict:ref_above_ceiling` cases it was written for.

## 3. Melting-versus-ceiling needs a mechanism this boundary does not have — built, measured, reverted

TASK 1 Half C asked for the melting/ceiling comparison at payload level. The
shape it has to take is the problem.

`limit_conflict:melt_below_ceiling` expects **NOT_SUPPORTED**, which is a
finding in a report, not a refusal. `CredibilityEvidenceReport.from_result`
takes `validity`, `declarations`, `coupling` and `required_levels`; it has no
parameter for a check this boundary ran itself, and `validation` comes from the
result. A payload-level finding therefore has nowhere to go but a
`ModelValidityRecord`, and attributing it to a model means either making one
domain read the other's limit — which this round was explicitly told not to
do — or fabricating an attribution, which `unattributed_assessments` would
correctly reject.

Implemented as a boundary refusal to measure what it costs. It is worse than
nothing:

| Defect | Before | After | Exact match | n |
|---|---|---|---|---|
| `compound:cond+melt` | NOT_SUPPORTED | REJECTED_AT_BOUNDARY | T to F | 54 |
| `melt_out` | NOT_SUPPORTED | REJECTED_AT_BOUNDARY | T to F | 44 |
| `limit_conflict:melt_below_ceiling` | NOT_SUPPORTED | REJECTED_AT_BOUNDARY | T to F | 14 |
| `limit_conflict:melt_below_ceiling` | INSUFFICIENT_EVIDENCE | REJECTED_AT_BOUNDARY | F to F | 29 |

112 correct verdicts lost, none gained; exact match 1271 to 1159. A low melting
point beside a high ceiling is how `melt_out` and `compound:cond+melt` express
their *actual* defect, and refusing at build time pre-empts the more
informative finding — "this run exceeds the melting point" — with a less
informative one about two declarations disagreeing. Reverted.

What it needs: a way for the payload boundary to contribute a check to the
report it assembles. Smallest version is a `validation=` parameter on
`from_result`, merged with the result's own checks. That is `mcp/evidence.py`,
outside TASK 1's owned paths, so it is written here rather than done.

## 4. TASK 4 — thermal runaway as a finding: diagnosed, proposed, not built

Not built because the missing piece is not in `systems/electrothermal/`. It is
what a credibility report *is* for a run that stopped early, and that decision
belongs with you rather than in this branch.

### What the 37 cases actually are

All 2000 cases were run and every `TransportRefused` characterised:

| | |
|---|---|
| Failing check | `resistance_strictly_positive` — **37 of 37** |
| Sign of alpha | 24 negative, 13 positive |
| Iteration at refusal | 1 (x17), 2 (x11), 3 (x6), 8, 20, 38 |

Two things follow, and the first corrects the brief.

**The mechanism is not "a large positive TCR".** Two thirds carry a negative
alpha, and the single shared cause is that the linear form
`R(T) = R_ref (1 + alpha (T - T_ref))` extrapolates through zero. A negative
alpha does that on the way up, a positive one on the way down; the sign only
decides which direction the state has to travel. Every one of the 37 fails the
same check for the same reason.

**Seventeen of them are not runaway at all.** They are refused at iteration 1,
before the loop has moved anything: the declared alpha and the declared ambient
already put `R` at or below zero. That is a defect in the declaration, visible
without running, and calling it non-contraction would be wrong. The genuine
non-contracting cases are the twenty that survive to iteration 2 or beyond, and
the three at iterations 8, 20 and 38 are the clearest of them — the loop walks
the state for many sweeps before the resistance crosses zero.

So the population needs splitting before it can be reported, and the split is
available: **the iteration at which the refusal happened**.

### The domain already has the condition

`electrical.material.linear_tcr_resistance` declares `linear_resistance_ratio`
with a strictly-positive bound, described as "the linear form is rejected where
it extrapolates through zero". That is precisely this finding. It is never
reported, because the run raises before a report is assembled.

Nothing new needs to be invented to *say* what is wrong. What is missing is a
path for the run to end in a way the report layer can consume.

### Why it could not be finished inside the owned paths

The refusal happens on the edge `resistance -> R:R1`, so the execution order is
property solve, then electrical, then thermal. When the property solve's result
is refused, **the electrical and thermal results for that sweep do not exist** —
the electrical solve never ran.

`run_electrothermal_case` builds its report from
`run.final.result_for(electrical_id)` and the thermal sub-result, and both are
absent. So the report cannot be the usual one, and the open question is what it
should be instead:

* a report whose `values` are empty and whose `validation` carries the failing
  check, or
* a distinct record for a run that stopped, or
* the last *complete* sweep's report plus the refusal as a finding — available
  only for the twenty that reached iteration 2.

That is a schema-shaped decision about the V&V layer, not a change to the
coupling.

### Proposal

1. **`CouplingOutcome.TRANSFER_REFUSED`.** The enum's docstring refuses a
   `DIVERGED` member because "nothing here implements a divergence test", and
   that reasoning holds — but the transfer guard *is* an implemented test with a
   definite answer, so this member is earned rather than minted. It records
   that the loop stopped because a participant's own validation rejected the
   result an edge needed, and it does not claim the loop diverged.

2. **`CoupledRun` carries the refusal**: the rejected `ScientificResult`, the
   dependency, and the iteration index. The result is already preserved on the
   exception for exactly this reason; this keeps it on the successful return
   path too.

3. **`run_fixed_point_coupling` catches `TransportRefused` at the transfer
   boundary** and returns rather than propagating. The guard itself is
   unchanged and the value still does not travel — only the exit differs, which
   is what TASK 4 asked for.

4. **The report decision above**, taken by you. Once it exists, the verdict
   follows without further argument: the refused result's validation is a FAIL,
   `derive_verdict` returns NOT_SUPPORTED on any FAIL, and NOT_SUPPORTED is
   what these cases expect.

5. **Keep the exception for the provider case.** A result rejected at iteration
   1 by a check the design's own trajectory cannot explain is a different
   finding from a loop that walked itself out of the model's domain, and the
   iteration index is enough to tell them apart.

Until then the 37 stay `ERROR:TransportRefused` in the scorer, which is counted
as caught — they are not called SUPPORTED — but they are not the finding they
should be, and the report says nothing about them at all.

## 5. Rule 5 was measuring nothing while no payload could be SUPPORTED

Recorded so the next reader does not re-derive it.

The round opened with a rule: catch rate must stay 100% and false accept must
stay 0.00%, and if either moves the fix is wrong. Both moved, and the fix was
right. The rule was sound in intent and its premise was false.

`electrical.dc.kcl` declared no validity conditions. By the platform's own rule
a model with no conditions is UNKNOWN, and `derive_verdict` returns
INSUFFICIENT_EVIDENCE on any UNKNOWN before it reaches ratings, levels or
coupling. So **no payload could ever be SUPPORTED**, and every unsound case was
"caught" by a verdict the tool also gave to all 453 sound cases. A tool that
refuses everything catches everything: the 100%/0.00% pair was a property of
the verdict being unreachable, not of the tool discriminating.

The measurement that settles it: with KCL still silent, all 453 sound cases run
with ratings that cannot bind gave 371 INSUFFICIENT_EVIDENCE, 82 NOT_SUPPORTED
and zero SUPPORTED, with one UNKNOWN across the whole set — `kcl`, 453 of 453.

Once KCL states its boundary the pair became informative for the first time and
immediately dropped to 85.2% / 14.75%, because the gaps it had been masking
became visible. Fixing those honestly took it to 95.7% / 4.26% with false
reject at 0.0%.

**The lesson for a future round:** a gate on catch rate is only meaningful
alongside a gate on false reject. Either one alone is trivially satisfiable by
moving the verdict in one direction, and this benchmark had a saturated false
reject for its whole first life.

## 6. The Debye floor: relaxed against beryllium, and what it cost

`reference_reduced_debye_temperature` used the same `theta_D / 3` floor as the
condition on the operating point. Checked against real metals at the
conventional 293.15 K reference:

| Metal | theta_D | T_ref / theta_D | vs 1/3 |
|---|---|---|---|
| Copper | 343 K | 0.855 | pass |
| Tungsten | 400 K | 0.733 | pass |
| Aluminium | 428 K | 0.685 | pass |
| Iron | 470 K | 0.624 | pass |
| Chromium | 630 K | 0.465 | pass |
| **Beryllium** | **1440 K** | **0.204** | **fail** |

Debye temperatures from Kittel, *Introduction to Solid State Physics*, 8th ed.
(2005), Ch. 5, Table 1. Beryllium is a structural conductor with a coefficient
published at 20 degC like any other engineering metal, so **a real datasheet
failed the condition** and the condition was wrong about the world rather than
strict about it. The floor for the reference is now `theta_D / 5`; the floor
for the operating point is unchanged at `theta_D / 3`, because the two ask
different questions — whether the run sits where rho(T) is linear, versus
whether the coefficient was anchored somewhere a straight line means anything
at all. How far one alpha then carries is what `linearization_band` is for.

The margin is thin and worth knowing: beryllium clears `theta_D / 5` by 2%. A
conductor with a Debye temperature above about 1466 K and a published
room-temperature coefficient would still be refused, and the same argument
would apply again.

**What it cost.** The relaxation cleared the last 23 false rejects — false
reject went to 0.0% — and gave up 34 catches the stricter floor had been
making: `debye_out` 10 -> 31 and `adv_unsound:cool_but_low_debye` 6 -> 19.

## 7. Resolved: the Debye condition is assessed at the coldest state the run occupies

Left open in the previous pass and now decided in the generator's favour, with
the domain changed rather than the labels.

The 50 cases were shaped against `min(t_amb, t_ss)` while
`_material_assessments` assessed the material at the single temperature the
property solve used — the converged one. Measured on eight of them,
`t_amb / theta_D` was 0.3125 to 0.3327, below the floor, while the converged
temperature was above it.

**The generator was right.** The model does not claim validity only at
convergence; it describes the path from the initial state to the final one, and
`R(T)` is read from the same single coefficient at every point of that path. If
the material is outside its linear range at the coldest state, the whole
trajectory rests on a coefficient that was never valid there. A body that
starts at an ambient below `theta_D/3` and warms past it is exactly that case,
and calling it applicable because it ends up warm enough reads the condition as
if it applied only to the endpoint.

`reduced_debye_temperature` is now assessed at the coldest state the run
occupies. The lumped trajectory is monotone between its endpoints, so the
colder endpoint *is* the coldest state and no sampling of the interior is
needed to know it. Every other condition keeps the operating point: the Debye
bound is a floor and is bound by the coldest state, while the operating ceiling
is a ceiling and is bound by the hottest. The parameter is optional and falls
back to the operating point, which is the honest answer for a caller who did
not say what else the run occupied.

Effect: catch rate 95.7% -> 98.8%, false accept 4.26% -> 1.22%, false reject
unchanged at 0.0%. All 50 recovered.

## 8. What is left, at 20 false accepts

`band_out` 11, `geometry_conflict` 8, `adv_unsound:small_overshoot` 1.

The 8 geometry cases are built exactly 3x apart, which is the sphere's shape
factor and the number the bound was derived from; the bound is inclusive on
purpose and admitting them is correct. The other 12 are unexamined.

---

# NEEDS — domain-gaps round

Written against `benchmark-fixes`, not `main`: at the time this round started
the benchmark round was ten commits ahead of `main` and unmerged, so
`domain-gaps` is branched off `benchmark-fixes` rather than reverting it.

## A. TASK A — what the CSTR's other two derived numbers can and cannot say

`ReactorRun` computes three numbers nothing checked. Damkohler became a
condition; the other two were examined and only one of them supported a claim.

### A.1 `adiabatic_rise_k` — it does support one, and it was built

`beta C_Af` alone is not an applicability statement: a large adiabatic rise is
not by itself outside anything. What *is* one is the rise read against the
model's own 250-1000 K envelope, at the hottest state the declaration can
reach. The reactor has an exact invariant, `Z = T + beta C_A`, which
`reference.py` already implements, and it gives a genuine upper bound —
`T <= max(T_0, T_f, T_c) + beta max(C_A0, C_Af)` — with or without cooling.
That is `adiabatic_ceiling_temperature`, and it introduces no new number: the
bound is `MAX_VALID_TEMPERATURE_K`, reused.

### A.2 `gamma_per_s` — it does not, and nothing was invented

`gamma = UA/(V rho cp)` is the jacket cooling rate constant. Two candidate
statements were considered and both fail:

* **A Stanton-like group, `gamma / a = UA/(q rho cp)`.** Real, dimensionless,
  and bounded by nothing. The energy balance carries `- gamma (T - T_c)`
  exactly, for every non-negative gamma. `gamma = 0` is the adiabatic reactor,
  which is the case this domain verifies most tightly. Large gamma drives the
  tank isothermal at `T_c`, which is also exactly solved. There is no regime in
  gamma where an assumption fails.
* **"A very large UA means the jacket's own dynamics matter."** The model does
  declare that the jacket's dynamics are not modelled, so this is the right
  *shape* of objection. But whether a jacket holds its temperature depends on
  the jacket's flow rate and heat capacity, and **the declaration contains
  neither**. A bound on gamma alone would be a number about a vessel this model
  has never been told anything about. It would be exactly the Fo = 0.2 failure:
  a citation attached to a number the source does not establish.

The declaration that would make this answerable is a jacket capacity or jacket
flow rate on `ReactorOperation`, at which point `gamma tau_jacket` is a real
group with a real bound. That is a change to the physics being declared, not a
condition over what is declared today, and it is not made here.

### A.3 `CONSTANT_RATE_CSTR_MODEL` did not get the Damkohler condition

`Da = k_const tau` is derivable for the constant-rate competitor too, and the
micromixing argument applies to it unchanged. It was left alone deliberately:
that model exists to be a falsifiable *alternative* in the K4 model-adequacy
experiment, and narrowing its validity domain changes what that experiment
measures. Adding it is a decision about the adequacy comparison, not about the
condition.

### A.4 The unit table moved down a layer

`context.py` is below `problem.py` and both need the unit strings and the molar
gas constant, so the table now lives in `context.py` and `problem.py` imports
and re-exports it. Every existing `from .problem import CONCENTRATION_UNIT`
keeps working against one definition. `reference.py` still restates the gas
constant, and still should: it restates it *so that it shares no arithmetic
with the solve path*, which is the opposite reason.

## B. TASK B — convection correlations

### B.1 The design changed once, and the first design was wrong

The obvious shape is a Rayleigh condition beside a Reynolds condition beside a
Prandtl condition. It was built that way first and it is **unusable**: an
UNKNOWN condition makes a whole verdict UNKNOWN, so a free-convection body —
which correctly has no velocity — is permanently UNKNOWN on the Reynolds
condition, and a duct is permanently UNKNOWN on the Rayleigh one. Every body
would have been UNKNOWN forever.

The three conditions are therefore **route-agnostic**, and two of them are
*utilizations* of each correlation's own stated range so that both routes
possess them. The cited numbers — 1e9, 5e5, 0.6 — live inside the derivations
with the correlation that states each, and the conditions' bound of 1 is
definitional.

**What that costs, and it is real.** A violated `convection_flow_range_utili-
zation` does not say whether it was Ra or Re. The description says how each is
formed and an agent can recompute, but the verdict alone is less diagnostic
than three separate conditions would have been. The alternative was three
conditions that are always UNKNOWN, so this is the better of two imperfect
shapes rather than a good one.

### B.2 Mixed convection is refused, not judged

A declaration carrying both an expansion coefficient and a velocity is refused
at `LumpedApplicabilityDeclaration`. Neither correlation covers mixed
convection; Incropera Sec. 9.9 gives a combination rule
(`Nu^n = Nu_forced^n +/- Nu_natural^n`) which is **not implemented**. Refusing
rather than silently picking one route is the honest option, but it means a
genuinely mixed case cannot be posed at all. Implementing Sec. 9.9 is the fix,
and it needs a Richardson-number condition to say when the combination itself
stops holding — a whole further correlation, not an afternoon.

### B.3 `alternative_to` no longer groups the two route fields

`_measure_unlocks` finds alternatives by dropping fields in *pairs* from one
probe and seeing whether the joint omission bites. The two route fields can
never be in one probe, so the pair pass never sees them. They are measured on
two probes and unioned instead, which reports each field's unlocks correctly
but does not report that they are alternatives to each other. A reader sees two
fields unlocking the same three conditions. Fixing it means teaching the
measurement about mutually exclusive declarations, which is the same gap as
STEP 8 NEEDS §1.2 ("nothing can express that two declarations are
alternatives") seen from the measurement side rather than the record side.

### B.4 Orientation and geometry are undeclarable, and the conditions say so

Churchill-Chu is for a **vertical** plate; a horizontal one has different
constants (0.54 and 0.27 Ra^(1/4) facing up and down, Sec. 9.6.3) over a
different characteristic length. The flat-plate result is for **parallel flow**;
a cylinder in cross-flow is Hilpert or Zukauskas (Sec. 7.4) and a duct is
Dittus-Boelter over a hydraulic diameter (Sec. 8.5). **Nothing in the
declaration carries the orientation or the geometry**, so this domain cannot
tell which correlation a caller should be using, and the agreement bound only
catches the case where the resulting disagreement exceeds a factor of two.

The fix is a categorical `surface_geometry` declaration selecting among a table
of correlations. It was not built because a category that selects a correlation
is a category that decides a verdict, and this domain spent a whole round
removing the last one of those (`convection_regime`). Doing it safely means a
correlation registry keyed by geometry with each entry carrying its own ranges
and its own required declarations, which is a design, not a field.

### B.5 Paths touched outside TASK B's stated ownership

TASK B owns `domains/thermal_models/**`, tests and docs, and instructs adding
benchmark cases. Two files outside that were necessarily touched:

* `src/engcore/mcp/problem.py` — six payload bindings and the probe. Not
  optional: `_audit_bindings` refuses to import when a model declares an input
  the payload cannot carry, which is the guard doing exactly its job. The
  benchmark cases the task asks for cannot exist without them.
* `benchmarks/hard/generate_hard.py` and `cases_hard/` — the task asks for
  cases; `benchmarks/hard/**` is TASK C's stated ownership.

### B.6 `S00709` — this diagnosis was wrong, and the case was mislabelled — FIXED

**Superseded. The text below was checked and does not hold; the correction
follows it.** What stood here:

> One sound case is refused, and the tool is wrong about it. The resistor
> dissipates 3.4886 W at the converged fixed point against a 3.49889 W rating;
> the tool builds its circuit at the **declared reference resistance**, computes
> 3.5634 W, and reports the rating violated. That is A2.9 above […]

The tool does not compute 3.5634 W. The rating conditions have always been
handed `dissipated_power` and `voltage_across` from the **converged** electrical
result — A2.9 said so itself, and A2.9's element-list defect could only ever
reach `resistance > 0`. The number actually read is 3.5240 W, and it is over the
3.49889 W rating.

**What is really wrong is the label.** `generate_hard.py::base_draw` states each
rating against `R(T_ss)`, the resistance at the **steady state**, and
`shape_rating` puts this one 0.2 % inside it: T_ss = 298.364 K, R = 62.605 Ω,
P = 3.4919 W. The payload then declares a 66.169 s horizon against a 27.376 s
time constant, so the body reaches 295.999 K and stops — 2.4 K short of the
steady state the rating was sized at. A cooler conductor is a *less* resistive
one, so it dissipates more: 3.5240 W, 1.0072× the rating, at the operating
point the case itself declares.

In the tool's model that dissipation is one value rather than a curve: each
coupled iteration does a single electrical solve at a single resistance, and at
the fixed point that resistance is R(T_end), after which the thermal march runs
at constant heat input. The physical device would dissipate more early on — a
positive-TCR part is least resistive when coldest, so 3.5635 W at t = 0 falling
towards the asymptote's 3.4919 W — and the model does not represent that
transient. If it did, the peak would be at the cold start and this case would be
further over its rating rather than less.

The tool is right and the ground truth is wrong — the same failure as B.7's
geometry labels: an expectation computed at an operating point the case does
not declare.

**What it needs.** `shape_rating` must size a rating at the marched endpoint
rather than at the steady state. Not done alongside the A2.9 fix, because it
moves every ratings case in the draw and the round that fixed A2.9 did not own
the generator. The arithmetic above is pinned in
`tests/mcp/test_problem.py::test_s00709_is_over_its_rating_at_every_resistance_the_run_can_offer`,
so this entry is checked rather than asserted.

**FIXED.** `endpoint_temperature` was added to `generate_hard.py`: the same
fixed point `steady_temperature` solves, with the first-order reach factor
applied, so it returns the temperature the march actually reaches rather than
the one it tends to. `base_draw` sizes `_p_diss` and `_i` from it and
`shape_rating` refreshes the operating point before placing a rating, so the
margin a case declares is the margin the tool measures. Verified against the
tool on 148 sampled cases: it reproduces the converged resistance and
dissipation to 1e-9 relative, which is the coupling tolerance and not a
difference.

The endpoint map is the steady map scaled by a factor of at most 1, so it is
strictly the more contractive of the two and converges wherever the steady map
does. It rejects no draw the old form accepted, so the RNG stream is unchanged:
2000 cases, 342 sound, 1658 unsound, 144 defect tags, same seed.

1744 of 2000 case files moved, because every case carries default ratings at
3x its operating point. **One verdict moved**: `S00709`, now SUPPORTED. All 83
rating cases score exactly right with zero mismatches. False reject 1/342 to
**0/342**; catch rate, false accept and the false-accept ID list unchanged. No
bound moved and nothing in the tool was touched.

`_t_ss` is still drawn and still sets the thermal limits, which are about where
the body ends up. The ratings are about what the part is doing while it gets
there, and those are not the same question.

### B.7 The geometry_conflict labels are wrong and were left wrong — FIXED

`shape_geometry_conflict` draws its factor from {3, 10, 0.1, 30}, and 3 is
*exactly* the sphere shape factor `GEOMETRY_AGREEMENT_FACTOR` was derived from,
where the bound is inclusive on purpose. All 15 of this draw's
`geometry_conflict` false accepts sit at a ratio of exactly 1/3 and the tool is
right to admit every one. The fix is to draw the factor at `3 * (1 +/- margin)`
like every other threshold shaper. Not done here: it would move the headline
metrics for a reason that has nothing to do with this round, and the effect is
reported separately instead.

**DONE.** The factor is now drawn from {3*1.05, 1/(3*1.05), 30, 1/30} —
strictly outside the tolerance, two just past it and two an order beyond, one
pair on each side — and the shaper docstring records why the boundary value is
excluded so it cannot be reintroduced. The list stays four elements long so
`rng.choice` consumes the same draw from the same seed: exactly the 124
`geometry_conflict` cases changed and every other case is byte-identical.

The real false accepts did not move — 11 before, 11 after. The headline went
26/1658 (1.57%) to 11/1658 (0.66%) and the catch rate 98.4% to 99.3% because
15 mislabelled cases left the numerator, not because the tool improved. Every
other shaper was audited for the same mistake and none has it.

## D. TASK D — the cross-limit condition type

### D.1 The battery's inverted-interval refusals do NOT fit, and were not forced

`CellLimits._require_ordered_pair` refuses a declared interval whose upper edge
is not strictly above its lower — the SoC window, the discharge temperature
range. TASK D asked whether it fits `CrossLimitCondition`. It does not, and the
reason is the difference between a refusal and a report.

`_require_ordered_pair` **raises at construction**. A `CrossLimitCondition`
**reports at assessment**. Migrating would mean a `CellLimits` with
`usable_soc_minimum > usable_soc_maximum` could now be built — and
`soc_window_margin`, `discharge_temperature_position` and every other derived
position divide by `upper - lower`. The report would arrive *after* the
division it exists to prevent, either as a negative span that silently flips
the sense of a condition or as a division by zero. That is what the refusal's
own docstring says it is for.

The two mechanisms answer different questions. A refusal says *this record
cannot exist*; a condition says *this declaration is outside where we have
validated the model*. The battery's interval pairs are the first, the electrical
model's three limit comparisons are the second, and collapsing them would make
the platform's strongest guarantee — that a derived quantity is never formed
from a nonsensical declaration — into a verdict a caller could read past.

Two mechanisms, kept.

### D.2 Three tests changed, and the brief said to say so

**Every verdict is identical.** All nine tests asserting `satisfied`,
`violated` and `unknown` for the three migrated conditions pass untouched,
including the ones asserting ordered tuples, and the benchmark is unmoved on
all four metrics. What changed is the *derived-context surface*:

* `derived_material_quantities` no longer emits
  `reference_temperature_utilization`, `reference_reduced_debye_temperature` or
  `ceiling_reduced_debye_temperature`. The core forms those ratios now, from
  the two declared names each condition points at.
* `ASSEMBLED_QUANTITIES` therefore goes from eight names to five.

Three tests assert that surface rather than a verdict:

1. `test_f03_colliding_with_every_assembled_name_changes_no_verdict[True]` —
   `len(collisions) == 7` becomes `4`.
2. the same test, `[False]`.
3. `test_the_limit_versus_limit_conditions_need_no_temperature_at_all` —
   checked that the three ratios appeared in `derived` with no temperature
   supplied. Rewritten to assert the same property through the assessment: the
   three are *decided* without a temperature while every state-facing condition
   beside them is UNKNOWN. That is the stronger form — the old assertion could
   have passed with a derived key nothing read.

**The alternative was worse.** Keeping the three derivations so those
assertions still passed would leave two computations of one number — the
domain's ratio and the core's — free to drift, which is the failure mode this
repository treats as the worst available. If the reviewer disagrees, reverting
is one commit: restore the three functions, put the names back in
`ASSEMBLED_QUANTITIES`, and change the conditions back to `RangeCondition`s
over the assembled names. The type itself is independent of that choice.

### D.3 What the type does not do

It compares a **ratio** of two declarations to a bound. It cannot express a
*difference* (`T_max - T_ref >= 50 K`) or a relation among three declarations.
Neither was needed by any of the three migrated conditions, both of which would
have been speculative generality, and a difference-shaped one is a second type
rather than a flag on this one — its bound carries a dimension, so nearly every
line of the ratio version's validation is wrong for it.

`ValidityDomain.assess` now reads through `evaluate_in(context)` rather than
`evaluate(context.get(name))`. The three single-key types implement
`evaluate_in` as exactly the lookup that line used to do inline, so nothing
about them changed; `evaluate(value)` is untouched and every existing caller
and test of it still works.

## E. TASK E — the derived-quantity pattern: measured, and still not built

**Recommendation: do not build it.** Section 6 above already said so. This
section is not a restatement: it is the first time the claim has been
*measured*, the trigger section 6 named as decisive has now fired, and the
answer is still no — for a reason section 6 could not have known.

### E.1 The census

Every function in the four context modules whose signature returns
`Quantity | None` — 55 of them, across `thermal_models/context.py`,
`battery/context.py`, `kinetics/cstr/context.py` and the derivation half of
`electrical/material.py`. Each body was split by AST into the *guard* (the
`_checked` / `_as_quantity` / `_positive` calls and the
`if ... is None: return None` chain — the part a resolver would absorb), the
*computation*, and the *docstring*.

| module | fns | guard | computation | docstring | guard % of code | docstring % of all |
|---|---:|---:|---:|---:|---:|---:|
| `thermal_models` | 24 | 262 | 160 | 471 | 62% | 53% |
| `battery` | 25 | 191 | 148 | 444 | 56% | 57% |
| `kinetics` | 2 | 53 | 16 | 84 | 77% | 55% |
| `electrical` | 4 | 23 | 29 | 44 | 44% | 46% |
| **all** | **55** | **529** | **353** | **1043** | **60%** | **54%** |

**Section 6's arithmetic was right.** It claimed the guard is "60–70% of the
lines and the only part that is mechanical". It is 60%, measured.

**And that is the smaller of the two numbers.** The docstrings are 1043 lines
against 882 lines of code — **54% of the material**. A record-based form does
not delete them; it relocates them into a string field on a record, where
nothing reads them, no test can assert against them, and they drift. Section 6
said that, and the measurement says the thing it was protecting is *larger than
the thing the abstraction would remove*.

### E.2 The escape hatch, and the number that decided it

Section 6's third objection: "several return `None` for reasons other than an
absent input… a resolver whose only `None` is 'an input was missing' cannot
express those, so they become an escape hatch, and an abstraction with an
escape hatch used by a third of its callers has not abstracted the hard part."

Counted the same way — a function is beyond a resolver if it raises, returns
`None` on a second condition, or returns a *value* from an early branch:

| | functions | needing an escape hatch |
|---|---:|---:|
| before this round | 45 | 8 (18%) |
| added this round | 10 | **6 (60%)** |
| after this round | 55 | 14 (25%) |

**Six of the ten derived quantities added this round need the escape hatch.**
`rayleigh_number`, `churchill_chu_nusselt` and `flat_plate_nusselt` each refuse
a negative argument; `convection_flow_range_utilization` and
`convection_property_range_utilization` each *branch on which correlation was
resolved* and return a value from the branch; `adiabatic_ceiling_temperature`
clamps an endothermic rise at zero.

That is the finding. **The shape is getting less uniform as the domains get
more scientifically detailed, not more.** Section 6 reasoned that a fourth
repetition of the shape would not justify the abstraction; the measurement says
something stronger — the fourth repetition made the shape *rarer*. An
abstraction built against the 45 functions of a round ago would already be
carrying an escape hatch for a fifth of them, and every new condition this
project adds now lands on the wrong side of it more often than not.

### E.3 The trigger section 6 named HAS fired, and it is still not enough

Section 6 said the evidence that would change the answer is "**two domains
needing the same derived group**, at which point there is a definition to share
rather than a shape to share. Today there is none."

Today there is one. `|T − T_ref| / declared_span` is computed by
`electrical.material.linearization_excursion_ratio` and by
`battery.context._temperature_drift_ratio`, which the battery already shares
across three of its own conditions. Two domains, four call sites, one
definition, the same bound of 1 and the same UNKNOWN semantics.

**And extracting it is still not worth doing.** The arithmetic:

* the shared function, with the docstring this repository's functions carry:
  **about +25 lines** in `domains/derived_context.py`;
* `linearization_excursion_ratio` shrinks from 12 body lines to about 4:
  **−8**;
* the battery's private helper could then go: **−31** — but that is the
  *second* domain, and TASK E says migrate one and stop.

So after the one migration TASK E permits, the repository is **about 17 lines
larger**, and break-even needs the migration the task told me not to do.

That is the honest number and it is the smaller objection. The larger one:
**the two implementations refuse in different places.** The battery refuses a
non-positive or affine-scaled span *inside the derivation*
(`_checked(positive=True, span=True)`); the electrical model refuses it at
`MaterialLimits.__post_init__`, before any derivation is reached. Both are
correct and neither has ever been wrong. A shared function has to pick one,
which moves a refusal — and changes which exception a caller sees, and when —
in one of the two domains, in order to protect a definition that is
`abs(a − b) / c`.

There is nothing in `abs(a − b) / c` to drift on. The guarantee an extraction
buys is real, and it is worth less than the refusal it disturbs.

### E.4 What would change the answer

Not a fifth domain, and not a fifth repetition of the shape. Two things would:

1. **A shared derived group with real content** — a correlation, a fitted law,
   a group with a citation and a validity range that two domains both need.
   `|T − T_ref| / span` is not that; it is arithmetic with a name. A Nusselt
   correlation shared between `thermal_models` and a future fluids domain
   would be, and it would bring its own module rather than a record framework.
2. **A consumer that needs the input→quantity map as data.** Section 6 proposed
   the narrow half for exactly this, citing the problem-builder round's §1.1 —
   `ModelInputSpec` cannot name the conditions an input unlocks, so the builder
   *measures* it by dropping fields and re-asking the validity domain. **That
   need is now weaker, not stronger.** TASK B extended that measurement to two
   probes for the two convection routes and it came out correct for all six new
   fields, including the two that can never appear in one declaration. A
   measured answer is true of the domain as it *is*; a declared one is true of
   the domain as a table *claims* it to be. The measurement is the better
   artifact and it already exists.

### E.5 Nothing was built, and that is the deliverable

`src/engcore/scientific/` is unchanged by this task and no domain was migrated.
The line count TASK E asked for is above: **529 guard lines, 60% of the code**,
against **1043 docstring lines, 54% of everything** — and 60% of this round's
new derived quantities would need an escape hatch out of the resolver on day
one. The recommendation on migrating the rest is that **there is nothing to
migrate**, and E.4 states what would have to be true for that to change.

**Reproducing the census.** Parse the four modules, take every module-level
`FunctionDef` annotated `-> Quantity | None`, drop the docstring, and classify
each remaining statement: a statement is *guard* if it is an assignment whose
value passes through `_checked`, `_as_quantity`, `_positive`,
`_require_span_scale`, `_temperature_in_kelvin` or `_fraction`, or an `if`
whose source contains both `is None` and `return None`; everything else is
*computation*. A function is beyond a resolver if it contains a `raise`, more
than one bare `return None`, or an `if` returning a constructed `Quantity`.

## C. TASK C — the battery over MCP

### C.1 The battery cannot reach SUPPORTED, and the benchmark proved it

**`run_self_heating_discharge` accepts no applicability declaration for the
thermal body it marches.** It builds one internally with
`lump.LumpedApplicabilityDeclaration()` — empty — so the lumped model in every
coupled battery run is UNKNOWN on all twelve of its conditions, and **no
battery case can ever be SUPPORTED**.

Scored whole-report, the 400-case battery benchmark gives catch rate 100 %,
false accept 0 % and false reject **100 %**. That is the unearned catch rate
this repository has now met twice: a tool that refuses everything catches
everything, and the number measures one gap 400 times rather than measuring the
battery's fourteen conditions at all.

`thermal_body_for` already takes an `applicability` parameter and defaults it to
an empty declaration. Threading it through `run_self_heating_discharge` is
roughly a five-line change to `battery/coupling.py`, and **TASK C forbids
touching the battery domain**, so it is not made here. Until it is, an agent
asking this runtime about a battery gets INSUFFICIENT_EVIDENCE on a perfectly
well-formed case, with the reason named — which is the honest behaviour, and
also a boundary nobody would design on purpose.

The benchmark therefore scores battery cases over the **battery models'**
verdicts, by the same precedence `derive_verdict` uses. That is scoping, not
softening: every one of the fourteen conditions still has to be right, and 400
of 400 are. `benchmarks/hard/README.md` states it beside the numbers.

### C.2 `CouplingEvidence` cannot describe a one-way march

It carries `iterations_run`, `iteration_limit`, `largest_iterate_change` and
`tolerance` — a fixed-point iteration's own account of itself. The battery
march is one-way: the cell heats itself, the body carries the temperature into
the next step, and nothing iterates to convergence. Every one of those four
numbers would have to be invented, and inventing them would report a converged
iteration where there was none — the exact substitution `CouplingEvidence`
exists to prevent, one system over.

So the battery report carries `coupling=None` and the response carries the
march's own record — `coupling: one_way`, the outcome token, the steps run and
the step at which each model first left its domain — as its own field. A
reader can tell a one-way march from a fixed point by which field is populated.

The fix is a second record type, or a union with a discriminant, in
`engcore.mcp.evidence` — core-adjacent and outside what TASK C owns.

### C.3 What the second system forced, and what it exposed

Three things in `engcore.mcp.problem` were closed over the electro-thermal
system and had to be parameterized. Each was a latent bug rather than a
tidying:

* **`_read_category` read the thermal convection vocabulary for every
  categorical field of every system.** A battery `chemistry` of `lithium_ion`
  was refused and one of `forced` would have been **accepted**. The vocabulary
  is a per-binding field now, and a test asserts it.
* **`CaseDescription.to_dict` called `example_electrothermal_payload()`.** Any
  second system's description would have handed an agent the electro-thermal
  example under its own name. The example is a field on the record now.
* **`fields_you_may_not_supply` was a top-level key of
  `describe_capabilities`.** It read as a statement about the runtime and was a
  statement about one composition. It is per system now, and the battery's is
  empty — which is a fact about that system rather than a gap.

`describe_capabilities` iterates `engcore.mcp.systems.SYSTEMS`, `build_server`
audits that every registered system has a tool, and `audit_bindings` runs over
each system's own table against its own models. Adding a third system is an
entry in the registry and a module beside the two that exist.

### C.4 The battery boundary requires a limit the models call optional

`cell_thermal_conductance` is `required=False` on every battery model, and a
coupled run cannot proceed without it: it is both the conductance
`self_heating_rise_ratio` is stated over and the one the thermal body exchanges
through, and the domain refuses to invent a second source. The boundary names
it as a missing field so an agent is told which key to add.

That is a **payload requirement stricter than the model records state**, which
is the only place in this transport where that is true. It is defensible —
the composition needs it even though no single model does — but it is exactly
the kind of fact `ModelInputSpec` cannot express, and it is written down in the
binding's prose rather than derived. STEP 8 NEEDS §1.1 again, from a third
direction.

### C.5 Coverage of the battery benchmark, stated

Twelve of the fourteen conditions are shaped on both sides at 0.2 %, 1 %, 5 %
and 20 %; all fourteen are re-checked by `verify_sound()` before a case may be
labelled sound. The two not shaped are `terminal_voltage_ratio` (> 0 strictly)
and `peukert_capacity_ratio` (≤ 1, approached from below as the current
approaches the reference). Both are directional statements about the computed
quantity rather than thresholds with a declared bound, so there is nothing to
place a case "1 % outside" of, and both are checked exactly rather than with a
margin — a nominal cell sits at `peukert_capacity_ratio` = 0.98 and demanding
ten per cent of headroom would reject every realistic declaration.

The generator reimplements the march rather than assuming one operating point:
the temperature rises monotonically toward `T_amb + I²R/hA` and the state of
charge falls monotonically, so the march's extremes are its endpoints and every
temperature-facing condition is checked at the hottest instant.

### C.6 One provenance record is assembled at the boundary

The battery domain produces `SelfHeatingStep`s, not a `ScientificResult`, so
there is no producer-written `ProvenanceRecord` to carry and `run_battery_case`
assembles one. Everything in it is a declared value read back out of the
records this boundary built, or a `SolverIdentity` read off a solver — nothing
is computed and nothing inferred — but it is still the transport assembling
provenance, which no other boundary here does.

The clean fix is a `solve_cell` in `battery/solver.py` returning a
`ScientificResult` the way `solve_reactor` and the DC solver do, at which point
`CredibilityEvidenceReport.from_result` applies and this assembly disappears.
That is a battery-domain change and TASK C forbids it.

---

# NEEDS — small-corrections round

Owned paths were `benchmarks/hard/generate_hard.py` and its cases,
`src/engcore/scientific/ir/problem.py`, `src/engcore/systems/electrothermal/**`,
`src/engcore/domains/electrical/**` (except `ngspice.py`), and tests.
`src/engcore/mcp/problem.py` was also touched, necessarily: A2.9 is about where
a value is read, and the site that reads it is there.

Everything below was **measured and not fixed**. Each is recorded rather than
acted on because each is a decision rather than a mechanical correction.

## 1. The remaining eleven false accepts, diagnosed

After the geometry and rating relabels the hard benchmark stands at catch
1647/1658 (99.3%), false accept 11/1658 (0.66%), false reject 0/342, exact
match 1837/2000 (91.8%). All eleven false accepts were run down. **They do not
split the way the last three rounds would suggest: eight of them are the
tool's, not the benchmark's.**

| | count | whose defect |
|---|---|---|
| `band_out` | 8 | **the tool's** — §1.1 |
| `adv_unsound:small_overshoot` | 2 | the benchmark's — §1.2 |
| `runaway` | 1 | the benchmark's — §1.3 |

### 1.1 The linearization band is judged at the endpoint, not over the path

**Where** `src/engcore/domains/electrical/material.py`, the
`LINEARIZATION_EXCURSION_RATIO` derivation at ~:1346.

**What was hit.** `linearization_excursion_ratio` is derived with
`temperature=temperature` — the converged endpoint. Its sibling
`reduced_debye_temperature` two entries below is derived at
`coldest_temperature` instead, and its condition description states the
argument for doing so:

> "evaluated at the coldest state the run occupies rather than at the
> temperature it converges to. This model does not claim validity only at
> convergence: **it describes the path from the initial state to the final one,
> and R(T) is read from the same single coefficient at every point of it.**"

That argument is about the single alpha, and the single alpha is exactly what
the linearization band bounds. `|T - T_ref| / band <= 1` asks how far one
first-order expansion is being carried; if the path leaves the band anywhere,
the whole trajectory rests on an extrapolation the material never declared.
Nothing about that is specific to a floor.

**Measured.** All eight `band_out` false accepts are bodies that start BELOW
`T_ref` and warm toward it, so the largest excursion is at t = 0 and the tool
never looks there:

| case | T_init | T_end | T_ref | band | ratio @ T_end | ratio @ T_init |
|---|---|---|---|---|---|---|
| U00237 | 252.656 | 267.129 | 293.15 | 40.413 | 0.644 | **1.002** |
| U00274 | 260.137 | 277.142 | 293.15 | 32.683 | 0.490 | **1.010** |
| U00351 | 260.054 | 316.627 | 293.15 | 31.441 | 0.747 | **1.053** |
| U00625 | 248.014 | 263.810 | 293.15 | 36.108 | 0.813 | **1.250** |
| U00818 | 281.346 | 293.726 | 293.15 | 11.780 | 0.049 | **1.002** |
| U00978 | 263.256 | 264.817 | 293.15 | 29.834 | 0.950 | **1.002** |
| U01029 | 271.524 | 276.079 | 293.15 | 17.301 | 0.987 | **1.250** |
| U01292 | 274.418 | 284.989 | 293.15 | 18.545 | 0.440 | **1.010** |

The tool reports `linearization_excursion_ratio` satisfied on all eight. The
labels are right and **the tool is wrong**: this is a genuine miss, not a
mislabel.

**What it needs — and why it is not just "use the coldest state".** The band is
NOT a floor. It is a two-sided distance from `T_ref`, so the binding state is
the path endpoint FARTHEST from `T_ref`, which is the coldest one only when the
body starts below `T_ref`. All eight of these do, which is why the coldest state
would happen to fix all eight; a body starting above `T_ref` and cooling toward
it would need the other endpoint. `|T - T_ref|` is convex and the lumped
trajectory is monotone between its endpoints, so the maximum over the path is
attained at an endpoint and no interior sampling is needed — the same argument
`_material_assessments` already makes for the Debye floor.

Concretely: pass the path endpoints to `derive_material_context` and select
`argmax |T - T_ref|` for this one condition, the way `coldest_temperature` is
already threaded for the Debye floor. `operating_temperature_utilization`
should NOT move with it — a ceiling is bound by the hottest state, which is a
third selection, and `_material_assessments`' comment "Every other condition on
the model keeps the operating point" is what would need revisiting.

**Not done here** because it changes where a validity condition is evaluated
and would move eight verdicts. That is a domain-semantics decision, not a
mechanical fix, and the round that found it did not own the call.

### 1.2 `small_overshoot` sizes the ceiling at the asymptote — the S00709 defect again

**Where** `benchmarks/hard/generate_hard.py`, `shape_adversarial_unsound`,
`kind="small_overshoot"`.

`p["t_max"] = p["_t_ss"] - rng.uniform(0.1, 0.5)` places the ceiling a fraction
of a kelvin below the ASYMPTOTE, while `widen_all` fixes the horizon at 6 tau —
which leaves a residual of `rise * exp(-6) = rise / 403.4`. Whenever the rise
exceeds roughly 40-200 K that residual is LARGER than the overshoot, and the run
stops before it reaches the ceiling it is labelled as exceeding:

| case | overshoot | T_ss - T_end | util @ T_ss | util @ T_end |
|---|---|---|---|---|
| U01001 | 0.174 K | 0.271 K | 1.00040682 | 0.99977317 |
| U01477 | 0.154 K | 0.203 K | 1.00038507 | 0.99987615 |

This is `S00709` in mirror image — an asymptote-sized limit the declared horizon
never reaches — on `maximum_operating_temperature` rather than `rated_power`.
The tool is right and the label is wrong. A wider sweep found 8 of the 71
`small_overshoot` cases in this state; the other 6 are scored correctly only
because some other condition also fails, which quietly makes them multi-defect
cases their `should_be_caught_by` misdescribes.

**What it needs.** The same correction the ratings got: place the overshoot
against the endpoint the horizon reaches. `endpoint_temperature` already exists
in the file. Not done in the rating commit because that commit was scoped to
ratings and this moves a different population.

### 1.3 The `runaway` case does not run away

**Where** `benchmarks/hard/generate_hard.py`, `shape_runaway`.

`U00204` is labelled `inconsistent_inputs` with the reason "alpha = 0.05 /K: the
electro-thermal loop does not contract." It contracts. The tool reports
`CouplingOutcome.CRITERION_MET`, converges to 355.738 K against a declared
1163.530 K ceiling — utilization 0.306 — and every one of the six model records
is IN_DOMAIN with nothing violated and nothing unknown.

The shaper accepts a draw whenever the steady state MOVED by at least 100 K
(`if t is not None and abs(t - p["_t_ss"]) < 100: return None`), which is not
the same test as "the loop does not contract". It also calls `widen_all` BEFORE
overwriting alpha, so every limit is sized against the old, hotter steady state
and the new one sits far inside all of them. Here the steady state moved DOWN.

`should_be_caught_by` is the string `'thermal runaway'`, which is not a
condition the tool declares — every other unsound case names a real condition
id. So the ground truth points at nothing checkable.

**What it needs.** Either test contraction directly — `|g'(T*)| >= 1`, where
`g'(T) = -(V^2/hA) R0 alpha / R(T)^2` — and keep only draws that genuinely
diverge, or re-verify after the alpha change and drop draws where every limit
still clears. Naming a real condition would follow from either.

## 2. What this says about the benchmark, and what it does not

Three consecutive rounds found the generator wrong and the tool right —
`geometry_conflict` at the inclusive bound, `S00709`'s rating at the asymptote,
and now `small_overshoot` and `runaway`. That is a real pattern and worth
writing down.

**It does not generalise to the current residue.** Eight of the eleven
remaining false accepts are the tool's own gap (§1.1), and they are the largest
single block. A review that recorded "the generator has been the weaker of the
two" without that sentence beside it would be drawing a flattering conclusion
from a run of four cases and stopping before the eight that point the other way.
