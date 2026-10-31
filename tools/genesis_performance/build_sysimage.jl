# The workload file executes in a tracing subprocess: fitted state is NOT saved.
using PackageCompiler
using GCCBootstrap_jll
VERSION == v"1.11.9" || error("wrong Julia binary")
Base.pkgversion(PackageCompiler) == v"2.4.4" || error("wrong PackageCompiler")
project, destination, mode = ARGS
mode in ("packages", "functions") || error("unknown build mode")
ENV["JULIA_CC"] = joinpath(GCCBootstrap_jll.artifact_dir, "bin", "x86_64-linux-gnu-gcc")
isfile(ENV["JULIA_CC"]) || error("compiler not found: inspect isolated toolchain artifact")
options = mode == "functions" ? (;precompile_execution_file=joinpath(@__DIR__, "precompile_workload.jl")) : (;)
create_sysimage([:SymbolicRegression, :PythonCall]; project=project,
                sysimage_path=destination, cpu_target="generic", incremental=true,
                sysimage_build_args=`--threads=1`, options...)
