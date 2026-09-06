# Results

## 1. What was measured

100 thermal designs, drawn from 35 real resistors and 23 real package thermal
resistances, were converted into engcore payloads and run. Each design carries a
label decided from the datasheet, a hand calculation or `reference.py` — an
independent statement of the applicability conditions that never imports
engcore — and every label was fixed before anything was run.

**These 100 designs were written by hand, not by a language model.** No API is
reachable from where this was built. The set exists to prove the harness works
end to end in the format captured model output will use, and to show the metrics
respond to physics rather than to bookkeeping. Nothing below is a statement
about any model's failure rate, and section 5 says what else it is not.

The set:

| label | n | what it is |
|---|---|---|
| `physically_sound` | 28 | inside every limit, on a model that applies |
| `limit_exceeded` | 26 | past a rating, a category temperature or a working voltage |
| `model_inapplicable` | 18 | Biot, Fourier, radiation share, a declared span, a declared band |
| `unit_or_sign_error` | 10 | kΩ as Ω, mW as W, a flipped temperature coefficient |
| `inconsistent_inputs` | 10 | two lengths for one body; a coefficient 5× its own correlation |
| `insufficient_input` | 8 | a part, a rail and an ambient, and nothing else |

92 carry a full declaration; 8 are deliberately sparse.

## 2. The numbers

Scored under three conversion policies. `violation_scoped` and `whole_report`
agree exactly on this set, so one table serves; the difference is expected to
appear only when real, sparsely-declared designs arrive.

| | `stated_only` | `datasheet_completed` | `fully_declared` |
|---|---|---|---|
| unconvertible | 8 | 8 | 6 |
| scored | 92 | 92 | 94 |
| exact verdict match | 86/92 (93.5 %) | 86/92 (93.5 %) | 86/94 (91.5 %) |
| catch rate | 58/64 (90.6 %) | 58/64 (90.6 %) | 60/66 (90.9 %) |
| false accept | 6/64 (9.4 %) | 6/64 (9.4 %) | 6/66 (9.1 %) |
| false reject | 0/28 (0.0 %) | 0/28 (0.0 %) | 0/28 (0.0 %) |
| runs ending in an exception | 0 | 0 | 0 |

Per failure class, `fully_declared`:

| label | n | caught | accepted | exact | decided by an invented value |
|---|---|---|---|---|---|
| `physically_sound` | 28 | 0 | 28 | 28 | 0 |
| `limit_exceeded` | 26 | 20 | **6** | 20 | 0 |
| `model_inapplicable` | 18 | 18 | 0 | 18 | 0 |
| `unit_or_sign_error` | 10 | 10 | 0 | 10 | 0 |
| `inconsistent_inputs` | 10 | 10 | 0 | 10 | 0 |
| `insufficient_input` | 2 | 2 | 0 | **0** | **2** |

Three numbers in those tables carry most of the information, and none of them is
the catch rate.

* **All six false accepts are one thing** — `S049`–`S054`, the derating family.
  See section 4.
* **`stated_only` and `datasheet_completed` are identical.** They differ only on
  designs that do not state their own limits, and every hand-built case states
  its own. Real AI output will not, so the two columns will separate; here they
  measure the same thing twice, and reporting them as agreement would be
  reporting an artefact of how the cases were written.
* **Six of the eight sparse designs cannot be posed at all**, under any policy.
  The two that can are the two whose part publishes a thermal resistance
  (SFR25 at 200 K/W, SFR25H at 150 K/W); for the chip parts no datasheet in
  `components.json` publishes one, so no conductance exists to build a payload
  from. That is not the tool refusing anything — the tool never saw them.

## 3. What the tool caught that a reviewer would have missed

**One thing, and it needed a probe to isolate it.**

A design that takes a package θ<sub>JA</sub> off a datasheet and uses it as the
thermal path to ambient is making a model error: JESD51-3 states these values
compare packages and do not predict application performance, and two of the TI
datasheets in `components.json` print that warning in their own words. A reviewer
checking the arithmetic — 40 °C ambient, 41 mW, 220.8 °C/W, 9 K rise, well inside
every rating — finds nothing wrong, because arithmetically there is nothing
wrong. The number is fine. Its provenance is not.

`probe_jedec_theta_ja.py` runs that design three ways:

| what the design declares | verdict | violated |
|---|---|---|
| no fluid | INSUFFICIENT_EVIDENCE | — (three convection conditions unknown) |
| still air, k = 0.0263 W/(m·K) | **NOT_SUPPORTED** | `convection_conductance_agreement_ratio` |
| still air, and a 250 K/W board figure instead | **NOT_SUPPORTED** | `convection_conductance_agreement_ratio` |

With the fluid declared, the coefficient the design states is about **34×** what
Churchill–Chu gives for that body in that air, and the tool refuses it on that
one condition with nothing left unknown. It got there by asking a question a
reviewer does not think to ask — *where did your conductance come from, and does
it agree with the air you say surrounds the part?* — rather than by knowing
anything about JEDEC.

**Two things stop this being a clean win.**

First, the third row. The tool refuses a perfectly ordinary 250 K/W board figure
for the same reason, because on a real board most of the heat leaves through the
copper and no board figure will agree with a free-convection correlation over the
chip's own top face. The condition is not detecting "a JEDEC number"; it is
detecting a disagreement that is often legitimate. Whether that makes it useful
or noisy on real designs is not established here.

Second, the first row. **Undeclared, the misuse is invisible.** A design that
says nothing about the air gets INSUFFICIENT_EVIDENCE — honest, and no help at
all in identifying what was wrong. Real AI designs say nothing about the air.

## 4. What the tool missed that a reviewer caught

**Six cases out of 100, all the same miss, and it is the one that matters most
for the product claim.**

A rated dissipation is a pair. Vishay's CRCW0805 is 0.25 W **at 70 °C**, falling
along its derating curve to zero at the 155 °C permissible film temperature. At
a 120 °C ambient the same part is rated 0.103 W. The payload's `rated_power` is a
scalar and carries no ambient, so the check compares the dissipation against a
rating the part no longer has:

| case | part | dissipation | printed rating | derated to 120 °C | verdict |
|---|---|---|---|---|---|
| S049 | CRCW0805 | 0.204 W | 0.25 W at 70 °C | 0.103 W | SUPPORTED |
| S050 | CRCW1206 | 0.204 W | 0.25 W at 70 °C | 0.103 W | SUPPORTED |
| S051 | CRCW2010 | 0.611 W | 0.75 W at 70 °C | 0.309 W | SUPPORTED |
| S052 | CRCW1210 | 0.407 W | 0.5 W at 70 °C | 0.206 W | SUPPORTED |
| S053 | CRCW2512 | 0.815 W | 1.0 W at 70 °C | 0.412 W | SUPPORTED |
| S054 | SFR25 | 0.326 W | 0.4 W at 70 °C | 0.165 W | SUPPORTED |

Every one is roughly **twice** its real rating, every other condition is
satisfied, nothing is unknown, and the report is SUPPORTED with no caveat. A
reviewer with the datasheet open catches all six in seconds; that is what the
derating curve on page one is for.

The tool is not missing an arithmetic step. `derating_factor` exists and a caller
who supplies it gets the right answer. What is missing is the ability to
*derive* the derating — the ambient is already declared on the body and the knee
is a property of the part, and nothing connects them. So the check is only as
good as a caller who already knows the answer, which is the opposite of what the
tool is for. `FINDINGS.md` F1 has the full record; nothing was fixed here.

**A second miss, smaller and mine rather than the tool's.** The two sparse
designs that could be converted (`S095`, `S100`) were labelled
`insufficient_input` — a reviewer cannot judge them because nobody said how long
the load lasts or what the thermal mass is. Under `fully_declared` the conversion
invented a duration, a heat capacity, a geometry, an emissivity and two constant-
property spans, and the tool returned NOT_SUPPORTED on eight conditions.

Four of those eight — the two constant-property spans, the linearisation band and
the radiation share — were **decided entirely by values the converter made up**,
and the static dependency check in `run.py` names them per case. The other four
are better founded but not clean either: 24 V across 470 Ω is 1.23 W against
SFR25's 0.4 W rating, which the design fails whatever else is assumed, and the
three temperature flags follow from that power and the datasheet's own 200 K/W —
but only once an invented run length lets the body reach its steady state at all.

So a gap became a verdict. One of the eight reasons stands on the design's own
numbers; three stand on the datasheet plus one invention; four stand on
inventions alone. A benchmark that reported this as a catch would be counting
its own converter.

## 5. What this does not establish

* **Nothing about any model.** No design here came from a language model. Every
  number above describes a hand-built set and the harness that ran it.
* **Nothing about difficulty.** The seed cases sit far from their bounds by
  construction — `reference.py` refuses to label any case whose verdict depends
  on which reading of the operating temperature is taken. A 90.6 % catch rate on
  cases built to be unambiguous is not comparable to `benchmarks/hard/`'s 99.3 %
  on 1658 cases placed 0.2 % from their bounds, and the frozen set is the one to
  quote for whether the checks are precise.
* **Nothing about the checks' correctness, beyond a weak agreement.**
  `reference.py` and engcore agreed on every condition of all 92 fully-declared
  cases, in both directions. The same person wrote both, from the same cited
  sources, so that agreement is close to guaranteed and is evidence of very
  little. A genuine cross-check needs a second implementer.
* **Nothing measured on a bench.** Ground truth is datasheet numbers and hand
  calculations. No claim here is that engcore's verdict matches what a real part
  does at 120 °C.
* **One reviewer, no adjudication.** Every label is one person's judgement, and a
  systematic misreading of a whole class would show up as agreement, not as
  error.
* **The conversion is not neutral, and cannot be made neutral.** `convert.py`
  logs every value it supplies and refuses to invent a supply current rating, and
  `run.py` flags every verdict whose violated conditions were fed by an invented
  value. That makes the contamination *visible*; it does not remove it. On the
  two cases where it mattered, four of five reasons for refusal came from the
  converter.
* **The scoping has not been exercised.** `violation_scoped` and `whole_report`
  agree on every case here, because the full-declaration cases leave nothing
  unknown. The scope exists for designs that declare almost nothing, and those
  do not exist in this set yet.
* **Sound cases are only as sound as their declarations.** The 28 that reached
  SUPPORTED all declare a fluid whose conductivity was **solved for** so the
  correlation reproduces the stated coefficient. That is the same synthetic
  construction `benchmarks/hard/` documents for its own fluid, and it means those
  28 cases test internal consistency, not whether the coefficient is right for
  real air over a real chip. The false-reject rate of 0/28 is a statement about
  self-consistent declarations, not about real designs.
