# A-1 / A-2 / A-13: semantic compatibility proposal

Phase A/B design recorded before shared implementation. Base: origin/main
`0284ae161ad957d51674ee481e47cfd43d10c5f0`; branch `codex/quantity-semantics`.
Checkpoint PR #158 is separate and is not an ancestor of this branch.
Owner authorizes bounded Build-First implementation after this compatibility proposal;
no pytest, numerical execution, full assurance, mutation or OD-3 is authorized.
Status: PROPOSED, then IMPLEMENTED / UNVERIFIED where code is supplied. No gap CLOSED.

## Contract and authority

Dimensions are necessary, not sufficient. Core contains no catalogue of thermal,
electrical, chemical or mechanical meanings. Domain Packs own open namespaced meaning
identifiers, physical laws, validity, model/realization identity and qualifications.
Matching declarations establish wiring consistency, not the physical truth of a label.

1. `ConservedQuantity`: open namespaced meaning id plus unit exemplar. This describes
   the precise measure being balanced (an amount OR an explicitly named rate); Core
   never infers an amount/rate relationship, species, reaction, charge number or frame.
2. `QuantitySemantics`: namespaced meaning id, dimensional unit exemplar, ordered set
   of physical roles (potential, effort, flow, intensive, extensive, density, integrated, other),
   optional namespaced custom role, and optional `ConservedQuantity`. Orthogonal roles
   can coexist (flow+density, potential+intensive). Unit exemplars are canonicalized;
   their dimensions bind the declaration to a port. Names are never parsed as laws.
3. `QuantityTransport`: structured signal or conserved transport. Signal matches exact
   meaning/roles and carries no conserved quantity. Conserved transport binds a precise
   conserved measure, an explicit delivered fraction (None is UNKNOWN and refuses
   execution), and named loss fractions. Fractions must be finite and account for all
   input. These are declared coefficients, not measured evidence; coefficient uncertainty
   is not invented, and new partitioned transfer output uncertainty remains UNKNOWN.
4. `PortDefinition.semantics`: optional trailing field, dimensional consistency required.
   `CouplingEdge.transport`: optional trailing field. If either endpoint is typed, both
   must be typed and an explicit transport is mandatory. Direct transport requires exact
   meaning/role equality; no typed/untyped bridge, inferred alias or prose override.
5. Transformations between different meanings are explicit model/realization participants,
   admitted by existing domain/provider qualification and applicability mechanisms. This
   slice does not implement a new qualification authority or let a string saying
   'qualified' authorize a conversion. Force and velocity can enter a Domain Pack power
   participant, whose computed power output is transported as power. Core never computes
   F*v from unit coincidence. Test callbacks are design probes, not qualified models.
6. `CoupledConservation` optionally names the conserved measure; typed terms explicitly
   declare inflow, outflow, source, loss or accumulation contributions. Typed bindings
   must match the edge's conserved measure, quantity dimension and transport partition;
   species and electric charge cannot be interchanged. Terms stay bound to executed
   transfer source/received/loss values. Arbitrary constants/caller evidence are not added.
7. General `BalanceTerm` and `ConservationBalance` gain optional semantic declarations
   so separately computed storage/source terms can use the existing arithmetic without
   confusing same-dimension species. This is still a necessary balance check, not a
   validation-level producer. No second Evidence, uncertainty or provenance system.

## Legacy admission and frozen boundaries

`QuantityDependency` and `EnergyConversion` are frozen exported records. Their shape,
serialization and import identity remain untouched; old standalone dependency paths
retain their conservative legacy restrictions. Typed `PhysicsGraph` edges use the new
semantic admission rather than treating force as an energy density through the legacy
dependency constructor. This is an explicit bounded migration path, not global closure
of every legacy dependency producer. Removing the frozen legacy path needs a separate
version/deprecation decision.

Untyped graph edges must match the declared quantity name as well as dimension. A legacy
EnergyConversion is allowed to connect distinct names only when the endpoints explicitly
match its declared input/output forms; otherwise the connection needs migration to typed
ports or a transformation participant. Free prose cannot override meaning mismatch.
Existing exact-name thermal edges and explicitly matched conversion forms retain behavior.
Existing alias-based thermal/provider graphs may now refuse; their direct source references
are inventoried in SEMANTIC_IMPACT_MATRIX.md. They must not be relabelled automatically by
Core, silently blessed as semantically equivalent, or have expected numerical values changed.

## API / serialization / identity compatibility matrix

| Surface | Decision | Compatibility / migration |
| --- | --- | --- |
| Frozen QuantityDependency, EnergyConversion, LossPath and exported API | no shape/schema/digest edits | no new freeze requested; standalone legacy limitations remain explicit |
| New semantic records | internal scientific module, own exact /1 schemas | no automatic canonical export or frozen promotion |
| PortDefinition, CouplingEdge, CoupledConservation and typed balance records | optional trailing fields outside frozen snapshot | untyped writer retains existing /1 payload bytes; typed writer emits /2 |
| Readers | exact accept-set /1 and /2 | /1 carrying new semantic keys refuses instead of silently stripping them; /2 requires complete typed fields |
| Nested ParticipantSpec, PhysicsGraph and run records | unchanged outer shapes | typed child /2 rejects in old child readers; no unversioned semantic metadata |
| Material identity | semantic declarations included by nested to_dict | changing meaning, roles, conserved measure, fractions or contributions changes graph/run digest |
| Deserialization admission | re-run graph/record constructors | no stored PASS/qualification assertion accepted as evidence |
| Transfer/runtime | scalar typed signal/partition path | loss readback uses existing TransferResult; diagnostics are not error bounds |
| General conservation arithmetic | existing ConservationBalance reused | typed terms checked for exact conserved measure; mixed typed/untyped refused |
| Legacy aliases and force prose | stronger refusal or explicit typed migration | behavior change is deliberate; no thresholds changed |
| Typed field transport | explicitly unsupported in this slice | refuse until separate A-3 field-kind/normal/sign design; no density guess |
| Import layering | scientific meaning -> multiphysics -> execution | no Domain Pack/provider/MCP import in Core |
| Certification | trust/admission and SCOPE changes | UNCERTIFIED; separate final-source OD-3, no pin regeneration to silence failures |

Core Freeze policy sections 6/8/10 and current certification ownership apply. Review
must check frozen manifests, exception roots, imports, supported legacy readers and
material identities. Behavioral restrictions require compatibility review even when
the frozen API digest does not move. No old experimental symbol is promoted.

## Mandatory adversarial design probes

- Stiffness and surface tension both N/m: typed meaning mismatch and untyped name mismatch refuse.
- Mechanical force N: explicit signal semantics carry force without an energy-transport classification.
- F and v enter a domain-owned transformation participant; its computed W output crosses
  an explicitly declared conserved-power transport. Direct F-to-power or semantic relabel refuses.
- Species A versus species B: even identical mol or mol/s dimensions refuse in one typed balance.
- Charge: C (or explicitly named charge rate A) balances only the same declared measure;
  a source/loss must be realized and named, never silently zero or converted to species.
- Thermal: exact-name legacy temperature transfer remains; typed conserved thermal power
  partitions account for all input; UNKNOWN delivery cannot become one.
- Typed serialization cannot be downgraded to /1 to discard meaning or transport; unknown
  schema/version, mixed declaration or incomplete /2 refuses.

## Scope limits and open decisions

No reaction/stoichiometry engine, scalar-to-vector shortcut, vector momentum projection,
field loss integration, time integration, frame-motion law, arbitrary transformation
registry, qualified mechanical capability or Domain Pack ontology is added. Each conserved
measure is an explicit domain declaration, not automatically verified science. Legacy
alias consumers need owner-reviewed migration dispositions before integration; a refusal
is not successful verification of the former application. The separate A-3 proposal must
resolve density/integrated/intensive mapping using unequal cells before typed fields run.

## Design review record

Independent Phase A/B static review requested before implementation. Findings and disposition
will be recorded in SEMANTIC_STATIC_REVIEW.md. No execution evidence is implied.

Phase A/B independent static review by `/root/semantic_review`: PASS before shared
implementation. No HIGH/MEDIUM design finding; no tests/imports/numerical code executed.
Named source/loss/accumulation bindings must read actual values, not infer physics.
Existing LossPath numerical fraction records will be reused for scalar partitions;
this bounded partition requires positive delivered fraction and existing positive partial
loss fractions. A complete single-sink loss remains unsupported, never defaulted.
