# FORGE BioBridge — Scientific Evidence, Data and Safety Boundaries

**Status:** Concept specification for a future nonclinical research initiative. **No biomedical capability verified. Tests: NOT RUN.** This document does not define a second Trust/Validation engine; it records additional **domain obligations** and maps them to the existing FORGE authorities.

## 1. Primary distinction: scientific evidence is use-case dependent

| Evidence type | Valid interpretation | Must not be promoted to |
|---|---|---|
| Numerical unit/integration/mesh convergence | Numerical correctness in tested mathematical conditions | Biological truth or empirical validation |
| Benchmark or cross-solver agreement | Verification/reference agreement | Patient outcome or clinical validity |
| Synthetic bio-kinetics trap-world success | Blind synthetic reasoning competence within benchmark representation | Novel therapeutic discovery |
| Independent benchtop measurement | Empirical validation inside measured setup and applicable envelope | Safety/efficacy in humans |
| Independent biological assay / measurements | Evidence about the specific measured biological endpoint and context | Clinical benefit or treatment recommendation |
| Observational clinical association | Observational association with study-specific biases and confounding | Causality, diagnosis reliability or therapeutic efficacy |
| Prospective clinical study | May support a specific clinical use when professionally designed/validated | General clearance for unrelated populations or claims |

Clinical evidence semantics must be designed and independently assessed in a **separate later program**; the existing mechanistic Trust Layer does not automatically confer them.

## 2. Mandatory research boundaries

1. **Intended use:** One specific nonclinical research question; study population, sample, device context and excluded uses explicit.
2. **Observable identity:** What was measured versus what the solver outputs (sensor position, time interval, averaging operator, units, instrument calibration, detection limit).
3. **Applicability:** Temperature / concentrations / load / geometry / biological context and actual fitted-parameter range; outside scope refuses.
4. **Verification ≠ validation:** Distinct authority and records; no euphemistic `VALIDATED` label for reference/solver agreement.
5. **Parameter origin:** Literature, measurement, calibration, assumption and unknown tracked separately with licensing and version.
6. **Uncertainty:** Measurement, parameters, numerical error, model discrepancy, and correlation explicitly addressed; UNKNOWN must not become zero.
7. **Evidence independence:** Calibration and evaluation split frozen before observing the withheld set; record who held it and possible leakage.
8. **Reproducibility:** Snapshot solver, code, inputs and domain model; permit clean-environment replay with disclosed non-determinism.
9. **Failure behavior:** Missing data, poorly identifiable parameters, incompatible observation operators, unqualified providers or unsupported biological context cannot produce a supported claim.
10. **Independent scrutiny:** At least one qualified domain specialist checks the physical/biological interpretation, applicability and negative controls.

## 3. Research data and participant safety

- **Phase-one data:** Use non-personal, consented and legally distributable benchtop measurements or openly licensed nonclinical research data that have been checked for reuse terms.
- **No identifiable health records:** No patient information or sensitive clinical datasets in initial pilot or public artifacts.
- **Data permissions:** Record source URL/owner, version, usage restrictions, commercial reuse conditions, citation, retention and permitted sharing; no silent scraping.
- **Human subjects:** Any later use involving human participants, clinical records or specimens requires an appropriately approved protocol, applicable privacy/data-protection controls and qualified institutional review.
- **Regulated software:** A later clinical-facing product requires intended-use classification, quality/safety management, clinical evaluation and jurisdiction-specific regulatory review before external clinical claims. Merely labeling a product `research` does not replace those obligations.
- **Misuse guard:** Reports explicitly prohibit interpreting outputs as diagnoses or treatment recommendations.

## 4. Scientific red-team tests (design only)

| Adversarial test | Required expected behavior |
|---|---|
| Change observed sensor coordinate without changing data | Comparison refuses or identifies invalid observation mapping |
| Remove a boundary condition / change material validity range | Applicability or input gate refuses; no silent default |
| Fit parameters on held-out data then call them independent | Evaluation marked invalid or leakage-reported; no independent claim |
| Remove measurement UQ or declare absent discrepancy = 0 | No confidence upgrade; explicit UNKNOWN |
| Swap a benchmark oracle for a real experiment | Evidence type stays distinguishable; no silent experimental-validation promotion |
| Perturb a sample outside the allowed biological/physical envelope | REJECT/REVIEW; no trusted extrapolation |
| Duplicate a test across many variants and report best only | Multiplicity tracked; selection bias disclosed |
| Change a dataset version, consent/licensing term or manifest checksum | Evidence and reuse permissions rechecked; stale support not retained |
| Seek patient diagnosis/treatment from a research result | Refuse the unsupported clinical interpretation |

All tests here are **proposed**; none were run or evidenced in this documentation change.

## 5. Owners and review gates

| Area | Canonical authority / responsibility |
|---|---|
| Scientific Trust/verdict, provenance, UQ | Existing FORGE layers; preserve current semantics and certified boundaries |
| Domain model and mechanisms | Future owner of a specifically bounded Biomedical Domain Pack |
| Predictive Mind/Discovery | Existing `FORGE_GENESIS` contracts; no standalone medical Mind |
| Benchmark and independent scoring | External research reviewer; evaluation outside assessed Mind |
| Clinical validity / study approvals | Separate qualified clinical/research/regulatory owners, **not** current FORGE Trust |
| Activation and development queue | `ACTIVE_PLAN`, owner decisions and Completion Policy |
| Data licences, privacy and sharing | Project data governance and legal review before access/distribution |

## 6. Go / No-go rule

**GO (research)** only if the owner approves an eligible narrow slice *after* required active-program gates, a domain expert reviews it, independent evidence is available, and applicable data rights can be documented.

**NO-GO** for clinical diagnosis, therapeutic advice, patient-facing use, unconsented data, unvalidated efficacy claims, absent measurement uncertainty disguised as zero, or any requirement that would bypass existing Trust/Genesis/Completion gates.

**Future clinical work is an independent program decision, not Phase 2 of this research roadmap.**
