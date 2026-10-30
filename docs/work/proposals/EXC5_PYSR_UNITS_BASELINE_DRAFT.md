---
ai_schema_version: 1
doc_id: FORGE-EXC5-PYSR-UNITS-BASELINE-DRAFT
doc_kind: SCIENTIFIC_DESIGN
doc_status: PROPOSED
authority_scope: NONE
source_ref: a9ddbf274cc5d24a8f14236586d8bd94a2760fcb
evidence_level: STATIC_REVIEW
last_reviewed: 2026-10-30
supersedes: none
---

# DRAFT EXC-5: a units-aware PySR development arm (a stronger competence baseline)

**DRAFT for the owner's decision. NOT approved, NOT in `ACTIVE_PLAN.md`, authorizes no code.** If approved, the eight
fields are copied into `ACTIVE_PLAN.md` "Active-epic exceptions" before any code, as for EXC-2..EXC-4.

## Why (static reading at `a9ddbf27`; nothing re-run)

- Genesis requires the **strongest applicable** equal-budget baseline (`FORGE_GENESIS.md` "Careful equal-budget
  baseline"). A weak baseline inflates any later Mind lift.
- The registered `pysr_symbolic` arm (`benchmarks/genesis_lite/arms_v3.py`, `PYSR_SETTINGS`) runs with
  `niterations=40`, `maxsize=15`, operators `+ - * /`, `exp`, `log`. It has no power operator, passes no units, and keeps
  PySR's default single chosen equation. A non-integer power law can only come out as `exp(c*log(x))`, which depends on
  how `to_grammar` maps it. The EXC-2 summary records discoverable credit 0.0 for this arm.
- PySR / SymbolicRegression.jl support soft dimensional constraints (`X_units`, `y_units`,
  `dimensional_constraint_penalty`, `dimensionless_constants_only`), but there are open user reports of breakage
  (PySR discussions #479, #950). UNVERIFIED for the pinned PySR 2.7.2 in `/opt/forge-mvp-20261028/.venv`.
- Static reading only: the 0.0 is **not** shown to be a configuration effect. It is a hypothesis.

## Proposed exception (eight fields)

1. **Exact scope:** a **new** arm `pysr_units` in a new `benchmarks/genesis_lite/arms_pysr_units_v3.py`, registered
   in `pilot_v3.py` and bound into `harness_v3.development_identity`, plus its tests. The registered `pysr_symbolic`
   arm, `PYSR_SETTINGS`, pinned v0.2 files, escrows and the credit table are **not touched** (no silent edit of a
   registered arm).
2. **Allowed work:** pass the presented card's public units as `X_units`/`y_units` (refuse on unparseable units, as
   EXC-4 does); add `^` with a constant exponent (`constraints` so the exponent is a constant); the same budget as
   `grammar_enumeration` measured as wall-clock and evaluations, declared before the pilot; choose among PySR's Pareto
   front with the shared held-out gate; record per-campaign whether the dimensional constraint was satisfied.
3. **Reason:** remove a plausible baseline-weakness confound before any Mind lift is measured.
4. **Start condition:** owner approval; EXC-4 pilot report recorded (so the EXC-4 root and this arm are separate).
5. **Exit condition:** red-first tests (units refused/accepted, constraint flag recorded, gate parity with
   `pysr_symbolic` on a units-free card); `forge-scientific-review`; one development pilot on fresh worlds reporting
   `pysr_units` vs `pysr_symbolic` vs `grammar_enumeration`, descriptive only.
6. **Expiry / timebox:** `OWNER_DECISION_REQUIRED` (proposed: 2026-12-15).
7. **Owner approval:** not given.
8. **Prohibited:** editing `pysr_symbolic` or its recorded results; tuning on EXC-2/3/4 results or roots; any
   preregistration, formal campaign, lift or superiority claim; new dependency installs beyond the existing `/opt`
   venv without separate approval.

## Risks

- PySR's dimensional constraint is a soft penalty: an expression may still violate units. The arm must report that,
  not hide it.
- Making the baseline stronger can shrink or remove a later Mind lift. That is the purpose, not a defect.
