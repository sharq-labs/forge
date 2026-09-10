# The blind scientific challenge

**Truth first. Freeze second. Forge third.**

A benchmark whose generator was tuned against the thing it measures is a
benchmark that measures its own tuning. `benchmarks/hard` says so about itself:
every figure in its round-by-round history is *"a full-set figure the generator
was tuned against"*, and its 600-case hold-out — the one part that was not — is
now **opened and contaminated** and cannot be used again.

This directory is the replacement. 444 cases whose truth was established by
independent oracles, sealed by digest, and committed **before Forge was run
against them even once**.

## Reproduce it

```bash
python benchmarks/blind/freeze.py            # regenerate cases + truth, re-seal
python -m pytest tests/test_blind_challenge_guards.py -q
```

The second command is the one that matters. It walks the import graph of
everything that built the truth and fails if any of it can reach `engcore`, and
it recomputes every digest in `FREEZE.json` against the bytes on disk.

## The order of operations, and why it is the whole point

```
NEW CASE  ->  INDEPENDENT ORACLE  ->  FROZEN TRUTH  ->  SEALED DIGEST
          ->  FORGE RUN  ->  COMPARISON
```

never

```
NEW CASE  ->  FORGE  ->  ADJUST TRUTH  ->  PASS
```

The firewall is a commit. `FREEZE.json` carries the digest of the case set, the
truth, the manifest, the disagreement log, the oracle register, the bound
register and every source file that produced them; the commit that lands it is
`PRE_FORGE_FREEZE_SHA`. Anything dated after it that changes a case or a truth
byte shows up as a digest that no longer matches, and the guard suite goes red.

## Files

| File | What |
|---|---|
| `BLIND_CHALLENGE_SPEC.json` | The contract the round was run under. Written before any case existed; carries no Forge result. |
| `families.py` | The plan: per-domain counts, the strata each family targets, the position ladder. Frozen before generation (Phase 1C). |
| `generate.py` | Writes payloads. States no verdict, no reason, no catcher. |
| `build_truth.py` | Decides truth, from the oracle layer only. |
| `bound_registry.py` | What KIND of statement each bound is — definitional, positivity, sourced, or policy. Transcribed from `docs/assurance/SCIENTIFIC_BOUND_REGISTER.md`. |
| `oracles/` | The independent implementations. Nothing here imports `engcore`. |
| `freeze.py` | Quality guards, then emit, then seal. |
| `v1/cases/*.json` | 444 payloads. No ground truth in them. |
| `v1/TRUTH.json` | The frozen truth, one record per case. |
| `v1/MANIFEST.json` | Composition, distribution contrast, oracle register, rejections. |
| `v1/ORACLE_DISAGREEMENTS.json` | Every pre-freeze disagreement between two independent oracles, with its resolution. |
| `v1/FREEZE.json` | The digests. |

## Generation independence, and what it does not cover

Nothing that generates a case or decides its truth may import, call or name any
`engcore` surface. Four separate audits enforce it: an AST import audit, a
name-and-string reference audit, a transitive import-graph walk, and a runtime
`sys.modules` check after importing the whole truth layer. A fifth test
*falsifies* the audit — it writes a module that does peek and asserts the audit
catches it — because an audit that has only ever run against clean code is
indistinguishable from one that passes everything.

**What is deliberately shared: the contract.** The oracle takes from the model
records what each condition means and which state coordinate it is read at. A
second implementer given a spec implements the spec; an oracle that *guessed*
which temperature `melting_temperature_utilization` is read at would be testing
whether two authors guessed alike. The arithmetic is what is independent, and
the arithmetic is where a defect lives.

**This is a real limit on blindness and it is not claimed away.** Each oracle's
contract reading was checked against the runtime on the *already-open*
development corpus before any blind case existed:

| oracle | agreement, measured before any blind case existed |
|---|---|
| electro-thermal | 1399/1400 verdicts, 1392/1399 violated-sets, 1400/1400 unknown-sets on the open dev split |
| battery | 400/400 verdicts, violated-sets and unknown-sets on `cases_battery` |
| kinetics | 400/400 on throwaway draws (379 assessed + 21 construction refusals), 0 mismatches |
| conduction | 400/400 on the same throwaway draws |

So this challenge tests **arithmetic and generalisation to unseen parameter
regimes**. It does **not** test the contract reading itself, and no figure from
it should be read as if it did.

## Where the numbers come from

**The resolution floor.** Two independent implementations of the same fixed
point agree on the final temperature to 3.77e-16 relative and on the steady
state to 2.05e-09 — the latter set by the caller-declared coupling tolerance,
not by either implementation. Measured over the 1400 open development cases.
The challenge's floor is 1e-3, five orders above the worse of those.

A case closer than that to its bound is tagged `ARITHMETIC_SENSITIVE` and
**leaves the primary denominator**, because at that distance the answer is
decided by which implementation rounds which way. This is not hypothetical:
`U00611` in the existing corpus computes `working_voltage_utilization` at
`1 + 1.2e-10`, and the oracle and the runtime disagree about it.

**Soft bounds get no exact-boundary truth.** `Bi <= 0.1` and `Fo >= 0.2` are
approximation criteria, not transitions — nothing changes in the world at the
number. A case beside one is tagged `SOFT_BOUND_NEAR` rather than being given a
boundary it does not have.

**Policy is not science.** `radiation_to_convection_ratio <= 0.1` is a
10 %-neglect allowance with no located source. Agreement on it says the runtime
implements a convention correctly and says nothing about physics. Cases decided
by a policy bound carry `truth_class: POLICY_DEPENDENT` and are scored in their
own denominator.

## What this challenge does NOT test

* **Refusal-path reporting.** A thermal-runaway design has a decidable
  *verdict*, but the condition set a refused coupling reports is a property of
  the iteration driver's bookkeeping rather than of the science. An independent
  oracle cannot state it without copying the driver, and an oracle that copies
  the driver is not an oracle. Non-converging designs are rejected pre-freeze
  under `oracle_non_convergence` and counted.
* **The contract reading**, per the calibration note above.
* **Any bound against experiment.** Every threshold here is a definition, a
  derivation, a citation or a policy. Nothing in this repository has been
  checked against a measurement.

## The result

**`docs/assurance/BLIND_CHALLENGE_V1_RESULT.md` is the full account.** In short:

| | decided denominator | false accepts |
|---|---|---|
| **first run — frozen, never revised** | **272 / 400 (68.0 %)** | 1, and it was the harness |
| post-fix, two proven runtime defects repaired | 336 / 400 (84.0 %) | 0 |

Across 444 cases whose truth was fixed before Forge saw them, **Forge accepted
nothing the independent truth refuses**. Two model-contract tiers scored 100 %.

It found two runtime defects, the second reachable only once the first was
fixed: a declaration could not state a temperature in degrees Celsius, and a
ratio of two declarations was computed on an interval scale, so the answer
depended on which unit the caller wrote. Neither was reachable from the
existing 2400-case corpus, in which every temperature is written in kelvin.

It also got two things wrong itself — 73 cases spelled `kilohm` where the
registry defines `kiloohm`, and 3 declared a limit the constructor refuses.
Forge is right about all of them. They are recorded in `v1/TRUTH_ERRATA.json`
and **the frozen truth was not edited**, which is why the 68.0 % stands rather
than improving.

## After Forge has run

`benchmarks/blind/v1` is closed. The first run is the result — preserved
especially if it is bad — and a re-run after a fix goes in a `POST_FIX`
artifact that never replaces it. A truth proven wrong afterwards is recorded as
a `TRUTH_ERRATUM` naming the case, the old frozen truth and the new evidence;
it is never edited in place. **A change to a frozen challenge is a new
challenge version**, and the next genuinely blind round needs a `v2` whose
cases this one has never seen.
