# The verification and validation (V&V) layer

> **A credibility evidence report is advisory input to an engineer of record.
> It is not a decision, not a certification, and not a claim of conformance
> with any standard.**

`engcore.mcp` is a consumer of `engcore.scientific` and never a modifier of
it. It computes no physics, evaluates no validity condition and re-runs no
check. Every scientific judgement it carries was made upstream — by a model's
validity domain, or by a solver's validation — and is *transported* here. The
only thing this layer decides is how to combine judgements already made, and
it does so in one pure function a reader can check in full.

## What it produces

A `CredibilityEvidenceReport` puts in one record the three facts the platform
otherwise keeps deliberately apart:

| Fact | Carried as |
|---|---|
| Was the model applicable? | `ValidityAssessment` — carried, never recomputed |
| Did the checks pass? | `ValidationReport` — **including what did not run** |
| What produced it? | `ProvenanceRecord` — carried unaltered |

plus the caller's own **caller-asserted context, not evidence**, in a field
that cannot be mistaken for any of the three, and a single advisory
`CredibilityVerdict` derived from the lot.

The verdict is a read-only property over `derive_verdict`, not a constructor
parameter. There is no stored copy to drift out of step with the contents, and
a payload whose stored verdict disagrees with what its contents produce is
refused on the way back in.

## What "credibility" means here

The word is used in the sense the V&V literature gives it:

- **ASME V&V 10** — verification and validation in computational solid
  mechanics.
- **ASME V&V 20** — verification and validation in computational fluid
  dynamics and heat transfer.
- **ASME V&V 40** — assessing credibility of computational modelling through
  verification and validation.
- **NASA-STD-7009** — models and simulations.

In all of them, credibility is a property of *the evidence supporting a result
in a stated context of use* — not a property of the model, and not a measure
of accuracy. That is what this record reports.

### The attained levels are an evidentiary scale

`ValidationLevel` says what a passing check **established**:

| Level | What a check claiming it has shown |
|---|---|
| `DIMENSIONALLY_VALID` | the reported quantities carry the dimensions the model declared |
| `NUMERICALLY_CONVERGED` | the discrete problem was solved to a declared tolerance |
| `ANALYTICALLY_VERIFIED` | agreement with a closed-form solution of the same equations |
| `BENCHMARK_VALIDATED` | agreement with an accepted reference case |
| `CROSS_SOLVER_VALIDATED` | agreement with an independent implementation |
| `EXPERIMENTALLY_VALIDATED` | agreement with measurement |

Loosely, the first three or four sit on the **verification** side of the
V&V 10/20 distinction — *did we solve the equations right* — and the last two
on the **validation** side — *did we solve the right equations, against the
world*. That correspondence is stated loosely on purpose. It is not a mapping
any of these standards defines, the boundary between the two sides is
genuinely arguable for `BENCHMARK_VALIDATED` and `CROSS_SOLVER_VALIDATED`, and
the levels are attained *independently* rather than climbed in order — so they
do not form a single ordinal grade the way a credibility assessment scale's
factors are each scored.

### `INSUFFICIENT_EVIDENCE` and NASA-STD-7009 level 0

`INSUFFICIENT_EVIDENCE` is the same idea as the bottom of NASA-STD-7009's
credibility assessment scale, **level 0, "insufficient evidence"**: nothing
here answers the question, and the fix is to go and produce the evidence
rather than to argue about the result.

It is not a formal score against that scale. NASA-STD-7009 assesses eight
factors separately and scores each; this layer applies the same distinction
once, to one report. The correspondence is in meaning, not in method.

A report is `INSUFFICIENT_EVIDENCE` when a model's validity is `UNKNOWN`, when
a check did not run, when a model that took part was never assessed, when a
level the caller declared it needs was not attained, when there are no
validity records — **or when no check both passed and established a level.**
That last rule is why a run can be clean in every other respect and still
report a gap: a passing check that establishes nothing has only failed to
object, and absence of an objection is not evidence. It is the same reason
`NOT_RUN` is a distinct outcome from `PASS`, applied one level up.

### `required_levels` is where a study states its own bar

Declaring `required_levels` is the move ASME V&V 40 makes when it sets the
required rigour from the model risk in a stated context of use. This layer
does **not** compute model risk and does not know the context of use. It
records the bar the caller declared and reports whether it was met.

## What is not claimed

- **No conformance.** This project is not certified, has not been assessed
  against ASME V&V 10, V&V 20, V&V 40 or NASA-STD-7009, and no standards body
  endorses it.
- **No endorsement.** Citing a standard is describing where the vocabulary
  comes from, not claiming the standard approves of this tool.
- **No decision.** A `SUPPORTED` verdict says nothing in the record argues
  against relying on the result. It does not say the result is right, and it
  does not discharge anyone's professional judgement or responsibility.

These standards are frameworks for **structured human judgement**. What this
layer does is execute a small, explicit part of that judgement as code, so the
part that *can* be mechanical is not left to a reader's memory. Everything
they ask of a person — deciding the context of use, weighing the risk,
accepting the result — is still asked of a person.

## The three verdicts

Three values and no more. A richer scale invites a reader to act on the grade
instead of the evidence.

| Verdict | What it means | What to do |
|---|---|---|
| `SUPPORTED` | Nothing in this report argues against relying on the result, and at least one evidentiary level was attained. | Read the checks and the conditions; decide. |
| `INSUFFICIENT_EVIDENCE` | Something needed to answer the question was never produced. | Produce it: declare the missing input, run the missing check. |
| `NOT_SUPPORTED` | Something that *was* produced argues against the result — a bound known violated, or a check that ran and failed. | Change the design or the model. More evidence will not help. |

**Precedence: `NOT_SUPPORTED` outranks `INSUFFICIENT_EVIDENCE`.** A finding
outranks a gap, because the two recommend opposite actions — and because the
alternative would let a caller bury a violated bound by omitting an unrelated
input.

**`WARNING` is not a failure and does not change the verdict.** A check that
warned produced its evidence. It stays visible in `warning_checks` for the
reader who must weigh it.

## Naming

The record was called `EvidencePackage` and the verdict `EvidenceVerdict`
before this layer adopted the V&V vocabulary. Both old names remain importable
as deprecated aliases **for one release**; new code should use
`CredibilityEvidenceReport` and `CredibilityVerdict`.

The serialized schema string is unchanged — `mcp_evidence_package/1`. It is a
wire identifier, not vocabulary: renaming it would reject every record written
before the rename while claiming to be one. Changing the wire form is a
version bump plus a reader that accepts both, and that has not been argued
for.
