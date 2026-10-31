#!/bin/bash
set -euo pipefail
# Fresh environment: PackageCompiler error messages must not dump operator env.
build=/opt/forge-sysimage-build-20261031
venv=/opt/forge-mvp-20261028/.venv
mkdir -p "$build/home"
exec /usr/bin/env -i PATH=/usr/bin:/bin HOME="$build/home" \
    JULIA_DEPOT_PATH="$build/depot:/opt/julia-depot-20261031" \
    JULIA_NUM_THREADS=1 JULIA_NUM_GC_THREADS=1 JULIA_NUM_PRECOMPILE_TASKS=1 JULIA_IMAGE_THREADS=4 \
    OPENBLAS_NUM_THREADS=1 JULIA_PYTHONCALL_EXE="$venv/bin/python" JULIA_CONDAPKG_BACKEND=Null \
    "$venv/julia_env/pyjuliapkg/install/bin/julia" --startup-file=no --project="$build/compiler" \
    "$build/build_sysimage.jl" "$build/project" "$@"
