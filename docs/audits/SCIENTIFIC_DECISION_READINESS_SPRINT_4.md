# Scientific Decision Readiness — Sprint 4: Generic Claim Assessment API

## Goal

Expose one cross-system AI-facing boundary that can answer:

> Is this explicitly named scientific claim sufficiently supported for this
> explicitly named decision under these explicitly required evidence levels?

The boundary is structured orchestration. It is not a natural-language
scientific planner and it does not select models automatically.

## Public tool

The MCP server now exposes:

`assess_claim`

Server version moves to `0.6.0` because this adds a public tool.

The domain-specific tools remain available:

- `run_electrothermal`
- `run_battery`

The generic tool executes those existing registered system boundaries rather
than introducing a second simulation path.

## Required request

The caller must supply all of:

- `system`: one name already registered in `engcore.mcp.systems`;
- `case`: the normal payload for that system;
- `quantity_name`: one quantity already present in the selected credibility
  report;
- `decision.id`;
- `decision.statement`;
- `required_levels`: one or more real `ValidationLevel` values;
- `discrepancy.kind`;
- `discrepancy.rationale`;
- `discrepancy.reference` where the chosen discrepancy kind requires it.

When a system produces multiple credibility reports, `report_index` is also
required.

The API refuses to guess any of these.

## Decision path

```
structured request
       |
       v
registered SystemBoundary
       |
       v
existing domain execution
       |
       v
CredibilityEvidenceReport
       |
       +---- report verdict / evidence basis
       |
       v
CampaignCharter
       |
       +---- explicit terminal decision
       +---- explicit required ValidationLevels
       |
       v
SRIA Evidence
       |
       v
CredibilityReportCritic
       |
       v
Arbiter
       |
       v
structured claim assessment
```

## Two gates, not one

A requested ValidationLevel is not enough by itself.

The generated obligation set requires:

1. the requested `validation_level:...` checks; and
2. the PROCESS critic itself.

`CredibilityReportCritic` now maps the report-level credibility verdict into
its own verdict:

- `SUPPORTED` -> PASS, provided required levels are present;
- `INSUFFICIENT_EVIDENCE` -> INCONCLUSIVE;
- `NOT_SUPPORTED` -> FAIL.

This prevents a passing benchmark or verification check from hiding another
applicability, convergence or evidence failure in the same credibility report.

## Authority

Validation-level obligations remain issuer-gated.

Only a critic registered with explicit
`validation_level_issuer=True` participates in resolving
`validation_level:...` checks.

The flag itself must be a Python bool. A truthy string such as `"false"` is
rejected rather than converted into scientific issuing authority.

The generic tool uses the existing reviewed `CredibilityReportCritic`; it
does not create another issuer vocabulary.

## Context identity

The API constructs a real `CampaignCharter` and derives:

`charter:<charter digest>#decision:<decision id>`

as the Evidence context reference.

The caller does not supply an arbitrary context string.

## Source dependency semantics

The generated SRIA Evidence uses the Sprint-3 lineage contract.

The production bridge may carry a known parent run, but it deliberately leaves:

`source_closure_complete = false`

because current production credibility reports cannot prove their complete
dataset/observation ancestry.

Therefore the generic assessment API does not create false independence merely
because two system executions have different run ids.

## Response

A successful structured assessment returns separately:

- claim value and units;
- Evidence record identity and context;
- source-lineage state;
- production credibility verdict;
- evidence basis;
- attained, required and missing ValidationLevels;
- SRIA assurance verdict;
- unmet obligations;
- assurance reasons;
- decision statement and charter digest;
- the explicit discrepancy declaration.

No scalar confidence score is produced.

## Refusals

Expected request failures return a structured refusal from the MCP tool.

Examples:

- unknown system;
- missing decision statement;
- no required evidence level;
- `UNVERIFIED` used as a requirement;
- unknown ValidationLevel;
- absent discrepancy declaration;
- invalid discrepancy declaration;
- missing quantity;
- ambiguous multi-report output without `report_index`;
- malformed underlying system case.

Unexpected implementation errors still raise. The transport does not disguise
a code defect as scientific insufficiency.

## Tests

`tests/mcp/test_claim_assessment.py` pins:

1. a SUPPORTED report with an attained requested level can reach VALID;
2. a missing required level becomes INCONCLUSIVE;
3. an attained level cannot hide an INSUFFICIENT_EVIDENCE report;
4. the decision standard cannot be omitted;
5. model discrepancy cannot be omitted;
6. multiple reports require explicit selection.

`tests/mcp/test_server.py` now treats `assess_claim` as an intentional public
tool with its own request schema.

SDR-10 is now a required passing invariant rather than an expected failure.

## Non-goals

Sprint 4 does not:

- parse a natural-language scientific question;
- choose a domain or model from prose;
- choose a result quantity;
- decide how dangerous a real-world action is;
- derive a required evidence level automatically;
- infer model-form discrepancy;
- admit the evidence into persistent ScientificBelief;
- replace an engineer or scientific decision maker.

Those are deliberately separate layers. This sprint provides the stable,
explicit boundary they can call later.
