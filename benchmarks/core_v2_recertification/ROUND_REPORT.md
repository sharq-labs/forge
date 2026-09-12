# Core V2 Recertification Infrastructure — Sprint 6

**Branch** `claude/core-v2-recertification-6` · **base** `416985c` · **certified commit** `af26c09`

---

## 1. Final result

> ### **CORE V2 RECERTIFICATION COMPLETE**

Certification is now reproducible, verifiable and machine-checkable. One
command answers the question V1 could not be asked:

```bash
python -m tools.certification.core_certificate --verify
```

and the same check runs as an ordinary test in the FAST tier, so a certificate
that stops describing the tree turns a suite red instead of sitting quietly.

| Acceptance item | Verdict |
|---|---|
| V1 status understood honestly | **HOLDS** — §3, and it corrects a Sprint 5 claim |
| V2 digest algorithm documented | **HOLDS** — §4 |
| V2 digest reproducible | **HOLDS** — executable, and a rebuild is byte-identical |
| per-file manifest exists | **HOLDS** — 72 files, §6 |
| aggregate digest exists | **HOLDS** — §6 |
| certified scope explicit | **HOLDS** — 6 areas in, 6 out, each with a reason, §5 |
| exact commit certified | **HOLDS** — §7 |
| assurance harness bytes pinned | **HOLDS** — §8 |
| `current_core_v2.json` exists | **HOLDS** — §15 |
| normal test detects drift | **HOLDS** — §13 |
| added/removed/modified detected | **HOLDS** — CERT-1/2/3, §13 |
| certification faults all fail | **HOLDS** — CERT-1..CERT-8, §13 |
| FAST green | **HOLDS** — §9 |
| FULL green | **HOLDS** — §9 |
| guards green | **HOLDS** — §10 |
| EI/RI/FM/SP green | **HOLDS** — with one known equivalent mutant named, §11 |
| certified 79-mutant harness green | **HOLDS** — §12 |

---

## 2. Why V1 became stale

**Not because its algorithm was lost.** Because nothing ran it.

V1 recorded a digest over `src/engcore/scientific/**/*.py` and wrote the exact
recipe for reproducing it into its own `verification` block. What it did not
have was a script, a command, or a test. So when Sprint 4 added seven modules
to that tree and Sprint 5 added one more, the certificate went on saying 47
modules and nothing anywhere compared the two numbers.

That is an infrastructure gap, and it is the one this sprint closes. The
mechanism that let it happen is the same one Sprint 5 found in the thermal
validation report: a fact was recorded, and nothing asserted on it.

---

## 3. Whether the V1 digest algorithm was recovered

> ### **RECOVERED, AND REPRODUCED.**

It is written out in `certification/current_core_v1.json` under
`verification.how_to_reproduce_the_certified_tree`, as a runnable snippet, and
described in `verification.digest_covers` as *"src/engcore/scientific/\*\*/\*.py,
path-ordered, over raw file bytes; `__pycache__` excluded"*.

Run against the commit V1 names, it reproduces V1's stored value exactly:

| | |
|---|---|
| commit | `be57bf4d705606d746175cbc1c240697e68ef0c2` |
| modules | **47** |
| computed | `82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507` |
| stored | `82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507` |
| | **identical** |

### A correction to Sprint 5

Sprint 5's report §19 states that the stored digest *"could not be
independently verified"* and that *"no script or documented method for
computing it exists in the repository"*. **That was wrong.** The method does
exist, inside the certificate itself, and the search that produced that claim
looked for external scripts and for the digest string, and read the `core`
block rather than the `verification` block beside it.

The correct statement is the one in §2: the algorithm was documented and
nothing executed it. Sprint 5's conclusion — that the certificate could not be
called current — was right for the wrong reason.

---

## 4. V2 digest algorithm

Implemented in `tools/certification/core_certificate.py`, documented in its
module docstring and restated in every certificate's own `digest_algorithm`
block.

Per file:

```
file_digest = sha256(exact bytes on disk)
```

Per area, over its files sorted by UTF-8 path bytes:

```
area_digest = sha256( for each: path_utf8 + 0x00 + file_digest_bytes )
```

Over the certificate, areas sorted by name:

```
aggregate = sha256( for each: area_name_utf8 + 0x00 + area_digest_bytes )
```

| Rule | Choice |
|---|---|
| root | the repository root (holds `.git` and `pyproject.toml`) |
| included | each area's explicit glob patterns, files only |
| excluded | any path with a `__pycache__` component; `*.pyc`, `*.pyo` |
| path normalization | repository-relative, POSIX separators |
| ordering | sorted by UTF-8 encoded path bytes |
| byte handling | exact bytes; nothing is decoded |
| line endings | **not normalized** |
| symlinks | **refused** in scope |
| generated files | none in scope beyond the exclusions |
| hash | SHA-256 throughout |

**Line endings are deliberately not normalized.** Several trees here are
already pinned by SHA-256 over raw bytes, and a certificate that normalized
would disagree with them and would hide a real change to what ships.

**The per-area construction is V1's**, with repository-relative paths where V1
used paths relative to `src/engcore/scientific`. That was recovered rather than
guessed, so reusing it is continuity rather than cargo-culting — but it does
mean the two numbers are **not comparable by construction**. The certificate
therefore also records `v1_continuity.v1_compatible_core_digest_now`, the core
tree recomputed exactly V1's way, so the relationship is a number:

| | |
|---|---|
| V1 core digest at `be57bf4` (47 modules) | `82558f5b…` |
| V1-compatible core digest now (55 modules) | `0df44b40…` |

**No timestamp.** V1 recorded when it was written with a note that timestamps
are not identity — true, and it also meant two engineers certifying one commit
produced two different files and had to take on trust that the only difference
was the clock. Omitting it makes a rebuild a comparison instead, and a test
asserts two builds from one tree are byte-identical.

---

## 5. Certified scope

The criterion is deliberately narrow: **an area is in when a silent edit to it
would change what a verdict *means*, rather than change an answer.** A domain
solver produces answers and carries its own assurance; the registry the core
reads to decide whether a threshold set is *declared* decides whether a level
may be awarded at all.

| Area | Class | Included? | Why |
|---|---|---|---|
| `src/engcore/scientific/**` | CORE_CERTIFIED | **yes** | the contracts, their invariants and their refusals. What V1 certified |
| `src/engcore/domains/__init__.py` | CORE_CERTIFIED | **yes** | the declarations the core verifies against and cannot see past. An edit turns a gate that awards nothing into one that awards a level without touching a line of the core |
| `src/engcore/adequacy/**` | CORE_CERTIFIED | **yes** | evidence identity and pairing: whether two models were assessed against the same evidence |
| `src/engcore/inference/**` | CORE_CERTIFIED | **yes** | the admission invariant for forward rows; a Sprint 1 trust boundary the certified harness exercises |
| `src/engcore/data/**` | RUNTIME_SUPPORT | **yes** | what a `ScientificDataReference` resolves through. The length-then-digest verification that makes the reference worth anything |
| harness (5 files) | HARNESS | **yes** | the mutation runner and the four suites it runs each mutant against |
| `src/engcore/domains/**` (rest) | DOMAIN_ASSURANCE | no | scientific models; they produce answers, and three are byte-pinned by frozen experiments |
| `src/engcore/mcp/**` | — | no | the product boundary: a consumer of the core |
| `src/engcore/design/**`, `sria/**`, `systems/**` | — | no | applications built on the core |
| `src/engcore/uq/**` | — | no | representation only; no verdict rests on it computing |
| `tests/**` (rest) | — | no | assurance for the above, not part of what is certified |
| `benchmarks/**`, `experiments/**`, `certification/**` | — | no | measurements, frozen artefacts, and the certificate itself — a scope containing its own bytes would need a fixed point |

---

## 6. File / module manifest

| Area | Class | Files | Area digest |
|---|---|---|---|
| `core` | CORE_CERTIFIED | 55 | `71eeddd96dca06fe…` |
| `evidence_identity` | CORE_CERTIFIED | 2 | `ee591e35866f2ebd…` |
| `harness` | HARNESS | 5 | `22acc63b7a206ce3…` |
| `inference_admission` | CORE_CERTIFIED | 3 | `f02ad3ddc1b00feb…` |
| `runtime_data` | RUNTIME_SUPPORT | 6 | `3efad22caee14a8a…` |
| `trust_registry` | CORE_CERTIFIED | 1 | `6d6ab0fe914fa666…` |
| **total** | | **72** | |

**Aggregate:** `2bd8a2807bdd3092ead58cba42acd01fddd3b105bdf76706aeb1a20daefcf0fc`

Every one of the 72 files is listed in the certificate with its own SHA-256.
That is what makes drift diagnosable: verification names the file that moved
rather than reporting that two hex strings differ.

---

## 7. Current commit

| | |
|---|---|
| certified commit | `af26c0989fa6856b32baa4a844a76a8177186dda` |
| branch | `claude/core-v2-recertification-6` |
| tree state at build | clean |

Building from a dirty tree is refused: a certificate names a commit, and one
built from uncommitted edits describes a tree nobody can check out.
`--allow-dirty` produces a certificate marked `diagnostic`, which the verifier
then refuses to accept as a certificate at all.

The certificate is committed as a **child** of the commit it certifies, as V1's
was. `--verify` therefore compares content by default and reports the commit
relationship informationally; content is unaffected because `certification/` is
outside certified scope. `--require-commit` demands the exact commit.

**This sprint changed no certified file.** `git diff 416985c..HEAD` over the
certified scope is empty; all 1283 added lines are new infrastructure outside
it. The certified content is exactly the content at the end of Sprint 5.

---

## 8. Harness identities

`'79/79 killed'` is a statement about exact bytes, so the bytes are pinned —
in the manifest's `harness` area and again in the certificate's
`assurance.harness_identity`:

| File | Role |
|---|---|
| `tests/mutation_guards.py` | the runner |
| `tests/test_core_guards.py` | target suite |
| `tests/test_repair_guidance.py` | target suite |
| `tests/test_offset_unit_declaration.py` | target suite |
| `tests/test_core_semantic_invariants.py` | target suite |

CERT-6 asserts that changing any of them fails verification and names the file.

Command recorded with the result:
`python -X utf8 tests/mutation_guards.py <scratch-dir>`

---

## 9. FAST / FULL

| Run | Selection | Result |
|---|---|---|
| **FAST** | `tests/ -m "not expensive"` | **4475 passed, 4 skipped, 541 deselected** (50.7 s) |
| **FULL** | `tests/` | **5016 passed, 4 skipped** (203.9 s) |

The certificate verification test is unmarked, so it runs in FAST: drift is
caught in the 51-second tier rather than only in the three-minute one.

**The figures embedded in the certificate are the earlier ones** — FAST 4471 /
FULL 5012, with 8 skips. That is deliberate and not stale: the certificate
records assurance measured **on the tree it certifies**, where
`current_core_v2.json` did not yet exist, so the five tests that read it
skipped. Re-running at the child commit, with the certificate present, turns
four of those five into passes and gives the numbers above. The fifth is the
symlink refusal test, which skips because symlinks are not creatable without
elevation on this platform; the refusal it covers is still in the code and is
unreachable from a test here.

---

## 10. Guard results

| Guard group | Result |
|---|---|
| Contract Guard | 305 passed |
| Capability Boundary | 304 passed, 675 deselected |
| Scientific Truth | 293 passed, 3 skipped |
| field suites | 124 passed |
| field profile suites | 147 passed |
| certification suite | 28 passed, 1 skipped |
| mutation harness self-guard | 6 passed |

---

## 11. EI / RI / FM / SP results

Run through the sprint-local apply/revert harness, which is kept **outside**
the repository because `tests/mutation_guards.py` is itself pinned and cannot
gain mutations without re-certification. **These are not part of the certified
79 and are recorded separately so the two are never added together.**

| Family | Total | Killed | Survivors |
|---|---|---|---|
| EI — evidence pairing integrity | 10 | **10** | 0 |
| RI — route independence authority | 12 | **11** | **1 (RI2b)** |
| FM — field and mesh records | 8 | **8** | 0 |
| SP — spatial profiles | 10 | **10** | 0 |
| | **40** | **39** | **1** |

Control GREEN for every family.

**RI2b is a known equivalent mutant**, not a gap. It was proven equivalent in
Sprint 3 by running the mutation in memory: the verdict gate already excludes a
shared implementation, so removing the second check changes no reachable
behaviour. It is recorded as a survivor rather than quietly excluded from the
count, and the certificate records it the same way.

---

## 12. 79-mutant harness result

| | |
|---|---|
| runner | `tests/mutation_guards.py` |
| command | `python -X utf8 tests/mutation_guards.py <scratch-dir>` |
| control | **GREEN** |
| total | **79** |
| killed | **79** |
| survivors | **0** |
| log SHA-256 | `b6ffd1890bdf553c4f9c31a27d9c7c917ac9ca0fd1bfef3e09748c1650a03f3b` |

Roughly 80 minutes, one copy of the tree per mutant, four suites against each.
`in_the_formal_certificate: true` — this is the certified suite, and the
targeted families in §11 are recorded beside it with that flag set to false so
the two can never be added together.

The log digest identifies **this run's** log and is not a reproducible value:
the log carries per-mutant wall times. V1 recorded a different one for the same
reason.

---

## 13. Certificate drift tests

`tests/test_core_certificate.py`. The load-bearing case reads the stored
certificate and compares the working tree against it. Everything else exists to
prove that case can fail.

The drift and fault cases run against a **synthetic repository** built in a
temporary directory — adding and deleting certified source files to see what
happens is not something a test should do to the tree it is running in.

| Fault | Detected as |
|---|---|
| CERT-1 modified certified byte | `MODIFIED: src/engcore/scientific/record.py` |
| CERT-2 added certified module | `ADDED: src/engcore/scientific/extra.py` |
| CERT-3 removed certified file | `REMOVED: src/engcore/scientific/units.py` |
| CERT-4 altered per-file digest | `MODIFIED:` the affected path |
| CERT-5 altered aggregate digest | expected vs actual aggregate |
| CERT-6 changed harness bytes | `AREA harness` + `MODIFIED: tests/mutation_guards.py` |
| CERT-7 certificate naming another commit | `names commit …, HEAD …` |
| CERT-8 dirty tree where policy forbids it | `uncommitted changes` |
| restore the tree | green again |

Also refused: an unknown certificate schema, a certificate whose `file_count`
disagrees with its own file list, a diagnostic certificate presented as a
certificate, and building from a dirty tree.

### No self-certification loophole

Asserted twice. **Structurally**: `verify_certificate`'s source is read and
checked never to call `build_certificate` or `build_manifest` — a verifier that
regenerated its expectations would compare the tree to itself and pass for any
tree. **Behaviourally**: a certificate built from one committed tree is
verified against a *different* committed tree and must fail.

### Proven end to end on the real tree

Not only on the synthetic one. A byte was appended to
`src/engcore/scientific/errors.py` and the FAST-tier test went red with:

```
AREA core
  MODIFIED: src/engcore/scientific/errors.py
  expected aggregate: 2bd8a2807bdd3092…
  actual aggregate:   862b9e165c1fa37e…
```

A new module `src/engcore/scientific/_drift_probe.py` was then added and
`--verify` reported `ADDED: src/engcore/scientific/_drift_probe.py` and
`FAILED`. Removing both returned it to `certificate matches the tree` / `OK`
with a clean tree.

### A defect found in the tool itself

`git status --porcelain` encodes the index and worktree states in the first two
columns and one of them is usually a space. Stripping the command's output
removes it from the first line only, so every path parsed from it loses its
first character: the tool reported an uncommitted
`tools/certification/core_certificate.py` as `ools/…`. Cosmetic in effect and
not in kind — the whole argument for a per-file manifest is that a failure
names the file that moved, and a name wrong by one character names no file.
Fixed, with a guard over all four status shapes including renames.

---

## 14. V1 status

> ### **HISTORICAL_CERTIFICATE — ALGORITHM RECOVERED**

Not wrong, and not broken. It certifies the commit it names, and it does so
correctly and reproducibly.

| | |
|---|---|
| V1 stored module count | **47** |
| current / V2 core module count | **55** |
| V1 stored digest | `82558f5b…` |
| V1 algorithm recovered | **yes**, from V1's own `verification` block |
| V1 digest reproduced at its own commit | **yes**, exactly |
| what V1 lacked | anything that executed it |

`certification/current_core_v1.json` is **unchanged by this sprint** and stays
historical. A test pins the recipe inside it, so the only reason its algorithm
is recoverable does not quietly disappear.

---

## 15. V2 certificate location

`certification/current_core_v2.json`, with `certification/README.md` beside it
giving the one command, the scope table, the digest construction and V1's
status.

---

## 16. Files changed

5 files, +1283 / −0. **No file in certified scope was touched.**

| File | Δ |
|---|---|
| `tools/certification/core_certificate.py` | **new**, 763 |
| `tests/test_core_certificate.py` | **new**, 433 |
| `certification/README.md` | **new**, 85 |
| `tools/__init__.py`, `tools/certification/__init__.py` | **new**, 1 each |
| `certification/current_core_v2.json` | **new** (this commit) |
| `benchmarks/core_v2_recertification/ROUND_REPORT.md` | **new** (this commit) |

`pyproject.toml` is untouched: `[tool.setuptools.packages.find] where = ["src"]`,
so a top-level `tools/` reaches no wheel.

---

## 17. Commits

| | |
|---|---|
| `39ebbeb` | `feat(certification): make the core tree digest executable` |
| `1aee3cb` | `test(certification): detect certificate drift` |
| `7d950af` | `fix(certification): report a dirty path with its first character` |
| `aa5cad1` | `docs(certification): point at the one command` |
| `8bd0ef4` | `test(certification): skip rather than error outside a checkout` |
| `af26c09` | `test(certification): a rebuild from one commit is byte-identical` |
| `6cfa8ac` | `cert(core): certify the core at af26c09` |
| *(this commit)* | `docs(core): close core v2 recertification` |

---

## 18. Push result

Pushed to `origin/claude/core-v2-recertification-6`. `main` untouched.
`current_core_v1.json` unchanged.
