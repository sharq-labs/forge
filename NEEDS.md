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
substitute.** `engcore.mcp.EvidencePackage` carries validity itself, as a tuple
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
- ``mcp``         evidence packaging for consumers: carries validity,
                  validation and provenance together and derives an advisory
                  verdict from them
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

### 1.8b SUPPORTED does not require any evidentiary level — proposed strengthening

**Not a core change; a change to the brief's verdict rule, so not made.**

`SUPPORTED` is specified as "everything else: all validity IN_DOMAIN, no
failures, no NOT_RUN gap". It says nothing about what the passing checks
*established*. A solver emitting one passing check with `establishes=None`
therefore yields a `SUPPORTED` package whose `attained_levels` is empty — and
that is not hypothetical: the lumped thermal solver deliberately claims no
level for its residual check ("being the one solver to award itself the highest
level in the taxonomy, from the weakest evidence, is exactly the unearned claim
the result contract exists to refuse"), so the IN_DOMAIN real-run package in
`tests/mcp/test_evidence.py` is SUPPORTED with `attained_levels == frozenset()`.

Defensible as specified — nothing in that package argues *against* the result,
which is what SUPPORTED claims — and weaker than a reader may assume. Three
things were done instead of changing the rule:

* `EvidencePackage.attained_levels` is exposed beside the verdict.
* `to_dict` emits a `verdict_qualifiers` block carrying `attained_levels`,
  `warning_checks` and `unassessed_models`, so a JSON reader who never opens
  the check list still sees what a SUPPORTED verdict rests on.
* `required_levels` lets a study declare the bar it needs; a level demanded and
  not attained is `INSUFFICIENT_EVIDENCE`.

**The proposal, if the rule is ever revisited:** make the guard evidential
rather than numeric — replace "there are no checks at all" with "no check both
passed and established a level". That reuses the core's own definition of what
counts and makes `SUPPORTED` mean "at least one level was actually attained".
The cost is that every current lumped-thermal package becomes
`INSUFFICIENT_EVIDENCE`, which is arguably the honest answer and is certainly a
decision for whoever owns the verdict semantics, not for this implementation.

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

**Why it matters here.** `EvidencePackage`'s verdict is decided by set
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
