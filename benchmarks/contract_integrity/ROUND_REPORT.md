# Contract Integrity Round

Does every shipped model say exactly what it actually guarantees?

This round asks one question of the whole shipped surface: for every published
record, does the claim match the guarded runtime behaviour? It looks for the
CORE-1 shape — the record says one thing, the runtime intentionally does
another, existing tests guard the runtime, so the shipped record is the thing
that misleads.

## FINAL DECISION

**CONTRACT INTEGRITY EXPOSED SHIPPED DEFECTS — HARDENING REQUIRED**

One shipped record misdescribed guarded runtime behaviour and has been
corrected. All eight CI gates now pass, but the round does not certify, for
three reasons that outlive the fix:

1. a shipped record was found misdescribing what its runtime does (CI-1);
2. **15 of 16 models still carry no executable record-versus-runtime guard** —
   they were reviewed and found clean, and nothing would notice if one drifted
   tomorrow;
3. the certified mutation suite is **structurally blind** to this defect class,
   proven empirically below, and the new semantic layer has a known survivor.

---

## Scope reviewed

| | |
|---|---|
| Systems | 6 |
| Shipped model records | 16 |
| **Claims reviewed** | **457** |
| Condition instances | 64 |
| Distinct conditions reviewed | 56 (55 in the surface + 1 route-specific) |
| UNKNOWN-promise checks | 110 |
| Required-input checks | 36 |
| Applicability / cross-check probes | 4 |
| **Total checks** | **150** |
| **Exact matches** | **146** |

Coverage is asserted, not claimed: the review computes
`coverage_complete = true` by comparing the conditions it reviewed against the
conditions in the inventory, and the self-test asserts it.

## Method

Each condition reads its inputs from one of three places, so each is checked
its own way:

* **assembled** — the domain's assembler derives the quantity. Supply
  everything, drop exactly one declaration, ask the assembler what it produces.
* **cross-limit** — the condition reads two declared parameters by name; an
  absent declaration leaves it UNKNOWN by construction in `ValidityDomain`.
* **declared parameter** — same, for a single parameter.

The shipped records write their preconditions in prose — *"unless both edges
are declared"*, *"unless the operating point is supplied"* — which no regex can
turn into an experiment. Every clause was read by hand and written down in
`audit/claim_map.py` as `all_of` (dropping any one must force UNKNOWN) or
`one_of` (alternative routes: dropping the whole group must force UNKNOWN,
dropping one member must not), with the clause quoted beside the mapping so the
reading itself can be audited.

## Results

| Result | Checks |
|---|---|
| MATCH | 146 |
| RECORD_TOO_BROAD | 1 → fixed (CI-1) |
| RECORD_TOO_NARROW | 0 |
| RECORD_AMBIGUOUS | 0 |
| RUNTIME_CONTRACT_VIOLATION | **0** |
| TEST_CONFLICT | **0** |
| UNKNOWN_INTENT | **0** |

| Defect class | Count |
|---|---|
| SHIPPED_CONTRACT_INTEGRITY | **1** |
| RUNTIME_IMPLEMENTATION_DEFECT | **0** |
| TEST_DEFECT | **0** |
| AMBIGUOUS_PRODUCT_SEMANTICS | **0** |
| NEEDS_PRODUCT_DECISION | **0** |
| AUDIT_DEFECT (not Core defects) | 4 |

## Confirmed defect

### CI-1 — a route-dependent precondition published as a flat requirement

| | |
|---|---|
| **ID** | CI-1 |
| **Severity** | LOW |
| **Defect class** | SHIPPED_CONTRACT_INTEGRITY |
| **Model** | `thermal.lumped.first_order_capacity` |
| **Condition** | `convection_flow_range_utilization` |

**Old published claim.** *"UNKNOWN unless the convection_length, kinematic
viscosity, Prandtl number, the operating point and one of the two route
declarations are all supplied."*

**Actual guarded runtime behaviour.** On the **forced** route the condition is
`Re/5e5` with `Re = u L / nu`, which carries no Prandtl number: it is answered
without one, and its value is bit-identical whether or not one is supplied. On
the **natural** route it is `Ra/1e9` with `Ra = Gr Pr`, and there the Prandtl
number genuinely is required. The record stated a flat conjunction that is true
on one route and false on the other.

**Minimal reproducer.**

```
derived_lumped_quantities(
    {surface_area, fluid_conductivity, fluid_kinematic_viscosity,
     fluid_velocity, convection_length, ambient_conductance,
     heat_capacity, duration},            # note: NO fluid_prandtl_number
    initial_temperature=..., ambient_temperature=..., heat_input=...)

-> convection_flow_range_utilization = 0.0333...   # answered
   convection_property_range_utilization           # UNKNOWN
   convection_conductance_agreement_ratio          # UNKNOWN
```

Adding a Prandtl number leaves the flow range at exactly `0.0333...`.

**Existing test evidence — the runtime is deliberate.**

* `test_one_missing_fluid_property_does_not_blank_the_others` — withholding
  `fluid_prandtl_number` must **not** blank the forced flow range. Its
  docstring: *"A Reynolds number never needed the conductivity... Over-reporting
  a gap looks like the safe direction and is not."*
* `test_withholding_prandtl_on_the_natural_route_does_take_the_flow_range` —
  the mirror image, pinned so the first test cannot be satisfied by a module
  that never marks a flow range undecidable.
* `test_the_prandtl_floor_binds_only_the_forced_route`
* `test_the_natural_route_needs_the_operating_point_and_the_forced_one_does_not`
  — docstring: *"A real asymmetry, not an oversight."*

**Source of truth: the RUNTIME.** `Re = u L / nu` is the record's own printed
formula and carries no Prandtl number. The asymmetry is pinned by four named
tests, two of which exist specifically to stop the gap being over-reported. The
record's precondition list was written as a flat conjunction and did not
survive the split into two routes.

**False-confidence impact: NONE at the verdict level.** A forced declaration
missing a Prandtl number still assesses UNKNOWN overall, through
`convection_property_range_utilization` (`0.6/Pr`) and
`convection_conductance_agreement_ratio`. The misdescription is confined to one
condition's precondition list, and the condition itself was correctly
evaluated. That is why this is LOW and CORE-1 was not.

**Fix: the record only.** It now states the route asymmetry, names which
sibling conditions do go UNKNOWN on a forced declaration without a Prandtl
number, and cites the two tests that pin it. No executable code changed — the
file's executable code digest is unchanged at `bea9ff6f6d880eca`.

**Regression test.**
`tests/test_core_semantic_invariants.py::test_the_flow_range_record_states_which_route_needs_a_prandtl_number`
asserts the published text names the asymmetry **and** that the runtime still
exhibits it on both routes, including that a Prandtl number does not move a
Reynolds-based flow range at all. Verified to FAIL against the pre-fix record.

## Audit defects — mine, not the Core's

Four. None is counted as a Core defect, and three were in the detection logic
itself.

| ID | What | Effect | Fixed by |
|---|---|---|---|
| AUD-1 | The clause parser read `body_volume` in the `biot_number` precondition as a third requirement. The clause says *"(declared, or derived from body_volume/surface_area)"* — an alternative route. | one false `RECORD_TOO_BROAD` | an explicit `all_of`/`one_of` claim map, read by hand |
| AUD-2 | The DC contexts were merged into one namespace, so a refusal in `resistor_rating_context` emptied the others and made every DC condition look dependent on `rated_power`. | two false `RECORD_TOO_NARROW` | one isolated context per assembler |
| AUD-3 | The battery exclusion *"no condition here would catch a charge"* was read as false because construction refuses a negative current. The claim is scoped to **conditions** and is literally true: `continuous_c_rate_utilization` takes `\|C\|`, so a −1C charge reads as a +1C discharge and no condition catches it. The refusal is a separate declaration guard. | one candidate defect withdrawn before it was recorded | reading the claim's scope, then testing the derivations directly |
| AUD-4 | Semantic mutation SC3 changed one word rather than the claim, so it survived for a reason unrelated to guard coverage. | one false SURVIVOR | strengthening SC3 into a genuine revert |

Two further near-misses were resolved by looking rather than concluding:
`battery:cell_discharge_step` appeared unprovided until
`battery_solver_capabilities()` was found, and `CellSpecification` defaults
`open_circuit_voltage_at_full` to `None` but refuses without it, so the
record's `required=True` is honoured.

## Contract mutation gap

**79/79 mutation success does NOT prove contract integrity.** Proven, not
asserted:

```
record text changed  : True        # an UNKNOWN promise inverted to its opposite
code digest changed  : False       # the certified harness registers nothing

(contrast, a one-line executable change)
code digest changed  : True
```

`_code_digest` drops STRING tokens and
`test_every_mutation_changes_executable_code` refuses any mutation whose only
effect is prose. Both are deliberate. The consequence is that the certified
suite is structurally blind to every defect class this round exists to find:

* required-input wording changes
* optional/mandatory metadata changes
* fake cross-check claims
* applicability wording changes
* UNKNOWN/refusal description changes
* a capability description becoming too broad
* reason text claiming evidence the runtime never evaluated

### Semantic contract mutation — a new, separate layer

`audit/semantic_contract_mutation.py`. It does not touch, extend or renumber
the certified 79-mutant suite; it copies the tree, mutates a published record's
text, and requires a named guard to go RED.

| | Mutation | Result |
|---|---|---|
| SC1 | a published UNKNOWN promise inverted | **RED (caught)** |
| SC2 | the geometry record back to promising an unperformed cross-check (CORE-1) | **RED (caught)** |
| SC3 | the flow-range record back to requiring Prandtl on both routes (CI-1) | **RED (caught)** |
| SC4 | the record claims a cross-check where one route is compared against nothing | **RED (caught)** |
| SC5 | an applicability claim widened past what the condition enforces | **SURVIVOR** |

**4 of 5 caught. SC5 is a real coverage gap, reported rather than closed:** no
shipped record currently carries that defect, so closing it is a future round's
work and not a minimal fix in this one.

## Auditor self-test

`benchmarks/contract_integrity/tests/test_auditor_self_test.py` plants five
controlled defects, runs the real detection logic against each, and requires
each to be found. Nothing is planted in production: the defects live in
synthetic claim/context pairs registered for one test, or in a monkeypatched
copy of a derivation, and every one is removed in a `finally`.

1. record requires three inputs, runtime accepts one — **detected**
2. record says one input is enough, runtime requires three — **detected**
3. record claims a cross-check, only one route executes — **detected**
4. record applicability wider than runtime validity — **detected**
5. runtime changes, record does not — **detected**, and the audit is asserted
   quiet again after the patch is reverted, so the detection was the planted
   drift and not a standing failure.

All six tests pass. All planted defects reverted.

## Guard coverage

| | |
|---|---|
| Models with an executable record-versus-runtime guard | **1 of 16** (`thermal.lumped.first_order_capacity`) |
| Models without | **15 of 16** |

Both guards live on `thermal.lumped` because both defects found so far are
there. The other fifteen models were reviewed and found clean — and nothing
executable would notice if one drifted tomorrow. This is the main reason the
round does not certify.

## Existing assurance preserved

The only production change is a record description string.

| | |
|---|---|
| Executable code digest of the changed file | **unchanged**, `bea9ff6f6d880eca` |
| `src/engcore/scientific` tree digest | **unchanged**, `82558f5b...d2507`, still matching the certification snapshot |
| FAST | **3834 passed, 3 skipped** (3833 + this round's guard) |
| `tests/test_core_semantic_invariants.py` | 111 passed |
| Contract-integrity self-test | 6 passed |
| Hard DEV / Battery DEV / 79-mutant suite | **not re-run, and cannot have moved** |

The last row is a claim with evidence behind it, not an assumption. The change
is STRING-token only, measured with the certified harness's own `_code_digest`,
which is exactly the function that decides whether a change is executable. No
executable scientific behaviour changed, so those three results carry over from
the state Blind V2 measured them at. **The previously certified scientific
digest remains unchanged and is not invalidated.**

## Blind V2 evidence

Untouched. No path under `benchmarks/blind_v2` changed at all; its freeze
manifest still verifies 30/30 artifacts, and `FIRST_RUN.json` and both
`FIRST_RUN` run files are byte-identical. The Blind V2 gates are not modified,
reused or renumbered — they answered a different question and their results
stand as they were.

## CI gates

| Gate | Verdict |
|---|---|
| CI-1 Contract surface complete | **PASS** |
| CI-2 Published/runtime agreement | **PASS** |
| CI-3 Runtime contract correctness | **PASS** |
| CI-4 Shipped contract integrity | **PASS** |
| CI-5 Executable consistency guards | **PASS** (with a caveat: 15 of 16 models unguarded) |
| CI-6 Audit truth quality | **PASS WITH CONCERN** |
| CI-7 Existing scientific assurance preserved | **PASS** |
| CI-8 Frozen evidence preserved | **PASS** |

CI-6's concern is the four audit defects, three of which were in the detection
logic itself. Every audit input stayed inside its physical range —
`assert_physical()` checks emissivity in [0,1], state of charge in [0,1],
coulombic efficiency ≤ 1, activation energy ≥ 0 and every strictly-positive
parameter — because Blind V2's worst challenge-side defect was a generator that
left exactly those ranges.

## What a hardening round should do next

1. Extend the record-versus-runtime guard pattern to the other 15 models. Both
   defects found so far were invisible to every existing suite and visible
   immediately to this one check.
2. Close the SC5 gap: nothing notices a record advertising applicability the
   condition refuses.
3. Consider promoting the semantic contract mutation layer to a standing suite,
   kept separate from the certified 79.
