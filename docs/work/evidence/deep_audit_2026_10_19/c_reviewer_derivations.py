"""Reviewer C independent derivations (stdlib only, no FORGE code).

C-01: a committed state relabelled in time.  A participant integrates dx/dt = 1.
Two committing nodes each delegate to a run whose plan is fixed at [0, 10] s
(the plan fingerprint is part of the authority identity, so the run window
cannot follow the state clock).  The executor only refuses t_new < t_state.

C-02: per-window conservation on a lagged edge.  Explicit staggered coupling,
source power q_n = n W in window n (dt = 1 s).  The runtime's balance reads
SOURCE and RECEIVED from the same TransferResult of window n; the target
actually advanced window n with the value transferred in window n-1.
"""
from fractions import Fraction as F


def c01():
    print("C-01 time relabel")
    state_t, x = F(0), F(0)
    for node in ("A", "B"):
        plan_start, plan_end = F(0), F(10)
        # run integrates over the PLAN window from the state's VALUE
        x_new = x + (plan_end - plan_start) * 1
        t_new = plan_end
        refused = t_new < state_t          # SystemState.advance: only backwards motion is refused
        print(f"  node {node}: state t={state_t}, x={x}; run [{plan_start},{plan_end}] -> "
              f"commit t={t_new}, x={x_new}; refused={refused}")
        state_t, x = t_new, x_new
    print(f"  final committed state: t={state_t} s, x={x}; exact x(t={state_t}) = {state_t}")
    # variant: plan later than state clock
    state_t, x = F(0), F(0)
    plan_start, plan_end = F(100), F(200)
    print(f"  variant: state t=0 x=0, run [{plan_start},{plan_end}] -> commit t={plan_end} x={x + 100}; "
          f"exact x(200)={200}; refused={plan_end < state_t}")


def c02(n_windows=6):
    print("C-02 lagged-edge conservation")
    q = [F(n) for n in range(n_windows)]   # source output per window (W), dt = 1 s
    seed = F(0)
    total_emitted = total_consumed = F(0)
    for n in range(n_windows):
        transferred = q[n]                 # identity transfer, efficiency 1
        runtime_residual = abs(q[n] - transferred)   # |SOURCE - RECEIVED| of the same TransferResult
        consumed = seed if n == 0 else q[n - 1]      # lagged target reads the window-start edge value
        total_emitted += q[n]
        total_consumed += consumed
        print(f"  window {n}: emitted {q[n]} J, target consumed {consumed} J, "
              f"recorded residual {runtime_residual} J, actual interface imbalance {q[n] - consumed} J")
    print(f"  run totals: emitted {total_emitted} J, consumed {total_consumed} J, "
          f"imbalance {total_emitted - total_consumed} J; every recorded residual 0")


if __name__ == "__main__":
    c01()
    c02()
