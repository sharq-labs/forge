# Scientific oracle register

What Forge's current science is checked against, how independent each check
actually is, and what remains unverified.

**The question this round asked:** the benchmark's answer key is 98.4 %
generator-constructed, so it can prove Forge is *consistent with itself* and
cannot prove Forge is *right*. Everything below is an attempt to obtain an
expected value **without Forge**.

The executable half lives in `tests/oracles/`, which enforces one rule: an
oracle may not obtain its expected value from the thing it checks.

---

## 1. Sources

Citations only — no reproduced text.

| ref | source | supports |
|---|---|---|
| **INC-6** | Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat and Mass Transfer*, 6th ed., Wiley (2007) | Bi (Eq. 5.10), lumped time constant (Eq. 5.7), Fo, Ra (Eq. 9.25), Re (Eq. 6.41), Churchill–Chu as printed (Eq. 9.27, §9.6.1), lumped single-phase formulation (§5.1, Eq. 5.6) |
| **CC-75** | Churchill, S. W. & Chu, H. H. S., "Correlating equations for laminar and turbulent free convection from a vertical plate", *Int. J. Heat Mass Transfer* **18**(11), 1323–1329 (1975) | the free-convection correlation Forge implements |
| **MCA-54** | McAdams, W. H., *Heat Transmission*, 3rd ed., McGraw-Hill (1954) | Nu = 0.59 Ra^(1/4), vertical plate, 1e4 ≤ Ra ≤ 1e9 — the **second, independent** correlation used to cross-check CC-75 |
| **KIT-8** | Kittel, C., *Introduction to Solid State Physics*, 8th ed., Wiley (2005), Ch. 5, Table 1 | beryllium θ_D = 1440 K, the datum behind the θ_D/5 reference floor |
| **PEU-1897** | Peukert, W., *Elektrotechnische Zeitschrift* **18**, 287–288 (1897) | the capacity–rate law |
| **PLETT-1** | Plett, G., *Battery Management Systems, Volume I: Battery Modeling*, Artech House (2015), Ch. 2–3 | coulomb counting with discharge-direction efficiency; OCV as tabulated data |
| **CODATA-18** | CODATA 2018 recommended values | σ = 5.670374419e-8 W m⁻² K⁻⁴ |
| **NGSPICE-42** | ngspice 42, U.C. Berkeley CAD Group | linear resistive DC solution |
| **SEBORG-3** | Seborg, Edgar, Mellichamp & Doyle, *Process Dynamics and Control*, 3rd ed., Wiley (2011), Ch. 2 | the non-isothermal first-order CSTR balances |

---

## 2. Oracle register

| ID | class | independent? | executable? | covers | limitation |
|---|---|---|---|---|---|
| `ORA-NGSPICE-DC` | `INDEPENDENT_EXECUTABLE` | **YES** | **YES** | node voltage, branch current, resistor dissipation | linear resistive DC only; skipped if ngspice absent |
| `ORA-RAD-LINEARIZATION` | `INDEPENDENT_ANALYTIC` | **YES** | **YES** | h_r reconstructs Stefan–Boltzmann exactly; matches a finite-difference derivative | grey diffuse surface, view factor 1 — the configuration Forge declares |
| `ORA-FREE-CONVECTION-CROSS` | `INDEPENDENT_REFERENCE_DATA` | **YES** | **YES** | CC-75 vs MCA-54, disagreement accounted for term by term | two fits to overlapping corpora; bounds transcription, not physics |
| `ORA-LUMPED-ODE` | `INDEPENDENT_ANALYTIC` | **YES** (algorithmically) | **YES** | closed form vs RK4 of the same balance | verifies the *solution*, not the *choice* of equation |
| `ORA-DIM-GROUPS` | `INDEPENDENT_ANALYTIC` | **YES** | **YES** | Bi, τ, Fo, Ra, Re from their definitions | says nothing about the bounds placed on them |
| `ORA-TCR-LIMITS` | `INDEPENDENT_ANALYTIC` | **YES** | **YES** | R(T_ref)=R_ref, exact linearity, α→0, sign symmetry | the linear form's algebra, not its applicability |
| `ORA-PEUKERT` | `LITERATURE_REFERENCE` | **YES** | **YES** | published law, k=1 limit, anchor, monotonicity | empirical fit; limited rate range, fixed temperature |
| `ORA-DIMENSIONAL` | `INDEPENDENT_ANALYTIC` | **YES** | **YES** | dimensions composed from SI base units here | necessary, not sufficient |
| `ORA-CONDUCTION-DISCRETE` | `INDEPENDENT_ANALYTIC` | **YES** | **YES** | exact backward-Euler amplification `(1+r·mu_1)^-N`, matched to 1e-10 at any mesh | checks assembly and linear solve, not the choice of scheme |
| `ORA-CONDUCTION-ANALYTIC` | `INDEPENDENT_ANALYTIC` | **YES** | **YES** | `u = sin(pi x/L) exp(-alpha pi^2 t/L^2)`, approached under refinement | verifies discretisation by convergence, not to round-off |
| `ORA-CSTR-STEADY` | `INDEPENDENT_ANALYTIC` | **YES** | **YES** | steady state by bisection of the energy residual with C eliminated | shares the balances; uniqueness in range is asserted, not assumed |
| `ORA-CSTR-RK4` | `INDEPENDENT_ANALYTIC` | **YES** | **YES** | trajectory by RK4 against Forge's BDF | tolerance from Forge's declared `rtol`, the less accurate side |
| `ORA-BATTERY-COULOMB` | `LITERATURE_REFERENCE` | **YES** | **YES** | coulomb counting, C-rate, Rint terminal voltage, affine OCV, the two SoC definitions | Rint is an approximation; the oracle checks its algebra, not cell fidelity |

**Thirteen oracles, all independent of Forge, all executable.** Before this round
the register carried three independent oracles, two of which were citations
nothing ran.

---

## 3. Do they bite?

Fourteen mutations of Forge's physics, applied one at a time to the real source
and restored byte-identical:

| mutation | outcome |
|---|---|
| Bi: `hL/k` → `hL/(2k)` | KILLED |
| Bi: length inverted | KILLED |
| τ: inverted | KILLED |
| Ra: `L³` → `L²` | KILLED |
| Ra: `/ν²` → `/ν` | KILLED |
| radiation: `(Ts+Tsur)` → `(Ts−Tsur)` | KILLED |
| radiation: squared term dropped | KILLED |
| Churchill–Chu: `0.670` → `0.607` | KILLED |
| Churchill–Chu: `9/16` → `9/17` | KILLED |
| Churchill–Chu: `Ra^¼` → `Ra^⅓` | KILLED |
| TCR: sign flipped | KILLED |
| Peukert: `k−1` → `k` | KILLED |
| DC: `P = VI` → `VI/2` | KILLED |
| DC: `P = VI` → `V²` | KILLED |

**14 applied, 14 killed, 0 survivors.**

A further twelve against the two domains added since:

| mutation | outcome |
|---|---|
| CSTR: reaction sign in the mass balance | KILLED |
| CSTR: exotherm sign | KILLED |
| CSTR: cooling term sign | KILLED |
| CSTR: reaction order `kC` → `kC²` | KILLED |
| CSTR: rate constant halved | KILLED |
| CSTR: dilution term dropped | KILLED |
| conduction: `r` doubled | KILLED |
| conduction: `dx²` → `dx` | KILLED |
| conduction: operator sign `(1+2r)` → `(1−2r)` | KILLED |
| conduction: off-diagonal sign flipped | KILLED |
| conduction: off-diagonal halved | KILLED |
| conduction: initial eigenmode 1 → 2 | KILLED |

**26 applied in total, 26 killed, 0 survivors.**

---

## 4. Per-domain coverage

| domain | relationships | independent oracle | literature-backed | coverage |
|---|---|---|---|---|
| electrical DC | ~6 | **ngspice, executable** | — | **STRONG** |
| thermal dimensionless groups | 6 | analytic, 4 groups + identity | INC-6 | **STRONG** |
| radiation | 2 | analytic + finite difference | CODATA-18 | **STRONG** |
| free convection | 5 | cross-correlation | CC-75, MCA-54, INC-6 | **MODERATE** — Churchill–Chu verified; Rayleigh/Reynolds range bounds unsourced |
| lumped transient | 4 | RK4 | INC-6 | **MODERATE** — solution verified, equation choice not |
| material TCR | 5 | limits + identities | KIT-8 (one datum) | **MODERATE** — form verified, band/floor policy unsourced |
| battery cell | ~25 | 12 relationships incl. coulomb counting with the efficiency direction pinned | PEU-1897, PLETT-1 | **MODERATE** — 12 of ~25 |
| kinetics CSTR | ~15 | steady state by bisection, trajectory by RK4, five derived limits | Seborg et al. 3rd ed. Ch. 2 | **MODERATE** — solution verified, model choice not |
| 1-D conduction | ~10 | exact discrete + exact continuous solution | INC-6 Ch. 5 | **STRONG** — the only domain checked against a closed form to round-off |
| coupling / consensus / uncertainty | — | none (contractual, not physical) | — | **N/A** |

---

## 5. Two disagreements found, both resolved in Forge's favour

Investigating the 11 battery false rejects produced the round's substantive
finding. All 11 are **ground-truth defects**, and they share one root cause.

### 5a. `load.duration` — step or horizon?

Forge's MCP boundary states it twice and warns about exactly this misreading:

> "THE STEP DURATION, not the horizon. The march advances `steps` intervals of
> this length, so the discharge lasts `duration * steps` and a caller who reads
> this as the total gets a run `steps` times too long."

`generate_battery.py` reads it as the horizon. With `steps = 10` the generator's
march is a tenth of the declared discharge.

### 5b. Coulombic efficiency on discharge — multiply or divide?

Forge: `SoC(t) = SoC₀ − I t / (η Q_nom)`, citing **PLETT-1** Ch. 2, with a
stated direction argument — discharge-direction efficiency *reduces* usable
charge, so a given delivered charge depletes more SoC. The generator multiplies,
and documents no basis.

### The independent check

Coulomb counting done here from the payload, using Forge's stated contract:

```
Δz = I · (steps · duration) / (η · Q_nom)
   = 1.5 · 600 / (0.99 · 9000) = 0.101010101…
z_end = 0.9 − 0.101010101 = 0.798989898989…
```

Forge reports **0.7989898989898995** — an exact reproduction. The generator's
reading gives 0.8899 (or 0.801 with its η convention), which is what put
`w_lo = 0.7993` on the wrong side of the trajectory.

| group | cases | independently computed | truth says | verdict |
|---|---|---|---|---|
| `soc_step_resolution_ratio` | 6 | 1.0101 and 1.0183, bound ≤ 1 | SUPPORTED | **truth defect** — Forge correctly refuses |
| `soc_window_margin` | 5 | z_end − w_lo = −0.0003, bound ≥ 0 | SUPPORTED | **truth defect** — Forge correctly refuses |

**Classification: `GROUND_TRUTH_DEFECT`, not a runtime defect.** No Forge code
was changed. The repair is a generator correction plus regeneration of
`cases_battery`, which is out of this round's scope; a field edit cannot fix it
because the *payloads* were drawn against the wrong horizon.

---

## 6. The six DEV cases under review

Each was recomputed here from its payload — Stefan–Boltzmann for the radiation
share, `(hA/A_s)·L/k` for Biot — never from Forge's output.

| case | condition | independent value | limit | margin |
|---|---|---|---|---|
| U01769 | radiation/convection | 1.016 | 0.1 | 10× |
| U01000 | radiation/convection | 0.655 | 0.1 | 6.5× |
| U00188 | radiation/convection | 0.543 | 0.1 | 5.4× |
| U01940 | radiation/convection | 0.258 | 0.1 | 2.6× |
| U01830 | Biot | 2.029 | 0.1 | 20× |
| U01881 | radiation/convection | 0.109 | 0.1 | **1.09×** |

**Five of six: the refusal is independently confirmed sound.** Radiation
carrying 26–100 % of the convective path, or a Biot number 20× the lumped
criterion, puts those bodies outside a convection-only lumped model under any
reading of the threshold.

**U01881 is not resolved.** It sits 9 % past a threshold (0.1) that
`UNSOURCED_BOUNDS.md` already records as unsourced. An oracle can confirm the
ratio and cannot confirm the bound.

**No truth was edited.** These cases remain incoherent in a way an oracle cannot
fix: their `defect` family says one thing and their firing mechanism is another,
because the shaper failed to widen a second condition. The honest repair is
regeneration, and `needs_review` stays set.

---

## 7. Coverage metrics

Verification coverage — **not** "scientific accuracy".

| metric | value |
|---|---|
| relationships with any oracle | ~24 of ~75 (**32 %**) |
| relationships with an **independent** oracle | ~24 of ~75 (**32 %**) — every oracle added is independent |
| domains with an independent **executable** oracle | 1 of 6 (electrical DC) |
| benchmark DEV cases whose truth is independently backed | **0 of 1400** — the oracles verify *relationships*, not case truth |
| critical applicability bounds sourced | 4 of 15 (**27 %**), unchanged — no bound was sourced this round |
| trust-affecting tolerances derived rather than chosen | oracle suite: 100 % (ngspice from print precision, RK4 from Richardson, convection from published coefficients) |
| fully circular benchmark truth | **1378 of 1400 (98.4 %)**, unchanged |

The fourth row is the one to read twice. Verifying that Biot is `hL/k` does not
make any benchmark case's *expected verdict* independently true — that still
comes from the generator.

---

## 8. Circularity audit

| what | circularity | why |
|---|---|---|
| oracle suite ↔ Forge | **NONE** to **LOW** | expected values from citations, other programs, or derivations here |
| `ORA-LUMPED-ODE` ↔ lumped model | **MEDIUM** | different algorithm, same governing balance |
| benchmark truth ↔ Forge | **HIGH** | shared repository, generator tuned against scoring |
| benchmark truth ↔ Forge, thermal constants | **FULLY_CIRCULAR** where the generator imports the same limit (e.g. `GEOMETRY_AGREEMENT_FACTOR = 3.0` appears in both) |
| hold-out | **HIGH** and opened | see `HOLDOUT_STATUS.md` |

A passing benchmark case under `FULLY_CIRCULAR` truth is regression evidence.
It is not independent scientific validation, and this round did not change that
for a single case.
