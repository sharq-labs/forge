# Owner-approved separate build environment; never Pkg.add into the experiment.
using Pkg
VERSION == v"1.11.9" || error("expected pinned Julia 1.11.9")
build = "/opt/forge-sysimage-build-20261031"
get(ENV, "JULIA_DEPOT_PATH", "") == build * "/depot:/opt/julia-depot-20261031" || error("wrong build depot")
Pkg.activate(build * "/compiler")
Pkg.add(PackageSpec(name="PackageCompiler", version="2.4.4"))
Pkg.add(PackageSpec(name="GCCBootstrap_jll", version="9.4.0"))
Pkg.pin(["PackageCompiler", "GCCBootstrap_jll"])
