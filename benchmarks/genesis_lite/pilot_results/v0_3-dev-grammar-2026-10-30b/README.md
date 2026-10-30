# EXC-4 second development pilot: grammar enumeration with a sealed root (2026-10-30)

**DEVELOPMENT_DESCRIPTIVE.** Counts and means only. No interval, test, rate, lift, ranking, novelty or superiority
claim. Not a formal campaign, not a preregistration, not Blindfold evidence. Owner decision "Second pilot" (ACTIVE_PLAN
EXC-4). The first pilot (`../v0_3-dev-grammar-2026-10-30/`) stays as recorded.

## Run

- Code: `a5c343f01f7829a030ca87ab146ce273b6ac4017` (clean clone), development identity
  `3cd8c9f38d48d473f14db0f1908bc39820f2c09c3b40b748eed29555bd4a2fe1` (same arm code as the first pilot).
- WSL2 Ubuntu 24.04, Python 3.12.3, `/opt/forge-mvp-20261028/.venv`, `PYTHONPATH=<clone>/src:<clone>`, BLAS threads 1,
  4 workers. Driver outside the tree calling `pilot_v3.run_pilot(all_arms(), workers=4, deadline_seconds=2700,
  fractions=(1.0,), root=<file>)`.
- Root: 32 random bytes written to a 0600 file outside the tree before the run; commitment SHA-256
  `1dd61e16f96c783c91f07f75099ad0a19af451d04fd6235570be6435f53c6d1c` (matches `environment.json`).
  Revealed after the run: `d9a6bc8a6e70a95f6c589ede2cadd84243dbe5c235dbe0f48e1f0378b7903a99`.
- 2520/2520 campaigns, 0 worker failures, all 21 arms 120/120 VALID, 1079.0 s.
- An earlier attempt with the same root failed at worker bootstrap in 1.8 s (driver lacked a `__main__` guard under
  spawn); no campaign ran and no world was revealed, so the root was reused.
- `runs.jsonl` (outside the tree, `/home/dev_kaeem/exc4-evidence/runs-b.jsonl`): digest in `runs.jsonl.sha256`.
- `expressibility.json`: `python -m benchmarks.genesis_lite.expressibility_v3 --runs runs.jsonl --root-file <root> --out ...`
  (every run universe re-derived from the root; kinds matched). `contrasts.json`: the same contrasts from records only.

## Expressibility of the hidden law in the five-shape grammar (by fit; NOT_FOUND is an upper bound, not a proof)

| Kind | EXPRESSIBLE_BY_FIT | NOT_FOUND_BY_FIT | other |
|---|---:|---:|---|
| discoverable | 89 | 31 | |
| indistinguishable | 56 | 64 | |
| insufficient_evidence | 88 | 32 | |
| spurious_correlate | 93 | 27 | |
| confounded | | | 120 OUTSIDE_GRAMMAR |
| no_solution | | | 120 NO_LAW |

## Mean credit, selected arms (120 worlds per kind)

| Arm | discoverable | confounded | no_solution | insufficient_evidence | spurious_correlate |
|---|---:|---:|---:|---:|---:|
| grammar_enumeration | 0.350 | 0.717 | 0.742 | 0.942 | 0.217 |
| mind_full | 0.292 | 0.842 | 0.775 | 0.992 | 0.183 |
| pysindy_stlsq | 0.217 | -0.183 | 0.650 | 0.900 | -0.042 |
| careful | 0.183 | 0.642 | 0.717 | 0.917 | 0.125 |
| monomial_enumeration | 0.175 | -0.075 | 0.975 | 0.775 | 0.033 |
| pysr_symbolic | 0.000 | -0.058 | 0.550 | 0.642 | 0.008 |

## Contrasts (paired by universe id)

(i) grammar minus monomial, discoverable: all 120, +0.175 (21 ahead, 1 behind); in the monomial family 55, +0.036
(3/1); outside it 65, +0.292 (18/0), split into grammar-expressible 34, +0.324 (11/0) and not found in the grammar 31,
+0.258 (7/0).

(ii) grammar minus PySR: all kinds 720, +0.320 (235/6); discoverable 120, +0.350 (42/0).

(iii) false laws on controls: 0/120 for grammar_enumeration, careful and mind_full on each of no_solution, confounded
and insufficient_evidence.

Grammar answers on discoverable worlds: 76 insufficient_evidence, 42 law, 2 confounded.

## Reading limits

- **Representation circularity (owner H2):** 89 of 120 discoverable laws are reproduced by some enumerated shape; three
  of the five shapes overlap the generator's families. Credit on these worlds is not evidence of general discovery.
- On the 31 out-of-family laws **not** found in the grammar the arm still earns +0.258 over monomial (7 ahead): an
  approximating shape can pass the accuracy rule. That is the scoring rule's tolerance, not exact recovery.
- Both pilots agree in direction: grammar_enumeration has the highest discoverable mean, above mind_full
  (0.275 vs 0.200, then 0.350 vs 0.292). A later Mind lift has to be measured against this baseline.
- PySR is the registered development configuration (see the EXC-5 draft).
