# Findings about the tool, found here and not fixed here

This round was told to produce a benchmark, not a fix. Nothing under `src/` was
changed. What follows is what running 100 designs and three probes through
engcore surfaced, with the evidence for each and an honest note on how sure it
is.

---

## F1 — A rated power carries no ambient, so it cannot be derated. **Confirmed.**

**What.** `ratings.rated_power` is a scalar watt figure. Every resistor datasheet
in `components.json` states its rating as a *pair*: 0.4 W **at 70 °C**, falling
along a derating curve to zero at the permissible film temperature. The payload
has no field for the ambient a rating is stated at, so a part run above that
ambient is checked against a rating it no longer has.

**Evidence.** Cases `S049`–`S054`. Each is a real part in a 120 °C ambient with a
10 K rise, dissipating just under the printed rating and about **twice** the
rating derated to 120 °C:

| case | part | dissipation | printed rating | rating derated to 120 °C | verdict |
|---|---|---|---|---|---|
| S049 | CRCW0805 | 0.204 W | 0.25 W at 70 °C | 0.103 W | SUPPORTED |
| S050 | CRCW1206 | 0.204 W | 0.25 W at 70 °C | 0.103 W | SUPPORTED |
| S051 | CRCW2010 | 0.611 W | 0.75 W at 70 °C | 0.309 W | SUPPORTED |
| S052 | CRCW1210 | 0.407 W | 0.5 W at 70 °C | 0.206 W | SUPPORTED |
| S053 | CRCW2512 | 0.815 W | 1.0 W at 70 °C | 0.412 W | SUPPORTED |
| S054 | SFR25 | 0.326 W | 0.4 W at 70 °C | 0.165 W | SUPPORTED |

Derated rating is P70·(155 − 120)/(155 − 70) from each datasheet's own knee and
permissible film temperature. Every other condition in all six is satisfied,
nothing is unknown, and the report is SUPPORTED. These are the only six false
accepts in the whole seed set.

**Why it is not simply a missing check.** `derating_factor` exists, and a caller
who supplies it gets the right answer. So the tool *can* express the derated
rating — it just cannot **derive** it, even though the ambient temperature is
already declared on the body and the knee is a property of the part. The gap is
in the payload's vocabulary for a rating, not in any condition's arithmetic.

**Why it matters for the product claim.** The thing being measured is whether
the tool catches the physics errors an AI makes when it designs. "0.25 W part,
0.2 W load, fine" is close to the archetypal AI answer, and it is wrong in any
ambient above about 90 °C. A caller who does not already know about derating
will not supply `derating_factor`, and the tool will agree with them.

**Not fixed in the round that found it.** A fix touches
`src/engcore/domains/electrical/dc/models.py` and the boundary's ratings binding
— a rating has to become a pair. That is a domain change and the round that
found this produced a benchmark.

**FIXED, in the round after.** `rated_power_temperature` and
`zero_power_temperature` are now optional inputs on the resistor model and
payload fields in the `ratings` block. Declared together they turn
`dissipated_power_utilization` from a comparison against a constant into a
comparison against the derating line; declared apart, or without a
`rated_power`, or inverted, they are refused; declared without an ambient the
condition is UNKNOWN rather than answered from the printed number. Omitting
them changes nothing, which is asserted directly and confirmed by the frozen
benchmark being byte-identical.

All six cases above are now NOT_SUPPORTED on `dissipated_power_utilization`
alone. The `stated_only` policy still accepts them, correctly: those designs
never state a rating temperature, and the fix gave the tool the ability to be
told rather than the design the habit of saying. See `RESULTS.md` section 4.

---

## F2 — The convection agreement condition catches the JEDEC θJA misuse, but only when the fluid is declared. **Confirmed. This one is in the tool's favour.**

**What.** JESD51-3 says a package θ<sub>JA</sub> compares packages and does not
predict application performance; two of the datasheets in `components.json` print
that warning themselves. Using θ<sub>JA</sub> as a body's conductance to ambient
is therefore a model error, and it is the error a "choose a package" prompt
invites. The tool has no notion of JESD51 and claims none — but it does ask
where a conductance came from, and that turns out to be enough.

**Evidence.** `probe_jedec_theta_ja.py`, three variants of one dull design
(220 Ω on 3 V, 41 mW, 40 °C ambient, 9 K rise, everything far from every limit),
whose stated thermal path is the OPA333 DBV θ<sub>JA</sub> of 220.8 °C/W:

| variant | verdict | violated | unknown |
|---|---|---|---|
| fluid not declared | INSUFFICIENT_EVIDENCE | — | the 3 convection conditions |
| real air declared | **NOT_SUPPORTED** | `convection_conductance_agreement_ratio` | — |
| 250 K/W board figure, real air declared | **NOT_SUPPORTED** | `convection_conductance_agreement_ratio` | — |

With air's own conductivity declared, the coefficient the design states is about
34× what Churchill–Chu gives for that body in that air, and the tool says so on
one condition with nothing left unknown.

**The caveat that keeps this honest.** Variant 3 shows the tool is not detecting
"a JEDEC number". It is detecting that a declared coefficient and a declared
fluid disagree — and it refuses a plausible 250 K/W board figure for the same
reason, because that figure is equally unsupported by the geometry beside it. On
a chip on a real board most of the heat leaves through the copper, not through
the air over the top face, so *any* honest board figure will disagree with a
free-convection correlation over the chip's own surface. The condition is doing
something real and it is not doing what its name might suggest to a reader in a
hurry.

**Nothing to fix.** Recorded because it is the one place in this round where the
tool caught something a reviewer following the datasheet would not have caught,
and because the caveat needs to travel with the claim.

---

## F3 — A published resistor R<sub>th</sub> is not a surface film coefficient, and the lumped model treats it as one. **Observation, not proven here.**

**What.** `ambient_conductance` is divided by `surface_area` to form `h`, which
then feeds the Biot number and the convection agreement ratio. For a leaded
resistor, the R<sub>th</sub> a datasheet publishes (SFR25's 200 K/W, PR03's
60 K/W) is a body-to-ambient figure that includes conduction out through the
leads into the board. A large share of the heat therefore never crosses the
surface the area describes, and `hA/A_s` is not the film coefficient the two
conditions read it as.

**Why it is only an observation.** Neither condition was wrong on any case in
this set, and separating the lead path from the surface path needs a measurement
this benchmark does not have. The domain's own documentation already records
that geometry and orientation are not carried by any declaration and that it
cannot detect a caller using the wrong correlation; this is the same family of
limitation and may be the same entry. Recorded so it is not discovered twice.

---

## F4 — No defect was found in any condition's arithmetic

`reference.py` computes every condition independently, from the cited literature,
without importing engcore. Across the 92 seed cases that carry a full declaration
and run, **the two agreed on every condition, in both directions**: engcore
flagged nothing `reference.py` did not, and missed nothing `reference.py` found.

The two disagreements in the whole set (`S095`, `S100`) are not disagreements
about physics. They are cases where the design declared nothing and `convert.py`
invented the missing values, so engcore was assessing four conditions that
`reference.py` had no declaration to assess at all. Those are counted as
conversion artefacts in `RESULTS.md`, not as tool behaviour.

**This is weak evidence of correctness and should be read as such.** The seed
cases sit far from their bounds by construction, and the same person wrote both
the cases and the reference model. `benchmarks/hard/` is where the arithmetic is
actually stressed, at 0.2 % from every bound, and its numbers are the ones to
quote for that.

---

## Not found

* **No exceptions.** 278 runs (100 designs × 3 policies, less the 22
  unconvertible) and three probes produced no exception and no boundary rejection. Every payload
  `convert.py` built was accepted as a well-formed statement.
* **No false rejects.** All 28 sound designs reached SUPPORTED under all three
  policies. Nothing was refused that should have been accepted.
