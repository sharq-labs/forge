# Labelling a design

One design, one label, one sentence. The label is a judgement about **the design
as stated**, not about the model that wrote it and not about what a tool says.

## The rule that makes this worth doing

**Never open the tool's output before labelling.** If you have already seen what
engcore said about a design, you cannot label it independently, and a benchmark
labelled that way measures agreement with the tool rather than the tool's
accuracy. Label first, run second, compare third. `run.py` will not read a
design file that has no label, and the results file keeps the label and the
verdict in separate fields for the same reason.

Ground truth comes from three places, in this order:

1. **The datasheet.** A rating is exceeded or it is not. `components.json` has
   the number and the document it came from.
2. **A hand calculation** you can write on one line: P = V²/R, ΔT = P·R<sub>th</sub>,
   T = T<sub>amb</sub> + ΔT.
3. **`reference.py`**, for the coupled cases where R depends on T and the fixed
   point has to be solved. It computes the physics from the cited literature and
   never imports engcore.

Record which one in `label.ground_truth_basis`.

## The six labels

### `physically_sound`

The design does what it claims, within every limit its own parts declare, using
a model that applies at the operating point it reaches.

Sound does **not** mean conservative, and it does not mean the reviewer would
have designed it that way. A part at 92 % of its rating is sound. A body at
900 K that is 200 K below its melting point is sound. Reserve the failure labels
for designs that are *wrong*, not for designs that are tight.

### `model_inapplicable`

The arithmetic is right and the model behind it does not apply here.

The commonest instance in this benchmark, by a distance: **using a JEDEC
θ<sub>JA</sub> to predict a junction temperature in an application.** JESD51-3
says in as many words that these values compare packages and do not predict
application performance, and the TI datasheets that print the caveat say
"cannot be used for design purposes". A design that computes
T<sub>J</sub> = T<sub>A</sub> + θ<sub>JA</sub>·P on a board that is not the test
board has used a number outside what it was measured to mean. Label it here even
when the resulting temperature happens to be right.

Others: a single-body temperature asserted for a body whose internal gradient is
not small; a first-order response quoted over a horizon shorter than the body's
own diffusion time; neglecting radiation where it carries a tenth of the heat or
more; a linear temperature coefficient used far outside the span the material
declares it over.

### `limit_exceeded`

The model applies, the numbers are right, and the answer is past a declared
limit — a rated dissipation, a maximum working voltage, a category temperature,
a junction limit, a melting point.

The limit must be one that is **declared**, by the datasheet or by the design
itself. A reviewer's private sense that 130 °C is too hot is not a limit.

### `unit_or_sign_error`

A number is in the wrong units, off by a factor, or has the wrong sign.

The interesting ones are not decade slips. They are factors of two and three: a
diameter used where a radius belonged, mW read as W, an area counted once when
the body has two faces, a negative temperature coefficient entered positive,
°C added to a value already in kelvin. If the mistake would survive a glance,
it belongs here.

### `inconsistent_inputs`

Two things the design states cannot both be true.

A characteristic length and a volume-over-area that describe different bodies;
a declared thermal resistance that does not agree with the geometry and fluid
also declared; a stated dissipation that is not V²/R for the stated V and R; a
part number whose datasheet contradicts a rating the design quotes for it.

### `insufficient_input`

The design cannot be judged without a value nobody supplied, and the design did
not supply it either.

This is the right label when a design gives a confident answer built on a number
it never stated and never derived — the ambient it did not ask for, the airflow
it assumed, the board it imagined. It is **not** the right label when the
designer explicitly stated the assumption; that design is judgeable, on the
assumption it named, and gets one of the other five labels.

## Precedence, when more than one applies

Leading label first, the rest in `secondary_findings`:

1. `unit_or_sign_error` and `inconsistent_inputs` — a wrong number or a
   contradiction poisons everything downstream, so they lead.
2. `model_inapplicable` — a limit read off a model that does not apply is not a
   meaningful reading, so applicability outranks the limit.
3. `limit_exceeded`.
4. `insufficient_input` — last, because it only leads when nothing else can be
   determined at all.

## The sentence

One sentence, and it must name the number that decides it.

Good:

> Computes T_J = 40 + 220.8 x 5 = 1144 C from a JEDEC theta-JA, which JESD51-3
> excludes from application prediction; 5 W in a SOT-23 is not a design either way.

> P = 24^2/33 = 17.5 W against a 0.25 W rating; the voltage check the reviewer
> relied on is not the binding one.

> States 0.4 W dissipation for 20 V across 47 ohms, which is 8.5 W.

Bad:

> Seems too hot.

> The model did not consider thermal effects properly.

## Filling in the record

* `label.verdict` — one of the six.
* `label.reason` — the sentence.
* `label.labeller` — who decided.
* `label.confidence` — `low` is a real answer and is better than a guess at
  `high`. Low-confidence labels are reported separately in `RESULTS.md`.
* `label.ground_truth_basis` — datasheet field, hand calculation, or
  `reference.py`.
* `expected_verdict` — what a correct tool should say. The mapping `run.py`
  applies:

| label | expected verdict |
|---|---|
| `physically_sound` | `SUPPORTED` |
| `model_inapplicable` | `NOT_SUPPORTED` |
| `limit_exceeded` | `NOT_SUPPORTED` |
| `unit_or_sign_error` | `NOT_SUPPORTED` |
| `inconsistent_inputs` | `NOT_SUPPORTED` |
| `insufficient_input` | `INSUFFICIENT_EVIDENCE` |

**The mapping is a claim, not a definition, and it is the weakest link in the
scoring.** A design labelled `unit_or_sign_error` is wrong, but nothing
guarantees the tool refuses it for *that* reason rather than for an unrelated
missing declaration. `RESULTS.md` reports the per-class breakdown separately from
the headline so a class that is only ever "caught" by an unrelated gap is
visible as such.
