# PRODUCT-0 Sprint — AI-to-Simulation Gateway

## Goal

Turn the existing scientific runtime into a product-facing contract that a web
UI, Claude integration, ChatGPT integration or any other agent can use without
moving scientific authority into the LLM layer.

## Scope

| Work item | Status in this branch | Acceptance |
|---|---|---|
| Product V1 contract | Done | Product scope and non-goals are explicit |
| Provider-neutral product package | Done | No Anthropic/OpenAI SDK in scientific/product runtime |
| Product capability discovery | Done | Derived from production CapabilityRegistry |
| LLM proposal grounding | Done | Physical values require exact source spans |
| Prepare without executing | Done | Non-ready proposals never run |
| Structured simulation run | Done | Reuses generic claim assessment runtime |
| End-to-end proposed run | Done | Propose -> compile -> execute only if READY |
| UI/API projection | Done | Result and trust fields projected from canonical record |
| Canonical audit record | Done | Full assessment record returned beside product view |
| MCP exposure | Done | Four product tools registered |
| Web UI / persistence | Not in PRODUCT-0 | PRODUCT-1 |
| Vendor API client | Not in PRODUCT-0 | Application layer, not scientific authority |
| New physics/domains | Not in PRODUCT-0 | Separate domain sprints |

## Product MCP surface

| Tool | Role |
|---|---|
| describe_product | Discover real executable product capabilities |
| prepare_simulation | Validate and compile an LLM proposal without running |
| run_simulation | Run a structured scientific claim |
| run_proposed_simulation | Run a grounded LLM proposal only when READY |

## Safety and scientific authority rules

1. The LLM proposes; Forge decides readiness.
2. A physical value not present in the cited user-text span is moved to missing input.
3. The LLM cannot assert verdict, selected model, applicability, evidence,
   attained levels, result or quantified uncertainty as authority.
4. Missing inputs are not defaulted to make the demo succeed.
5. Product views never re-derive scientific judgement; they project the
   canonical assessment record.
6. Capability discovery is registry-driven, so the product cannot advertise a
   domain simply because code for that domain exists somewhere in the repo.

## Next sprint

PRODUCT-1 should consume this contract from an actual application:

- project/run persistence;
- HTTP API/auth boundary;
- Ask screen;
- preparation/missing-input screen;
- simulation plan graph;
- result plots;
- Trust panel;
- run comparison;
- replay/downloadable assessment record.

No new domain should be required to complete PRODUCT-1.
