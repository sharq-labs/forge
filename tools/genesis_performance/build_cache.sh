#!/bin/bash
set -euo pipefail
# Import-only compiler caches. Never reads a Forge world, root, result or fit.
venv=/opt/forge-mvp-20261028/.venv
cache=/opt/forge-julia-cache-20261031
mkdir -p "$cache" /opt/forge-sysimage-build-20261031/cache-home
exec /usr/bin/env -i PATH=/usr/bin:/bin HOME=/opt/forge-sysimage-build-20261031/cache-home \
    PYTHON_JULIACALL_PROJECT="$venv/julia_env" \
    PYTHON_JULIACALL_EXE="$venv/julia_env/pyjuliapkg/install/bin/julia" \
    PYTHON_JULIACALL_THREADS=1 JULIA_NUM_THREADS=1 JULIA_NUM_GC_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    JULIA_DEPOT_PATH="$cache:/opt/julia-depot-20261031" PYTHON_JULIAPKG_OFFLINE=yes \
    "$venv/bin/python" -c 'import pysr; from pysr.julia_import import jl; print(jl.VERSION, jl.seval("Threads.nthreads()"))'
