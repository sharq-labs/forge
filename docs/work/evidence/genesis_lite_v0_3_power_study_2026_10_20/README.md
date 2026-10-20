# Genesis-lite v0.3: power and null-calibration study (ODC-O1b), 2026-10-20

**Status:** NON-FORMAL, SYNTHETIC. This is evidence for the owner about the v0.3 statistical rule. It is not a measurement of
any arm, and not a lift result. No hidden world, pilot record or formal root was read.

**Authorisation:** owner D2 (2026-10-20), run after D3 (decided 2026-10-20).

**Provenance:**
- Run at HEAD `27a5d6db` (`feat/genesis-lite-v03-amendment-draft`), with `benchmarks/genesis_lite/v0_3/power_study.py`
  sha256 `23e459a44fd646de8afe5b575bb47a6244695e27e7cd71ea76b4e47a30655957` (uncommitted at run time, committed unchanged next).
- The draft preregistration at run time had sha256 `b57d7775fbde30b12bc50b480eb9395bdfa74d63d3e508493e354b15e0fb4707`.
- Environment: Windows venv, Python 3.14.
- Command:
  `python -m benchmarks.genesis_lite.v0_3.power_study --out <result.json> --reps 100 --null-reps 2000 --workers 4`.
- Exit code 0, wall time 1,366 s. The raw output is [`result.json`](result.json).

**Method:** see the module docstring.
- Part A applies the D2 statistic with a fresh root-keyed stream per replicate, at the formal sizes (600 / 2,400 world sets).
- Part B applies `lift_decision` itself to synthetic records:
  - arms: `careful`, `monomial_enumeration` and a candidate;
  - per-universe Bernoulli credits of ±1;
  - candidate coupled to `careful` through a shared uniform with probability rho.
- The "statistical claim" is `lift_claimed` without the identity and binding problems that every synthetic run must have.
- The bootstrap is vectorised (same B and order statistic). Two cells were re-run with the original: claims and pooled means are identical.

## Part A: null calibration (D2 statistic)

| null | n | alpha 0.01 | alpha 0.05 | alpha 0.10 | Holm FWER (5-member family) |
|---|---|---|---|---|---|
| exchangeable (in scope), 2,000 reps | pooled 2,400 | 0.0095 | 0.0490 [0.040, 0.059] | 0.0925 | 0.045 [0.036, 0.055] |
| exchangeable, 2,000 reps | presentation 600 | 0.0100 | 0.0465 | 0.0900 | |
| skewed mean-zero (out of scope), 1,000 reps | pooled 2,400 | 0.0130 | 0.0630 [0.049, 0.080] | 0.1080 | 0.043 |
| skewed mean-zero, 1,000 reps | presentation 600 | 0.0070 | 0.0390 | 0.0980 | |

Brackets are exact 95 % Clopper-Pearson intervals.
- The in-scope null is calibrated.
- The out-of-scope skewed null is mildly anti-conservative at the pooled level (0.063). This is consistent with the null
  scope the owner accepted in D2.

## Part B: power of the whole v0.3 decision (100 reps per cell)

`careful`: discoverable success 0.2. The candidate's discoverable rate is 0.2 + delta, and it is equal to `careful` on
every other kind.

| controls (careful's rate) | delta | rho 0 | rho 0.5 | rho 0.9 | rho 1.0 |
|---|---|---|---|---|---|
| solved (0.8 → CONTROL_SOLVED) | 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| solved | 0.05 | 0.00 | 0.00 | 0.00 | 1.00 |
| solved | 0.10 | 0.00 | 0.00 | 0.49 | 1.00 |
| solved | 0.20 | 0.00 (pooled mean −1.20) | 0.00 | 1.00 | 1.00 |
| unsolved (0.4) | 0 | 0.01 | 0.00 | 0.02 | 0.00 |
| unsolved | 0.05 | 0.20 | 0.41 | 0.98 | 1.00 |
| unsolved | 0.10 | 0.63 | 0.94 | 1.00 | 1.00 |
| unsolved | 0.20 | 0.69 | 0.99 | 1.00 | 1.00 |

Two further cells:
- unsolved, delta 0.2, rho 1, with 30 % of the truths out of family: 1.00 (pooled mean +0.28).
- unsolved, delta 0.2, rho 1, with the representation arm solving discoverable at 0.8: 0.00, by design (§10.3).

## Findings

1. **False claims stay at or below alpha.**
   - At delta = 0, 3 claims in 800 decisions; no cell is above 2/100.
   - The D2 statistic is calibrated under its stated null.
2. **The cap form decides the claimable region (owner question D3b(a)).**
   - The FDA-06 / CONTROL_SOLVED cap is a per-world-set `min(mine, theirs)`, as in v0.2.
   - In a capped cell the candidate loses every world set the baseline solved and it missed, and gains nothing back. The
     cell contributes −E[(ref − mine)⁺] < 0. Under independence that is −2·p·(1−p) per capped kind.
   - With solved controls, a candidate that is not a near-copy of `careful` (rho ≤ 0.5) never claims. This holds even
     when it doubles discoverable success: pooled mean −1.20, claim 0/100.
   - Claims need rho ≥ 0.9, i.e. world-by-world dominance on the capped cells.
   - The rule never gives false support, but it is far stricter than §10.5 ("cannot support a lift claim for that class").
3. **The kind non-inferiority conjunction caps power (owner question D3b(b)).**
   - With independent outcomes and equal skill, each kind's 0.10 margin is about 3.5 standard errors (SE ≈ 0.028). The
     95 % lower bound fails it about 6 % of the time per kind, so about 30 % across six kinds.
   - As a result, power saturates near 0.7 at rho = 0 even for delta = 0.2.
   - Diagnosed by re-scoring 30 replicates: the per-kind standard deviation of the mean matches the binomial SE.
