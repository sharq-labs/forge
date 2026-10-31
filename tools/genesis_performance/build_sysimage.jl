# The workload file executes in a tracing subprocess: fitted state is NOT saved.
using PackageCompiler
VERSION == v"1.11.9" || error("wrong Julia binary")
Base.pkgversion(PackageCompiler) == v"2.4.4" || error("wrong PackageCompiler")
project, destination, mode, cpu_target = ARGS[1:4]
mode in ("packages", "functions", "bridge") || error("unknown build mode")
length(ARGS) == (mode == "bridge" ? 5 : 4) || error("bridge mode requires the exact base image")
ENV["JULIA_CC"] = "/opt/forge-mvp-20261028/.venv/bin/python " * joinpath(@__DIR__, "link_sysimage.py")
options = mode == "functions" ? (;precompile_execution_file=joinpath(@__DIR__, "precompile_workload.jl")) : (;)
if mode == "bridge"
    # Only precompile statements enter this process, never Python fit state.
    options = (;base_sysimage=ARGS[5],
               precompile_statements_file=joinpath(@__DIR__, "bridge-statements.jl"))
end
create_sysimage([:SymbolicRegression, :PythonCall]; project=project,
                sysimage_path=destination, cpu_target=cpu_target, incremental=true,
                sysimage_build_args=`--threads=1`, options...)
