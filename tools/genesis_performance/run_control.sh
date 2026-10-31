#!/bin/bash
# Public development software controls only. No formal root read or generated.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
venv=/opt/forge-mvp-20261028/.venv
export PYTHONPATH="$PWD/src" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
configuration=$1
shift
extra=()
extra_expose=()
depot=/tmp/jdepot:/opt/julia-depot-20261031
if [[ "$configuration" != baseline ]]; then
    extra+=(PYTHON_JULIACALL_THREADS=1 JULIA_NUM_GC_THREADS=1)
fi
if [[ "$configuration" == sysimage-* ]]; then
    extra+=("PYTHON_JULIACALL_SYSIMAGE=/opt/forge-sysimage-20261031/${configuration#sysimage-}.so")
fi
if [[ "$configuration" == cache ]]; then
    depot=/tmp/jdepot:/opt/forge-julia-cache-20261031:/opt/julia-depot-20261031
    extra+=(FORGE_JULIA_CACHE=/opt/forge-julia-cache-20261031)
    extra_expose+=(/opt/forge-julia-cache-20261031)
fi
exec "$venv/bin/python" -m benchmarks.genesis_lite.performance_v4 "$@" \
    --expose /opt/julia-depot-20261031 /opt/forge-sysimage-20261031 "${extra_expose[@]}" \
    --env "PYTHON_JULIACALL_PROJECT=$venv/julia_env" \
    "PYTHON_JULIACALL_EXE=$venv/julia_env/pyjuliapkg/install/bin/julia" \
    "JULIA_DEPOT_PATH=$depot" PYTHON_JULIAPKG_OFFLINE=yes JULIA_NUM_THREADS=1 \
    FORGE_PERF_DIAGNOSTICS="${FORGE_PERF_DIAGNOSTICS:-0}" FORGE_PERF_RESOURCES=1 "${extra[@]}"
