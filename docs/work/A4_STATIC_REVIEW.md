# Independent A-4 scientific static review

Reviewer /root/a4_review, read-only scientific reviewer, 2026-10-18. Applied
.claude/skills/forge-scientific-review/SKILL.md. No files edited, commands, module
imports, tests or numerical executions by reviewer. Static PASS is not evidence.

## A. Scope

Core Freeze/repository contract, architecture decision and matrix, typed interface
semantics, field declarations, graph/ports, mapper, transfer, neutral admission,
CHT wrapper, new adversarial tests and historical WS3 fixtures.

## B. Authority boundary

Declarations authorize bounded transfer, not applicability, qualification or a
scientific verdict. Common-plane embedding is explicitly declarative.

## C. Applicability and model use

Scalar normal CELL components on structured planar rectangles only. Exact quantity
meaning, full coverage and qualified geometry/method are prerequisites. Oblique
projection, frame mismatch, unsupported geometry/representations refuse. Domain
Packs retain conserved meanings and constitutive laws.

## D. Verification / validation

Mapper and reporting distinguish local residuals from constructed oriented integral
diagnostics. Independent target-solver fluxes/coupled physical conservation remain
unknown; numerical solution verification and experimental validation not established.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED. No gate CLOSED.

## E. Uncertainty

Spatial transfers return existing UNKNOWN uncertainty. Zero transfer residual does
not quantify missing local error, model discrepancy or scientific uncertainty.

## F. Evidence / context / policy

No evidence admission, contradiction, risk-policy or certification authority added.
Neutral admission checks meanings/graph consistency; CHT is a thermal instance.

## G. Provenance / replay

Executable edge /3 requires the contract and refuses downgrade/mixed scalar transport.
Nested support fingerprints, conventions, plane geometry and meanings enter graph
identity. CHT /2 output embeds graph-bound neutral admission. No historical identity
rewrite or frozen/certificate pin update.

## H. Adversarial test coverage

Read, NOT RUN: opposing/same/reversed normals and orientations; unequal discretization
areas; direct/graph density and integrated transfer; both partial-coverage directions;
missing/oblique/frame conventions; unsupported geometry/vector/method; stale support;
unit/meaning/kind refusal; schema downgrade and graph identity; thermal CHT and
nonthermal charge/potential; roundtrip limit and disabled-check refusal; successful
unit scaling and identity sign execution.

## I. Findings

| Severity | File/symbol | Smallest counterexample | Inspected correction |
| --- | --- | --- | --- |
| HIGH, resolved statically | execution/multiphysics/mapping.py:FieldMapper._interface | Requested verify_round_trip=True/limit0 ignored on nonconstant differently discretized fields | Same-kind reverse norm and finite/limit refusal; direct + graph regressions |
| MEDIUM, resolved statically | execution/multiphysics/interface_exchange.py:InterfaceContract.problems | INTEGRATED_FLUX mistakenly classified as density | Exact representation branch; integrated execution + neutral admission tests |

A preliminary port-frame concern was retracted: scalar ports cannot declare the
independent frame used by that proposed counterexample. No unnecessary guard added.
No remaining HIGH/MEDIUM defect found in final reviewed source/tests. Corrections
are source-inspected, not executed. Historical WS3 lines68-104 require explicit
migration of prose-only admission/old sign interpretation; that suite is not certified
by this review. Unsupported surfaces/projections and independent coupled balances remain
limitations. No assurance, mutation, provider run or OD-3 performed.

## J. Verdict

PASS
