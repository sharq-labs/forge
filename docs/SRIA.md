# Where `src/engcore/sria/` sits

About 20,000 lines across 53 modules — roughly a third of the source tree — and
**nothing outside it in `src/` imports it**. That fact is easy to find and easy
to misread, so this page says what it means.

It does not mean the tree is core, and it does not mean it is dead. It means
SRIA sits at a different altitude from everything else in `src/engcore/`.

## What it is

An independent **experimental-campaign, decision and assurance layer**. Where
the domains answer *what does this system do*, SRIA answers the questions one
level up:

| | |
|---|---|
| `evidence.py`, `admission.py`, `gateway.py`, `trust.py` | what may change scientific belief, and through which gate |
| `assurance/` | critics, an arbiter, assessments, uncertainty budgets, obligations |
| `decision/` | terminal decisions, hypotheses, utility, recommendation, replay, coherence |
| `campaign/` | the sequential research loop — budget, stopping, checkpoints, persistence, certification |
| `calibration/` | learned cost, failure and fidelity models, and their datasets |
| `charter.py`, `actions.py`, `outcomes.py`, `domain_pack.py` | the campaign's declared frame and its executable actions |

Its governing invariant is one sentence: **no source writes scientific belief
directly.** Candidate evidence goes through critics and an arbiter to an
admission decision, and only the belief-update gateway writes. The enforcement
is architectural — capability boundaries and an import scanner — not security
isolation, and `sria/__init__.py` says so plainly.

## What it is not

**It is not on the verification path.** Nothing in the MCP evidence layer, the
electro-thermal system, the battery domain, or any domain solver imports it.
A `CredibilityEvidenceReport` is assembled from a `ScientificResult`, a
`ValidationReport` and a `ProvenanceRecord`, and never consults SRIA. If the
whole tree were removed, every domain, the coupling, the credibility verdict
and the problem-builder boundary would behave identically.

Layering runs one way and is tested: SRIA imports the Scientific Core, the
Scientific Core never imports SRIA, and neither imports an LLM provider —
pinned by `tests/test_sria_m1.py`.

## What froze it

SRIA reached V0.1 through its own milestone sequence, each with acceptance
tests that also run standalone under `python -m tests.<module>`:

| Milestone | What it froze | Tests |
|---|---|---|
| **M1** | the trust foundation and its boundaries | `test_sria_m1.py` |
| **M2A / M2B** | the outcome bridge gate; calibration semantics | `test_sria_m2a_bridge.py`, `test_sria_m2b_calibration.py`, `test_sria_m21_semantics.py` |
| **M3** (+ M3.1–M3.4) | the assurance layer, trust chain, authorization, registration | `test_sria_m3_assurance.py`, `test_sria_m31…m34_*.py` |
| **M4** (+ M4.1–M4.4) | decision intelligence, replay, coherence, basis | `test_sria_m4_decision.py`, `test_sria_m41…m44_*.py` |
| **M5** (+ M5.1) | the sequential campaign loop; close-out and durability | `test_sria_m5_*.py`, `test_sria_m51_*.py` |
| **Core V0.3** | campaign persistence | `docs/milestones/core-v0.3-campaign-persistence-prereg.md`, nine `test_sria_campaign_persistence_v03*.py` modules |
| **E1 / E2 / E3** | the electrical experiment line and the adequacy obligation | `test_sria_e1_electrical.py`, `test_sria_e2_model_adequacy.py` (both **SHA-256 byte-pinned** by `experiments/electrical_e2/e2_config.py` and `experiments/electrical_e3/e3_config.py`), `test_sria_e3_adequacy_obligation.py` |
| **V0.1** | the minimal end-to-end certification path | `test_sria_v01_certification_path.py` |

The reasoning invariants V0.1 commits to — including the ones recorded but not
implemented — are in
[`docs/sria/scientific_brain_v0_1.md`](sria/scientific_brain_v0_1.md), frozen
against the M5.1 base commit. That document is normative for design review and
is explicit that it describes intent rather than current implementation.

## Reading it

Start at `sria/__init__.py`, which states the invariant and lists what M1
deliberately excludes; then `docs/sria/scientific_brain_v0_1.md` for the
reasoning contract; then `tests/test_sria_m1.py`, whose twelve numbered tests
are written as boundary proofs — each tries to do the wrong thing and asserts
that the architecture refuses.
