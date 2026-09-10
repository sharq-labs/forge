# Blind Challenge v2 — Certified-Core Generalization Gate

A fresh, independently constructed, pre-sealed challenge against the Forge
Scientific Core at its certified revision. This file is the round's report.
Every figure in it was measured in this round; nothing is quoted from
documentation.

**Decision: BLIND V2 EXPOSED A SHIPPED CORE CONTRACT DEFECT — RETURN TO
CURRENT-CORE HARDENING FOR CONTRACT-INTEGRITY RECERTIFICATION.**

The defect is a shipped published record contradicting guarded runtime
semantics. It is not an incorrect numerical or scientific runtime
implementation, and no executable scientific behaviour was changed to resolve
it.

---

## A. Repository state

| | |
|---|---|
| HEAD at start | `b5cedffda947238c298a3d81ed08750434b8b143` |
| `origin/main` | same commit (fetched; the local ref was stale and was updated) |
| Branch | `claude/blind-challenge-v2-5k8t3u` |
| Working tree | clean |
| Worktrees | one |

`benchmarks/hard/results_hard.json` was rewritten by the baseline benchmark
run and restored: the only difference was its `generated` timestamp, every
scored figure being byte-identical, which is itself a reproducibility result.

## B. Certified-Core verification

The snapshot `certification/current_core_v1.json` was verified with its own
recipe, not with a reimplementation of it.

| | |
|---|---|
| `CERTIFICATION_CODE_SHA` | `be57bf4d705606d746175cbc1c240697e68ef0c2` |
| `FINAL_CERTIFICATION_SHA` | `b5cedffda947238c298a3d81ed08750434b8b143` |
| Core tree sha256 | `82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507` — **matched** |
| Modules | 47 — matched |
| Python | 3.11.15 (snapshot: 3.14.2 on Windows 11) |
| ngspice | ngspice-42, native (snapshot: ngspice-42 via WSL) |
| MCP SDK | present |
| numpy / scipy / pint / pytest | 2.4.6 / 1.17.1 / 0.25.3 / 9.1.1 |

Certified baseline, re-measured here one suite at a time:

| Suite | This round | Snapshot |
|---|---|---|
| FAST | 3832 passed, 3 skipped | 3832, 3 |
| SCIENTIFIC | 4366 passed, 3 skipped | 4369, 3 — the 3 are Windows-only ngspice tests deselected on Linux |
| benchmark guards | 57 | 57 |
| scientific oracles | 363 + 2 skipped | 363 + 2 |
| independent verdict | 83 | 83 |
| independent reason/catcher | 124 + 2 skipped | 124 + 2 |
| blind-v1 guards | 51 | 51 |
| performance guards | 12 | 12 |
| mutation | **79/79 RED, 0 GREEN, CONTROL GREEN, exit 0** | 79/79 |
| Hard DEV | 1362/1400, FA 0, FR 0, digests identical | same |
| Battery DEV | 272/280, FA 0, FR 8 (same ids), digests identical | same |

The certified state reproduces exactly on a different operating system and a
different Python.

## C. V2 pre-registration

`CHALLENGE_SPEC.json`, committed in `2da8b2d` at 17:07:12Z, **before any case
existed**. It fixes the seed (20260910), the target of 720 primary cases over
six systems, the six families, the four-outcome truth vocabulary, the two
reserved non-verdicts, the dual-oracle plan and its A/B/C/D independence
scale, the boundary margins, the affine-unit rule, the refusal stages, and the
decision rules.

Two scoring rules were registered there specifically so that applying them
later could not be mistaken for leniency:

* a case carrying both a violation and a missing declaration is marked
  `precedence_dependent` and scored on the accept/refuse axis separately from
  the exact verdict (30 cases);
* a physically invalid but dimensionally legal declaration may be refused at
  construction *or* caught as a condition, so both are acceptable and neither
  can be a false accept (116 cases).

## D. Systems covered

Discovered from the declared contract surface, not assumed. The historical
expectation was "approximately six"; the code says **exactly six**, split by
the first two segments of each model's own `model_id`.

| System | Models | Conditions on the primary model |
|---|---|---|
| `thermal.lumped` | 1 | 12 |
| `electrical.material` | 2 | 9 |
| `battery.cell` | 4 | 11 |
| `electrical.dc` | 6 | 3 |
| `kinetics.cstr` | 2 | 6 |
| `thermal.conduction1d` | 1 | 1 |

16 shipped `ScientificModelDefinition` records in total, 54 distinct declared
bounds between them.

## E. Case families

Six per system, assigned by **what a case turned out to be**, never by what it
was aimed at. The generator states an intent; the oracles decide; a mismatch
is a logged rejection.

| Family | Cases |
|---|---|
| nominal interior | 190 |
| isolated violation | 173 |
| missing evidence | 137 |
| boundary refusal | 87 |
| unit representation | 85 |
| compound mechanism | 48 |

6,928 samples were proposed and not kept, logged in `GENERATION_LOG.json` with
why: 575 not constructible, 468 a declaration already made, 105 with no bracket
for the requested margin, and 5,780 surplus to a quota already filled. A
rejection is always a fact about the sampler and never about what the system
under test would have said, which the generator has no way to ask. `thermal.conduction1d` and `kinetics.cstr` have no compound
family and the log says so: with one and two independent levers respectively
there is no compound mechanism to find, and a quota that pretended otherwise
would have been filled with mislabelled cases.

## F. Primary corpus composition

720 cases, 120 per system.

| Truth outcome | Cases |
|---|---|
| SUPPORTED | 254 |
| NOT_SUPPORTED | 239 |
| INSUFFICIENT_EVIDENCE | 140 |
| REJECTED_AT_BOUNDARY | 87 |

Boundary stratification, by what the arithmetic **achieved** rather than what
was aimed at: 54 `MATHEMATICAL_BOUNDARY` (exact float equality with the
bound), 186 `REPRESENTABLE_BOUNDARY`, 2 `WITHIN_1_ULP_BOUNDARY`. Reaching an
exact boundary required bisecting the declaration in log space until the
bracket was two adjacent floats and then walking single ULPs; a tolerance-based
stop left the quantity thousands of ULPs away.

## G. Metamorphic shadow composition

231 shadows over six transformations — equivalent units, declaration order,
JSON round trip, integer spelling, provenance metadata, and the affine-span
probe. A shadow carries no independent truth; it is an invariance probe naming
its parent.

## H. Truth classes

| Class | Cases |
|---|---|
| INDEPENDENT_SCIENTIFIC | 402 |
| MIXED_SCIENCE_AND_POLICY | 215 |
| CONTRACT_ONLY | 83 |
| POLICY_DEPENDENT | 20 |
| **UNRESOLVED** | **0** |

## I. Bounds / policy register

All 54 bounds classified in `BOUND_REGISTER.json`, none left unclassified.

| Class | Bounds |
|---|---|
| ANALYTICALLY_DERIVED | 41 |
| SOURCE_BACKED | 8 |
| INTERNAL_POLICY | 4 |
| CONTRACT_DECLARED | 1 |

The four internal policies are named as conventions: the factor of 3 on
`geometry_route_ratio`, the factor of 2 on
`convection_conductance_agreement_ratio` (which the record itself already
admits no source prints), the 5% budget on
`polarization_unmodelled_fraction`, and the 1/5 floor on
`reference_reduced_debye_temperature` chosen to admit beryllium.

## J. Oracle inventory

| System | Route 1 | Route 2 |
|---|---|---|
| `thermal.lumped` | closed form of `C dT/dt = Q - hA(T - T_amb)`; Incropera 6th ed. groups | in-challenge RK4, refined until the answer stops moving; steady state by bisection on the residual |
| `electrical.material` | exact rational evaluation of `R_ref(1 + α(T - T_ref))` | in-challenge RK4 on `dR/dT = α R_ref` |
| `battery.cell` | closed-form charge balance and Rint chord (Plett Ch. 2–3) | in-challenge RK4 on `dz/dt` |
| `kinetics.cstr` | the exact invariant `Z = T + βC_A` and its ceiling | in-challenge RK4 of the balances, which must respect the ceiling |
| `thermal.conduction1d` | separation of variables, exact for all time | in-challenge Crank–Nicolson with a Thomas sweep written here |
| `electrical.dc` | **a real ngspice subprocess** | modified nodal analysis assembled and solved here, Gaussian elimination written in-challenge |

## K. Oracle independence

Nothing under `benchmarks/blind_v2/challenge` imports `engcore`, proven four
ways: syntax-tree imports, the transitive import graph, a name and string
scan, and a fresh interpreter's `sys.modules`. The units algebra is written
for this challenge and shares no backend with the system under test.

The bound **values** were captured once from the declared model records, into
`CONTRACT_SURFACE.json`, by a script that is outside the audited package and
is never imported by it. That is contract reading, not peeking — but it is
recorded, and every bound also carries an independent justification.

## L. Dual-oracle coverage

330 of 633 scientifically decided cases (**52.1%**, target 50%), with at least
37 in every system.

| Level | Cases |
|---|---|
| A — external executable vs in-challenge route | 94 |
| B — analytic closed form vs independent numerical solver | 236 |
| D — same equation relaid out | **0, never claimed** |

Mean route disagreement 4.6e-6, worst 8.2e-5 (Crank–Nicolson truncation on a
coarse mesh). The ngspice pairs agree to 4.6e-16 where its printed precision
allows; their tolerance is fixed at 2e-6 because ngspice prints about seven
significant figures, and that was registered before the run.

**21 CSTR cases lost their second route before the freeze.** The oracle
self-test found the RK4 route diverging on an uncooled exotherm and reporting a
peak of 3.5e11 K, from which it concluded the analytic ceiling was breached.
Its own refinement had known — halving the step still moved the answer by 100%.
It now abstains. Found without asking Forge anything.

## M. No-peek proof

All four checks clean. The audit was then **falsified**: a module that
deliberately imports `engcore` is written into the package and all four checks
catch it. An audit never shown to fail is a decoration.

No sealed holdout was opened. No existing case payload, truth label, reason
key or catcher key was read. Documentation was not used as a numeric
authority; every count here was measured.

## N. Freeze manifest

`FREEZE.json` digests 30 artifacts — spec, inventory, bound register, every
generator and oracle module, the cases, the shadows, the truth, the generation
log and the Phase-1 tests — with an independent verifier that recomputes each.
It verifies clean.

## O. `PRE_FORGE_FREEZE_SHA`

`979ed983f786f38838e8db8373e02ffec5ad9b97`, committed 2026-09-10T17:19:58Z.
Tree clean after the commit.

## P. First-run SHA / timestamp

`c29ec4efab17987a874ee6cd92f944bb2c85f962`, sealed 2026-09-10T17:26:40Z,
committed before any record in it was compared against truth.

## Q. Time-order proof

| Artifact | Entered history | Commit |
|---|---|---|
| CHALLENGE_SPEC, SYSTEM_INVENTORY, BOUND_REGISTER | 17:07:12Z | `2da8b2d` |
| generator, oracles, truth, cases, shadows, FREEZE | 17:19:58Z | `979ed98` |
| runner | 17:25:56Z | `c0755c8` |
| FIRST_RUN artifacts | 17:26:40Z | `c29ec4e` |

`git diff` over `cases/`, `truth/`, `challenge/`, `FREEZE.json`,
`CHALLENGE_SPEC.json` and `BOUND_REGISTER.json` between the freeze commit and
HEAD is **empty**.

## R. First-run result

720 primary cases, 231 shadows, one run, 1.4 s and 0.8 s of wall clock.

| | |
|---|---|
| Total primary | 720 |
| Decided denominator | 633 |
| Truth SUPPORTED / NOT_SUPPORTED / INSUFFICIENT / REJECTED | 254 / 239 / 140 / 87 |
| **Exact verdict agreement** | **541 / 720 (75.1%)** |
| **Acceptable verdict agreement** | **630 / 720 (87.5%)** |
| TRUE_ACCEPT | 252 |
| **FALSE_ACCEPT** | **5** |
| TRUE_REJECT | 417 |
| FALSE_REJECT | 2 |
| Records filed as Core errors | 44 |
| Runner errors | 0 |

After adjudication: **674 / 720 exact (93.6%)**, **0 false rejects**, **0 Core
crashes**, and **2 false accepts relative to the frozen published contract** —
which post-adjudication evidence resolved to a contract-integrity defect rather
than a behavioural one. **Behavioural false accepts after adjudication: 0.**
See section Z.

## S. System-by-system results

| System | Cases | Decided | Exact | Acceptable | FA | FR | CE | Insuff. dis. | Bnd. dis. |
|---|---|---|---|---|---|---|---|---|---|
| `electrical.material` | 120 | 106 | 111 | 120 | 0 | 0 | 0 | 0 | 0 |
| `thermal.lumped` | 120 | 106 | 106 | 115 | 2 | 1 | 0 | 2 | 0 |
| `battery.cell` | 120 | 106 | 96 | 118 | 2 | 1 | 0 | 0 | 0 |
| `electrical.dc` | 120 | 106 | 92 | 104 | 1 | 0 | 0 | 15 | 1 |
| `kinetics.cstr` | 120 | 105 | 71 | 76 | 0 | 0 | 44 | 26 | 2 |
| `thermal.conduction1d` | 120 | 104 | 65 | 97 | 0 | 0 | 0 | 23 | 0 |

The two weakest rows are the challenge's fault, not the Core's. Every
`kinetics.cstr` "Core error" is a `ReactorConfigurationError` — a declared
refusal filed under the wrong heading by the runner — and both low exact
scores come from the challenge predicting a late refusal where the Core
refuses early. Neither crosses the accept/refuse line.

## T. Truth-class results

| Class | Cases | Exact | Acceptable | FA | FR |
|---|---|---|---|---|---|
| INDEPENDENT_SCIENTIFIC | 402 | 237 | 318 | 2 | 0 |
| MIXED_SCIENCE_AND_POLICY | 215 | 206 | 214 | 0 | 2 |
| CONTRACT_ONLY | 83 | 80 | 80 | 1 | 0 |
| POLICY_DEPENDENT | 20 | 18 | 18 | 2 | 0 |

No aggregate accuracy in this report implies scientific validation. The
INDEPENDENT_SCIENTIFIC row is the only one that speaks to the science, and its
two false accepts are CORE-1 — false accepts against the frozen published
contract, not against the runtime's computed science, which was found to be
deliberate and guarded.

## U. Dual-oracle results

The strongest subset: 330 cases, **310 exact (93.9%)**, 312 acceptable, **0
false accepts**, 2 false rejects (both the challenge's own unbounded levers).
Levels A 94, B 236. Mean route disagreement 4.6e-6, worst 8.2e-5.

## V. Metamorphic results

| Transformation | Pairs | Same outcome | Different | Justified | **Unjustified** | Mechanism drift |
|---|---|---|---|---|---|---|
| equivalent units | 42 | 42 | 0 | 0 | **0** | 0 |
| declaration order | 42 | 42 | 0 | 0 | **0** | 0 |
| serialization round trip | 42 | 42 | 0 | 0 | **0** | 0 |
| integer spelling | 42 | 42 | 0 | 0 | **0** | 0 |
| provenance metadata | 42 | 42 | 0 | 0 | **0** | 0 |
| affine span probe | 21 | 2 | 19 | 19 | **0** | 0 |

**Zero unjustified violations in 210 semantics-preserving pairs.** No
equivalent physical declaration produced a stronger trust verdict because of
how it was written.

All 21 affine-span probes — the one transformation declared *not*
semantics-preserving — were refused, with a message naming the confusion
exactly: *"capacity_excursion_bound is a temperature span and may not use
'degree_Celsius': its zero is conventional, so a difference expressed in it is
not a value of that unit."* There is no silent state-for-span substitution.

## W. Reason results

| | Cases |
|---|---|
| EXACT_REASON | 198 |
| VALID_ALTERNATE_REASON | 7 |
| MISSING_CAUSAL_REASON | 4 |
| **WRONG_MECHANISM** | **0** |
| NOT_APPLICABLE | 511 |

## X. Causal results

| | Cases |
|---|---|
| EXACT_CAUSAL_MATCH | 139 |
| VALID_CAUSAL_PLUS_REDUNDANT | 18 |
| NO_UNIQUE_PRIMARY | 25 |
| WRONG_CAUSAL_MECHANISM | 2 |
| NOT_APPLICABLE | 536 |

Causal truth was frozen before the run, by repairing one declared defect back
to its nominal value, leaving every other defect where it was, and recomputing.

## Y. Mismatch triage

| Class | Cases |
|---|---|
| AGREEMENT | 541 |
| EXPECTED_CONTRACT_DIFFERENCE | 62 |
| REPRESENTATION_BOUNDARY | 57 |
| CHALLENGE_TRUTH_DEFECT | 54 |
| ORACLE_DEFECT | 4 |
| **CORE_DEFECT** | **2** |
| UNRESOLVED | 0 |

The 2 `CORE_DEFECT` rows are the CORE-1 cases. `CORE_DEFECT` here means a
defect in the shipped Core product; section Z establishes that its class is
**SHIPPED_CONTRACT_INTEGRITY** — the published record, not the computed
science.

172 of the 179 mismatches are refusal against refusal: the challenge expected
a condition to catch what the Core refused earlier, at construction. The Core
is stricter and earlier, which is the safe direction.

## Z. Genuine Core defects

**CORE-1 — Published capability contract contradicts guarded runtime
semantics.** Class **SHIPPED_CONTRACT_INTEGRITY**. Severity MEDIUM,
false-confidence potential yes.

**This is a shipped contract/record integrity defect. It is not an incorrect
numerical or scientific runtime implementation.** No computed quantity, no
verdict and no benchmark figure is affected by it, and none needed to change to
resolve it.

Two statements about `geometry_route_ratio` shipped together and contradict
each other:

* the **published record** — the text a caller reads and `to_dict` serializes —
  said *UNKNOWN unless characteristic_length, body_volume and surface_area are
  all supplied; with one route there is nothing to compare, which is not the
  same as two that agree*;
* the **derivation** returns `1.0` with a single route, so the condition is
  reported in `satisfied` and the assessment reaches IN_DOMAIN.

Both are shipped. They cannot both describe the product. The defect is that
contradiction, and it is located in the published record.

Reproduction, frozen: `geometry_route_ratio(declared=1 mm, volume=None,
surface_area=0.01 m²)` returns `1.0 dimensionless`, and an assessment over that
declaration reaches IN_DOMAIN with the condition in `satisfied`. The published
record predicted UNKNOWN.

**The runtime semantics are deliberate and guarded.**
`test_one_route_alone_is_not_a_contradiction` pins the single-route behaviour by
name and gives the reason: demanding all three fields would be a larger claim
than this condition makes, and the Biot number is computed from an unambiguous
value either way. Changing the derivation to return `None` broke 25 existing
tests. So the record was the half that was wrong, and the record is what moved.

It now states what the condition does, including the part a reader most needs:
with one route the condition is satisfied and **no cross-check was performed**,
and `satisfied` here means "no declared geometry contradicts another", never
"two routes were compared". It also records that whether a single-route
declaration should instead be UNKNOWN is a live product question, and names the
test that pins the current answer, so the next round decides it rather than
rediscovering it. A regression guard now pins the record and the derivation
together so they cannot drift apart again.

Resolved in `0e9bcc219ba7d19eb823cd739dec11c115012ad3`. No executable
scientific behaviour changed; no verdict anywhere changed.

### What the two cases are, precisely

`V2-THERMAL_LUMPED-00065` and `-00074` were **false accepts relative to the
frozen published contract** the challenge read before the run. Independent
truth was derived from that record, the record said UNKNOWN, and the system
reported SUPPORTED. That is exactly the frozen Gate 3 condition, and the gate
result stands on it.

Post-adjudication evidence then established *where* the defect sits. Because
the runtime behaviour is deliberate and guarded, **neither case is a
behavioural false accept**: the runtime did what the product intends, and the
published record misdescribed it.

| | |
|---|---|
| Behavioural false accepts after adjudication | **0** |
| Contract false accepts under the frozen published contract | **2** |

**Zero genuine Core crashes.** All 44 exceptions the runner filed as
`core_error` are declared domain refusals.

## AA. Challenge / oracle defects

* **The levers were not bounded by the physics they moved.** The one driving
  `radiation_to_convection_ratio` walked `surface_emissivity` past 1; the one
  driving `soc_window_margin` walked a state-of-charge edge below 0. The oracle
  computed with both. An emissivity is a ratio of emitted to black-body flux
  and a state of charge is a fraction of usable charge; neither has a reading
  outside [0,1]. The Core refused both at construction and was right. This is
  the most serious challenge-side defect: a generator that can leave the
  physical domain of its own declarations can manufacture findings.
* **The evidence map treated required declarations as droppable.** 49 cases.
* **A float path landed one ULP above an inclusive bound.** 2 cases; exact
  rational arithmetic on the declared decimals gives exactly 1.
* **A refusal probe was aimed at a field with no unit.** 1 case.
* **The registered channel-ambiguity flag was applied to one branch of the
  generator and not the other.** 16 cases.
* **The runner's exception taxonomy knew only the core's own two classes.** 60
  records across both runs.

## AB. Truth errata

7 errata over 90 of 720 cases — a **12.5% truth-defect rate**, recorded in
`TRUTH_ERRATA.json`, which is append-only. `truth/truth.jsonl` is byte-identical
to the freeze commit and was never edited. The first-run score stands against
the frozen truth; the adjudicated score is reported beside it, never instead.

## AC. Contamination accounting

| | |
|---|---|
| FOUND_WITHOUT_FORGE | ERR-8 |
| FORGE_GUIDED **discovery** | ERR-1, ERR-2, ERR-3, ERR-5, ERR-6, ERR-7 |
| FORGE_GUIDED **repair** | **none** |

Six of seven errata were found because the Core disagreed. That is real
contamination of this challenge's independence and it is not hidden. None took
its *answer* from the Core: each was re-derived from exact rational arithmetic,
from the definition of the quantity, or from a fact the challenge had frozen
before the run and failed to use.

## AD. Policy sensitivity

No production threshold was changed and no frozen truth was touched. The four
INTERNAL_POLICY bounds were re-evaluated against reasonable alternatives.

**377 of 391 condition verdicts are robust; 14 are policy-boundary dependent** —
2 on the geometry factor (at a generous factor of 4), 5 on the convection
agreement factor, 0 on the polarization budget, 7 on the Debye reference floor
(at a stricter 1/4). 96% of what these conventions decided would have been
decided the same way by a reviewer who chose different numbers.

## AE. Performance sanity

Median 0.69 ms per case, p95 6.6 ms, p99 15.3 ms, worst 320 ms (one
`thermal.conduction1d` solve). 0 timeouts, 0 Core errors that were not declared
refusals. This is not comparable to any certified measurement — different
machine, different OS, different Python — and no regression is claimed from it.
It is reported to show nothing pathological happened.

## AF. Regression preservation

Production code changed, so the full certification-relevant sweep was re-run.

**Every runtime figure below is unchanged, and that is the expected result.**
The CORE-1 correction changed the published contract/record and added its
executable consistency guard; it did not change the runtime scientific result
for the frozen corpus. Hard DEV, Battery DEV, every case-set digest and every
frozen verdict output are therefore byte-identical, and the post-fix run of the
v2 corpus reproduces the first run exactly. The only movements in the table are
the two suites that gained this round's regression guard.

| Suite | After the fix | Certified baseline |
|---|---|---|
| FAST | 3833 passed, 3 skipped | 3832 + this round's guard |
| SCIENTIFIC | 4367 passed, 3 skipped | 4366 + this round's guard |
| benchmark guards | 57 | 57 |
| oracle suite | 363 + 2 skipped | 363 + 2 |
| independent verdict | 83 | 83 |
| independent reason/catcher | 124 + 2 skipped | 124 + 2 |
| blind-v1 guards | 51 | 51 |
| performance guards | 12 | 12 |
| core semantic invariants | 110 | 109 + this round's guard |
| mutation harness self-guard | 6 | 6 |
| **mutation suite** | **79/79 RED, 0 GREEN, CONTROL GREEN, exit 0** | identical |
| blind-v2 challenge tests | 83 | new |
| Hard DEV | 1362/1400, FA 0, FR 0 | identical, same digests |
| Battery DEV | 272/280, FA 0, FR 8 | identical, same ids and digests |

## AG. V2 validity audit

**VALID_BLIND_V2.** Fourteen checks in `VALIDITY_AUDIT.json`: eleven PASS, one
PASS with a recorded source-read incident, two CONCERN — the 12.5% truth-defect
rate and the discovery contamination on six errata.

## AH. Safety gates

| Gate | Verdict |
|---|---|
| 1 — Blindness | **PASS** |
| 2 — Challenge truth quality | **PASS WITH CONCERN** |
| 3 — Zero genuine false accepts | **FAIL** — qualified, see below |
| 4 — Zero unresolved Core defects | **PASS** |
| 5 — Metamorphic representation safety | **PASS** |
| 6 — Certified Core digest preserved | **PASS WITH SCOPE CAVEAT** |
| 7 — Mutation assurance preserved | **PASS** |
| 8 — Existing benchmarks preserved | **PASS** |

**Gate 3's definition is frozen and is not redefined here.**
`CHALLENGE_SPEC.json`, committed before the corpus existed, defines a false
accept as *"the system reports SUPPORTED where independent truth refuses"*. The
two CORE-1 cases meet that definition — independent truth was derived from the
published record, the record said UNKNOWN, the system said SUPPORTED — so the
gate fails and the result stands as measured.

> **Gate 3 fails under the frozen published contract; post-adjudication
> evidence established that the runtime behaviour was deliberate and the defect
> was in the published record.**

Stated on the two axes the evidence actually supports:

| | |
|---|---|
| Behavioural false accepts after adjudication | **0** |
| Contract integrity | **FAIL** — the published record contradicted guarded behaviour |

**Gate 6's caveat is a scope fact a reader needs, not an accusation.** The
`src/engcore/scientific` tree digest is unchanged, both immediately before the
first run and now — and production code *did* change. The CORE-1 fix is in
`src/engcore/domains/thermal_models/lumped.py`, which is outside the path the
snapshot digests.

The snapshot is explicit about this: `core.path` is `src/engcore/scientific`,
`digest_covers` names `src/engcore/scientific/**/*.py`, and the scope section
already says it does not cover "any domain, shape or regime outside those
exercised here". So the digest behaved exactly as specified. But the sentence
"the certified Core digest is preserved" is, on its own, compatible with having
changed a shipped model record that a caller reads — which is what happened
here. Anyone reading Gate 6 as "no production code changed" would be wrong, and
that is why the caveat is attached rather than the gate simply marked PASS.

**The previously certified scientific digest remains unchanged and is not
invalidated** — nothing it covers was touched. A new shipped-product /
contract-integrity certification cycle is required because a shipped
domain-model record contradicted guarded runtime semantics.

## AI. Remaining scientific limitations

Carried forward, all still true, none newly falsified by this round:

* consensus independence is declaration-based, never proven;
* scientific-capability / solver-capability naming debt;
* `ScientificVariable` legality split between the IR and its sampling consumer;
* no field or mesh scientific semantics beyond 1-D diffusion;
* no general UQ engine — representation only;
* no multivariate curve semantics;
* exact float boundary equality is not invariant across every unit spelling;
* **no general experimental validation of any scientific model.** This round
  validates software behaviour against independently computed truth. It
  validates no physics against any experiment, and the corpus contains no
  measurement.

New, from this round:

* the certification digest covers `src/engcore/scientific/**` only, as it says
  it does, so "certified Core digest preserved" does not by itself mean no
  shipped production code changed (Gate 6);
* **the current mutation harness cannot detect this defect class**, because
  STRING-token-only changes are intentionally excluded from its `_code_digest`
  and `test_every_mutation_changes_executable_code` refuses any mutation whose
  only effect is prose. CORE-1 lives entirely in a published record's text, so
  the 79/79 result is silent about it — a scope limit, not a weakness in the
  result. A future semantic-contract or record-mutation layer, which would
  mutate published record text and require a guard to notice, could cover this
  class. The regression guard added this round is the first instance of exactly
  such a guard.

## AJ. Harsh scores

| | /10 | Why not higher |
|---|---|---|
| Blindness integrity | **9** | freeze proven, audit falsified, no forbidden read — but one recorded overread into a validity implementation |
| Challenge truth quality | **5** | 12.5% erratum rate, and two levers left the physical domain of their own declarations |
| Oracle independence | **8** | no `engcore` anywhere, proven four ways; bound *values* were still captured from the declared records |
| Dual-oracle strength | **7** | 52% coverage and 94 level-A pairs, but most level-B pairs are one equation solved two ways |
| Scientific breadth | **6** | six systems and 55 conditions, all lumped or 1-D; no fields, no UQ, no multivariate |
| Boundary robustness | **9** | 54 exact-boundary hits and correct inclusive/exclusive semantics throughout; the only ULP disagreement was the challenge's own arithmetic |
| Unit / metamorphic robustness | **10** | 210/210 invariant, 21/21 affine spans refused with an exact message |
| Refusal-path robustness | **9** | refuses early and names the field and the reason every time; the late path is less well measured because the challenge over-predicted it |
| Verdict generalization | **7** | 93.6% adjudicated; 0 behavioural false accepts, but 2 against the frozen published contract |
| Reason generalization | **9** | 198 exact, 0 wrong mechanisms |
| Causal generalization | **8** | 139 exact, 2 wrong |
| False-confidence resistance | **6** | a shipped published record that did not describe its own guarded behaviour, in the unsafe direction |
| Policy / science separation | **9** | every bound classed, conventions named as conventions, 96% of their verdicts robust |
| Reproducibility | **9** | deterministic generation verified, every artifact digested, benchmarks byte-identical across a different OS and Python |
| Certified-Core generalization | **7** | one shipped contract-integrity defect; runtime behaviour held over 720 fresh cases and 231 shadows with no crashes, no behavioural false accept and no metamorphic violation |

## AK. Final decision

**BLIND V2 EXPOSED A SHIPPED CORE CONTRACT DEFECT — RETURN TO CURRENT-CORE
HARDENING FOR CONTRACT-INTEGRITY RECERTIFICATION.**

This is the frozen decision option *"BLIND V2 EXPOSED CORE DEFECTS — RETURN TO
CURRENT-CORE HARDENING"*, stated with the defect class the evidence supports.
The round's vocabulary is not being redefined; the class is being named.

**What was found.** One Core defect, CORE-1, of class
**SHIPPED_CONTRACT_INTEGRITY**: the published `geometry_route_ratio` record
contradicted the guarded runtime semantics it documents. It is **not** an
incorrect numerical or scientific runtime implementation.

**Why the runtime was not changed.** The single-route behaviour is deliberate
and guarded by `test_one_route_alone_is_not_a_contradiction`, which pins it by
name and states its reason. Changing the derivation broke 25 existing tests.
Overriding a guarded product decision on the strength of a challenge
disagreeing with a record would have been the wrong repair. The published
record was corrected instead, and a regression guard now pins the record and
the derivation together so they cannot drift apart again.

**Why Gate 3 still fails.** Its definition is frozen in `CHALLENGE_SPEC.json`
and is not redefined here: the system reported SUPPORTED where independent
truth — derived from the published record before the run — refused. Gate 3
fails under the frozen published contract; post-adjudication evidence
established that the runtime behaviour was deliberate and the defect was in the
published record. Behavioural false accepts after adjudication: **0**. Contract
integrity: **FAIL**.

**Why the post-fix outputs are identical.** The correction changed the
published contract/record and added its executable consistency guard; it did
not change the runtime scientific result for the frozen corpus. Hard DEV
(1362/1400), Battery DEV (272/280), every case-set digest and every frozen
verdict output are therefore unchanged and byte-identical, exactly as expected.
An identical post-fix run is the confirmation that the repair was
record-scoped, not evidence of a failed fix.

**Why the mutation suite is silent.** 79/79 RED with CONTROL GREEN is preserved
and valid. The current mutation harness cannot detect this defect class because
STRING-token-only changes are intentionally excluded from its `_code_digest`. A
future semantic-contract or record-mutation layer could cover it.

**What recertification is for.** The previously certified scientific digest
remains unchanged and is not invalidated — nothing it covers was touched. A new
shipped-product / contract-integrity certification cycle is required because a
shipped domain-model record contradicted guarded runtime semantics, and the
existing certification scope (`src/engcore/scientific/**`) does not reach the
shipped domain-model surface where that happened.

**What the challenge earned, and what it cost.** It was able to fail Forge, and
it did — on a contradiction between what the Core publishes about itself and
what it does, which no existing suite could see and which the mutation harness
cannot express. It also carried a 12.5% truth-defect rate of its own: three of
the five apparent false accepts and both apparent false rejects were the
challenge's fault, its generator left the physical domain of its own
declarations, and six of seven errata were found only because Forge disagreed.
Those caveats stand undiminished beside the finding.
