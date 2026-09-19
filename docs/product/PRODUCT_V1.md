# Forge Product V1

## Product statement

Forge V1 is a scientific simulation runtime for people and AI agents.

A user describes an engineering question. An LLM may translate that prose into
a structured proposal, but it is never the scientific authority. Forge grounds
the proposal in the user's own text, compiles it against registered scientific
capabilities, executes the selected simulation only when the claim is ready,
and returns an auditable result with validity, verification, validation,
uncertainty, evidence, provenance and repair information.

The product loop is:

Ask -> Prepare -> Simulate -> Verify -> Understand

## V1 product contract

The provider-neutral product gateway exposes four operations:

| Operation | Purpose |
|---|---|
| describe_product | Discover executable capabilities, quantities, inputs and evidence routes |
| prepare_simulation | Ground an LLM proposal in the user's prose and compile it without running physics |
| run_simulation | Execute an already structured scientific claim and return a product view plus the canonical record |
| run_proposed_simulation | End-to-end proposal -> grounding -> compile -> execute when READY |

The same functions are intended to sit below MCP, HTTP and the future web UI.
No Anthropic or OpenAI SDK belongs in this layer.

## LLM boundary

An LLM may:

- interpret natural language;
- propose a structured claim;
- cite exact spans that contain physical values;
- explain the returned record.

An LLM may not:

- invent missing physical values;
- assert that a model is applicable;
- choose a credibility or validation verdict;
- declare uncertainty zero;
- inject evidence or attained levels as authority.

A value proposed without a valid source span is moved to missing_inputs.
The deterministic compiler then returns NEEDS_INPUT, AMBIGUOUS,
UNSUPPORTED_CAPABILITY, REFUSED or READY.

## V1 scope

V1 product work uses only capabilities that the production registry actually
declares and can execute. It does not promise a domain because a module exists
somewhere in the repository.

Current product scope is therefore driven by the production capability
registry and grows only by adding evidence-backed executable declarations.

The UI should render at least:

1. the prepared scientific question and missing inputs;
2. the selected capability and execution plan;
3. the requested quantity and result;
4. model applicability;
5. verification and validation levels/checks;
6. demanded and quantified uncertainty;
7. credibility and assurance verdicts;
8. limitations, missing evidence and repair actions;
9. assessment identity for later replay/audit workflows.

## Non-goals for V1

- no CAD editor;
- no attempt to reproduce COMSOL, Ansys or OpenFOAM solvers;
- no generic CFD or FEA authoring environment;
- no LLM-generated scientific truth;
- no automatic safety certification;
- no claim that every repository domain is product-ready;
- no product-specific conditional inside engcore.scientific.

## Definition of Done

PRODUCT-0 is complete when:

- the product gateway is transport-neutral;
- the LLM proposal path cannot grant scientific authority;
- a proposal can be prepared without running;
- a READY proposal can run end-to-end;
- a non-READY proposal never runs;
- the response has a compact UI view and the canonical assessment record;
- MCP can expose the same gateway without duplicating scientific logic;
- capability discovery comes from the production registry, not a hand-written
  product list.

PRODUCT-1 after this sprint is the first web or API consumer of this contract,
with projects, saved runs, plots and a Trust panel. Persistence and UI are
explicitly outside PRODUCT-0.
