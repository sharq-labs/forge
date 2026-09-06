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

## Result 2 — the FAST tier does **not** reproduce, and that is the finding

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

**By inference, not measurement:** the `fast` CI job installs `pip install -e
".[dev]"` on a bare `ubuntu-latest` runner — the same declared set, and the same
absent `mcp` — so it must hit the same collection error. That has not been
observed here; no CI run was available to check.

**Nothing was tuned away.** No dependency was added, no test was edited, no
guard was inserted. The `Dockerfile` installs exactly what the project declares
and will fail at the same line, which is why the `reproduce` CI job carries
`continue-on-error: true` with a comment naming the commit that should remove
it. The finding is recorded in `NEEDS.md`, evidence round, **B.1**. Closing it
is a change to `pyproject.toml` and `tests/mcp/test_battery_boundary.py`, and
this round owned neither.

---

## Expected output and runtime

Once `mcp` is declared, `docker run --rm crafty-repro` should print:

| Stage | Expected | Runtime |
|---|---|---|
| `docker build` | base image + ngspice + `pip install -e ".[dev]"` | 2–4 min cold, seconds cached |
| FAST tier | `2146 passed` (0 skipped, 0 errors) | ~20–35 s at `-n 4` |
| Benchmark, dev split | `1282/1400 (91.6%)`, catch `99.1%`, FA `0.86%`, FR `0.4%` | ~20–90 s at `--workers 4` |

**Today it prints `2091 passed, 1 skipped, 1 error` and exits non-zero at the
FAST stage.** The benchmark numbers are the ones to check against; the case-set
digest `476976c1…` must match, and a run that prints a different digest is a run
against different cases, not a different result.

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
