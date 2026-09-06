# A buyer's first technical question is whether this runs anywhere but the
# author's laptop. This image answers it from a bare base: install, FAST tier,
# benchmark score, no host state.
#
#     docker build -t crafty-repro . && docker run --rm crafty-repro
#
# See docs/reproduce.md for the expected output and the runtime.

# Pinned to a minor version, not `latest` and not `3`. A base image that
# floats is a base image that can move a number without anyone touching the
# code, which is the exact failure this whole round exists to close.
FROM python:3.12-slim-bookworm

# ngspice is installed so that NOTHING is skipped. The FAST tier does not
# launch the provider -- tests/conftest.py keeps the process-launching
# ngspice tests in the `expensive` tier and only the source-reading ones in
# FAST -- but the SCIENTIFIC tier does, and an image that could not run it
# would be answering a smaller question than the one that was asked.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ngspice git \
 && rm -rf /var/lib/apt/lists/*

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
RUN pip install --no-cache-dir -e ".[dev]"

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
RUN printf '%s\n' \
  '#!/bin/sh' \
  'set -e' \
  'echo "== environment =="' \
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
