# K3 predictive-support boundary — scored failure record

Status: **RECORDED SCIENTIFIC FAILURE / NO SILENT RECOVERY**

Milestone: `K3`

Scored implementation source: `68fcc6a6a9ea305016119a86238aa9329ef33b9c`

Frozen K3 preregistration: `c640af0f9a436b9efb5828b7e4d0caba07d67882`

## What happened

The K3 scored run successfully reconstructed the frozen K2 posterior, admitted the H1/H2 truth evaluations, and built the full 61x61 H1/H2 predictive forward table through the frozen K1.5 inference-admissibility boundary.

Measured holdout build:

- 3,721 parameter points;
- 3,699 / 3,721 points admitted;
- 7,420 / 7,442 condition evaluations admitted;
- 24 workers;
- 928.40 s wall-clock telemetry;
- predictive cache saved successfully.

K3 then failed closed before producing posterior-predictive UQ because some parameter points carrying non-zero posterior probability under K2 were not numerically admissible at H1/H2.

The frozen K3 rule explicitly forbids silently deleting posterior mass and renormalizing. The implementation therefore raised `UQProblemError` as intended.

## Diagnostic evidence

A read-only support diagnostic reported:

- K2 admitted points: 3,686 / 3,721;
- K3 holdout admitted points: 3,699 / 3,721;
- K2-admitted but K3-rejected points: 22;
- primary multi-condition posterior mass on those points: `2.5757981943588344e-224`;
- weak-C2 posterior mass on those points: `4.1546995154574106e-59`.

The dominant unsupported weak-C2 mass is concentrated at one H1 point with weight `4.1546995154574106e-59`. All observed support failures are numerical-admissibility failures: the two tightest CSTR verification rungs still disagreed above the frozen `1e-6` convergence threshold. No failure was converted into an admissible result.

Several additional unsupported points already carry exactly zero floating-point posterior weight; they are still retained in the diagnostic because support membership and probability mass are separate facts.

## Scientific interpretation

This is not evidence that the K2 posterior is wrong, nor evidence that H1/H2 physics are invalid.

It establishes a distinct boundary condition for predictive UQ:

> A posterior support point may be scientifically admissible at the fitting conditions and fail numerical admission at a new predictive condition.

The current K3 contract correctly refuses to hide this by implicit conditioning.

The observed unsupported posterior mass is extremely small, but it is not mathematically zero. The original K3 preregistration did not authorize a non-zero support-loss budget, so the scored K3 run cannot be called PASS by adding one post hoc.

## Decision

- Do not rewrite the frozen K3 preregistration.
- Do not weaken K1.5 convergence thresholds.
- Do not regenerate the 928.40 s holdout grid merely to obtain a pass.
- Preserve the saved H1/H2 cache as scored evidence from source `68fcc6a6a9ea305016119a86238aa9329ef33b9c`.
- Treat original K3 as stopped at the predictive-support binding gate.
- Introduce a separately preregistered successor methodology for explicit predictive-admission conditioning with a declared probability-mass budget and full audit of excluded mass.

## Why a successor methodology is needed

A general Virtual Scientific Laboratory will routinely face models or numerical solvers whose validity/admissibility domain changes across operating conditions. The correct platform-level behavior is not always `all support or abort`, and it is never silent truncation.

The successor must make the policy explicit:

1. measure posterior mass that lacks predictive admission;
2. fail if that mass exceeds a preregistered budget;
3. if it is within budget, condition explicitly on the predictive-admissible event;
4. record original mass, retained mass, excluded mass, conditioning factor, rejected point identities, and reasons;
5. label resulting predictions as conditional on predictive admission;
6. preserve a hard fail path for materially unsupported posterior regions.

This failure therefore becomes reusable scientific architecture rather than an exception hidden inside K3.
