# Hold-out status: OPENED, and not acquisition-grade blind

**visibility_status: `OPENED`**

This document exists so that nobody has to reconstruct the answer from a log
and three digests. The sealed partition of `cases_hard` has been read, the
figure on record describes a case set that no longer exists, and no reshuffle
of these 2000 cases can restore blindness.

---

## What the seal is, and what it was for

`split_hard.json` assigns 600 of 2000 `cases_hard` cases to a hold-out under
rule `stratified-hash-hamilton/1`, seed 20260906. `score_hard.py` refuses
`--split holdout` and `--split all` without `--open-holdout`, and an opening
appends a dated line to `HOLDOUT_OPENINGS.log`.

The seal exists because the generator behind `cases_hard` has been corrected
several times in response to what scoring it revealed, so **every development
figure is a figure the generator was tuned against**. The hold-out was the one
number that was not.

## What has actually happened to it

| when | how | case-set digest then | recorded |
|---|---|---|---|
| 2026-09-08 | deliberate `--open-holdout`, scored 600 cases: 579/600 (96.5%), FA 1/499 | `e14542c1…` | yes, by the scorer |
| 2026-09-09 | **incidental** — an ad-hoc analysis script globbed `cases_hard/*.json` and ran all 2000 cases, executing the 600 sealed ones | `2f0a48db…` | yes, appended by hand during this round |

The second entry is the one worth dwelling on. `score_hard.py` guards the seal;
**nothing guards the case directory.** Any script that reads the files directly
bypasses the refusal, the `--open-holdout` flag and the log at once, and leaves
no trace the seal can see. That is a structural hole in the mechanism, not a
lapse in one script.

## Why the recorded figure no longer describes anything on disk

The case set has moved three times since the deliberate opening:

```
e14542c1…  the opening on 2026-09-08 was scored here
2f0a48db…  after the internal-fourier-number adjudication (23 verdicts)
585eff4b…  after the U00204 adjudication
e0ae5086…  after the U01001 adjudication  <- current
```

So `579/600 (96.5%)` is a true statement about a case set that has since been
edited four times, taken on a working tree that gave dev `1342/1400 (95.9%)`.
It is history, not a current measurement, and it must not be quoted as one.

## Why re-splitting cannot fix this

Re-drawing a hold-out from the same 2000 cases produces a partition whose cases
have all been seen — by the deliberate opening, by the incidental sweep, or by
being in the development set all along. Blindness is a property of *exposure*,
not of *assignment*, and a reshuffle changes only the assignment.

`split_hard.py` says the same thing in its own words under **REGENERATING AN
EXISTING SPLIT OPENS THE HOLD-OUT**: regenerating an unchanged set moves cases
from hold-out into dev, where the next `--split dev` run scores them with no
flag and no log line.

**A new subset of these cases must never be described as blind.**

## What an acquisition-grade blind hold-out would require

One of:

* **new cases**, generated after the generator is frozen, from a seed and a
  generator version recorded before anyone runs them;
* **third-party cases**, produced outside this repository;
* **a frozen partition created before development access**, with the freeze
  recorded and the cases physically unavailable to the development loop.

And a mechanism stronger than a flag on one script — the current seal is
defeated by `pathlib.Path.glob`.

## What this round did and did not do

* Did **not** re-split, re-shuffle, or regenerate anything.
* Did **not** use any hold-out case to justify either adjudication. Both
  `U00204` and `U01001` are development cases, and the family audits behind
  them were restricted to the development split.
* Did edit two case files, which changes the case-set digest for all 2000 —
  including the sealed ones. Their *truth* is untouched; only the digest that
  covers the directory moved, and `split_hard.json`'s `dev` and `holdout`
  membership arrays are asserted byte-identical after every application.
* Did append the incidental exposure to the log.

## The honest one-line summary

> The `cases_hard` hold-out has been opened, its recorded figure describes a
> superseded case set, and no figure from it may be presented as an
> independent or blind result.
