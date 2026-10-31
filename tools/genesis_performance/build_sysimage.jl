# The workload file executes in a tracing subprocess: fitted state is NOT saved.
using PackageCompiler
VERSION == v"1.11.9" || error("wrong Julia binary")
Base.pkgversion(PackageCompiler) == v"2.4.4" || error("wrong PackageCompiler")
project, destination, mode, cpu_target = ARGS
mode in ("packages", "functions") || error("unknown build mode")
ENV["JULIA_CC"] = "/opt/forge-mvp-20261028/.venv/bin/python " * joinpath(@__DIR__, "link_sysimage.py")
options = mode == "functions" ? (;precompile_execution_file=joinpath(@__DIR__, "precompile_workload.jl")) : (;)
create_sysimage([:SymbolicRegression, :PythonCall]; project=project,
                sysimage_path=destination, cpu_target=cpu_target, incremental=true,
                sysimage_build_args=`--threads=1`, options...)
