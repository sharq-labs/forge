# EXC-4 development pilot: grammar enumeration baseline (2026-10-30)

**DEVELOPMENT_DESCRIPTIVE.** Counts and means only. No interval, test, rate, lift, ranking, novelty or superiority
claim. Not a formal campaign, not a preregistration, not Blindfold evidence.

## Run

- Code: `e5af5f55eafc1373d1bf934f8e4ca3e758f49e6b` (clean clone `/home/dev_kaeem/forge-exc4-e5af5f55`),
  development identity `3cd8c9f38d48d473f14db0f1908bc39820f2c09c3b40b748eed29555bd4a2fe1`; v0.2 pins unchanged.
- WSL2 Ubuntu 24.04, Python 3.12.3, `/opt/forge-mvp-20261028/.venv` with `PYTHONPATH=<clone>/src:<clone>` (engcore
  import checked from the clone), BLAS/Julia threads 1 per worker, 4 workers, 20 CPUs.
- `python -m benchmarks.genesis_lite.pilot_v3 --out <dir> --arms all --workers 4 --deadline-seconds 2700 --budget-fractions 1.0`
- 2520/2520 campaigns, 0 worker failures, all 21 arms 120/120 VALID, 1085.5 s (inside the 45-minute cap).
- Fresh root from `secrets` after the code commit; commitment SHA-256
  `9036c6fd3b2567fb90419effc141bc0648d67f272e81dce313e8129e6686632e`.
- `runs.jsonl` (14 MB) kept outside the tree at `/home/dev_kaeem/exc4-evidence/runs.jsonl`; digest in `runs.jsonl.sha256`.
- Contrasts: `contrasts.json`, computed from the run records only by a session-scratch script equivalent to
  `expressibility_v3.report` without the expressibility part.

## Not available: per-world grammar expressibility

`pilot_v3.run_pilot` draws the root in-process and stores only its commitment. The root was never written, so the
worlds cannot be re-derived and `expressibility_v3` cannot run on this pilot. **EXC-4 exit condition "per-world grammar
expressibility" is NOT MET.** Recovering it needs a pilot that reveals its root after sealing, which is a new run and
an owner decision.

## Results (120 worlds per kind, paired by universe id)

Mean credit, selected arms:

| Arm | discoverable | confounded | no_solution | insufficient_evidence | spurious_correlate |
|---|---:|---:|---:|---:|---:|
| grammar_enumeration | 0.275 | 0.667 | 0.750 | 0.933 | 0.258 |
| mind_full | 0.200 | 0.792 | 0.750 | 0.992 | 0.242 |
| careful | 0.150 | 0.633 | 0.750 | 0.900 | 0.183 |
| pysindy_stlsq | 0.142 | -0.217 | 0.642 | 0.958 | -0.050 |
| monomial_enumeration | 0.092 | -0.133 | 0.975 | 0.767 | 0.167 |
| pysr_symbolic | 0.008 | -0.108 | 0.592 | 0.608 | -0.008 |

(i) grammar minus monomial, discoverable: all 120, mean +0.183 (22 better, 3 worse, 95 tied); in the monomial family
51, +0.020 (4/3/44); outside it 69, +0.304 (18 better, 0 worse, 51 tied).

(ii) grammar minus PySR: all kinds 720, +0.312 (220/10/490); discoverable 120, +0.267 (32/0/88).

(iii) false laws (answer `law` or `indistinguishable`) on controls: 0/120 for grammar_enumeration, careful and
mind_full on each of no_solution, confounded and insufficient_evidence.

Grammar answers on discoverable worlds: 86 insufficient_evidence, 33 law, 1 no_law.

## Reading limits

- **Representation circularity (owner H2 disclosure):** the grammar is five declared shapes, three of which overlap the
  Blindfold generator's families. The out-of-family gain may reflect that overlap, not general discovery ability.
  Without the expressibility split this cannot be separated.
- A baseline (grammar_enumeration) has a higher discoverable mean than mind_full here. Any later Mind lift claim must
  be measured against it.
- PySR runs the registered development configuration (see the EXC-5 draft); its low score is not shown to be intrinsic.
