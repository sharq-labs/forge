# Adversarial review — 2026-09-07

**Target.** `engcore` at `d23f7ae`, the whole verification path. `src/engcore/sria/`
was out of scope: it is off the verification path and imported by nothing outside
itself.

**Method.** Read and run. Every finding below was reproduced by executing it, and
the exact snippet and the exact output are given. Anything that could not be
reproduced is in *Hypotheses*, labelled as such. Probe scripts were kept outside
the repository; nothing in `tests/` was added during the review itself.

**Environment.** Python 3.14.2, numpy 2.5.2, scipy 1.18.1, pint 0.25.3, pytest 9.1.1.
`ngspice` was not installed, so the provider was probed through its parser and its
admission layer rather than end to end. Windows; `pytest --basetemp` had to be
pointed at a writable directory, and 25 pre-existing `PermissionError`s in
`tests/mcp/test_bundle.py` reproduce identically on an unmodified clone.

**How to read it.** Three sections carry the weight, and they are not the findings
list. *What was attacked and held* is the record of nine attacks that failed, each
naming the mechanism that stopped it — that is what says which claims are real.
*Three claims that did not survive* records a false alarm, including the part where
the reviewer was wrong. *The fifth rule* is what this round added to the four the
project already derived from its own failures.

---

## 1. The published numbers, re-measured

Reproduced from the repository, on the development split, with the seal armed:

```bash
python benchmarks/hard/score_hard.py --src src --cases benchmarks/hard/cases_hard \
       --split dev --workers 2 --results <somewhere-outside-the-repo>.json
```

| Metric | Value |
|---|---|
| Exact verdict match | **1291/1400 (92.2 %)** |
| Catch rate | **1157/1159 (99.8 %)** |
| False accept | **2/1159 (0.17 %)** |
| False reject | **0/241 (0.0 %)** |

`case_set_digest e14542c1…`, `split-rule stratified-hash-hamilton/1 seed 20260906`,
false-accept ids `U00204`, `U01001`. Identical to the published four. The hold-out
was not opened; `HOLDOUT_OPENINGS.log` still has nothing below its header.

`--split dev` was *accepted*, which is only possible when the case-set digest
matches `split_hard.json`. All three digests agree, in the working tree and in a
fresh clone:

```
########## WORKING TREE ##########
  cases_hard      2000 files  computed=e14542c1e09f258d  files_with_CR=0
  results_hard.json      case_set_digest=e14542c1e09f258d
  split_hard.json        case_set_digest=e14542c1e09f258d
########## FRESH CLONE OF d23f7ae ##########
  cases_hard      2000 files  computed=e14542c1e09f258d  files_with_CR=0
```

The case files are single-line JSON with no interior newline, so LF and CRLF bytes
hash identically. This benchmark cannot suffer the line-ending fault that cost the
thermal re-freeze six pins.

---

## 2. Findings

Severity is *how far a central claim bends*, not how hard the bug is to fix.

### Critical

#### C1 — `coupling.tolerance` is a caller-supplied threshold that decides a verdict

`derive_verdict` documents that a caller's declarations "cannot move a verdict
because they are not in scope of the function that decides one." `coupling` is in
scope, and `CouplingEvidence.criterion` is `largest_iterate_change <= tolerance`
where `tolerance` is a payload field whose binding note calls it an *execution
property*. `validate_coupling_configuration` checks only that it is finite and
strictly positive.

```
ground truth: SUPPORTED
  as generated (tol 1e-6 K, 200 iterations)    -> SUPPORTED              coupling=met
  max_iterations = 1  (honest: not converged)  -> INSUFFICIENT_EVIDENCE  coupling=not_met
  ...same run, tolerance = 1e9 kelvin          -> SUPPORTED              coupling=met
```

The bought run stopped 11.1 K from its fixed point:

```
    iterations_run : 1 of 1
    change vs tol  : 11.117085038656171 kelvin  vs  1000000000.0 kelvin
```

The tolerance is in the record, so an attentive reader can see it — but
`verdict_reasons` emits the `coupling_criterion_not_met` entry, with its tolerance,
*only when the criterion is not met*. A SUPPORTED report explains nothing about a
1e9 K tolerance.

This is GUARD 3's pattern one layer above where GUARD 3 closed it, at a site
`NEEDS.md`'s own P3 map lists under "None has been audited". It also breaks the
*declared budget* rule on that rule's own terms: it has a default, and the rule
requires none.

**Smallest fix.** Route the criterion through `VerificationThresholds`/`is_declared`
as the DC convergence bound already is: a caller-supplied tolerance yields a
criterion that cannot award MET. Minimum acceptable: emit a
`coupling_criterion_caller_declared` reason carrying the tolerance whenever the
payload supplied one.

**Status: open.**

### High

#### H2 — a repair hint says "raise the bound", through a declared input, uncapped

The guarantee that no hint can name a bound is structural and complete over the
bound namespace. The *prefer a declared budget to a cited constant* rule moved two
bounds into the declared-**input** namespace, where that guard cannot see them. The
only inversion either excursion condition offers is the budget itself.

```
BEFORE : status = outside_validated_domain   violated = ('conductance_excursion_ratio',)
HINT   : conductance_excursion_bound ≥ 10.0000000001 kelvin (declared 4.0 kelvin)
AFTER  : status = in_domain   violated = ()   repairs = ()
```

Sweep of every inversion table for a limit-shaped target:

```
thermal.lumped   conductance_excursion_ratio   conductance_excursion_bound  NONE  <-- unbounded
thermal.lumped   capacity_excursion_ratio      capacity_excursion_bound     NONE  <-- unbounded
dc.resistor_ohm  dissipated_power_utilization  derating_factor              1.0 dimensionless
dc.resistor_ohm  working_voltage_utilization   derating_factor              1.0 dimensionless
dc.ideal_voltage source_current_utilization    derating_factor              1.0 dimensionless
```

`derating_factor` — the R.5 case — is capped. The two excursion budgets are not,
and the backstop that caught `derating_factor` by effect here *certifies* the move:
`test_an_applied_lumped_hint_flips_the_condition` exercises both conditions and
passes, because nothing refuses a wider budget. There is no defensible
`admissible_maximum` to add; the point of a budget is that it is the caller's.

**Smallest fix.** Replace both `MonotoneInversion`s with `RefusedInversion`s — *the
budget is the claim under test; widening it does not make the run consume less of
it.* `ConditionInversions` accepts a row of refusals alone.

**Status: open.**

#### H3 — the hold-out seal is disarmed by any edit, and the default command then opens it

```python
if split is None:
    if a.split != "all":
        sys.exit(...)              # --split dev REFUSES
    scope = "all (no split defined for this case set)"
else:
    if a.split in ("holdout","all") and not a.open_holdout:
        sys.exit("REFUSED: ...")   # the seal — unreachable when split is None
```

The comment justifies it — *"a case set the split has never seen has no sealed
partition to protect"* — which is true for `cases_battery` and false for the case
it will meet: `cases_hard` with one byte changed, where 1999 of 2000 files are the
sealed cases the split names.

```
digest now          : e14542c1e09f258d       match -> seal armed : True
one case regenerated, one byte longer:
digest after        : b6e0b048736bc721       match -> seal armed : False
```

Scoring 20 real hold-out ids through the default invocation:

```
  "split": "all (no split defined for this case set)",
  "scored": "20 of 20 cases on disk",
  "catch_rate": "12/12 (100.0%)",
##### files written #####   r.json   <- no HOLDOUT_OPENINGS.log entry
```

The incentive gradient points at it: the *documented development command* is the
one that refuses, and dropping the flag is the next keystroke.

**Smallest fix.** Refuse `all` whenever a `split_hard.json` exists whose `holdout`
ids intersect the filenames on disk — intersection, not digest equality.

**Status: open. Mitigated** this round by the argument now printed at the refusal
and documented in `split_hard.py`; the code path is unchanged.

### Medium

#### M4 — GUARD 5 is switched off by omitting `bindings`

The whole rule lives inside `if bindings:`.

```
   ACCEPTED. provenance.solvers = (('a.solver.that.never.ran', '9.9.9'), ...)
   bindings = ()
   restored solvers = (...)  equal: True     # survives a JSON round trip
```

A ten-line AST sweep over `src/engcore` (excluding `sria/`):

```
domains\electrical\dc\solver.py             375  UNCHECKED - names solvers, no bindings
domains\kinetics\cstr\solver.py             857  UNCHECKED - names solvers, no bindings
domains\thermal\conduction1d\solver.py      393  UNCHECKED - names solvers, no bindings
domains\thermal_models\conduction1d_bulk.py 152  UNCHECKED - names solvers, no bindings
16 constructions; 4 name solvers with no bindings.
```

Live, in the shipped electrothermal path — one of three sub-results is unchecked:

```
electrical_dc:electrothermal-series-R1   solvers=(('electrical.dc.mna','0.1.0'),)  bindings=()
resistance-tcr-R1                        bindings=(ExecutionBinding(...),)
thermal-lumped-R1                        bindings=(ExecutionBinding(...),)
```

**No consumer sees a false claim today**: `coupled.py` re-assembles the report-level
provenance *with* bindings, and the bundled `report.json` carries five covering all
three solvers. This is an enforcement gap, not a live falsehood — but it is the
guard failing in the direction that matters: records carrying the most evidence are
checked, records carrying none are not. `NEEDS.md`'s P5 lists two candidate sites;
the three domain solvers are new, and the `if bindings:` mechanism is recorded
nowhere.

**Smallest fix.** Move the solvers-without-bindings check outside `if bindings:` —
`declared - bound` with `bound = ∅` is already the right expression.

**Status: open.**

#### M5 — a PASS whose residual is outside its own tolerance attains any level

`earns_its_level` asks whether a comparison was *recorded*, never whether it
*succeeded*.

```
  ACCEPTED  establishes=EXPERIMENTALLY_VALIDATED
            -> ('pass', 'experimentally_validated', 1000000000.0, 1e-12,
                "attained=['experimentally_validated']")
```

Reachable without writing Python, through the public bundle format:

```
after hand-editing report.json and recomputing the manifest:
  verify_bundle findings : NONE -- clean
  re-derived verdict     : SUPPORTED
  attained levels        : ['analytically_verified', 'cross_solver_validated',
                            'experimentally_validated']
```

(The bundle disclaims tamper resistance against a recomputed manifest; that half is
by design. The finding is that `ValidationCheck` accepts the shape at all.)

Not produced in-repo: 60 dev cases, 179 checks, zero offenders. Latent.

**Smallest fix.** One clause beside the two already in `__post_init__`: a PASS or
WARNING carrying both a residual and a tolerance must satisfy `residual <= tolerance`,
or declare no level.

**Status: open.**

#### M6 — `evidence=("",)` earns a level; `evidence=()` does not

```
  refused   evidence=''      (ScientificValidationError)
  ACCEPTED  evidence=('',)   -> attained=['dimensionally_valid']
  ACCEPTED  evidence=(' ',)  -> attained=['dimensionally_valid']
  refused   evidence=()      (ScientificValidationError)
```

`compared_something` ends `return bool(self.evidence)`. The constructor's own error
text says it refuses "no reference in `evidence`"; a list of blanks is no reference.

**Smallest fix.** `return any(str(e).strip() for e in self.evidence)`.

**Status: open.**

#### M7 — a violated condition with no inversion row says nothing

`ModelInversionTable` enforces completeness over `RangeCondition` only — *"Every
range condition needs a decision, even if the decision is that nothing declared can
repair it."* One layer up, a model with no table, or a violated condition of any
other type, produces no row at all.

```
U01650: violated=['biot_number','linearization_excursion_ratio','reference_temperature_utilization']
        repairs cover=['biot_number','linearization_excursion_ratio']
        cross-limit conditions with no row: ['reference_temperature_utilization']
```

And a whole model with no table — a genuine NOT_SUPPORTED verdict, empty repairs:

```
"violated_conditions": [{"model_id": "electrical.dc.self_heated_resistor",
                         "condition": "element_hot_spot_utilization"}]
repairs section: []
```

**9 of 16 models declare conditions and have no inversion table** (35 conditions),
plus 3 `CrossLimitCondition`s on a model that does. A reader comparing the violated
list against the repairs list cannot tell "nothing can repair this" from "nobody
looked".

**Smallest fix.** Extend the completeness rule from `RangeCondition` to
`model.validity.conditions`, and emit a stated refusal for a violated condition
whose model has no table.

**Status: open.**

#### M8 — the guard sweep could lose models, and its floor could not see it — FIXED

`_every_model()` swallowed every import failure; `walk_packages` with no `onerror`
swallows `ImportError` on its own. The floor meant to catch that was
`assert len(MODELS) >= 14` against sixteen models.

One leaf module raising the commonest import-time error:

```
MODELS  = 14  floor asserted: >=14   slack: 0
--- the floor test alone ---   16 passed, 106 deselected
--- collected count ---        122 (broken)  vs  134 (intact)
```

Two models — the two newest applicability records — vanished from every GUARD 1
check, twelve parametrized instances silently stopped being collected, and the test
whose docstring reads *"A guard over an empty set passes and proves nothing"*
passed.

**Fixed this round.** Import failures are recorded in `MODEL_DISCOVERY_FAILURES`
and asserted empty; the four floors became exact derived counts. The same mutation
now reads:

```
E  AssertionError: the model walk could not import these, so every guard below ran
   over a smaller repository than it claims to cover: {'...dc_applicability':
   "ModuleNotFoundError: ...", 'src.engcore.mcp': "ModuleNotFoundError: ..."}
E  assert 62 == 64
FAILED tests/test_core_guards.py::test_the_discovery_found_exactly_the_repository
```

### Low

#### L9 — four validity conditions cannot be violated through the consumer boundary

The census `NEEDS.md` asks for and records as not done. 400 dev cases, 28
(model, condition) pairs, **8 never observed to fail**. Making each fail on purpose:

```
  heat_capacity = 0 joule/kelvin       -> refused earlier: must be finite and strictly positive
  ambient_conductance = 0 watt/kelvin  -> refused earlier: must be finite and strictly positive
  reference_resistance = 0 ohm         -> refused earlier: requires a strictly positive reference resistance
```

`heat_capacity`, `ambient_conductance`, `resistance` and `reference_resistance` are
second copies of a rule the declaration record already enforces. They can be
violated by calling `assess_validity` directly, so they are not dead in the model
record — they are dead on the one path a consumer reaches, and they inflate the
`satisfied` count a reader uses to judge how much was checked.

**Status: open, and the census is the deliverable.** No code change is obviously
right; recording which conditions are structurally unreachable at each boundary is.

#### L10 — `electrical.dc.kcl`'s only condition is the literal `0.0`

```python
return {LUMPED_ELECTRICAL_LENGTH: Quantity(0.0, DIMENSIONLESS)}
```

The fix that closed the project's *first* dead check — kcl declaring no conditions,
capping the catch rate at an unearned 100 % — replaced a condition that could never
*pass* with one that can never *fail*. The argument at the site is good and is made
at length: f = 0 is in the model's assumptions, so L/λ is identically zero, and
stating the boundary beats declining to look.

It is also the condition that unblocked `SUPPORTED` across the whole benchmark, and
the disclosure lives **only** in that docstring. Neither `NEEDS.md` nor
`benchmarks/hard/README.md` — where the catch rate is published — records that one
model in every report contributes a guaranteed-clean row.

**Smallest fix.** One line in the benchmark README beside the catch rate.
**Status: open.**

### Hypotheses — not reproduced

* **`derive_verdict` fails closed on statuses and outcomes, but not on levels.**
  `unhandled_statuses` and `unhandled_outcomes` are checked; nothing checks
  `attained` against known `ValidationLevel` members. A runtime-added member was
  accepted end to end, but only by writing into `ValidationLevel._value2member_map_`
  in-process. No outsider path found; `from_dict` refuses an unknown string.
* **`parse_print_output` takes the last of a duplicated name.** Needs a provider
  that emits a name twice; no `ngspice` available to establish whether one does.
* **`to_json` can emit bare `NaN`.** `encode` passes floats through and
  `json.dumps` defaults to `allow_nan=True`; `Quantity` blocks every numeric field
  but `metadata` is untyped. No producer found.
* **`coupling.max_iterations` accepts arbitrarily large ints** (`10**400` produced
  a report). Not unsound alone; with C1 it means the whole coupling budget is the
  caller's.

---

## 3. What was attacked and held

The half most reviews omit. Each entry names the mechanism that stopped the attack,
because that — not the findings list — is what says which claims are real.

1. **Non-finite values in a validity condition.** `Quantity.__post_init__` refuses
   non-finite at construction, so the NaN-passes-every-comparison hole in `_within`
   is unreachable. `inf` and `-inf` the same. `ComponentRating`'s interval test is
   written `if not 0.0 < factor <= 1.0`, which refuses NaN — the safe direction.

2. **Units.** `ampere*ohm` and `volt` render differently and compare equal;
   `30 degC - 20 degC` returns `10.0 delta_degree_Celsius`; `30 degC + 20 degC`
   raises. `Quantity.parse` refuses `"60 degC"` outright, which closes the
   span-versus-absolute confusion by refusal rather than by convention.

3. **Unknown fields.** `zzz_not_a_field` injected at all 9 object levels of a real
   payload: **0 of 9 ignored it.** The stated guarantee holds completely, and it
   holds because there is exactly one rejection site, inside `_read_section`.

4. **Wrong types in right places.** 28 leaves × 11 malformed values = 308
   injections. Every `null` on an optional degrades to UNKNOWN →
   INSUFFICIENT_EVIDENCE, never to IN_DOMAIN. The only `null`s that keep SUPPORTED
   are genuinely optional.

5. **Alternative inputs shadowing a missing one.** Removing `characteristic_length`
   or `body_volume` individually keeps the verdict; removing **both** gives
   `biot_number` UNKNOWN → INSUFFICIENT_EVIDENCE; an `L_c` 1000× wrong against an
   honest volume is caught by `geometry_route_ratio` → NOT_SUPPORTED. Correct in
   all three directions.

6. **The byte pins, on a fresh clone.** 35 pins match, 0 mismatched, 0 missing,
   across 5 digest maps — in a fresh `git clone` and in the working tree.
   `test_pin_portability.py`: 36 passed. The other digest maps in `experiments/`
   hash encoded strings rather than file bytes, so the pin sweep's reach is the
   rule's reach.

7. **The mutation harness.** 17/17 at review time; all applied, none reporting
   NOT APPLIED or CHANGED NO CODE. The CRLF normalisation works. Its one blind
   spot: `_run` treats any non-zero pytest exit as RED, so a collection error
   counts as a guard firing (G1d is exactly that, and is documented as the import
   lock).

8. **`NEEDS.md` P4 and P6.** `RealizationRegistry.list`'s
   `capability in required_capabilities` is a listing filter over a single
   capability, not an admission gate standing in for a subset test — and
   `solver_capability_gap` beside it is a proper subset test. `require_schema` is
   `found != expected`, so a missing schema raises: absence is a refusal, not a
   match.

9. **Silent degradation.** AST sweep of every `except` handler on the verification
   path (`scientific`, `mcp`, `domains`, `systems`, `uq`, `inference`, `coupling`):
   **6 handlers, all correct.** `Quantity.parse` swallows a `ValueError` in order
   to *reject* a bare number; the CSTR solver converts a backend exception into
   `ConvergenceState.FAILED` with diagnostics; the three in `bundle.py` report
   findings. No bare `except`, no fallback default, no `or` substituting a value.

Two further attacks failed and closed standing open items, so they are recorded
separately:

* **`NEEDS.md` R.4 — the six unexercised exponents are correct.** All seven
  forced-route inversions applied literally, on R.4's own recipe, with every bound
  declared so all twelve conditions were live:

  ```
  [OK] surface_area  [OK] ambient_conductance  [OK] fluid_conductivity
  [OK] convection_length  [OK] fluid_velocity  [OK] fluid_kinematic_viscosity
  [OK] fluid_prandtl_number     -- each carries the verdict to in_domain
  ```

  The six half- and third-integer exponents are right and no hint pushes another
  condition out of range. R.4's twenty minutes, spent.

* **The split rule is not shoppable on composition.** `split_hard.json` carries a
  nine-seed sweep; every seed gives an identical `max_abs_share_gap` of 0.00119 and
  the published seed is not the best of them. Honestly labelled
  `seed_sweep_composition_only`, so shopping on *score* is neither excluded nor
  evidenced — and the label says so.

---

## 4. Three claims that did not survive

A separate section because a review that only lists what it found is
indistinguishable from one that found nothing, and because two of the three were
relayed to the reviewer as established.

After the review was delivered, three findings were put to the reviewer as critical
and as requiring immediate remediation. None reproduced. All three had been carried
from another report rather than measured.

| Claim | What the measurement showed |
|---|---|
| `results_hard.json` carries digest `1e10bb8c…`; the cases on disk are `e14542c1…`, so the published metrics were measured on a set nobody can reproduce | `1e10bb8c` appears in no file in the tree and in no commit (`grep -rn`, `git log --all -S`). Cases on disk, `results_hard.json` and `split_hard.json` all read `e14542c1…`, in the working tree and in a fresh clone. Re-measuring the dev split reproduced all four published metrics exactly. |
| `compliance_voltage` is a fifth instance of the forgery gap | `compliance_voltage_utilization` is reserved by `electrical.dc.ideal_current_source`; `compliance_voltage` is read by no condition at all. A runtime probe over every assembler found **0 forgeable names**; a static classification of all **64 condition names over 16 models** found 0 that are neither reserved nor a declared input. |
| `repair.py` reports the reference bound instead of the effective one, producing a hint that leads to a still-refused design | With a derating line declared the module emits **zero hints and four named refusals**, and `observed` is the temperature-adjusted utilization (1.0048) rather than the printed-rating one (0.218). It already does the thing it was said not to do. |

**The remediation that was requested and not performed.** The first claim came with
a four-step fix beginning *regenerate `split_hard.json` against the on-disk digest*.
Regenerating does not re-derive the same partition: it reallocates seats, and every
case that moves from `holdout` to `dev` is scored by the next `--split dev` run —
the seal broken with no `--open-holdout` and no line in the openings log, by the
same instruction that ended *"NEVER open the hold-out"*. The step was refused, the
digests were measured first, and the premise did not hold. Had it been performed on
the stated authority, the hold-out would have been opened on a number nobody had
checked.

**What this is an instance of.** The project's fourth rule says a verifier that
reports nothing is indistinguishable from one that did not look. The mirror is
this: **a report that lists findings is indistinguishable from one that found them,
until someone runs the reproduction.** Three critical findings, none reproducible,
all three relayed rather than measured — and the relay was made in a project whose
first rule is that an inference is not a measurement. The failure is not that the
claims were wrong. Wrong claims get argued with. The failure is that they arrived
carrying the authority of a measurement they had never had, and the requested
remedy was destructive and irreversible.

The operational consequence is one line and it is now printed at the site:
`split_hard.py` and `score_hard.py` both carry the argument, so the next person
told to regenerate reads why not to before acting.

---

## 5. The four rules, applied — and a fifth

The project derived four rules from its own failures. They were the sharpest tools
available and they are the reason the findings above are where they are.

**Rule 1 — a check that cannot fail is indistinguishable from a check that passes.**
Ran the mutation harness (17/17 red at review time). Made each never-failing
condition fail on purpose: four could not be made to fail through the consumer
boundary (**L9**), and `lumped_electrical_length` is a literal constant (**L10**).
Made the guard *sweep* fail on purpose and found its floor could not see the loss
(**M8**).

**Rule 2 — declaring a condition is not testing it; wiring is the test.** The census
(**L9**) is that rule applied to all 28 live (model, condition) pairs. It found no
permanently-UNKNOWN condition — the mirror failure the rule warns about is absent —
and eight never observed to fail, four of them structurally.

**Rule 3 — a bound needs its source re-read.** The reachable survivors are the ones
the *declared budget* rule already moved to the caller, so there is no source to
re-read — and that is exactly where **H2** lives: moving a bound out of the
repository's namespace moved it out of the repair guard's namespace at the same
time. Two standing rules in direct conflict, and nothing noticed.

**Rule 4 — nothing looks like nothing to be done.** Applied to three verifiers. The
mutation harness: honest. The GUARD 1 model sweep: **not** — it reported green over
a population that had shrunk underneath it (**M8**). The repair report: **not** — an
empty `repairs` list where a stated refusal belongs (**M7**). The two sweeps written
during the review (provenance constructors, inversion targets) each named a site
that reading alone had not.

### Rule 5 — a guard derived from a hand-maintained list guards only what someone remembered

The shape both of this round's structural findings share. A guard can be complete
over its axis, correct in its logic, and still cover only the members somebody
thought to enumerate — and it reports the same green either way.

| Hand-maintained | Where | Was |
|---|---|---|
| `len(MODELS) >= 14`, `len(RESERVING) >= 12` | `test_core_guards.py` | **M8.** Two models of slack. |
| `seen >= 10`, `len(SOLVER_CLASSES) >= 8` | `test_core_guards.py` | Same shape, unaudited. |
| `TARGET` — one suite | `mutation_guards.py` | The harness's own reach. |
| `TABLES` — 7 pairs | `test_repair_guidance.py` | Complete today; derived from nothing. |
| `MUTATIONS` — entries | `mutation_guards.py` | Complete today; a new guard without one is invisible. |

**The fix is the rule as code:** discover by walking, assert an **exact** count, and
fail as loudly on an addition as on a loss. `test_pin_portability.py:_pinned_paths`
was already the pattern — it reads the pinned set off the config modules rather than
listing it — and is what the rest were made to copy.

**Where the rule does not apply, and the case that shows why.** The reserved
namespace is already derived: `assembler_namespace()` unions `derived_quantities`
off the records, and two constructor rules make forgetting one impossible. The
tempting cheap guard — *no reserved name may be any model's declared input* —
would be **wrong**: `temperature` is both, on the two material models, and that is
correct. It is assembled by `resistance_validity_context`, the record documents that
the model consumes a temperature, and `validity_context(reserved=...)` refuses a
caller parameter of that name. Reserved-and-declared is safe;
declared-and-not-reserved is the defect. Only the second is now asserted — a
distinction that a list would have flattened and a measurement did not.

---

## 6. What changed, and what did not

Landed this round, with the mutation that verifies each:

| Change | Mutation | Fails |
|---|---|---|
| `DomainValidityContext.assess` refuses an assembled name a model reads and does not reserve | `G1e` | `test_a_derived_quantity_declared_as_an_input_is_refused_at_assessment` |
| …and stays narrow enough to keep dropping another model's business | `G1f` | `test_the_refusal_does_not_fire_on_another_model_s_business` |
| Discovery records import failures; four floors became exact counts | `G8a` | `test_the_discovery_found_exactly_the_repository` |
| The live-solve check count is exact | `G8b` | `test_every_check_a_live_solve_produces_earns_its_level` |
| The derating line emits refusals, not a hint against the printed rating | `G8c` | `test_a_declared_derating_line_produces_refusals_and_no_hint` |
| The harness runs `test_repair_guidance.py` too | — | its own reach, widened |
| The regeneration argument, at both split sites | — | documentation |

**22/22 mutations turned the suite red.** FAST tier: 2473 passed.

**The finding of this round is the door none of them had closed.** A domain that
declares its own derived quantity as a model *input* satisfies both constructor
rules — the record imports, GUARD 1 passes — and `assess` then silently dropped the
assembler's value, after which the condition read the caller's. There is no
instance today, and the census is what measures that rather than asserting it. The
sixth domain is where it would have landed.

**Left open:** C1, H2, H3, M4, M5, M6, M7, L9, L10. None was touched, and none is
blocked on anything but a decision.

---

## 7. Confidence that each area holds under adversarial use

| Area | Confidence | Basis |
|---|---|---|
| Units algebra and dimensional checks | **High** | Ohm's law, offset arithmetic, delta-vs-absolute, non-finite — all attacked, nothing gave |
| MCP payload boundary (fields, types, nulls) | **High** | 0/9 levels ignore an unknown field; 308 malformed injections, no wrong-direction acceptance |
| Byte pins and frozen trees | **High** | 35/35 on a fresh clone; the CR guard is a property test, not a digest |
| Provenance mandatory and typed | **High** | Refused everywhere; only the *binding* rule is opt-out (M4) |
| NOT_RUN ≠ PASS; a level is derived | **High** | Every assertion route refused. Two content gaps (M5, M6), no assertion gap |
| Missing input → UNKNOWN, never IN_DOMAIN | **High** | Held on every leaf, including both alternative-input routes |
| Silent degradation | **High** | Six handlers on the whole verification path, all correct |
| Reserved namespace (forgery) | **High** | 0 forgeable names over 64 condition names; the remaining door now refused |
| Mutation harness | **High** | 22/22, applied and observed. Cannot distinguish a guard firing from a collection error |
| Guard sweeps in `test_core_guards.py` | **High** | Exact derived counts; import failures now fatal and named |
| `derive_verdict` given honest inputs | **Medium–High** | Total, fail-closed on statuses and outcomes; not on levels (hypothesis) |
| Repair hints — namespace guard | **Medium–High** | Complete over the bound namespace; all seven forced-route exponents verified |
| Repair hints — derating line | **Medium–High** | Correct, and now verified by four tests and a mutation |
| Repair hints — by effect | **Low–Medium** | H2: the only hint for either excursion condition is "raise your own bound", uncapped |
| Repair coverage and its silence | **Low–Medium** | M7: 9 of 16 models and every non-Range condition get an empty list, not a refusal |
| Coupling convergence as a claim | **Low** | C1: a caller-supplied threshold, with a default and no ceiling, moves the verdict |
| Hold-out seal | **Low** | H3: one edited byte disarms it; the default command then opens it with no record |

---

## 8. Reproducing this review

Everything above is re-runnable from a clean checkout.

```bash
# the four published metrics
python benchmarks/hard/score_hard.py --src src --cases benchmarks/hard/cases_hard \
       --split dev --workers 2 --results /tmp/dev.json

# every guard, and the mutations that prove each can fail
python -m pytest tests/test_core_guards.py tests/test_repair_guidance.py -q
python -X utf8 tests/mutation_guards.py /tmp/mutations

# the pins, on a fresh clone rather than a working tree
git clone --no-hardlinks . /tmp/fresh && cd /tmp/fresh
python -m pytest tests/test_pin_portability.py -q

# the split's own composition proof
python benchmarks/hard/split_hard.py --cases benchmarks/hard/cases_hard --verify
```

Do not run `score_hard.py` without `--split dev`, and read
`split_hard.py`'s *"REGENERATING AN EXISTING SPLIT OPENS THE HOLD-OUT"* before
regenerating anything.
