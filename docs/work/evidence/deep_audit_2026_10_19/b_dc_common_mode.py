"""Independent derivation (stdlib only): DC MNA componentwise residual gate under common-mode offset.

Re-states, from first principles, the formulas of
  src/engcore/domains/electrical/dc/validation.py:check_linear_residual (lines 294-316) and check_kcl (338-398)
for one circuit and evaluates them on a deliberately corrupted solution vector. No FORGE code is imported.

Circuit: node a held at Vcm + dV by ideal source S1 (a -> ref), node c held at Vcm by S2 (c -> ref),
R1 = R between a and m, R2 = R between m and c. Unknowns x = [Va, Vc, Vm, i1, i2] (node order sorted a, c, m).
"""
from fractions import Fraction as F

def gates(Vcm, dV, R, delta, rtol=F(1, 10**9), atol=F(1, 10**9)):
    G = 1 / R
    Va, Vc = Vcm + dV, Vcm
    Vm_true = Vcm + dV / 2
    i = (Va - Vm_true) / R          # current a -> m -> c
    # MNA: KCL rows "sum leaving = 0"; source branch current i_k defined leaving + node through source
    # node a: G(Va - Vm) + i1 = 0 -> i1 = -i ; node c: G(Vc - Vm) + i2 = 0 -> i2 = +i
    i1, i2 = -i, i
    Vm = Vm_true + delta            # corrupted midpoint, source currents left as solved
    nodes = ["a", "c", "m"]
    # matrix rows (node a, node c, node m, src1, src2) x cols (Va, Vc, Vm, i1, i2)
    A = [[G, 0, -G, 1, 0],
         [0, G, -G, 0, 1],
         [-G, -G, 2 * G, 0, 0],
         [1, 0, 0, 0, 0],
         [0, 1, 0, 0, 0]]
    z = [0, 0, 0, Va, Vc]
    x = [Va, Vc, Vm, i1, i2]
    r = [sum(A[k][j] * x[j] for j in range(5)) - z[k] for k in range(5)]
    scale = [sum(abs(A[k][j]) * abs(x[j]) for j in range(5)) + abs(z[k]) for k in range(5)]
    node_floor = atol * max(scale[0:3]); src_floor = atol * max(scale[3:5])
    tol = [rtol * scale[k] + (node_floor if k < 3 else src_floor) for k in range(5)]
    residual_pass = all(abs(r[k]) <= tol[k] for k in range(5))
    # KCL at m rebuilt from components (check_kcl): gross = sum |branch|
    b1 = (Vm - Va) / R; b2 = (Vm - Vc) / R
    net, gross = b1 + b2, abs(b1) + abs(b2)
    current_scale = max(abs(Va - Vm) / R, abs(Vm - Vc) / R, abs(i1), abs(i2))
    kcl_tol = rtol * gross + atol * current_scale
    kcl_pass = abs(net) <= kcl_tol
    rel_current_error = abs(((Va - Vm) / R) - i) / abs(i)
    return residual_pass, kcl_pass, float(rel_current_error), float(abs(r[2])), float(tol[2])

for Vcm in (F(0), F(1000), F(10**6)):
    rp, kp, err, res, tol = gates(Vcm, dV=F(1, 1000), R=F(1), delta=F(1, 10**4))
    print(f"Vcm={float(Vcm):>9g} V  dV=1 mV  delta(Vm)=0.1 mV -> branch current error {err:.0%}; "
          f"row-m |r|={res:.3e} tol={tol:.3e} residual_gate_PASS={rp}  KCL_PASS={kp}")
