# Cross-domain architecture audit (2026-10-18)

Read-only audit for the Cross-Domain Scientific Architecture Requirements (CDAR) of
[ENGINEERING_FOUNDATIONS_PROGRAM.md](../project/ENGINEERING_FOUNDATIONS_PROGRAM.md). **Nothing was executed**; every
statement comes from reading the code. The tree audited is the Phase 3.5 branch
(`feat/phase35-engineering-foundation-completion`, `D:/forge-phase35`), a superset of `main`. Files marked **(P)** exist
only on the unmerged Phase 1–3.5 branches. Paths are under `src/engcore/` unless stated.

Question asked: is the shared multiphysics structure physics-agnostic, or does it carry thermal assumptions?

**Answer.** The runtime core is mostly physics-agnostic: ports, participants, conservation algebra, field mapping,
frames and the multiscale scheduler name no physics. A non-thermal coupled run already exists:
`systems/products/drone_coupled.py`, which couples a propeller (mechanical), motor and ESC (electrical), a battery and
thermal models, with voltage and current criteria, as a steady screening template (its mechanical link crosses as power
through an `EnergyConversion`, not as force or displacement); a test exists, `tests/foundations/test_drone_coupled_hover.py`
(not run here). The
risk is less heat-specific code than what the contracts never DECLARE: semantic roles, field kinds, non-energy losses.
Thermal hard-coding exists in one admission module and one message.

## Generic, biased, missing

| Area | Generic (exists) | Thermal-biased | Missing |
| --- | --- | --- | --- |
| Port typing | `scientific/multiphysics/ports.py:24-35, 68-152` (kind, quantity, unit, algebra, frame); `scientific/fields/definition.py:30-41` (node / cell) | none | potential vs flow role; intensive vs extensive; density vs integrated; facet location |
| Edge checks | `scientific/multiphysics/graph.py:248-371` (kind, dimension, algebra, components, frame transform) | energy-centred, not thermal: the energy-density rule applies to field edges (`graph.py:285-295`) AND to every scalar edge, which `graph.py:301` builds into a `QuantityDependency` (`scientific/composition/dependency.py:231, 241`); its set `ENERGY_DERIVED_DIMENSIONS` (`conversion.py:133-149`) holds force (J/m), pressure (J/m^3) and surface tension (J/m^2), so a mechanical edge must state a prose transport (A-13; with A-2) | `quantity` not compared (`graph.py:252`); same-dimension, different-meaning pairs pass once that rule is answered (`scientific/composition/conversion.py:127-132`) |
| Conservation | `scientific/conservation.py`, `scientific/multiphysics/conservation.py:26-29, 93`, runtime `_balance` | losses only with `EnergyConversion` (`graph.py:412-423`) | lossy mass / charge / species crossings; field-valued balances (refused, `graph.py:401-405`) |
| Field transfer | `execution/multiphysics/mapping.py` (identity, nearest, bilinear, conservative cell), component-wise vectors | message text names kelvin (`mapping.py:969`) | a field-kind flag: conservative remap assumes a density (`mapping.py:1005, 1067`) |
| Flux / intensive | `execution/multiphysics/interface_exchange.py:41-43` (P) | none | not wired into graph or runtime; sign convention never applied; no normal projection |
| Interface admission | reuses `InterfaceContract` | `execution/multiphysics/conjugate_interface.py:48-49` (P): admission gates are K and W/m^2; names and keys thermal | a generic Dirichlet-Neumann admission |
| Edge conversion | `scientific/composition/conversion.py:44-50` | energy / power only (`conversion.py:111-149, 326-334`) | generic quantity conversion (charge to mass, gearing, transformer) |
| Participants | `execution/multiphysics/participant.py:190, 433`; `steady.py:62` (P) (steady scalar); `external.py:158`; `coupling/adapters.py:170`; MNA participant `executionpacks/builtin_electrothermal_feedback.py:57, 167` | none | ODE / DAE participant; CSTR, multibody, structural participants; domain-pack factories |
| Materials | `materials/properties.py:56-70, 215` | none | tensor / anisotropic values; property registry; domain qualifiers |
| Time scales | `multiscale/runtime.py`, `multiscale/scales.py`; `execution/multiphysics/subcycling.py` (P) | none | multirate windows; interpolated inputs |
| Frames | `scientific/multiphysics/frames.py:18, 59-104`; `execution/multiphysics/transfer.py:100-153`; `spatial/geometry.py:214` | none | translation, time-varying, rotating frames; frame-invariant vector fan-in (`execution/multiphysics/transfer.py:344-347`) |
| Problem identity | `providers/problem_identity.py:50-60` (P) | none | extensible aspects; interface and frame aspects |
| Verification | `scientific/verification/ladder.py`, `scientific/results/validation.py:652`, `domainpacks/manifest.py:79` | none | typed domain-pack protocol (`provider.py:14-24, 42` is `Any`); field-norm comparison |
| API | `run_simulation`, canonical engineering intent | domain-named MCP tools (`mcp/battery.py`, `mcp/nafems_t3.py`) | — |

## Gaps, mapped to requirements and owners

| # | Gap | CDAR | Owner | Kind |
| --- | --- | --- | --- | --- |
| A-1 | No semantic port role (potential / flow, intensive / extensive, density / integrated); `quantity` not compared | 1 | Core review | Core semantic change |
| A-2 | Losses and conversions energy-only; no lossy mass, charge or species crossing; field balances refused | 2 | Core review | Core semantic change |
| A-3 | Conservative remap assumes a density; flux / intensive contract not applied; no sign application or normal projection | 3 | Core review; M1, M2, E2 | Core + program |
| A-4 | CHT admission hard-codes K and W/m^2 (P) | 3 | Core review, then E2 (generic Dirichlet-Neumann admission) | Core-package semantics (admission in `engcore.execution`) |
| A-5 | Scalar-only materials, free property ids | 5 | later review | Core-adjacent |
| A-6 | No multirate coupling | 6 | later review | runtime |
| A-7 | `ProblemAspect` closed; no interface or frame aspect | 7 | Core review | Core-adjacent |
| A-8 | Domain-pack verification protocol untyped; no field norms | 8 | later review | domain packs |
| A-9 | Static frames only; component-wise vector fan-in | 9 | Core review; E3 | Core semantic change |
| A-10 | Domain-named MCP tools; packs without participants | 10 | later review | API |
| A-11 | No ODE / DAE, chemical, multibody or structural participant | 4 | program fixtures; later specialization | runtime |
| A-12 | Offset-scale refusal message suggests kelvin (`mapping.py:969`) | 3 | next code pass (message only) | text |
| A-13 | Every force, pressure, stiffness or surface-tension edge (scalar or field) falls under the energy-density rule and can answer it only with a free-prose `transport_declaration`: a dimension cannot tell a force from an energy per length. Deliberate (the rule refuses silence, and its message names the force case), but mechanics has no declared way to say "no energy crosses". Found by the CDAR fixtures (pinned there by `test_gap_a_force_edge_must_speak_in_energy_terms`) | 1, 2 | Core review, with A-1 and A-2 | Core semantic change |

## Next steps (deferred, not done here)

- Run the three architectural fixtures, written 2026-10-18 on branch `test/cdar-architectural-fixtures` (`D:/forge-cdar`,
  stacked on the Phase 3.5 branch; test code only; NOT RUN, DV-99 there). Gaps are pinned there by ordinary tests
  (`test_gap_...`), not xfail.
- Refactor `conjugate_interface.py` into a generic Dirichlet-Neumann admission with CHT as its instance (E2).
- Generalize the `mapping.py:969` message (A-12).
- Take A-1, A-2, A-3, A-4, A-7, A-9 and A-13 through the Core compatibility review (Core-package semantics; none of the
  symbols is in the frozen API snapshot). Gates that depend on them (M2 on A-3, E2 on A-4) may be built before the
  review but are decided only after it; M1 declares its variable kind locally until A-3 is decided.
- Update the stale "BLOCKED by policy (OD-P2-1)" docstring of `conjugate_interface.py` (P) when OD-6 merges.
