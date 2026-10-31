# PUBLIC SYNTHETIC workload only. No Forge imports, roots, worlds or results.
# Identical search budgets/operators to the two arms. Only method specializations
# survive via PackageCompiler trace statements; no hall-of-fame/search state.
using SymbolicRegression
using Random
function public_workload()
    x = Float32.(range(1, 3; length=32))
    X = permutedims(hcat(x, 1 .+ sin.(x).^2))
    for units in (false, true)
        y = units ? log.(2 .+ X[1, :] ./ X[2, :]) : 2 .+ X[1, :] ./ X[2, :]
        options = Options(binary_operators=[+, -, *, /], unary_operators=[exp, log],
                          populations=8, population_size=33, maxsize=units ? 20 : 15,
                          deterministic=true, seed=0)
        equation_search(X, y; niterations=40, options=options, parallelism=:serial,
                        variable_names=["x0", "x1"], return_state=true, verbosity=0, progress=false,
                        X_units=units ? ["m", "m"] : nothing, y_units=units ? "1" : nothing)
    end
    nothing
end
public_workload()
