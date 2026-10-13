# FORGE BioBridge
## Biomedical Research & Validation Roadmap

**Status:** FUTURE / RESEARCH CONCEPT — DOCUMENTATION ONLY  
**Established:** 2026-10-14  
**Base reviewed:** `main@2639a45d196e75ed89dde880873b0690cb12c1f5`  
**Owner decision:** Biomedical execution **NOT AUTHORIZED** by this document. No clinical or therapeutic use is asserted.

### Why this name?

**BioBridge** means extending FORGE's existing scientific-engineering foundations into *bounded* biomedical research using domain-specific models and evidence — without creating a second Mind, Trust Layer, evidence graph, or clinical decision engine.

### Mission

Develop a research-grade, scientifically falsifiable route that uses the existing FORGE architecture to **model, reason about, and validate bounded biomedical-engineering or bio-kinetics questions**. A demonstration is not a medical-device authorization, clinical validation, therapeutic claim, or scientific discovery certificate.

### Initial focus — in recommended order

| Focus | Example research problem | Rationale | Readiness claim |
|---|---|---|---|
| Biomedical Engineering — physical systems | Thermal behavior of an instrument/lab-equipment mock-up or non-patient-facing benchtop component | Closest to current heat / multiphysics / uncertainty substrate | **Candidate only** |
| Bio-kinetics (nonclinical) | Distinguish two bounded reaction models using simulated observations and an independent laboratory dataset if available | Tests Mind/Discovery transfer to another reasoning structure | **Candidate only** |
| Systems biology | Carefully specified small reaction network with observable endpoints | Additional scientific-evidence and data-contract work | **Future** |
| Therapeutic Hypothesis Assurance | Mechanistic/observational hypothesis evaluation | Requires additional, distinct biological and clinical evidence semantics | **Separate LATER decision** |
| Clinical Decision Support / Diagnosis / Treatment | Decisions affecting real patients | Separate safety, clinical-validation and regulatory program | **OUT OF SCOPE** |

### What this folder is — and is not

- It is a **proposal** for an eventual research track and a set of explicit go/no-go gates, not an executable task list or a new development epic.
- It does not change `docs/work/ACTIVE_PLAN.md`, `docs/project/FORGE_MASTER_PLAN.md`, `FORGE_GENESIS.md`, `scientific_capability_completion.json`, or maturity/status semantics.
- The live execution sequence remains **G0 → A1 (Genesis-lite / Blindfold) → A2 (Minimal Mind) → B1 (narrow engineering demo)**.
- The current active maturity epic is `battery.thevenin_1rc`. New biomedical capability foundations require the existing policy's owner-approved canonical epic change or a narrowly scoped reviewed exception when the work becomes eligible. This document grants neither.
- Biomedical and therapeutics are explicitly **LATER** in the current Master Plan; none of this work should interrupt the active Trust and Genesis gates.
- **Tests run for this proposal: NOT RUN.** It records no new result, qualified provider, clinical validation, or capability maturity.

### Documents

1. [ROADMAP.md](ROADMAP.md) — phased proposal, initial pilot, decision gates and dependencies.
2. [EVIDENCE_AND_SAFETY.md](EVIDENCE_AND_SAFETY.md) — evidence semantics, safety boundaries, data and review requirements.

### Architecture

```text
User/research question
    ↓
FORGE Mind / Discovery (proposal + experiment planning; only after justified)
    ↓
Existing typed model/provider selection and bounded domain pack
    ↓
External solver + observable / measurement adapter
    ↓
Existing applicability, provenance, replay, UQ and Trust authority
    ↓
VERIFIED / REVIEW / REFUSED as authorized by existing FORGE semantics
    ↓
Independent research evaluator and reproducible research report
```

**A biomedical domain pack supplies scientific meaning; it never upgrades a verdict or declares a validation grade by itself.**

### Primary source-of-truth references

- [Master Plan](../project/FORGE_MASTER_PLAN.md) — **LATER** classification.
- [Active Plan](../work/ACTIVE_PLAN.md) — only execution queue.
- [Completion Policy](../project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md) — active epic, gates and maturity.
- [Genesis](../discovery/FORGE_GENESIS.md) §17.1 — therapeutics postponed; start biological transfer only with bounded mechanistic bio-kinetics.
- [Working Contract](../../CLAUDE.md) — science, authority, no silent defaults, certification and testing.

### First later-stage approval question

> After the active G0/A1/A2/B1 gates permit a new initiative, should the owner approve a **single, explicitly bounded nonclinical biomedical benchmark** with an external domain expert, independent measurements and a fixed evaluation budget?

Until that approval: **planning only; no implementation or dataset ingestion**.
