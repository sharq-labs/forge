# Independent scientific oracles

**Everything in this directory answers one question: is Forge right about the
world, as opposed to consistent with itself?**

That is not the question the rest of `tests/` asks. A regression test asserts
that today's answer equals yesterday's, which is valuable and cannot fail for
the reason that matters most — the formula being wrong from the start. An
oracle test asserts that Forge's answer equals an answer obtained **without
Forge**.

## The rule every file here obeys

> An oracle must not import, call, or copy the Forge function it checks.

It may import Forge to obtain the value **under test**. It may not obtain the
**expected** value from Forge, from the benchmark generator, or from a constant
that was read off either. Where the expected value comes from is recorded on
every test as an `ORACLE_ID`, and `ORACLE_REGISTER` in `oracle_ids.py` says what
class of thing that is and how independent it actually is.

## What "independent" means here, precisely

| class | meaning |
|---|---|
| `INDEPENDENT_EXECUTABLE` | a different program, written by different people, run as a subprocess |
| `INDEPENDENT_ANALYTIC` | a derivation this suite performs from first principles, sharing no code path with Forge |
| `INDEPENDENT_REFERENCE_DATA` | two published sources that must agree with each other |
| `LITERATURE_REFERENCE` | a published equation, transcribed here from the citation rather than from Forge |
| `INTERNAL_DERIVATION` | honest label for a check that shares a governing equation with the thing it checks |

The last one is **not** independent verification and is labelled so a reader
cannot mistake it for one.

## What this suite does not do

It does not establish that Forge's *applicability bounds* are the
scientifically correct bounds. A bound is a policy choice about where a model
may be trusted; an oracle can verify the arithmetic that evaluates it and the
literature that motivates it, and cannot verify the choice.
`docs/assurance/UNSOURCED_BOUNDS.md` tracks that separately.

## Running it

```bash
.venv/Scripts/python.exe -m pytest tests/oracles -q
```

Tests that need an external program are skipped, never failed, when it is
absent — and the skip says so, because a silent skip would let coverage rot.
