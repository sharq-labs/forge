# Electrical DC V0

> **Electrical DC V0 is a validated linear resistive DC analysis domain.
> It is not a SPICE replacement.**

The first real scientific domain built on Scientific Core V0.0.1. It exists
as much to test the universal contracts as to analyse circuits: it was
implemented without modifying a single line of `engcore.scientific`.

## Scope

**Supported:** resistors, ideal independent DC voltage sources, ideal
independent DC current sources, an explicitly declared reference node.
Linear, steady-state, lumped.

**Not supported (out of V0 scope):** capacitors, inductors, transient or AC
analysis, frequency domain, diodes, transistors, MOSFETs, any nonlinear
element, dependent/controlled sources, SPICE netlist parsing, ngspice,
power electronics, electromagnetic field simulation.

## Scientific claim boundary

This domain establishes results for **linear, steady-state, lumped,
resistive circuits with ideal independent sources**. It establishes nothing
about nonlinear devices, AC or transient behaviour, distributed circuits,
electromagnetics, real source internal impedance (unless you model it
explicitly as a resistor), temperature-dependent resistance, or parasitics.

Models are registered as `SELF_CONSISTENT`, not `BENCHMARK_VALIDATED` and
not `EXPERIMENTALLY_VALIDATED`: agreeing with hand-derived analytical values
in a test suite is internal consistency, not an external benchmark process,
and involves no measurement. Model `references` are deliberately empty —
these are standard textbook relations, but this repository has no curated
reference set yet and citations will not be invented.

## Mathematical formulation

Modified Nodal Analysis, `A x = z`, with the reference node eliminated.

For `N` non-reference nodes and `M` ideal voltage sources the system is
`(N + M) × (N + M)`:

| Unknown | Index range | Ordering |
|---|---|---|
| Non-reference node voltages | `0 … N−1` | node ids sorted |
| Voltage-source branch currents | `N … N+M−1` | component ids sorted |

Ordering is derived by sorting ids, so an identical circuit always assembles
an identical matrix regardless of the order components were added — verified
by test.

### Stamps

Resistor `R` between `a` and `b`, `G = 1/R` (rows/columns for the reference
node dropped):

```
A[a,a] += G    A[b,b] += G    A[a,b] -= G    A[b,a] -= G
```

Current source `I` flowing `from → to` inside the source. Each KCL row states
*sum of currents leaving the node = 0*:

```
z[from] -= I    z[to] += I
```

Voltage source `k` between `p` (positive) and `n` (negative), branch current
`i_k` defined as the current **leaving `p` through the source**:

```
A[p, N+k] += 1    A[n, N+k] -= 1        (i_k enters the KCL rows)
A[N+k, p] += 1    A[N+k, n] -= 1        (the constraint row)
z[N+k] = Vs                             →  V_p − V_n = Vs
```

## Numerical backend

`scipy.linalg.solve(A, z, assume_a="gen")`. No custom matrix inversion, no
heuristic circuit solver, and never `inv(A) @ z`. Mature linear algebra does
the linear algebra; this domain owns the formulation, the units and the
validation.

## Unit conventions

Every electrical value is a Scientific Core `Quantity`. Validation is by
**dimensionality, never by unit string**, so `1 kΩ` and `1000 Ω` are the same
resistance and `500 mV` and `0.5 V` are the same voltage. Wrong dimensions
(a resistance in volts, a source in kilograms) are rejected at component
construction, long before any matrix exists. Raw floats appear only inside
`RawSolverOutput`; `extract_metrics` restores units.

Resistance must be strictly positive: zero is a short (an ideal 0 V source)
and negative resistance is an active device — both need a different
formulation than the conductance stamp used here.

## Sign conventions

| Element | Convention |
|---|---|
| Resistor | `V_ab = V(a) − V(b)`; `I_ab = V_ab / R` positive `a → b`; absorbed `P = V_ab·I_ab = I²R ≥ 0` |
| Voltage source | branch current `I` **leaves the positive node through the source**; absorbed `P = (V_p − V_n)·I`, **negative when delivering** |
| Current source | current flows `from → to` **inside** the source (injected at `to`); absorbed `P = (V_from − V_to)·I`, negative when delivering |

Power balance sums *absorbed* power over every element and must vanish
(Tellegen). No `abs()` is applied anywhere to make a sign work out.

## Validation strategy

A converged linear solve is **not** a validated result. Six checks run on
every analysis, and they are **not equally strong** — calling them "six
independent checks" would overstate the evidence, so each is classified:

| Check | Kind of evidence | Default tolerance |
|---|---|---|
| `dimensional_consistency` | dimensional contract check | exact |
| `linear_system_residual` | numerical equation-solve check, `‖A x − z‖` | `1e-9 + 1e-9·‖z‖` |
| `kirchhoff_current_law` | **independently reconstructed** topology/physics cross-check | `1e-9 A` |
| `resistor_metric_consistency` | internal constitutive consistency — *self-derived, not independent* | `1e-9 V` |
| `voltage_source_relation` | **independently reconstructed** source-constraint check | `1e-9 V` |
| `power_balance` | global physical consistency (Tellegen) | `1e-9 W + 1e-9·Σ|P|` |

The genuinely independent checks rebuild quantities from the component list
rather than re-evaluating a row of `A`. Re-using the matrix would only
re-prove that `A x = z` was solved; it could never catch an incorrect
*stamp*. A test deliberately corrupts a stamp to prove the distinction is
real. `resistor_metric_consistency` derives `I = V/R` and then checks
`V − I·R`, so it vanishes by construction: useful against a defective
metric-extraction path, but not physical evidence — which is exactly why it
is no longer named `resistor_constitutive_relation`.

Tolerances live in one `DCValidationSettings` object, are carried in
`SolverSettings`, and are recorded in provenance — never scattered as
literals through production code. Each must be finite and non-negative: NaN
would make every comparison silently false (turning validation into a rubber
stamp) and infinity would make every comparison silently true.

### Validation-level honesty

Only two levels are claimable at runtime: `DIMENSIONALLY_VALID` (from the
dimensional check) and `NUMERICALLY_CONVERGED` (from the residual check).

The physics checks pass or fail but establish **no** level. They demonstrate
internal consistency, not agreement with an external benchmark or a
measurement, and the core's `ValidationLevel` vocabulary has no term for
"internally physically consistent". `ANALYTICALLY_VERIFIED` is **not**
claimed at runtime: analytical comparison happens in the test suite against
independently hand-derived values, not during an analysis.
`BENCHMARK_VALIDATED`, `CROSS_SOLVER_VALIDATED` and
`EXPERIMENTALLY_VALIDATED` are never claimed.

## Failure behaviour

A floating sub-network, or two ideal sources contradicting each other across
the same node pair, produces a singular system. The solver reports
`ConvergenceState.FAILED` with an explanatory warning and **no metrics**.

It never adds epsilon to the diagonal, never falls back to least squares or a
pseudo-inverse, and never picks a datum on the caller's behalf. A system with
no unique solution has no unique solution; inventing a plausible answer would
be the worst possible outcome for a platform whose purpose is trustworthy
results. Note that two *identical* parallel ideal sources are also singular —
consistent, but with indeterminate individual branch currents.

Structurally invalid circuits (no reference node, two reference nodes,
duplicate ids, unknown node references, self-connected components, zero or
negative resistance, wrong dimensions) are rejected at construction and never
reach the solver.

## Scientific Core mapping

| Domain concept | Universal contract |
|---|---|
| `DCCircuit` topology | **stays in the domain** — carried to the solver in `PreparedSolve.payload` as `PreparedDCSystem` |
| node potentials, source currents | `ScientificVariable`, role `OBSERVABLE` (a DC analysis chooses nothing) |
| element values | `ScientificParameter` with `Quantity` values |
| reference node, analysis type | `ScientificParameter` with `CategoricalValue` — typed, not metadata |
| Ohm / KCL / ideal-source relations | three `ScientificModelDefinition`s with typed `ModelInputSpec`/`ModelOutputSpec` |
| `electrical:dc_linear` | domain-local `SolverCapability`; `CoreCapabilities` is never extended |
| analysis output | `ScientificResult` + `ValidationReport` + `ProvenanceRecord` |

IR naming: `V:<node>`, `I:<vsource>`, `R:<resistor>`, `Vs:<vsource>`,
`Is:<isource>`, plus `reference_node` and `analysis_type`.

**Topology deliberately does not enter the universal IR.** `ScientificProblem`
describes *what is computed*; connectivity is domain-specific and reaches the
solver through the prepared-solve payload. A circuit is bound to a solver
instance with `bind_circuit(circuit, problem_id)` — domain-local state, never
a global registry.

**Model binding is per component.** Models declare generic physical names
(`resistance`, `voltage_across`) while a circuit problem necessarily uses
per-instance names (`R:R1`), so binding is verified with small relation
problems (`resistor_relation_problem`). This is what proves the V0.0.1
hardening under a real domain: a parameter *named* `resistance` but carrying
volts is rejected, and a required parameter supplied as a variable is
reported.

## Scientific identity and binding integrity

A `ScientificProblem` and a `DCCircuit` are separate artifacts, so nothing
inherently stops a caller pairing the wrong two. `DCCircuit.fingerprint()`
closes that: a SHA-256 over `canonical_dict()`, which is

* **unit-normalised** to ohm / volt / ampere, so `1 kΩ` and `1000 Ω` are the
  same physical system and share an identity — a cosmetic unit choice must
  not create a different scientific artifact;
* **order-independent** (nodes and components sorted by id), so declaration
  order cannot change identity;
* **label-independent** — `circuit_id` and `description` are excluded, since
  renaming a circuit does not change the physics;
* **terminal-order sensitive** — resistor terminals and source polarity are
  preserved, never sorted, because swapping them flips the sign of the
  reported metrics.

`build_dc_problem` records the fingerprint in problem metadata
(`domain_artifact_type`, `domain_artifact_fingerprint`,
`domain_artifact_schema`, `domain_artifact_label`). That is identity and
provenance, not hidden science: every scientific value remains in a typed IR
field. `verify_problem_matches_circuit` is enforced in `prepare()` and in
`solve_circuit()`, **before** assembly or any numerical work. A mismatch
raises `CircuitBindingError` naming the problem id and truncated digests —
never a serialized circuit in a traceback. The problem is never silently
rebuilt and the circuit never silently replaced: only the caller knows which
artifact is correct.

`bind_circuit()` is idempotent for the same physical system and refuses to
rebind a problem id to a different one.

Provenance records both `circuit_fingerprint` (*was it this circuit?*) and
the full `circuit_canonical` topology (*what exactly was solved?*). Element
values alone cannot identify a circuit — two differently wired networks can
share every component value — so the topology record is what makes a result
reproducible.

## Active model set

Attaching every domain model to every circuit would overstate what a result
depends on. `models_for_circuit()` returns only the models a circuit
actually invokes: KCL always, plus the resistor, ideal-voltage-source and
ideal-current-source models when those component types are present. The same
set appears in `ScientificProblem.models`, `ScientificResult.models` and
`ProvenanceRecord.models` — they can never disagree. Result assumptions are
the deterministic, de-duplicated union of the active models' assumptions.

## Uncertainty

`UNKNOWN` for every metric, always, in V0. Element values are taken as exact
and no tolerance propagation is performed. Reporting anything else — even
`±0` — would be fabrication.

## Known limitations

* No component tolerances, no Monte Carlo, no sensitivity analysis.
* Dense solve only; fine for V0-scale circuits, unsuitable for large sparse
  networks.
* Near-singular circuits are reported through SciPy's ill-conditioning
  warning path rather than an explicit condition-number policy.
* No `ValidationLevel` exists for "internally physically consistent", so the
  KCL/source/power checks establish no level. This is a candidate future core
  addition, not something the domain should work around.
* The fingerprint identifies a circuit *artifact*, not a canonical electrical
  network: two topologically equivalent circuits that use different node or
  component ids have different fingerprints. Graph-isomorphism-based identity
  is deliberately out of scope.
* Ground is explicit by design: a node named `"0"` or `"gnd"` is **not**
  automatically the datum.
