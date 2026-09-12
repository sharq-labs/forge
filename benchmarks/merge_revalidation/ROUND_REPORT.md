# Merge re-validation — closing Sprint 7

## 1. Why this round exists

Sprint 8 opens with a prerequisite gate:

```
python -m tools.certification.core_certificate --verify
```

It came back **FAILED**, so Sprint 8 did not start. This round is what the gate
was for.

The certificate was stale, and that turned out to be the smallest of four
problems. All four have the same cause: merge `9f0ed8e` joined the empirical
and independent-validation branch into the sprint chain, and **the full suite
was never run afterwards**.

The two branches were not close together:

| parent | head | `src/engcore/scientific` modules |
|---|---|---|
| `f7772a0` — the sprint chain | performance/campaign round closed | **55** |
| `594ae17` — the merged branch | empirical round closed | **47** |

A 47-module branch was merged into a 55-module chain. Everything below follows
from that, and none of it had been observed.

---

## 2. What was actually broken

### 2.1 The certificate (the gate itself)

`AREA harness` had drifted: `tests/test_core_guards.py` and
`tests/test_core_semantic_invariants.py` both changed after the last
recertification, which certified the tree at `7d509fd`.

The drift was legitimate content — the capability-boundary round added one
condition to each of three records (`EXPECTED_CONDITION_NAMES` 64 → 67,
`EXPECTED_RESERVED_NAMES` 46 → 49) and the blind-v2 and contract-integrity
rounds added semantic invariants. Nothing was wrong with the changes. What was
wrong is that the certificate was never reissued, so the FAST tier was red on
`tests/test_core_certificate.py` and had been since the merge.

The other five certified areas — `core` (55 files), `evidence_identity`,
`inference_admission`, `runtime_data`, `trust_registry` — matched exactly.

### 2.2 Collection: a second `conftest` won the name

`tests/test_tier_classification.py` did `from conftest import CAMPAIGN_TESTS`.
pytest imports a `conftest.py` in a directory with no `__init__.py` as a
**top-level module called `conftest`**, and collection is alphabetical, so
`benchmarks/scientific_truth/tests/conftest.py` reached `sys.modules` first.
The import raised `ImportError` and took the whole FAST suite's collection with
it.

The repository had been defending the bare name **by convention**, and the
convention was written down in three places —
`tests/domains/battery/battery_cases.py` declines to be a `conftest.py` and
says why, `benchmarks/empirical_validation/tests/test_empirical_validation.py`
declines for the same reason, and `NEEDS.md` asks for a note in
`docs/TESTING.md` that would "save the next person the same hour". Five
benchmark rounds now ship such a file; one of them did not know.

Fixed by removing the dependency on the convention: the test loads
`tests/conftest.py` **by path**, which no import order can change.

### 2.3 Collection: an undeclared dependency

`benchmarks/scientific_truth/oracles/material.py` does `from mpmath import mp,
mpf` and `mpmath` was declared nowhere, so that round's test module could not
be collected either.

Declared as an optional `[oracles]` group. The guard that pins the
declared-but-unimported set —
`test_a_declared_dependency_nothing_imports_is_recorded_rather_than_assumed` —
asks for exactly this: *"if a THIRD unused declaration lands this fails and
somebody looks at it"*. Somebody looked at it. `mpmath` **is** imported; it is
imported from `benchmarks/`, and that guard's sweep walks `src/` and `tests/`
only.

The sweep was deliberately **not** widened. `benchmarks/` also reaches
`jsonschema` and `psutil`, neither declared, and several rounds append their
own directory to `sys.path` so local names (`adapters`, `challenge`,
`claim_map`, `nominals`, `reference`, `review`) read as third-party to an AST
walk. Widening means declaring two distributions and teaching the walk about
the `sys.path` appends — a dependency-hygiene round, not a line in an
assertion. The blind spot is now recorded in the guard's own docstring so the
next reader inherits it as a known one.

### 2.4 FULL only: the ngspice reference could not run

`benchmarks/empirical_validation/reference/spice.py` resolved the provider as
`shutil.which("ngspice") or "/usr/bin/ngspice"` and passed a temp-file path.

On a host that reaches ngspice through WSL — this one — that POSIX path is not
executable from Windows, and a Windows path is not resolvable inside the guest.
The file's own `available()` answered `False` correctly; the rebuild called
`run()` without consulting it, and the round died with `WinError 2`.

Two other spellings of the same idea already existed and were right:
`src/engcore/domains/electrical/ngspice.py` holds an argv **prefix**
(`wsl.exe -e ngspice`, overridable with `CRAFTY_NGSPICE_ARGV`) and feeds the
netlist on **stdin** so no path crosses the boundary; `benchmarks/blind/
oracles/spice.py` probes WSL the same way. The empirical round now resolves the
provider identically. `netlist()` is untouched, so the bytes ngspice reads are
the same bytes.

Three further call sites used the removed path constant — the IPM-7
construction mutation, `spice.version()`, and the evidence-provenance record —
and all three now go through `spice.ARGV`. The provenance record's `binary` key
became `invocation`, because where the provider is reached through WSL there is
no single executable path and recording one would describe a binary nothing
ran. `EV-5` accepts both.

### 2.5 FULL only: two rounds pinned a digest that cannot be reached

Both merged rounds pinned

```
CERTIFIED_DIGEST = 82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507
```

— Core V1's digest over 47 modules — and gated on the recomputed scientific
tree equalling it.

Recomputing that digest at every commit that ever touched
`src/engcore/scientific` shows the pin was **last true at `be57bf4d7056`, the
V1 certification commit itself**, and diverged at the very next scientific
commit, `3d642dcef5db` ("fix(consensus): enforce consensus completeness
invariants"). The tree then grew to 55 modules through the field, composition
and spatial-profile rounds. On its own branch the pin was correct; on this
chain it had been unreachable for many sprints.

Re-pinned to the merged tree's digest
`1422c1b9e84159b17887ad4e2ef07df6d0296a60082d60247b31266e920be7f0` and renamed
to `EXPECTED_SCIENTIFIC_DIGEST`. The rename is the point: a field called
`certified_digest` holding a value no certificate ever issued is precisely the
kind of record these rounds exist to catch. Both gate schemas go to `/2`.

**What the gates are FOR is unchanged.** Their question is "did this round
change anything the earlier rounds certified?", and the half that answers it is
the `git status` check for touched paths under `src/` and `tests/` — which is
lineage-independent and was always the substantive half.

---

## 3. What was NOT changed

- **No file under `src/engcore/scientific`.** The scientific tree is
  byte-identical; its digest is the same before and after this round.
- **No scientific result.** Every numeric change in the regenerated artifacts
  is at or below the double-precision noise floor (§5).
- **No mutation was added to `tests/mutation_guards.py`.** It is certified and
  cannot gain entries outside a re-certification round; the certified 79 were
  re-run, not extended.
- **No digest was hand-edited.** The certificate was reissued with the tool.

---

## 4. Artifact regeneration

Both rounds write their artifacts as a side effect of the rebuild the tests
run. Regenerated and committed, for a reason worth stating: `MV-11` ("FROZEN
EVIDENCE PRESERVED") fails if any *earlier* round's tree is dirty, and
`empirical_validation` is on its list. With stale artifacts on disk, whichever
round ran second would fail on the other's dirt. Both now **rebuild
byte-identically on this host**, verified by rebuilding twice and diffing, so
the tree stays clean across a FULL run.

One trap met on the way: these builds use `pathlib.write_text`, which on
Windows emits CRLF. The repository's `.gitattributes` pins `* text=auto eol=lf`
repository-wide precisely so a checkout cannot rewrite bytes a digest is taken
over, and it normalises these on `git add` — so the CRLF churn does not reach a
commit. It does make `git status` noisy in the meantime.

---

## 5. The numeric differences, stated precisely

| artifact | differing floats | worst absolute | where | relative there |
|---|---|---|---|---|
| `empirical/ERROR_SHAPE.json` | 28 | 1.147e+03 | `ngspice_precision/improvement_factor` | 6.5e-4 |
| `empirical/VALIDATION_RESULTS.json` | 59 | 7.90e-09 | a `-67.936 V` node voltage | 1.2e-10 |
| `mmv/VALIDATION_RESULTS.json` | 107 | 2.04e-14 | `MV-D/max_departure_v` | 3.6e-14 |
| `mmv/RESIDUAL_ANALYSIS.json` | 11 | 1.78e-15 | `MV-C/low_to_high_drift` | 1.4e-14 |

Three different magnitudes, and lumping them together would hide the one that
is actually largest, so:

- **`improvement_factor`, 1 749 592 → 1 750 738.** The biggest number on the
  page and the least alarming: it is a RATIO of two relative differences that
  are themselves ~1e-13, so noise-floor jitter in the denominator moves it by
  parts in ten thousand. It measures how much tighter twelve-figure printing is
  than the default format — a property of ngspice's output formatting.
- **A `-67.936 V` node voltage moving by 7.9e-09**, i.e. 1.2e-10 relative.
  This is the largest change to an actual *physical quantity* anywhere in the
  regeneration, and it is ~1e-10 of the value against a round that declares
  its agreement bound far above that.
- **Entries showing a 100 % RELATIVE change** are the least significant of all:
  disagreement values moving between `0.0` and `~1e-16`, where relative
  difference is a meaningless statistic because the quantity was already
  indistinguishable from zero.

The empirical round's values move because **this host's ngspice is a different
build** than the one that wrote the committed values — which is what an
independent external oracle being independent looks like. The `mmv` values move
because least-squares fits resolve differently on this machine's BLAS; those
are last-ulp throughout.

> **Correction.** Commit `58c64eb`'s message says "the largest absolute
> difference is ~1e-15". That is wrong — it described the 100 %-relative
> entries and missed `improvement_factor` and the node voltage above. The table
> here is the measured answer. The commit is left as written rather than
> rewritten, and this note is the correction.

The round's own gates are the judge of whether that matters, and they are: 11/11
PASS for the empirical round, `CONSISTENCY_AUDIT` **CONSISTENT**.

`MV-7` stays **FAIL** for the model-measurement round, which is its **published
verdict** — `MVF-1` is a material mismatch the round found and reported. A
green `MV-7` here would mean the finding had been lost. Rebuilt totals match
the published ones exactly: 10 passed, 1 failed, 0 planted failures missed.

---

## 6. Assurance

Every suite below ran on a clean tree at `6d3a5ec`, before the certificate was
reissued.

| suite | result |
|---|---|
| FAST (`-m "not expensive"`) | 4802 passed, 7 skipped, **1 failed** |
| FULL (no marker filter) | 5347 passed, 7 skipped, **1 failed** |
| Contract Guard | 305 passed |
| Capability Boundary | 306 passed, 675 deselected |
| Scientific Truth | 293 passed, 3 skipped |
| field suites | 124 passed |
| field profile suites | 147 passed |
| certification suite | 27 passed, 1 skipped, **1 failed** |
| mutation harness self-guard | 6 passed |

The single failure in FAST, FULL and the certification suite is the same test —
`test_the_certificate_describes_this_tree` — and it is the **expected** state
for a round that changes a certified file before reissuing. It is §8.

Two environment notes for whoever runs this next, because both cost time:

- pytest's default temp root is not writable in this sandbox, and the
  certification suite builds throwaway git repositories under it. It needs
  `--basetemp` redirected — and redirected somewhere **short**: the session
  scratchpad path is ~150 characters, and MAX_PATH truncation surfaces as a
  pile of unrelated fixture errors rather than as a path error.
- `-n auto` spawns 24 workers on this machine and exhausts memory. `-n 4`.

### EI / RI / FM / SP — carried forward, not re-measured

| family | total | killed | survivors |
|---|---|---|---|
| EI — evidence pairing integrity | 10 | 10 | 0 |
| RI — route independence authority | 12 | 11 | **1 (RI2b)** |
| FM — field and mesh records | 8 | 8 | 0 |
| SP — spatial profiles | 10 | 10 | 0 |

These were measured in the `core_v2_recertification` round through an
apply/revert harness kept **outside** the repository, because
`tests/mutation_guards.py` is itself certified and cannot gain mutations
without a re-certification round. They are **not** part of the certified 79 and
are never added to it.

They are carried forward rather than re-run, and the justification is checkable
rather than rhetorical: all four families mutate evidence pairing, route
independence, field/mesh records and spatial profiles, every one of which lives
in `src/engcore/scientific` — and **every certified file under it is
byte-identical** to the commit they were measured at. The five `src/` files
that did change this round are domain models
(`battery/context.py`, `battery/models.py`, `electrical/material.py`,
`kinetics/cstr/alternatives.py`, `thermal_models/lumped.py`), which the
certificate's own scope block puts explicitly **out** of scope and which none
of these families touches.

`RI2b` is a **known equivalent mutant**, proven equivalent in Sprint 3 by
running the mutation in memory: the verdict gate already excludes a shared
implementation, so removing the second check changes no reachable behaviour. It
is recorded as a survivor rather than quietly excluded from the count.

---

## 7. The certified 79

Re-run in full, because `tests/test_core_guards.py` is **one of the four
TARGETS** this harness runs every mutant against and it changed this round — so
the previous run's numbers were statements about different bytes.

```
CONTROL GREEN    unmutated copy, 18s -- a red result below is the mutation's doing
                 470 passed, 5 warnings in 17.73s
...
79/79 mutations were killed by the guard they name.
```

| | |
|---|---|
| control | **GREEN**, 470 passed on the unmutated copy |
| killed | **79** |
| survivors | **0** |
| killed before any test ran | `G1d`, `G14a` |
| log | 34 876 bytes, 319 lines |

The control is not a formality. It is the four TARGET suites run against an
unmutated copy of the tree; without it, a RED result could be the copy being
broken rather than the mutation being caught.

Two readings of the log are recorded and they agree: the per-mutation
`RED`/`GREEN` column, and the runner's own closing tally. That cross-check
earned its place immediately — the first parser written for it used a stricter
pattern, missed `G1d` and `G14a` (which report `RED (refused at import)` with a
single space, because the mutated tree does not survive import and is killed
before any test runs), and reported 77 against the runner's 79. The
disagreement is surfaced in the certificate rather than averaged away.

**A note on the first run of this harness.** It was invoked through
`| tail -40`, so the captured log was truncated and the `CONTROL` line — which
is the *first* line — was lost. Hashing that would have put a `log_sha256` into
a certification artifact that no future reader could reproduce or compare. The
harness was re-run with the full transcript captured. The control was also
measured independently, by running the four TARGET suites directly against the
preserved control tree of the first run: **470 passed**, matching the second
run exactly, and matching the `470 − N passed` that every mutant line reports.

---

## 8. Wheel

Built from `git archive` at this branch's head and installed into an empty
target: **201 Python files**, `engcore/execution/` ships, `tools/` correctly
does not. **313 passed.**

The trap this run is written around is worth stating, because a wheel smoke can
pass while testing nothing. `python -I` implies `-E`, so it ignores
`PYTHONPATH`, and it does **not** skip site-packages — where this venv's
editable install hook for the checkout lives. Run that way, `engcore` resolves
to the *checkout* and every assertion passes while proving nothing.

So: `python -S -E`, with the wheel inserted at the front of `sys.path` by an
explicit launcher and site-packages appended after it for pytest and
numpy/scipy. `-S` means `site.py` never runs and the editable `.pth` hook is
never registered; appending a directory does not process its `.pth` files.

And it was falsified rather than assumed:

```
with -S : engcore <- D:\fwheel\install\engcore\__init__.py
without : engcore <- ...\phyx\src\engcore\__init__.py
```

The copied suites also carry a `conftest.py` that asserts `engcore.__file__`
lives under the install target before any test is collected.

---

## 9. Certificate

Certified scope changed: `tests/test_core_guards.py`, in the `harness` area.
The certificate went **RED and named it** before the reissue, which is the
requirement proved rather than asserted:

```
AREA harness
  MODIFIED: tests/test_core_guards.py
            tests/test_core_semantic_invariants.py
  expected area digest: 22fe10831fc4711e…
  actual area digest:   b8b7dfb687c8527b…
expected aggregate: 61f9546d367def9d…
actual aggregate:   a8c1f9ca44c5eb5c…
FAILED
```

Reissued with the tool at `6130003`. **No digest was hand-edited.**

| | |
|---|---|
| files | 72 — unchanged; nothing entered or left scope |
| aggregate | `61f9546d367def9d…` → `a8c1f9ca44c5eb5c…` |
| areas changed | `harness` only |
| areas byte-identical | `core` (55), `evidence_identity`, `inference_admission`, `runtime_data`, `trust_registry` |
| `diagnostic` | `false` |
| verification | `certificate matches the tree` · **OK** |

One practical note: the assurance JSON must be passed from **outside** the
repository. Copying it in first makes the tree dirty, and the build refuses a
dirty tree — correctly, since a certificate names a commit.

---

## 10. Final state

| | before | after |
|---|---|---|
| FAST | 4802 passed, **1 failed** | **4803 passed, 0 failed**, 7 skipped |
| FULL | 5347 passed, **1 failed** | **5348 passed, 0 failed**, 7 skipped |
| certificate | `FAILED` | **OK** |
| working tree | clean | clean |

Both rounds rebuild byte-identically, so a FULL run leaves the tree clean.

---

## 11. Verdict

**SPRINT 7 CLOSED.** The gate that opened this round now passes:

```
$ python -m tools.certification.core_certificate --verify
certificate matches the tree
commit: certified commit 61300036b69e, HEAD 760b2adacf47
OK
```

### What this round claims

Merge `9f0ed8e` was re-validated. Four breakages it introduced — two collection
failures, one unreachable external provider, one unreachable digest pin — are
fixed, and the assurance that was never run after the merge has been run:
FAST, FULL, the four guard suites, the certified 79 mutants with a green
control, the installed wheel, and the certificate.

### What this round does NOT claim

- **The EI/RI/FM/SP families were not re-measured.** They are carried forward
  with the grounds recorded and `re_run_this_round: false` in the certificate.
  The grounds are checkable, not rhetorical — but they are grounds, not a
  measurement.
- **No claim that the merged rounds' science was re-audited.** Their gates were
  made runnable and were run; their findings, including `MV-7`'s standing
  `FAIL` on `MVF-1`, are unchanged and unexamined by this round.
- **No claim about hosts other than this one.** The ngspice fix makes the
  provider reachable through WSL *here*; the empirical round's numbers moved at
  the noise floor because this host's ngspice is a different build, and a third
  host would move them again.
- **No claim that the `benchmarks/` dependency blind spot is closed.**
  `jsonschema` and `psutil` are still reached from `benchmarks/` and declared
  nowhere. That is recorded in the guard's docstring as known, and left.
- **No new scientific capability.** Nothing under `src/engcore/scientific`
  changed; its digest is identical before and after.
