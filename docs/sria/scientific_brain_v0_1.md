# SRIA Scientific Brain — V0.1 invariants

Frozen record of the reasoning invariants SRIA must satisfy. This document is
normative for design review; it is **not** a description of what is currently
implemented. Where an invariant is recorded but unimplemented, that is stated.

Base: M5.1 freeze `793e8dbcafea0831ae3974c1a63c7593fc5c4a8b`.

---

## 1. Terminal decision first

Scientific information value is undefined in the abstract. It exists only
relative to a declared **terminal decision**, a **loss/utility** over that
decision, a **quantity of interest**, and a **required tolerance**. A number
called "value of information" computed without all four is a preference wearing
a decision-theoretic costume.

## 2. Posterior is derived state

No solver, LLM, Domain Pack, Critic, Arbiter or other source may write
posterior belief directly. The posterior is always the output of

```
Posterior = Inference(
    active eligible observations,
    model-specific interpretations,
    model space,
    priors,
    likelihoods,
    discrepancy specification,
    inference configuration
)
```

Anything that wants to change belief changes an *input* to that function, in
the open, where it can be re-run.

## 3. Observation != interpretation != likelihood

```
Execution Record -> Observation -> Model-specific Interpretation
                 -> Likelihood  -> Posterior
```

These are four distinct objects. Collapsing them is how a solver's opinion of
its own output becomes a scientific fact. **M1 contracts are not refactored to
express this during the falsification phase** — the separation is recorded here
and honoured by construction in isolated experiments.

## 4. Prediction before observation

A belief-changing scientific action must carry a declared observation /
predictive model *before* its result is seen. A likelihood chosen after looking
at the data is not a likelihood.

## 5. Verification != model adequacy

A numerically correct execution proves the code solved the equations it was
given. It says nothing about whether those equations describe the world. The
Numerical Critic and the Domain Critic answer different questions and neither
substitutes for the other.

## 6. Conflict must remain visible

The evidence ledger never silently reconciles conflicting observations. Model
checking must be *able* to detect conflict; averaging it away is forbidden.

## 7. No fake statistics

No critic score, LLM confidence, governance verdict or otherwise-arbitrary
number may influence posterior belief without a declared, scientifically
defensible statistical relationship. A number is not a likelihood because it
lies in [0, 1].

## 8. NOT_ASSESSED means zero belief update

An unassessed result changes nothing. Absence of assessment is not weak
evidence.

## 9. Computational failure != physical evidence

A failed run updates executability and cost models by default. It may affect
physical inference **only** through an explicitly declared mechanism (e.g. a
declared censoring model). Silent leakage from infrastructure failure into
physical belief is prohibited.

## 10. Evidence dependency / closure

Derived artifacts must eventually be able to identify which source observations
influenced them, so double counting is detectable. **Recorded only — the
closure system is not implemented in this phase.**

## 11. Identifiability matters

The system must distinguish *"more observations are needed"* from *"this
observation type cannot identify the scientific question at all"*. **Recorded
only — no generic identifiability framework in this phase.** The falsification
benchmark exercises one concrete instance: a decision-irrelevant observation
must yield EVSI ≈ 0.

## 12. Model inadequacy must be representable

The system must be able to say *"the current model space is not adequate to
support this conclusion"*, as a first-class outcome rather than an exception.

## 13. Unsupported transport cannot certify stop

**The rule this phase exists to test.**

> Low EVSI is **not** sufficient to certify stopping when the terminal decision
> relies materially on unsupported extrapolation / transport beyond the
> empirically or scientifically justified support region.

Posterior confidence and scientific support are different quantities. A
posterior can be arbitrarily sharp about a region where no observation has ever
constrained the model, because sharpness is a property of the model's *form*,
not of the evidence's *reach*. EVSI inherits that sharpness and collapses to
zero — so a decision-theoretically impeccable agent concludes that no further
experiment is worth buying, precisely where it knows least.

Certifying a stop therefore requires **both**:

1. a decision-theoretic condition (no affordable action has positive net value), **and**
2. a support condition (the terminal decision condition lies within the
   justified support region, or is covered by an explicitly declared and
   recorded transport justification).

Failing (2) yields `STOP_NOT_CERTIFIABLE` with reason `UNSUPPORTED_TRANSPORT`.
This is not a claim that extrapolation is always wrong — it is a claim that
extrapolation must be *declared and owned*, not inferred from a tight posterior.

The support region is **domain-declared**, not derived from a universal
geometric theorem. For a 1-D benchmark a declared interval with a margin is
sufficient and is documented at the point of use.

## 14. LLM optionality

With every LLM disabled, scientific reasoning must operate correctly and
completely. LLMs may later assist with paper parsing, natural-language
interfaces and explanation. They are never in the numerical truth path.

---

## Scope of the falsification phase

Implemented, in an isolated harness outside the SRIA core:

* a finite frozen parameter grid, explicit prior, explicit likelihood, exact
  normalized Bayesian reweighting (invariant 2, in miniature);
* a predictive distribution and a genuine one-step EVSI computed from it
  (invariants 1 and 4);
* the support/transport rule and the two stopping policies (invariant 13);
* a decision-irrelevant observation as a concrete identifiability probe
  (invariant 11).

Not implemented, deliberately: generic inference engine, posterior database, GP
discrepancy, SMC/MCMC, continuous-action optimization, evidence closure,
identifiability framework, Domain Pack changes, any modification to M1–M5.1.
