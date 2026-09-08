# Where `src/engcore/sria/` sits

**19,887 lines across 53 modules — 26.9% of the source tree — and nothing
outside it in `src/` imports it.** Those numbers are measured, and the commands
that produce them are in *The numbers, measured* below. The fact is easy to find
and easy to misread, so this page says what it means, what depends on it, and
what separating it would involve.

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

---

## The numbers, measured

Taken on the tree at the commit that added this section. Every one is
reproducible from the command beside it.

| | | how |
|---|---|---|
| lines | **19,887** | `find src/engcore/sria -name "*.py" \| xargs wc -l \| tail -1` |
| modules | **53** | `find src/engcore/sria -name "*.py" \| wc -l` |
| share of `src/` | **26.9%** of 73,867 lines | the same two counts |
| imports from outside `src/engcore/sria/` | **0** | `grep -rn "engcore\.sria\|from \.\.sria\|from \.sria\|import sria" --include=*.py src/ \| grep -v "^src/engcore/sria/"` |
| tests | **630** across 34 `test_sria_*.py` modules, of 2,955 in the suite (21.3%) | `pytest tests/test_sria_*.py --collect-only -q` |
| byte-pinned test modules | **2** — `test_sria_e1_electrical.py`, `test_sria_e2_model_adequacy.py` | pinned by `experiments/electrical_e2/e2_config.py` and `experiments/electrical_e3/e3_config.py` |

The import count is the one worth running yourself. It is zero, and it is zero
in the direction that matters: **nothing depends on SRIA, and SRIA depends on
the rest of the tree.**

## What depends on it

Frozen experiments, and nothing in `src/`. Measured with
`for d in experiments/*/; do grep -rl sria "$d"; done`:

| Experiment | How it depends |
|---|---|
| `electrical_e1`, `electrical_e2`, `electrical_e3` | **They are SRIA experiments.** E1 is the campaign over an electrical model space, E2 the model-adequacy study, E3 the adequacy obligation. Their configs, harnesses, truths, results and reports are SHA-256 pinned, and two of the pinned files are SRIA's own test modules. |
| `electrical_v01_demo` | the minimal end-to-end certification path |
| `falsification` | `benchmark.py` and `s11_sweep.py` use the campaign and decision layers |
| `thermal_t1` | **the one that is easy to miss.** `t1_run.py` imports `src.engcore.sria.calibration`, and T1's results carry SRIA schema strings (`sria_model_fidelity_rung/1`, `sria_model_fidelity_relationship/1`). T1's fidelity ladder *is* an SRIA record. |

`design_d3`, the multirotor studies, and the kinetics experiments do **not**
reference it — worth stating, because "the campaign layer" sounds like it would
be under every design study and it is not.

**Nothing in `src/`.** Verified by the command above, and separately by
`tests/test_sria_m1.py`, which pins the layering in the other direction too:
SRIA imports the Scientific Core, the core never imports SRIA, and neither
imports an LLM provider.

## Which way the dependency runs

SRIA reaches into four subsystems and none of them reaches back. Counting
import references:

| SRIA imports | import statements |
|---|---|
| `scientific/` | 50 |
| everything else under `engcore/` | **0** |

`scientific.serialization` alone accounts for 39 of the 50 — schema strings for
the records SRIA writes. That is the shape of a consumer, and it is why the
tree can be read as a layer rather than as a fork.

**This table used to say something else, and it was wrong.** It read
`scientific/ 55, data/ 15, inference/ 3, domains/ 2`. There is no import of
`data/`, `inference/` or `domains/` anywhere under `sria/` — not in this
commit and not in any commit reachable in this repository. Corrected against a
measurement rather than adjusted: every import under `sria/` is resolved,
relative ones included, and counted by subpackage. SRIA reaches **one**
package, not four.

The numbers are now checked rather than published:
`tests/test_core_guards.py::test_the_sria_dependency_table_in_the_docs_matches_the_tree`
fails if the counts move or if this table stops agreeing with them, and
`::test_nothing_under_sria_imports_a_domain_or_a_system` fails if SRIA reaches
any `engcore` package other than `scientific/`. Both walk the tree; neither
reads a list of module names.

A caution for anyone measuring this again with `grep`: the one-line command in
the table above answers the INBOUND question and is exact for it. The outbound
question cannot be answered by grepping for `engcore.` — SRIA reaches the core
through relative imports (`from ...scientific.results.result import ...`) in
all 50 cases, and `src/engcore/sria/trust.py::scan_imports` discards relative
imports by design, so it is not the tool for this direction either.

## What separating it would involve

Stated as scope, not as a recommendation.

**What is easy.** The import direction. A consumer with zero inbound edges
lifts out without touching a single caller: no domain, no solver, no system, no
MCP boundary would change a line. The one subsystem it imports, `scientific/`,
becomes a dependency of the new repository rather than a sibling package.

**What is not.**

1. **The frozen experiment pins break, and they are the awkward kind.**
   `experiments/electrical_e2/e2_config.py` and `electrical_e3/e3_config.py`
   pin `tests/test_sria_e1_electrical.py` and
   `tests/test_sria_e2_model_adequacy.py` by SHA-256 over their bytes. Moving
   those files to another repository does not change their bytes, but it moves
   them out of the path the pin resolves, so either the experiments move too or
   the pins are rewritten to point across a repository boundary — which is the
   thing a pin exists to make impossible. The thermal re-freeze is the worked
   example of what a deliberate re-pin costs, and that one moved four files
   inside one tree.

2. **The thermal line is pinned to an SRIA import.** `thermal_t1/t1_run.py`
   imports `sria.calibration` and is itself byte-pinned by
   `t2_config.T1_FROZEN_FILE_DIGESTS`, which `t3_config` pins in turn. So
   separating SRIA does not break one experiment line, it breaks two, and the
   second one is the three-link cascade the thermal re-freeze had to walk.

3. **The E1–E3 experiment line goes with it, or it splits.** Those experiments
   *are* SRIA experiments; their evidence documents cite them. Leaving them
   behind leaves `experiments/` referencing a package that is no longer present.

4. **One subsystem becomes a published interface.** `scientific/` is imported
   freely today because it is in the same tree. Across a boundary it needs a
   version, and every future change to `scientific.serialization` acquires a
   downstream consumer.

   This point used to name four subsystems, on the strength of the table above
   before it was corrected. It is **one**, which makes this the cheapest of the
   five rather than a second hard one: the interface to version is a single
   package, and 39 of the 50 references into it are schema strings.

5. **The test suite splits 630/2,325**, and the tiering in `docs/TESTING.md`
   splits with it.

**What it would not fix.** Nothing about the verification path, because SRIA is
not on it. The separation is a packaging decision about what a reader and a
buyer are handed, not a correctness one.

## Recommendation: document in place

**Document in place. Do not separate.** The cost is not the code motion — that
part is genuinely easy — it is that separation breaks two pinned experiment lines — the electrical one and, less obviously, the thermal cascade — whose
entire purpose is to make "this was not edited" a checkable claim, and it breaks
them to solve a problem that a paragraph in the README solves.

The reasoning:

* **The problem is legibility, and legibility is cheap.** A buyer's objection is
  *why is a third of this code unexplained*, not *why is it in the same
  repository*. That objection is answered by naming it in the README where they
  meet it, with the numbers and the one-line command that proves the import
  count. That is what this round did.
* **Separation trades a documentation problem for an integrity one.** Rewriting
  a pin to point across a repository boundary weakens exactly the guarantee this
  project sells. This repository has re-pinned deliberately once, for the
  thermal tree, and the justification there was that the pin was protecting a
  defect. No defect is being protected here.
* **The zero-import property is the asset, not the liability.** It is what makes
  the claim "SRIA is not on the verification path" checkable in one grep. A
  reader who doubts the credibility layer can satisfy themselves in seconds. In
  a separate repository the same claim becomes an assertion about two trees.
* **Nothing is foreclosed.** Zero inbound edges is what makes separation
  cheap-in-the-code, and that stays true. If a buyer wants only the verification
  path, the tree lifts out then, with the pins handled deliberately as part of a
  transaction rather than pre-emptively.

**The cost of the recommendation**, stated plainly: the repository stays 27%
larger than the product it is being read for, and every future reader still has
to be told. That is a real and recurring tax, and it is paid in prose. The
alternative pays it once in integrity, and integrity is the thing being sold.

**What would change the recommendation.** If SRIA acquires its own release
cadence, or an outside consumer, or a dependency the verification path must not
carry, the balance moves — at that point separation buys something, and the pin
rewrite is a cost against a benefit rather than against a paragraph.
