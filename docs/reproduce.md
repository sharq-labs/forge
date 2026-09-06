# Reproducing the numbers

A buyer's first technical question is whether this runs anywhere but the
author's laptop. This page answers it, including where the answer is **no**.

---

## The one command

```bash
docker build -t crafty-repro . && docker run --rm crafty-repro
```

`Dockerfile` goes from `python:3.12-slim-bookworm` to: apt-install ngspice,
`pip install -e ".[dev]"`, FAST test tier, benchmark score on the development
split. No host state — `.dockerignore` keeps `.git`, `.venv` and every cache
out of the build context.

It prints the interpreter, the platform, the ngspice version, the pinned
package versions, then the two measurements.

---

## What was actually run, and what was not

**Docker is not installed in the environment this page was written in.** The
image has not been built. Claiming a run that did not happen is the exact
failure this whole round exists to close, so it is stated here rather than
buried: the `Dockerfile` above is delivered **unbuilt and unverified as an
image**.

What *was* run is the next-best thing available, and it answers most of the
same question:

| | host | clean environment |
|---|---|---|
| OS | Windows 11 Pro 10.0.26200 | Ubuntu 24.04.3 LTS (WSL2) |
| Python | 3.14.2 (MSC v.1944, 64-bit) | 3.12.3 |
| numpy / scipy | 2.5.2 / 1.18.1 | 2.5.3 / 1.18.1 |
| scikit-learn / Pint | 1.9.0 / 0.25.3 | 1.9.0 / 0.25.3 |
| pytest / xdist | 9.1.1 / 3.8.0 | 9.1.1 / 3.8.0 |
| ngspice | via `wsl.exe -e ngspice` | ngspice-42, native, `CRAFTY_NGSPICE_ARGV=ngspice` |
| Dependencies | the author's long-lived `.venv` | freshly downloaded from PyPI into `/tmp` |

The clean environment was built with no `sudo`, nothing written to `~`, and
nothing written outside `/tmp/crafty-repro`: pip was bootstrapped from
`get-pip.py` into a throwaway `--target` directory, **only the packages
`pyproject.toml` declares** were installed, and the source tree was copied in
without `.git`, `.venv` or any cache. Different OS, different kernel, different
CPython minor version, different interpreter build, independently resolved
dependencies. It is not a container, and it shares the host's filesystem and
CPU; a container would additionally rule out a stray environment variable or a
system library. Read it as a strong second data point, not as the container run.

---

## Result 1 — the benchmark reproduces exactly

```
########## RUN 3: benchmark, development split ##########
{
  "generated": "2026-09-06T22:47:33",
  "cases_dir": "cases_hard",
  "case_set_digest": "476976c15a1a22d89019c9d6f80ec061a123d0579efc9b5fbecfc16312dd4a1f",
  "split": "dev",
  "split_rule": "stratified-hash-hamilton/1 seed 20260906",
  "split_digest": "7353123acaf903e48e3e6aa90f11de46e888edec7b055aef8ce8b35c7a48aae0",
  "scored": "1400 of 2000 cases on disk",
  "total": 1400,
  "sound": 241,
  "unsound": 1159,
  "exact_verdict_match": "1282/1400 (91.6%)",
  "catch_rate": "1149/1159 (99.1%)",
  "false_accept": "10/1159 (0.86%)",
  "false_reject": "1/241 (0.4%)",
  "false_accept_ids": [
    "U00204", "U00237", "U00274", "U00351", "U00625",
    "U00818", "U00978", "U01001", "U01029", "U01292"
  ],
  "errors": {}
}

real	0m20.216s
```

**Identical to the host, field for field** — the same four metrics, the same
case-set digest, and the same ten false-accept ids in the same order. Across two
operating systems, two CPython minor versions and an independently resolved
numpy, not one case changed its verdict. That is the strongest single piece of
evidence on this page: the number is a property of the code, not of the machine.

The seal travels too:

```
########## RUN 4: seal must refuse here too ##########
REFUSED: --split all scores the sealed hold-out.
  600 of 2000 cases are sealed under rule stratified-hash-hamilton/1, seed 20260906.
  ...
exit=1
```

---

## Result 2 — the FAST tier did **not** reproduce. Fixed, and re-measured.

**Status: closed on this branch.** The transcript below is what a clean machine
did before the `[mcp]` group existed. It is kept because it is the measurement
that found the defect, and because the fix turned out to need a second one.

Re-run on the same clean machine after the fix:

```
########## FAST tier WITHOUT the [mcp] group -- must be GREEN ##########
SKIPPED [1] tests/mcp/test_battery_boundary.py:34: install the optional [mcp] dependency group
SKIPPED [1] tests/mcp/test_server.py:22: could not import 'anyio': No module named 'anyio'
2091 passed, 2 skipped in 18.19s
pytest exit=0

########## now install the [mcp] group and run again ##########
2146 passed in 18.60s
pytest exit=0
```

| | before | bare install, after | `.[dev,mcp]`, after |
|---|---|---|---|
| Passed | 2091 | 2091 | **2146** |
| Skipped | 1 | 2 *(two whole modules)* | 0 |
| Errors | **1** | 0 | 0 |
| Exit code | **1** | **0** | **0** |

Two honest qualifications. On a bare install **the same 55 tests still do not
run** — they are now a clean skip instead of a collection error, which is the
difference between a suite that reports what it did not cover and a suite that
falls over. And the fix takes `2146 passed` on a machine that had never seen the
SDK, which is full parity with the host.

---

## Appendix — the original finding

```
########## RUN 1: FAST tier, exactly as documented ##########
tests/mcp/test_battery_boundary.py:19: in <module>
    from src.engcore.mcp import server as srv
src/engcore/mcp/server.py:34: in <module>
    import mcp.types as mcp_types
E   ModuleNotFoundError: No module named 'mcp.types'
=========================== short test summary info ============================
ERROR tests/mcp/test_battery_boundary.py - ImportError while importing test m...
2091 passed, 1 skipped, 1 error in 19.59s

real	0m19.793s
```

| | host | clean environment |
|---|---|---|
| Passed | **2146** | **2091** |
| Skipped | 0 | 1 |
| Errors | 0 | **1** |
| Runtime | 33.47 s | 19.59 s |

**55 tests do not run on a machine that installs only what this project
declares.** Two packages are imported but appear in neither `pyproject.toml`,
`requirements.txt` nor the CI workflow:

* **`mcp`** (Model Context Protocol SDK; the host has 2.1.1) — imported at
  module scope by `src/engcore/mcp/server.py:34`.
* **`anyio`** — `pytest.importorskip`-ed by `tests/mcp/test_server.py:22`.

The two behave differently, and the difference is the actual defect.
`tests/mcp/test_server.py` guards its imports and **skips cleanly**, and its own
comment states the rule:

> The MCP SDK is the optional `[mcp]` dependency group. The suite must stay
> runnable — and green — without it, the same rule pytest-xdist is held to.

Two things are wrong with that sentence as of this commit. There is **no `[mcp]`
optional dependency group in `pyproject.toml`** — the group it names does not
exist, so there is no supported way to install the SDK. And
`tests/mcp/test_battery_boundary.py:19` imports `src.engcore.mcp.server` at
module scope with **no guard**, so the module errors at collection and the rule
its sibling states is already broken.

The single skip is `anyio`, not `mcp` — `importorskip("anyio")` runs first, so
`test_server.py` would skip on this machine even if the SDK were installed.

Ignoring only the unguarded module gives a clean run, which locates the failure
precisely rather than leaving it as "something about MCP":

```
########## RUN 2: same, minus the module that cannot import ##########
SKIPPED [1] tests/mcp/test_server.py:22: could not import 'anyio': No module named 'anyio'
2091 passed, 1 skipped in 17.35s
```

**Measured, not inferred.** `gh run list` was checked rather than reasoned
about, and CI is red for exactly this reason and has been for hours:

| run | branch | jobs | result |
|---|---|---|---|
| `34051999995` (2026-09-06 18:31) | `main` | `fast`, `scientific` | both `ModuleNotFoundError: No module named 'mcp.types'` |
| `34049876434` (17:51) | `main` | same | same |
| `34046571740` (16:47) | `main` | same | same |
| `34029223990` (11:05) and every run before it | `main` | — | **green** |

```
fast        E   ModuleNotFoundError: No module named 'mcp.types'
fast        ERROR tests/mcp/test_battery_boundary.py - ImportError while importing test module
fast        1996 passed, 1 skipped, 1 error in 56.92s
scientific  2511 passed, 1 skipped, 1 error in 179.83s (0:02:59)
```

Two things this measurement adds that the inference did not.

**It is `scientific` as well as `fast`.** Both tiers error at collection, so
*every* CI job that runs pytest has been failing, not just the FAST one.

**It bisects to a commit.** CI was green through `step9-mcp-server` at 11:05 —
that round added `tests/mcp/test_server.py`, which guards its import and skips
cleanly — and went red at 16:47 with the `domain-gaps` merge, the round that
added the unguarded `tests/mcp/test_battery_boundary.py`. The guard is the
whole difference between the two commits, and between green and red.

The runner's pass count (1996) is lower than this machine's (2091) because
those runs were on `main` at the `label-corrections` merge, five commits behind
this branch and carrying fewer tests — not because the runner behaves
differently. The error is identical.

**Nothing was tuned away in the round that found this.** The fix landed in the
next one: `pyproject.toml` gained the `[mcp]` group, both MCP test modules
gained a working guard, and CI and the `Dockerfile` now install `.[dev,mcp]`.
`NEEDS.md` **evidence round B.1** is the finding; **presentation round P.1** is
the fix.

**The obvious guard was a no-op, and that is the part worth reading.**
`pytest.importorskip("mcp")` — copied from `test_server.py` — did not skip.
`tests/mcp/` has no `__init__.py`, and pytest's prepend import mode puts
`tests/` on `sys.path`, so that directory *is* a PEP 420 namespace package
named `mcp`. Measured with site-packages stripped from `sys.path`:

```
find_spec(mcp)      -> FOUND
  loader             None
  search locations   ['.../tests/mcp']
  mcp.types?         False
```

Which is why the error above reads `No module named 'mcp.types'` and never
`No module named 'mcp'`: the top-level name always resolved. The guard is now on
`mcp.types`, which only the real SDK provides. **`test_server.py` carried the
same dead guard** and nobody could have noticed, because its `anyio` check skips
first on every machine anyone tried.

---

## Expected output and runtime

Once `mcp` is declared, `docker run --rm crafty-repro` should print:

| Stage | Expected | Runtime |
|---|---|---|
| `docker build` | base image + ngspice + `pip install -e ".[dev]"` | 2–4 min cold, seconds cached |
| FAST tier | `2146 passed` (0 skipped, 0 errors) | ~20–35 s at `-n 4` |
| Benchmark, dev split | `1282/1400 (91.6%)`, catch `99.1%`, FA `0.86%`, FR `0.4%` | ~20–90 s at `--workers 4` |

The image installs `.[dev,mcp]`, so it should reach `2146 passed`. The benchmark
numbers are the ones to check against; the case-set digest `476976c1…` must
match, and a run that prints a different digest is a run against different
cases, not a different result. **The image itself is still unbuilt** — see
`NEEDS.md` evidence round B.2.

Runtimes were measured on a 24-core host at `-n 4` / `--workers 4`. Both worker
counts are fixed rather than `auto` on purpose: memory grows ~200 MB per worker
and `-n auto` on a large machine walks into the exhaustion documented in
[TESTING.md](TESTING.md).

---

## Running it without Docker

```bash
pip install -e ".[dev]"
python -m pytest -m "not expensive" -q -n 4 --dist loadfile
python benchmarks/hard/score_hard.py --src src \
  --cases benchmarks/hard/cases_hard --workers 4 --split dev
```

On Linux, add `CRAFTY_NGSPICE_ARGV=ngspice` and the three Windows-only
deselections listed in [TESTING.md](TESTING.md) before running the SCIENTIFIC
tier; the FAST tier launches no provider and needs neither.

The default `--split` is `all`, which contains the sealed 600-case hold-out and
**exits non-zero** without `--open-holdout`. That is the seal working. See
[benchmarks/hard/README.md](../benchmarks/hard/README.md).
