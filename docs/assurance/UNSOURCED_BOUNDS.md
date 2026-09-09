# Applicability bounds without a source

The backlog this round produced and deliberately did not work on. **No
threshold below was researched, changed, or re-derived here.** The list exists
so the next scientific-validation round starts from an inventory rather than a
grep.

**"In code" is not a source.** A number that appears in a `RangeCondition` with
a paragraph of reasoning beside it is *documented*, which is better than
undocumented and is not the same as *sourced*. Sourced means a specific
external authority is named at the point of declaration, so a reader can go and
disagree with it.

---

## Inventory

| condition | domain | threshold / range | declared in | source status | benchmark dependence | risk if wrong |
|---|---|---|---|---|---|---|
| `melting_temperature_utilization` | thermal lumped | ≤ 1 | `thermal_models/context.py` | **SOURCED** — Incropera et al. 6th ed. §5.1 (single-phase lumped form) | 32 hard cases name it | low: the bound is definitional |
| `peak_body_temperature` (max-of-endpoints) | thermal lumped | — | `thermal_models/context.py` | **SOURCED** — Incropera 6th ed. §5.1 Eq. 5.6 | underlies every ceiling | low |
| `reference_reduced_debye_temperature` | material | ≥ θ_D/5 | `electrical/material.py` | **SOURCED** — Kittel 8th ed. Ch. 5 Table 1 (beryllium θ_D = 1440 K) | 34 cases | low |
| `reduced_debye_temperature` | material | ≥ θ_D/3 | `electrical/material.py` | **PARTIAL** — Bloch–Grüneisen linear regime is standard; the exact 1/3 is repository policy | **168 cases** | **medium**: a wrong floor moves 168 expected verdicts |
| `biot_number` | thermal lumped | ≤ 0.1 | `thermal_models/lumped.py` | **PARTIAL** — 0.1 is the conventional lumped-capacitance criterion, not cited at the declaration | **401 cases**, the largest single family | **medium**: conventional and near-universal, but uncited |
| `internal_fourier_number` | thermal lumped | floor | `thermal_models/context.py` | **PARTIAL** — one-term series validity; adjudicated 2026-09-09 as a *conservative screen* rather than a finding | 175 cases | low: adjudicated to produce UNKNOWN, which cannot create false confidence |
| `operating_temperature_utilization` | material | ≤ 1 | `electrical/material.py` | **UNSOURCED** for its operating point | 132 cases | **medium** — see below |
| `linearization_excursion_ratio` | material | ≤ 1 | `electrical/material.py` | **UNSOURCED** — the Taylor-remainder argument is stated; the band is caller-declared | 93 cases | low: the band comes from the caller |
| `radiation_to_convection_ratio` | thermal lumped | limit | `thermal_models/lumped.py` | **UNSOURCED** | 71 cases, and 3 of the accepted alternates | medium |
| `conductance_excursion_ratio` | thermal lumped | ≤ 1 | `thermal_models/lumped.py` | **UNSOURCED** — the budget is caller-declared | 163 cases | low |
| `capacity_excursion_ratio` | thermal lumped | ≤ 1 | `thermal_models/lumped.py` | **UNSOURCED** — caller-declared | 79 cases | low |
| `geometry_route_ratio` | thermal lumped | 1/3 … 3 | `thermal_models/lumped.py` | **PARTIAL** — the factor 3 is derived from the sphere identity `L_c = r_o` vs `V/A_s = r_o/3`, which is stated | 87 cases (as the real catcher) | low: derived, and the derivation is written down |
| `convection_flow_range_utilization` | thermal lumped | correlation range | `thermal_models/context.py` | **PARTIAL** — correlation validity ranges | 76 cases | medium |
| `convection_property_range_utilization` | thermal lumped | Prandtl range | `thermal_models/context.py` | **PARTIAL** | 75 cases | medium |
| `convection_conductance_agreement_ratio` | thermal lumped | agreement band | `thermal_models/context.py` | **UNSOURCED** | 95 cases | medium |

Counts are occurrences of the condition as a declared catcher across all 2000
`cases_hard` cases, and are a proxy for how much benchmark truth rests on the
bound — not for how often it is evaluated.

---

## The one that is not just a missing citation

`operating_temperature_utilization` is **definitionally** ≤ 1: a ratio of a
temperature to a declared maximum reaching 1 *is* the statement that the limit
was reached. The bound needs no source.

What is unsourced is the **operating point it is read at**, and this round's
`U01001` adjudication turned on exactly that. Two hard material ceilings in one
report use different points:

| condition | evaluated at |
|---|---|
| `melting_temperature_utilization` | `max(T₀, T_ss)` — bounds the whole trajectory, "including horizons the caller has not yet asked for" |
| `operating_temperature_utilization` | `T(duration)` — the state the declared run occupies |

The endpoint convention is the one the landed `internal_fourier_number`
adjudication requires (moving to the peak fixes 1 dev case and breaks 18), so
it is *governed*, and it is not *sourced*: no external authority says a
conductor's operating-temperature rating is a constraint on a declared mission
rather than on the design's equilibrium.

**The open consequence**, recorded in the U01001 event's `residual` field:
Forge computes `steady_state_temperature`, that value can exceed the declared
ceiling, and no condition reads it. A design whose equilibrium is above a hard
material limit is flagged nowhere.

---

## What a sourcing round would have to do

1. For each `PARTIAL` and `UNSOURCED` row, find or commission a citation and
   put it at the declaration, next to the number — not in a document.
2. Where no source exists, say so at the declaration too, so the condition
   carries its own status.
3. Decide `operating_temperature_utilization`'s operating point as a stated
   policy with a rationale, rather than leaving it as the residue of an
   unrelated adjudication.
4. Re-run the blast-radius measurement for any bound that moves. Every one of
   these has a benchmark dependence in the table above, and a changed bound is
   a ground-truth event for every case that names it.

Nothing in that list is a code defect. It is the gap between *the code
implements the declared rule correctly* — which the assurance round
established — and *the declared rule is the scientifically right rule*, which
nothing in this repository currently establishes.
