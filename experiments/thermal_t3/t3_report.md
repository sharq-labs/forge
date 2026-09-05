# T3 — Decision-aware fidelity escalation

Config hash: `f445c46be4aba5ab0108436bccba5ef1cabb50147cc255fe4ddbcd27124ac7d1`
Preregistration hash: `2d756f0abc376b51db248afbc1bcc29f2cc79878dfdeffa82e79d09f6b171688`
Base commit (T2 freeze): `4da598d5994fae09b202727228eb5b302cb60c01`

**Can a cost-aware decision rule determine when the current numerical fidelity is sufficient for a downstream scientific decision, and when paying for higher fidelity is necessary?**

1000 preregistered scenarios in four margin bands. Calibrate α on the 60 s observation; decide about the slab at 180 s (r = 3), a condition never assimilated.

## The premise, checked first

At the assimilated condition (r = 1) the three rungs' predictions span 5.07e-08 — they agree, which is T2's cancellation. At the terminal condition (r = 3) they span 1.69e-02, an amplification of **333472×**. The out-of-sample design works; had it not, nothing below would mean anything.

## Cost to correct decision

Nominal cost of a wrong decision: 3,276,800 work units (10× the reference rung).

| strategy | accuracy | mean work | wrong | CCD | vs policy |
|---|---|---|---|---|---|
| always coarse | 0.601 | 80 | 399 | 2,175,579 | 2.99× |
| always medium | 0.779 | 5,120 | 221 | 936,191 | 1.29× |
| always reference | 0.910 | 327,680 | 90 | 684,167 | 0.94× |
| **decision aware** | 0.874 | 222,124 | 126 | **726,546** | 1.00× |

## Escalation behaviour

| strategy | escalations | unnecessary | missed | incorrect confident |
|---|---|---|---|---|
| always coarse | 0 | 0 | 326 | 399 |
| always medium | 0 | 0 | 148 | 185 |
| always reference | 0 | 0 | 0 | 5 |
| decision aware | 1662 | 722 | 36 | 0 |

### Where the policy stopped

| band | coarse | medium | reference | accuracy | mean work |
|---|---|---|---|---|---|
| FAR | 0 | 250 | 0 | 1.000 | 5,200 |
| MODERATE | 0 | 12 | 238 | 1.000 | 317,151 |
| NEAR | 0 | 76 | 174 | 0.856 | 233,265 |
| UNDECIDABLE | 0 | 0 | 250 | 0.640 | 332,880 |

## Accuracy by band — is the benchmark rigged toward refinement?

| band | always coarse | always medium | always reference | decision aware |
|---|---|---|---|---|
| FAR | 1.000 | 1.000 | 1.000 | 1.000 |
| MODERATE | 0.480 | 1.000 | 1.000 | 1.000 |
| NEAR | 0.456 | 0.648 | 1.000 | 0.856 |
| UNDECIDABLE | 0.468 | 0.468 | 0.640 | 0.640 |

- in **FAR**, always coarse, always medium match(es) the reference rung's accuracy at a fraction of the cost
- in **MODERATE**, always medium match(es) the reference rung's accuracy at a fraction of the cost

## Numerical error relative to the decision margin

| band | coarse (median ratio / frac>1) | medium (median ratio / frac>1) | reference (median ratio / frac>1) |
|---|---|---|---|
| FAR | 0.51 / 0.00 | 0.06 / 0.00 | 0.01 / 0.00 |
| MODERATE | 3.28 / 1.00 | 0.38 / 0.00 | 0.05 / 0.00 |
| NEAR | 15.04 / 1.00 | 1.74 / 1.00 | 0.22 / 0.00 |
| UNDECIDABLE | 151.24 / 1.00 | 17.49 / 1.00 | 2.16 / 1.00 |

A ratio above 1 means the rung's numerical error alone is larger than the distance to the decision boundary — the numerics can flip the decision by themselves.

## Where each strategy wins

| cost of a wrong decision | always coarse | always medium | always reference | decision aware | winner |
|---|---|---|---|---|---|
| 10,000 | 6,772 | 9,409 | 361,077 | 255,588 | always coarse |
| 30,000 | 20,050 | 15,083 | 363,055 | 258,472 | always medium |
| 100,000 | 66,522 | 34,942 | 369,978 | 268,563 | always medium |
| 300,000 | 199,301 | 91,682 | 389,758 | 297,396 | always medium |
| 1,000,000 | 664,027 | 290,270 | 458,989 | 398,311 | always medium |
| 3,000,000 | 1,991,814 | 857,664 | 656,791 | 686,641 | always reference |
| 10,000,000 | 6,639,068 | 2,843,543 | 1,349,099 | 1,695,794 | always reference |
| 30,000,000 | 19,916,938 | 8,517,484 | 3,327,121 | 4,579,089 | always reference |
| 100,000,000 | 66,389,484 | 28,376,277 | 10,250,198 | 14,670,623 | always reference |

The decision-aware policy is not cost-optimal at any swept wrong-decision cost. Recorded as a negative result.

## Preregistered criteria

- **FAIL** — A1_policy_ccd_beats_every_baseline
- **FAIL** — A2_policy_accuracy_within_2pp_of_reference
- PASS — A3_policy_work_below_reference_work
- PASS — A4_far_band_rarely_reaches_reference
- **FAIL** — A5_near_band_usually_reaches_reference
- PASS — A6_benchmark_contains_both_regimes
- PASS — A7_reference_not_dominant_in_every_band

Falsification triggers fired: **F1_policy_failed_to_beat_baselines, F4_saving_bought_with_reliability**

## Why it came out this way

Diagnosis of the preregistered outcome, computed from the run. Nothing in the design, the costs or the criteria was altered by any of it.

**1. Escalation is not free.** a strategy pays for every rung it walks past, so reaching the reference rung by escalation costs 332,880 against 327,680 for going there directly. The policy escalated all the way on most scenarios, so its saving in the FAR band was outweighed. The policy paid more than Always Reference on 662 of 1000 scenarios.

**2. The give-up rule is corrupted by the very bias it is hunting.** the stopping rule declares a decision statistically undecidable when |mu_k - tau| falls inside the statistical band. But mu_k is the BIASED prediction. A biased rung can therefore push a perfectly decidable scenario to look like a coin flip, and the policy stops paying exactly when it should have carried on. It stopped below the reference rung on 76 scenarios, of which 36 decided wrongly — concentrated in NEAR: 76. This is why A5 failed.

**3. The error indicator is conservative**, by a median factor of 4.5× — declared in advance. the successive-difference indicator over-estimates the finer rung's error, so the robustness test rarely passes at the medium rung and the policy escalates past a fidelity that was already sufficient. The preregistration declared this would happen in the MODERATE band; it did. 722 escalations changed nothing.

## Answer

**No — not as specified.** The preregistered rule was beaten by fixed baselines at every swept cost of a wrong decision. Always Medium wins below about 3×10⁶ work units and Always Reference above it; the decision-aware policy is never optimal. It also decided less accurately than the reference rung (87.4% vs 91.0%), so its 32% work saving was partly bought with reliability rather than earned. That is what F4 was written to catch, and it fired.

The question itself is not answered in the negative — a cost-aware rule *could* still work. What is established is that **this** rule does not, and the run says exactly why: escalation pays for every rung it walks past, the give-up test reads a biased mean, and the error indicator is 5× too conservative. All three are properties of the rule, not of the benchmark, which passed A6 and A7.

One measured result runs the other way and is recorded without being allowed to offset the failure: the policy made **0** incorrect confident decisions across 1000 scenarios, against 5 for Always Reference and 399 for Always Coarse. It never claimed robustness and was wrong. That is a different objective from the preregistered one, and it does not rescue A1, A2 or A5.

## What this does not show

- no generic FidelityPolicy and no new SRIA module — the escalation logic is experiment-side
- no commitment promotion, no ObligationSet redesign, no certification change, no new EVSI machinery
- no production SRIA change of any kind
- no physical validation; the hidden truth is synthetic and known
- no modification to T1 or T2, which are pinned by digest and used only as frozen prior calibration evidence