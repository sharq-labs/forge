# The verification and validation (V&V) layer

> **A credibility evidence report is advisory input to an engineer of record.
> It is not a decision, not a certification, and not a claim of conformance
> with any standard.**

`engcore.mcp` is a consumer of `engcore.scientific` and never a modifier of
it. It computes no physics, evaluates no validity condition and re-runs no
check. Every scientific judgement it carries was made upstream — by a model's
validity domain, or by a solver's validation — and is *transported* here. The
only thing this layer decides is how to combine judgements already made, and
it does so in one pure function a reader can check in full.

## What it produces

A `CredibilityEvidenceReport` puts in one record the three facts the platform
otherwise keeps deliberately apart:

| Fact | Carried as |
|---|---|
| Was the model applicable? | `ValidityAssessment` — carried, never recomputed |
| Did the checks pass? | `ValidationReport` — **including what did not run** |
| What produced it? | `ProvenanceRecord` — carried unaltered |

plus the caller's own **caller-asserted context, not evidence**, in a field
that cannot be mistaken for any of the three, and a single advisory
`CredibilityVerdict` derived from the lot.

The verdict is a read-only property over `derive_verdict`, not a constructor
parameter. There is no stored copy to drift out of step with the contents, and
a payload whose stored verdict disagrees with what its contents produce is
refused on the way back in.

## What "credibility" means here

The word is used in the sense the V&V literature gives it:

- **ASME V&V 10** — verification and validation in computational solid
  mechanics.
- **ASME V&V 20** — verification and validation in computational fluid
  dynamics and heat transfer.
- **ASME V&V 40** — assessing credibility of computational modelling through
  verification and validation.
- **NASA-STD-7009** — models and simulations.

In all of them, credibility is a property of *the evidence supporting a result
in a stated context of use* — not a property of the model, and not a measure
of accuracy. That is what this record reports.

### The attained levels are an evidentiary scale

`ValidationLevel` says what a passing check **established**:

| Level | What a check claiming it has shown |
|---|---|
| `DIMENSIONALLY_VALID` | the reported quantities carry the dimensions the model declared |
| `NUMERICALLY_CONVERGED` | the discrete problem was solved to a declared tolerance |
| `ANALYTICALLY_VERIFIED` | agreement with a closed-form solution of the same equations |
| `BENCHMARK_VALIDATED` | agreement with an accepted reference case |
| `CROSS_SOLVER_VALIDATED` | agreement with an independent implementation |
| `EXPERIMENTALLY_VALIDATED` | agreement with measurement |

Loosely, the first three or four sit on the **verification** side of the
V&V 10/20 distinction — *did we solve the equations right* — and the last two
on the **validation** side — *did we solve the right equations, against the
world*. That correspondence is stated loosely on purpose. It is not a mapping
any of these standards defines, the boundary between the two sides is
genuinely arguable for `BENCHMARK_VALIDATED` and `CROSS_SOLVER_VALIDATED`, and
the levels are attained *independently* rather than climbed in order — so they
do not form a single ordinal grade the way a credibility assessment scale's
factors are each scored.

### `INSUFFICIENT_EVIDENCE` and NASA-STD-7009 level 0

`INSUFFICIENT_EVIDENCE` is the same idea as the bottom of NASA-STD-7009's
credibility assessment scale, **level 0, "insufficient evidence"**: nothing
here answers the question, and the fix is to go and produce the evidence
rather than to argue about the result.

It is not a formal score against that scale. NASA-STD-7009 assesses eight
factors separately and scores each; this layer applies the same distinction
once, to one report. The correspondence is in meaning, not in method.

A report is `INSUFFICIENT_EVIDENCE` when a model's validity is `UNKNOWN`, when
a check did not run, when a model that took part was never assessed, when a
level the caller declared it needs was not attained, when there are no
validity records — **or when no check both passed and established a level.**
That last rule is why a run can be clean in every other respect and still
report a gap: a passing check that establishes nothing has only failed to
object, and absence of an objection is not evidence. It is the same reason
`NOT_RUN` is a distinct outcome from `PASS`, applied one level up.

### `required_levels` is where a study states its own bar

Declaring `required_levels` is the move ASME V&V 40 makes when it sets the
required rigour from the model risk in a stated context of use. This layer
does **not** compute model risk and does not know the context of use. It
records the bar the caller declared and reports whether it was met.

## What is not claimed

- **No conformance.** This project is not certified, has not been assessed
  against ASME V&V 10, V&V 20, V&V 40 or NASA-STD-7009, and no standards body
  endorses it.
- **No endorsement.** Citing a standard is describing where the vocabulary
  comes from, not claiming the standard approves of this tool.
- **No decision.** A `SUPPORTED` verdict says nothing in the record argues
  against relying on the result. It does not say the result is right, and it
  does not discharge anyone's professional judgement or responsibility.

These standards are frameworks for **structured human judgement**. What this
layer does is execute a small, explicit part of that judgement as code, so the
part that *can* be mechanical is not left to a reader's memory. Everything
they ask of a person — deciding the context of use, weighing the risk,
accepting the result — is still asked of a person.

## The three verdicts

Three values and no more. A richer scale invites a reader to act on the grade
instead of the evidence.

| Verdict | What it means | What to do |
|---|---|---|
| `SUPPORTED` | Nothing in this report argues against relying on the result, and at least one evidentiary level was attained. | Read the checks and the conditions; decide. |
| `INSUFFICIENT_EVIDENCE` | Something needed to answer the question was never produced. | Produce it: declare the missing input, run the missing check. |
| `NOT_SUPPORTED` | Something that *was* produced argues against the result — a bound known violated, or a check that ran and failed. | Change the design or the model. More evidence will not help. |

**Precedence: `NOT_SUPPORTED` outranks `INSUFFICIENT_EVIDENCE`.** A finding
outranks a gap, because the two recommend opposite actions — and because the
alternative would let a caller bury a violated bound by omitting an unrelated
input.

**`WARNING` is not a failure and does not change the verdict.** A check that
warned produced its evidence. It stays visible in `warning_checks` for the
reader who must weigh it.

## Naming

The record was called `EvidencePackage` and the verdict `EvidenceVerdict`
before this layer adopted the V&V vocabulary. Both old names remain importable
as deprecated aliases **for one release**; new code should use
`CredibilityEvidenceReport` and `CredibilityVerdict`.

The serialized schema string is unchanged — `mcp_evidence_package/1`. It is a
wire identifier, not vocabulary: renaming it would reject every record written
before the rename while claiming to be one. Changing the wire form is a
version bump plus a reader that accepts both, and that has not been argued
for.

---

# The MCP server

`engcore.mcp.server` exposes this runtime to an AI agent over MCP stdio, using
the official Python `mcp` package. It is a **thin transport**: it computes no
physics, evaluates no condition and decides no verdict. Every fact it returns
came from `problem.py` or `evidence.py` and is carried unaltered.

## Install

The SDK is an optional dependency group. If `pyproject.toml` carries the
`[mcp]` extra:

```bash
pip install -e ".[mcp]"
```

If it does not — the stanza is recorded in `NEEDS.md` and has not been added,
because `pyproject.toml` is outside this step's owned paths — install the SDK
directly:

```bash
pip install "mcp>=2.1,<3"
```

The suite stays green without it: `tests/mcp/test_server.py` skips when the SDK
is absent, the same rule `pytest-xdist` is held to.

## Run it

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m engcore.mcp.server
```

On PowerShell:

```
$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m engcore.mcp.server
```

No network, no authentication, no persistence, and no CLI arguments. It speaks
MCP over stdin/stdout and nothing else.

### Claude Desktop

Add to `claude_desktop_config.json` — on Windows
`%APPDATA%\Claude\claude_desktop_config.json`, on macOS
`~/Library/Application Support/Claude/claude_desktop_config.json`. Replace
`<REPO>` with the absolute path to this checkout:

```json
{
  "mcpServers": {
    "crafty-engcore": {
      "command": "<REPO>/.venv/Scripts/python.exe",
      "args": ["-m", "engcore.mcp.server"],
      "cwd": "<REPO>",
      "env": { "PYTHONPATH": "<REPO>/src" }
    }
  }
}
```

On macOS or Linux the command is `<REPO>/.venv/bin/python`.

## The two tools

### `describe_capabilities()`

Takes no arguments. Returns what an agent must know before it can ask anything,
**derived from the model registries at call time** rather than written down, so
a model input added or re-dimensioned in a domain changes the description
instead of making it quietly false:

| Key | What it carries |
|---|---|
| `systems[].fields` | Every accepted field: `path`, `required`, `dimension`, `unit_exemplar`, the model and input it comes from, and its prose |
| `systems[].fields[].unlocks_conditions` | For an optional field, the validity conditions that go from decidable to UNKNOWN without it |
| `systems[].fields[].alternative_to` | Keys interchangeable with this one, and what the group unlocks between them |
| `systems[].example_case` | A complete runnable case with every optional field supplied |
| `fields_you_may_not_supply` | Model inputs the coupling solves for, and why declaring one would fix the fixed point |
| `verdicts` | For each of the three: what it means, **what it does not mean**, and what to do |

### `run_electrothermal(case)`

Takes the case object. Returns one report per stage:

| Key | What it carries |
|---|---|
| `coupling` | The coupled run's own outcome token, iterations against budget, final iterate change against tolerance, and the derived criterion — **its own field**, not folded into `validation` |
| `stages[].verdict` | The verdict, what it means and does not, and `verdict_reasons` |
| `stages[].report` | The `CredibilityEvidenceReport` exactly as `to_dict()` produced it: values with units, per-model validity with satisfied/violated/unknown condition names, every validation check including `NOT_RUN`, provenance, and the caller's asserted context under `caller_asserted` |

**`verdict_reasons` is the part that makes a verdict actionable.** Each entry
names the rule of `derive_verdict` that fired and the specific condition, check
or gap behind it. `other_findings` carries rules that fired without deciding —
gaps outranked by a finding, and warnings, which never decide anything. An
agent receiving `NOT_SUPPORTED` can tell which bound was violated, and one
receiving `INSUFFICIENT_EVIDENCE` can tell what is missing, without a second
call.

The enumeration is checked against the report's own verdict on every call: a
non-`SUPPORTED` verdict that no rule explains raises rather than reaching an
agent as a refusal it cannot act on.

## The nominal case is `INSUFFICIENT_EVIDENCE`, and that is not a bug

A well-formed nominal run reports `INSUFFICIENT_EVIDENCE`. The payload has no
field for a resistor's rated dissipation or a source's current limit, and
`electrical.dc.kcl` declares no validity conditions at all, so those models are
honestly UNKNOWN — see `NEEDS.md` A2.4 and A2.5. **The server transmits it
unchanged.** It does not soften, filter or re-rank a verdict, and the tool
description warns an agent not to read it as a failure and retry. A transport
that improved a verdict on the way past would be the exact substitution the
layer beneath it exists to refuse.

## Errors are repairable, not generic

A payload the boundary refuses comes back as a structured tool error —
`isError: true` with structured content — carrying the field, what the caller
sent and what was expected:

```json
{
  "error": "WrongDimensionError",
  "field": "stages[0].body.duration",
  "received": "120 kelvin",
  "expected": {
    "path": "stages[].body.duration",
    "kind": "quantity",
    "required": true,
    "dimension": "[time]",
    "unit_exemplar": "second",
    "model_id": "thermal.lumped.first_order_capacity",
    "description": "Length of the interval over which the state advances."
  },
  "repair": "Send any unit of the dimension in expected.dimension. The value parsed; its dimension is not the one this field needs.",
  "message": "stages[0].body.duration has the wrong dimension: '120 kelvin' is [[temperature]], but this field must be [[time]] ..."
}
```

`field` is the path the boundary named — every message in `problem.py` begins
with it. `received` is read back out of the caller's **own payload** at that
path and `expected` out of the **registry-derived** description, so neither is
reconstructed from the message prose. `message` is the boundary's own words,
verbatim. One entry per refusal class, because each maps to a different repair:
`MissingFieldError`, `MissingUnitError`, `WrongDimensionError`,
`UnknownFieldError`, `MalformedPayloadError`.

## A worked `NOT_SUPPORTED` example

The example case with the conductor rated to 301 K, which the run crosses:

```json
{
  "stages": [{"conductor": {"limits": {"maximum_operating_temperature": "301 kelvin"}}}]
}
```

— the rest of the case is `example_case` from `describe_capabilities`. The
response:

```json
{
  "schema": "mcp_electrothermal_response/1",
  "system": "electrothermal",
  "coupling": {
    "schema": "mcp_coupling_evidence/1",
    "outcome": "criterion_met",
    "iterations_run": 10,
    "iteration_limit": 50,
    "largest_iterate_change": {
      "schema": "quantity/1",
      "magnitude": 4.7410196657438064e-07,
      "units": "kelvin"
    },
    "tolerance": {
      "schema": "quantity/1",
      "magnitude": 1e-06,
      "units": "kelvin"
    },
    "criterion": "met"
  },
  "stages": [
    {
      "component_id": "R1",
      "verdict": {
        "value": "not_supported",
        "means": "Something that was produced argues against the result: a bound known to be violated, or a check that ran and failed.",
        "does_not_mean": "It does not mean the numbers are arithmetically wrong — it means the model was applied outside where anyone has said it holds, so the numbers evidence nothing. More evidence cannot rescue it.",
        "action": "Change the design or the model. NOT_SUPPORTED outranks INSUFFICIENT_EVIDENCE, so gaps may also be present; they are reported under other_findings.",
        "verdict_reasons": [
          {
            "rule": "model_validity_violated",
            "produces": "not_supported",
            "detail": {
              "violated_conditions": [
                {
                  "model_id": "electrical.material.rated_linear_tcr_resistance",
                  "condition": "operating_temperature_utilization"
                }
              ]
            }
          }
        ],
        "other_findings": [
          {
            "rule": "model_validity_unknown",
            "produces": "insufficient_evidence",
            "detail": {
              "models": [
                {
                  "model_id": "electrical.dc.ideal_voltage_source",
                  "unknown_conditions": [
                    "source_current_utilization"
                  ],
                  "note": ""
                },
                {
                  "model_id": "electrical.dc.kcl",
                  "unknown_conditions": [],
                  "note": "declares no validity conditions, so nothing was evaluated"
                },
                {
                  "model_id": "electrical.dc.resistor_ohm",
                  "unknown_conditions": [
                    "dissipated_power_utilization",
                    "working_voltage_utilization"
                  ],
                  "note": ""
                }
              ]
            }
          }
        ]
      },
      "report": { "…": "the full CredibilityEvidenceReport — see the table above" }
    }
  ]
}
```

The bound that was violated is named, with the model that declared it. The
gaps are still reported, under `other_findings`, outranked rather than erased.

## The schemas an agent sees

Both tools take and return free-form JSON objects, so the schemas are
deliberately permissive: the *contract* is `describe_capabilities`, which is
computed from the registries, not a JSON Schema that would have to be
maintained beside them and could drift.

```json
[
  {
    "name": "describe_capabilities",
    "title": "Describe what this runtime accepts",
    "input_schema": {
      "type": "object",
      "properties": {},
      "title": "describe_capabilitiesArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "describe_capabilitiesDictOutput"
    }
  },
  {
    "name": "run_electrothermal",
    "title": "Run an electro-thermal case",
    "input_schema": {
      "type": "object",
      "properties": {
        "case": { "type": "object", "additionalProperties": true, "title": "Case" }
      },
      "required": ["case"],
      "title": "run_electrothermalArguments"
    },
    "output_schema": {
      "type": "object",
      "additionalProperties": true,
      "title": "run_electrothermalDictOutput"
    }
  }
]
```

The description text each tool carries is the literal value of
`_DESCRIBE_DESCRIPTION` and `_RUN_DESCRIPTION` in
[`server.py`](../../src/engcore/mcp/server.py), and
`test_the_descriptions_say_what_an_agent_must_know_before_calling` pins the
claims in it that an agent cannot be allowed to miss.
