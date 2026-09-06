# AI-design benchmark — real components, real designs, one reviewer

## What this measures

Whether engcore catches the physics errors that appear in **thermal designs
someone else wrote**, when those designs are converted into payloads and run.

That is a different question from the one `benchmarks/hard/` answers. The frozen
2000-case set measures whether the *checks work*, on payloads built to sit
0.2 % from every bound. This set measures whether the checks *reach* the errors
that actually occur, on designs that were never written as payloads and that
leave most of the declaration unsaid.

## What this does not measure

**No design in this repository came from a language model.** No API can be
called from where this was built, so the 100 cases in `designs/seed/` are
hand-written by the benchmark author in the same format that captured model
output will use. They prove the harness runs end to end and that the metrics
move when the physics does. **Every number computed from them is a statement
about the harness, not about any model's failure rate.** `RESULTS.md` says the
same thing in the place where the numbers are.

Beyond that:

* **One reviewer.** Every label is one person's. There is no second opinion and
  no adjudication, so a systematic misreading of a class would not show up.
* **No laboratory measurement.** Ground truth is datasheet numbers and hand
  calculations. Nothing here was measured on a bench, and nothing establishes
  that engcore's verdict matches what a real part does.
* **One model family, when there is one.** When designs are captured, they will
  come from whatever model produced them, and a failure rate measured on one
  family is a fact about that family.
* **Conversion is a source of error and is not eliminated.** See below.

## Run it

    python benchmarks/ai_designs/generate_prompts.py
    python benchmarks/ai_designs/make_seed_designs.py
    python benchmarks/ai_designs/run.py --src src
    python benchmarks/ai_designs/probe_jedec_theta_ja.py --src src

`run.py` writes `results_ai_designs.json`. It reads only labelled designs and
counts the rest.

## Files

| File | What |
|---|---|
| `components.json` | 35 resistors and 23 package thermal resistances, every number with its datasheet. |
| `components.md` | What each field means, how the numbers were obtained, what JEDEC's caveat implies. |
| `generate_prompts.py` → `prompts.json`, `prompts.md` | 20 design prompts. Writes files; calls no API. |
| `design_schema.json` | The shape of a captured design: what was stated, why, and one human label. |
| `label_template.md` | What a reviewer decides, the six classes, the precedence, and the rule about labelling before running. |
| `reference.py` | The independent physics. Ground truth. Never imports engcore. |
| `make_seed_designs.py` → `designs/seed/*.json` | The 100 hand-built cases, each re-checked by `reference.py` before it is kept. |
| `convert.py` | Design → payload, under three policies, logging every value it had to supply. |
| `run.py` → `results_ai_designs.json` | The runner and the scorer. |
| `probe_jedec_theta_ja.py` | Three variants of one design, isolating what the tool does with a JEDEC θ<sub>JA</sub>. |
| `RESULTS.md` | The numbers, and where the tool is blind. |
| `FINDINGS.md` | Tool behaviour found here and deliberately not fixed here. |

## How ground truth is decided

By the datasheet, by a hand calculation, or by `reference.py` — which restates
the applicability conditions from Incropera et al. and Churchill & Chu and
solves the electro-thermal fixed point itself. **Never by asking engcore.** A
benchmark whose labels come from the tool under test measures agreement with the
tool, and `label_template.md` makes the rule explicit: label first, run second,
compare third.

`reference.py` also refuses to label a case whose verdict depends on which of
two readings of "the operating temperature" is taken — the end-of-interval
temperature the coupling transports, or the steady temperature the conditions
are formed from. A case that close to a bound is not one this benchmark is
willing to have an opinion about.

## Conversion, and why it is reported three ways

A design is prose with numbers in it. A payload is a complete declaration. What
fills the gap is a claim nobody made, so `convert.py` runs three policies and
`run.py` reports all three:

* **`stated_only`** — only what the design said.
* **`datasheet_completed`** — plus what the named part's datasheet gives. The
  design named the part, so the datasheet is the design's own referent.
* **`fully_declared`** — plus a fixed, documented set of invented declarations
  for the body and the fluid. The only policy under which SUPPORTED is reachable
  for a sparse design, and the only one whose numbers have the same shape as the
  frozen benchmark's.

Every supplied value is logged with its class (`stated`, `arithmetic`,
`datasheet`, `literature`, `invented`) and its justification. A design that
cannot be posed without inventing a *required* value is not forced through: it
is its own outcome, **`unconvertible`**, excluded from the rates and counted.

One invention is refused in every policy: the supply's own current limit. Every
other invented value is a property of a body that some datasheet could in
principle publish; a rail's current rating is a choice the design made, and a
made-up one would decide a condition on nothing at all.

## Two scopes, and why

`whole_report` is engcore's verdict for the report as a whole — directly
comparable with `benchmarks/hard/score_hard.py`.

`violation_scoped` collapses a report to NOT_SUPPORTED if any model reports a
violation, SUPPORTED if every model is in domain, INSUFFICIENT_EVIDENCE
otherwise. It exists for the reason `score_hard.py` scopes its battery cases: a
design that never declares an emissivity leaves that condition UNKNOWN, and a
whole-report score over such designs measures one gap N times. On the seed set
the two scopes agree exactly, because the full-declaration cases leave nothing
unknown. They will diverge the moment real designs arrive, which is why both are
computed now rather than added later.
