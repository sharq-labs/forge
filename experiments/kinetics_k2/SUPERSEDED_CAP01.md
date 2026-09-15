# K2 (multi-parameter inference): superseded by audit CAP-01

Status: **superseded**. The frozen records (docs/milestones/kinetics-k2-multiparameter-inference-prereg.md, experiments/kinetics_k2/k2_report.md) are not edited; they record what the study measured under the model record in force at its freeze. This note records why it no longer re-derives.

## Why

Audit CAP-01 (domains stream) tied the CSTR model's single-liquid-phase claim
to the declared fluid's boiling and freezing temperatures. The K-series code, as
frozen, declares neither, so every CSTR assessment it produces is UNKNOWN on the
liquid-phase conditions and the inference admissibility boundary refuses the
predictions ("applicability was assessed and not established").

Declaring the textbook liquid's real range does not rescue this study. The
domain declares it once, in `src/engcore/domains/kinetics/cstr/fluids.py`
(`SEBORG_TEXTBOOK_LIQUID`: a dilute aqueous liquid, 273.15-373.124 K at an
ASSUMED 101.325 kPa -- the textbook states no operating pressure), and a solved
run is assessed at the temperatures it actually reached. Measured at the frozen
truth coordinates (k0 = 1.2e9 1/s, E/R = 8750 K):

| condition | realised T_max | liquid? |
|---|---|---|
| K2 C1 | 300.65 K | yes |
| K2 C2 | 324.69 K | yes |
| K2 C3 | 524.44 K | **no -- boils** |
| K3 H1 | 506.64 K | **no -- boils** |
| K3 H2 | 310.59 K | yes |

## This study

K2's preregistered likelihood uses all three conditions C1-C3. C3's truth trajectory boils, so its predictions are refused and the study as preregistered cannot be re-derived. C1 and C2 are admitted (tests/domains/kinetics/test_k2_truth_admissibility.py asserts both halves).

A study that means a pressurised tank would have to declare its own fluid envelope and be re-preregistered; stretching the textbook liquid's range to admit these runs would be a declaration the source does not make.
