import math, sys
def cols(n, k):
    out = []
    for c in range(k):
        s = 2*c+1
        while math.gcd(s, n) != 1: s += 2
        out.append([((i*s + c) % n + 0.5)/n for i in range(n)])
    return out
def r(a, b):
    ma, mb = sum(a)/len(a), sum(b)/len(b)
    num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    return num / math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
for n, k in ((4, 3), (32, 2), (32, 17)):
    C = cols(n, k)
    worst = min(((r(C[i], C[j]), i, j) for i in range(k) for j in range(i+1, k)))
    print(n, k, "most negative r=%.6f cols %d,%d" % worst, "r01=%.4f" % r(C[0], C[1]))
# E-01: type-7 quantile on midpoint lattice
for n in (4, 32):
    p = 0.025; h = p*(n-1); lo = (h+0.5)/n
    print(n, "covered mass", 1-2*lo, "formula", 0.95-0.95/n)
