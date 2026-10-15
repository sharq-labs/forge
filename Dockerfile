# A buyer's first technical question is whether this runs anywhere but the
# author's laptop. This image answers it from a bare base: install, FAST tier,
# benchmark score, no host state.
#
#     docker build -t crafty-repro .
#     docker run --rm -v "$PWD/.git:/crafty/.git:ro" crafty-repro
#
# The image carries no history (.dockerignore drops .git), but the FAST tier
# reads it: the certificate, freeze-manifest and replay tests resolve the
# repository root, HEAD and committed snapshots such as V1's at af43c896. So
# the checkout's own FULL history (not a depth-1 clone) is mounted read-only
# at run time; the reproduce script refuses to start without it.
#
# See docs/reproduce.md for the expected output and the runtime.

# Pinned to a minor version, not `latest` and not `3`. A base image that
# floats is a base image that can move a number without anyone touching the
# code, which is the exact failure this whole round exists to close.
#
# trixie, not bookworm, for ngspice. Bookworm ships ngspice-39, whose batch
# mode exits 1 after a correct `.control` / `op` / `print` run ("No .plot ...
# lines; no simulations run"): src/main.c only learned to read `sim_status`
# in later releases. ngspice-42 (the hosted runner, the author's WSL) and
# trixie's 44.2+ds-1 share the same batch-exit block and exit 0, so
# tests/oracles/test_oracle_ngspice_dc.py keeps its returncode == 0 assertion.
FROM python:3.12-slim-trixie

# ngspice is installed so that NOTHING is skipped. Most process-launching
# ngspice tests sit in the `expensive` tier (tests/conftest.py), but the
# independent DC oracle runs in FAST whenever ngspice is on PATH, and the
# SCIENTIFIC tier launches the provider; an image that could not run them
# would be answering a smaller question than the one that was asked.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ngspice git \
 && rm -rf /var/lib/apt/lists/*

# The mounted .git belongs to the host user (uid 1001 on a GitHub runner)
# while the tests run as root, so git would otherwise refuse the repository as
# "dubious ownership". --system rather than --global so a test that points
# HOME elsewhere still sees it. This trusts exactly /crafty, nothing else.
RUN git config --system --add safe.directory /crafty

# The provider's default invocation is ("wsl.exe", "-e", "ngspice") -- the
# author's Windows host, src/engcore/domains/electrical/ngspice.py:191. On
# Linux it is discovered through this variable, which still carries the old
# product name; see docs/TESTING.md for why renaming it is deferred.
ENV CRAFTY_NGSPICE_ARGV=ngspice \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /crafty

# Dependency metadata first, so an edit to a case or a test does not invalidate
# the layer that downloads scipy.
COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
# Install every declared test/benchmark extra the reproducibility image can
# reach. A bare image must not accidentally rely on packages present on the
# author's host.
RUN pip install --no-cache-dir -e ".[dev,mcp,oracles,benchmarks]"

COPY . .

# One command, and it prints what it measured against as well as what it
# measured. The case-set digest and the split rule come from the scorer's own
# summary, so a run against different cases is visibly a different run.
#
# -n 4, not -n auto: the worker count must not track whatever hardware the
# image happens to land on. Memory grows ~200 MB per worker and `-n auto` on a
# large host walks into the exhaustion documented in docs/TESTING.md.
#
# --split dev: the hold-out stays sealed. Scoring it needs --open-holdout and
# writes a dated record; see benchmarks/hard/split_hard.py.
#
# The history checks fail closed before anything is measured: a run with no
# .git, a shallow one, or one whose HEAD does not describe the image's tree
# would turn history-reading tests red for a reason that is not the code's,
# or green against a commit the image was not built from.
RUN printf '%s\n' \
  '#!/bin/sh' \
  'set -e' \
  'if ! git rev-parse --verify -q HEAD >/dev/null; then' \
  '  echo "refused: no git history at /crafty/.git; run with -v <checkout>/.git:/crafty/.git:ro (docs/reproduce.md)" >&2' \
  '  exit 2' \
  'fi' \
  'if [ "$(git rev-parse --is-shallow-repository)" != false ]; then' \
  '  echo "refused: /crafty/.git is shallow; the freeze and certificate tests read full history (fetch-depth: 0)" >&2' \
  '  exit 2' \
  'fi' \
  'if [ -n "$(git status --porcelain --untracked-files=no)" ]; then' \
  '  echo "refused: the mounted HEAD does not describe this image tree:" >&2' \
  '  git status --short --untracked-files=no | head -20 >&2' \
  '  exit 2' \
  'fi' \
  'echo "== environment =="' \
  'echo "commit $(git rev-parse HEAD)"' \
  'python -c "import sys,platform; print(sys.version); print(platform.platform())"' \
  'ngspice --version 2>&1 | sed -n 2p' \
  'pip freeze | grep -Ei "^(numpy|scipy|scikit-learn|pint|pytest|pytest-xdist)=="' \
  'echo' \
  'echo "== FAST tier =="' \
  'python -m pytest -m "not expensive" -q -n 4 --dist loadfile' \
  'echo' \
  'echo "== benchmark, development split (hold-out sealed) =="' \
  'python benchmarks/hard/score_hard.py --src src \' \
  '  --cases benchmarks/hard/cases_hard --workers 4 --split dev \' \
  '  --results /tmp/results_dev.json' \
  > /usr/local/bin/reproduce && chmod +x /usr/local/bin/reproduce

CMD ["reproduce"]
