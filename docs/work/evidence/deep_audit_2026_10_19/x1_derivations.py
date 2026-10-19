from fractions import Fraction as F
# C-01: dx/dt=1, two committing nodes each integrating plan [0,10] from committed state
x, t = F(0), F(0)
for node in range(2):
    start, end = F(0), F(10)        # plan window fixed at authority construction
    x = x + (end - start)           # run integrates from committed values over plan window
    assert end >= t                 # state.advance only refuses backwards time
    t = end
print("C-01 committed t=%s x=%s exact x(t)=%s" % (t, x, t))
# C-02: explicit staggered, source q_n = n W, dt=1 s, 6 windows; target consumes previous window value
q = [F(n) for n in range(6)]
recorded = [abs(q[n] - q[n]) for n in range(6)]              # SOURCE vs RECEIVED of same transfer
consumed = [F(0)] + q[:-1]
print("C-02 recorded residuals", [str(r) for r in recorded], "emitted", sum(q), "consumed", sum(consumed), "gap", sum(q)-sum(consumed))
# relaxation: RECEIVED = x_prev + w*(H - x_prev); SOURCE = H
w, H, xp = F(1,2), F(100), F(100) - F(1,10**6)
print("C-02 relaxed single-edge residual (1-w)|H-xprev| =", float(abs(H - (xp + w*(H-xp)))))
