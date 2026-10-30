---
ai_schema_version: 1
doc_id: FORGE-BLINDFOLD-FIRST-EXPERIMENT-10H-PROMPT-DRAFT
doc_kind: SCIENTIFIC_DESIGN
doc_status: PROPOSED
authority_scope: NONE
source_ref: 921f8d26df920d209ee07faf11f435d88f4a1023
evidence_level: STATIC_REVIEW
last_reviewed: 2026-10-30
supersedes: none
---

# DRAFT session prompts: close the Step-1 gaps, then reach launch readiness for the first formal Blindfold experiment

**DRAFT (revision 2). It authorizes nothing by itself.** It becomes a valid instruction only when the owner pastes
it into a session. That session copies the approved scope into `docs/work/ACTIVE_PLAN.md` before any code, so
`ACTIVE_PLAN.md` stays the only executable queue.

This was written from a static reading at `921f8d26df920d209ee07faf11f435d88f4a1023`. Sources: `FORGE_GENESIS.md`
§10, §12, §18–19; `ACTIVE_PLAN.md`; PROGRESS 2026-10-19..30; the deep-audit
[blocker matrix](../evidence/deep_audit_2026_10_19/closure/GENESIS_BLINDFOLD_BLOCKER_MATRIX.md) (at `abed661f`, so
historical); `benchmarks/genesis_lite/analysis_v3.py`, `evaluator/score.py`, `score_v3.py`; the EXC-5 draft;
`engcore/blindfold/isolation.py`. The only thing executed for this revision was one arithmetic check (section 2, G1).

## Why revision 2

Revision 1 skipped half of the Step-1 blockers that the deep-audit matrix lists, and it had no power analysis.
Formal results run on that plan could have been valid but uninformative, or open to challenge. Every gap below was
checked against the live tree: an ID with no closure record after 2026-10-19 is counted as OPEN.

**What "good results" means here.** We cannot design the outcome. We can design the experiment so that whatever
it shows is valid, has enough power and cannot be challenged afterwards. Step 1 is the formal **baseline** campaign.
The Mind is measured against those frozen baselines in Step 2 (Genesis §10.5), so it stays out (D1).

---

## 1. Decisions

### Accepted by the owner in chat, 2026-10-30 ("Accept defaults")

D1 = Step 1, baselines only. D2 = EXC-5 as drafted, falling back to `NOT_QUALIFIED`. D3 = OS isolation on the WSL
`/opt` checkout, with the level stated. D4 = the owner seals the formal root, recorded as `INTERNAL_CUSTODY`.
D5 = the owner sets the cap at launch. D6 = one OD-3 batch (moved to Session B). D7 = `backup/…` branch pushes only.
D8 = M-3, review-r5, Stage 2b and EXC-6 stay deferred.

### New, raised by this review (the session prepares options; the owner decides at the hour-5 checkpoint)

| ID | Decision | Why it matters |
|---|---|---|
| D9 | The inference method and the number of independent units (gap G1) | Under the current test, a realistic lift can never be significant at the formal floor |
| D10 | The FDA-06 cap rule across kinds (G2) | Scoring cannot be frozen while out-of-family credit is capped for one kind only |
| D11 | FDA-18 answer exclusivity: randomize the kind mix, or declare it (G3) | A fixed mix lets a proposer infer answers by elimination |
| D12 | An independent reviewer for the preregistration (G12) | A self-review by Claude is not independent (Context Map §3) |

---

## 2. Gap register (what is still open for Step 1)

| # | Gap | Live status | Closure in these prompts |
|---|---|---|---|
| **G1** | **Power.** `analysis_v3.bounded_paired_test` is Hoeffding over unit scores in [-6, 6] (difference width 24), with Holm over every frozen baseline. Arithmetic run 2026-10-30, `.venv` Python: the observed unit-mean difference needed to reject at n = 30 units is 5.36 with 1 baseline and 7.58 with 20 (about 0.9–1.3 per campaign out of a maximum of 2). n = 240 needs 1.90–2.68; n = 1000 needs 0.93–1.31. EXC-4b observed mind_full − grammar = −0.058 per campaign. | A Step-1 freeze with this contract would make Step 2 almost impossible to pass. **Fix before the freeze**: power analysis plus options (A3). The "unit = six campaigns" reading comes from the module docstring (static). |
| G2 | **FDA-06**: out-of-family credit is capped for `discoverable` only, not `spurious_correlate` / `confounded` (REPRODUCED by R-06). `analysis_v3.compare_paired_scores` has no cap; no closure record. | OPEN → A4 |
| G3 | **FDA-18**: answer exclusivity in the campaign mix. | OPEN, undecided → A4 |
| G4 | **FDA-19**: the isolation probe cannot see the Genesis-lite leak class (root file, presentation key, driver memory, pilot outputs). | OPEN → A2 |
| G5 | **B-LEAK / OD-20**: the v0.3 pilots ran in-process, or through `proposer_host` under the same account. `OS_ISOLATION_BOUNDARY_VERIFIED` was reached by the isolation demo on `/opt` (2026-10-28, a patched tree on `dd567d53`), not by a v0.3 campaign. | OPEN → A2 |
| G6 | **FDA-21 / FDA-22**: baseline degrees of freedom and the kind-prior tell (a card feature that reveals the kind). | OPEN → A1, A4 (decide or disclose) |
| G7 | **PySR = 0.000** credit, and PySR has to run under isolation: no network, and a Julia depot readable by uid 65534 (today it is under `/home`, mode 0750). | OPEN → A1 |
| G8 | **P-4 formal driver**: EXC-4b used an out-of-tree driver, so the run is not identity-bound to a commit. | OPEN → A5 (in-tree, reviewed, committed) |
| G9 | **P-5 environment manifest** (Python, pip freeze, Julia and package versions, BLAS threads, kernel, wsl.conf), frozen and digested. | OPEN → A5 |
| G10 | **Cost**: the 3.67 h ESTIMATE used 20 BLAS threads per worker and no isolation. | OPEN → A6 |
| G11 | **Certificate**: binds `0d1d6823`; OD-3 rerun 1 refused; the fix is at `921f8d26`, not rerun. | OPEN → Session B |
| G12 | **Independent review** of the preregistration and inference. | OPEN → D12 |
| G13 | **No end-to-end rehearsal**: seal → run → reveal → adjudication → expressibility → analysis → replay has never run once on the formal driver. | OPEN → Session B |
| G14 | **Root-operator YAMA finding**: the proposer can read the operator's memory when the operator is root and both share an account. | OPEN → A2 (state the operator identity) |
| G15 | **Representation circularity**: 89/120 discoverable laws expressible by the grammar; 3 of 5 shapes overlap the generator's families. | Disclose and stratify → A4 |
| G16 | **The formal run must start from a committed, clean SHA** (the `/opt` tree carried an uncommitted patch). | → A5 / Session B |

Not blocking Step 1 by dependency (blocker matrix §3): FDA-01/02/03/04/14 (not on the Genesis-lite path), M-3, r5,
Stage 2b. OD-25 (CI dark) is a G0 item recorded under the owner's OD-1 choice; it does not stop a local formal run,
but the readiness report must state it.

---

## 3. Session A prompt: gap closure (about 10 h; paste from here)

> You are resuming Forge for one long bounded session (about 10 hours): **Session A, Step-1 gap closure**. The goal
> is to close or decide every Step-1 gap in the gap register of
> `docs/work/proposals/BLINDFOLD_FIRST_EXPERIMENT_10H_PROMPT_DRAFT.md` (§2, G1–G16 except G11 and G13, which are
> Session B), and to produce a preregistration v0.4 candidate. **You do not launch any formal campaign, generate or
> read its root, freeze or digest the preregistration, or run OD-3.**
>
> Owner decisions already made (2026-10-30): D1 Step 1 baselines only; D2 EXC-5 as drafted, falling back to
> `NOT_QUALIFIED`; D3 OS isolation on WSL `/opt`, level stated; D4 owner-sealed root, `INTERNAL_CUSTODY`; D5 cap at
> launch; D7 `backup/…` branch pushes only; D8 deferred. D9–D12 are decided by the owner at the hour-5 checkpoint.
>
> **Overriding rules.** `CLAUDE.md`, `FORGE_GENESIS.md`, the Completion Policy and `PERFORMANCE.md` win over this
> prompt: on a conflict, record OWNER_DECISION_REQUIRED and move to the next phase that does not depend on it.
> Invoke `forge-lessons-learned` first and write a `Lessons applied` list. Invoke `forge-scientific-review` after
> every change to arms, scoring, statistics, escrow or isolation, and fix or record every finding. Never write
> passed/verified/green without a command run here. Log every command, exit code and failing node ids to
> PROGRESS.md (UTF-8, append only). Use full 40-hex SHAs. Diff FAILED node ids against a pristine base before
> calling a red new. Run tiers alone. Commit locally at the end of each phase; push only `backup/…` branches.
>
> **A0. Resume and scope (0:30).** Verify live state: HEAD, status, log, the `ACTIVE_PLAN.md` head, WSL, and no other
> session or OD-3 running. Check each gap G1–G16 against the live tree; a gap someone closed since 2026-10-30 is
> marked closed with its evidence. Write one bounded `ACTIVE_PLAN.md` section with the eight Completion Policy fields
> (scope = A1–A7; expiry 7 days; prohibitions = "Never" below), and copy the EXC-5 fields if D2 applies. Print a
> status table in Egyptian Arabic.
>
> **A1. Baseline roster (G6, G7) (1:45).** Map each v0.3 arm to Genesis §10.5 per task class; a class without a
> strong applicable baseline is recorded as unable to support lift. Implement EXC-5 red-first, with every setting
> justified by design, never by EXC-2/3/4 outcomes. Make PySR run with no network and a Julia depot under `/opt`
> readable by uid 65534 (precompiled, digested). Check it on a fresh **development** root only. If discoverable
> credit stays 0 after one bounded attempt, mark it `NOT_QUALIFIED` and stop tuning. Record baseline degrees of
> freedom per arm (FDA-21) and test for a kind-prior tell (FDA-22): can a trivial classifier on public card
> features predict the kind above chance on dev worlds? Record the configuration source and tuning effort per arm.
>
> **A2. Isolated campaign path (G4, G5, G14) (2:00).** Read `isolation.py`, `isolation_probe.py`,
> `proposer_host.py`, `harness_v3.py`, `pilot_v3.py`. Add the smallest launcher that runs every v0.3 proposer as
> the isolated Discovery process, reusing the existing mechanism (no second escrow, no second protocol), red-first.
> Extend the probe to the Genesis-lite leak class (FDA-19): root file, presentation key, driver memory, other
> campaigns' outputs, pilot result directories, `/mnt/*` drvfs. Each new attack gets a positive control that must
> yield NOT_PROVEN. State the operator identity explicitly (YAMA finding) and test under it. Run on WSL `/opt` from a
> clean commit, as a non-root operator where the YAMA test needs it. Record the level reached and never relabel it.
>
> **A3. Power and inference (G1) (1:30).** Re-derive by reading the unit of `compare_paired_scores` (what one
> independent unit contains). Write a power analysis for Step 2's future lift test: minimum detectable difference
> versus n units and versus the number of Holm-tested baselines, using the bounded test as is. Then compare at most
> three **valid** alternatives, each with its assumptions stated: (i) more independent units at the measured cost;
> (ii) Holm over only the pre-declared strongest applicable baselines per class instead of every arm; (iii) a sharper
> valid bound (for example empirical-Bernstein, or an exact paired sign-flip/permutation test, with the null each
> actually tests). Check the type-I error of each on synthetic **null** development worlds in at most 30 CPU
> minutes, reported as development calibration. **Change no statistics code before D9.**
>
> **A4. Scoring and campaign design (G2, G3, G15) (1:00).** Draft the FDA-06 rule options (cap by kind, with each
> kind's semantics stated) and the FDA-18 options (randomized kind mix vs declared mix, plus what a stateless
> isolated proposer can infer). Design the stratified reporting for representation circularity: expressible vs
> not-expressible worlds, in-family vs out-of-family, and classes the grammar already solves reported as measuring
> representation (Genesis §10.3). Keep v0.2 files and the credit table untouched.
>
> **Hour-5 decision checkpoint.** Send the owner ONE message (Egyptian Arabic) with D9–D12, each with options, a
> recommendation and the evidence. Keep working on A5–A6 parts that do not depend on the answers. After the owner
> answers, implement the chosen D9/D10/D11 red-first, with review.
>
> **A5. Formal driver and manifest (G8, G9, G16) (1:00).** Move the sealed-root driver in-tree (with a
> `__main__` guard and `--root-file`; it refuses a root inside the tree or with mode other than 0600), reviewed and
> committed. Write the environment-manifest generator and its digest (P-5). New result files get provenance records
> in `CURRENT_PROVENANCE.json` in the same commit.
>
> **A6. Cost (G10) (1:00).** Run the 10-campaign rung for every arm and class through the isolated path, with BLAS
> threads = 1 and 4 workers, on a fresh development root. Write MEASURED (SHA, environment), then an ESTIMATE with an
> interval for the formal size that D9 implies.
>
> **A7. Preregistration v0.4 candidate and handoff (0:45).** New files only: classes, instance and unit counts from
> D9, seeds, the roster with digests, budgets, scoring v3 with the D10 and D11 rules, the primary outcome, null,
> test, multiplicity, minimum effect, power, WORKER_FAILED/invalid handling, abort rules, the leakage level from A2,
> custody `INTERNAL_CUSTODY`, circularity strata, the environment-manifest digest, and the deviation policy. Run a
> `forge-scientific-review`; the D12 independent review comes afterwards. Write a step record with a gap table
> (G1–G16: CLOSED with evidence / DECIDED / DISCLOSED / OPEN). Commit, push `backup/…`, final table in Egyptian
> Arabic.
>
> **Never.** Launch a formal campaign; generate, read or log the formal root; freeze or digest the preregistration;
> reuse any pilot root; tune any arm, threshold, prior or scoring rule on earlier pilot results; change Gen1 Mind
> code or start Stage 2b; edit v0.2-pinned files, the credit table or SHA-pinned evidence; widen a tolerance or add a
> skip to pass a gate; run OD-3; merge; push `main`; install dependencies beyond the present `genesis-baselines`
> extra; claim lift, novelty, validation or maturity.
>
> **Stop and ask.** A scientific invariant would weaken; a review finding cannot be fixed in scope; isolation cannot
> reach the D3 level; an alternative in A3 needs a new statistical assumption the owner has not accepted.

---

## 4. Session B prompt: certification and dress rehearsal (about 6–7 h; after Session A and D12)

> **Session B.** Preconditions: Session A's step record shows G1–G10, G12 and G14–G16 CLOSED, DECIDED or DISCLOSED,
> and the independent preregistration review (D12) has no open blocking finding. If not, stop and report.
>
> 1. **Dress rehearsal (G13).** Use the formal driver on a fresh development root at a small scale (for example 3
>    units per class), isolated, from the committed candidate SHA. Run the full chain: seal → run → reveal →
>    adjudication → expressibility → analysis → replay of every campaign bundle. Any failed step is a NO-GO; fix it
>    within scope and repeat once.
> 2. **OD-3 (G11).** Commit; run `forge_check --changed --base <full origin/main SHA> --workers 4`, then FAST alone,
>    and classify against `FAILURE_BASELINE_2026-10-20.md`. Then `local_assurance prepare` and `run` on that exact SHA
>    in the WSL OD-3 checkout, with nothing else running. Fix only owner-approved blocker classes (provenance
>    records, exact-node declared skips). Never regenerate pins.
> 3. **Readiness package.** `docs/work/BLINDFOLD_STEP1_LAUNCH_READINESS_<date>.md` with:
>    - a GO/NO-GO row per gap;
>    - the certificate SHA = candidate SHA;
>    - the launch commands (the owner generates the root outside any agent, 0600, outside the tree; sets the D5 cap);
>    - abort rules, and how a failed run is recorded without rerunning on the same root;
>    - what the campaign will not show (no Mind lift, no novelty, no external validation; CI dark per OD-25).
>
>    Commit, push `backup/…`, final table in Egyptian Arabic.

**Then the owner:** freeze the v0.4 preregistration (digest), generate and seal the root, set the cap, launch.

---

## 5. Time budget (ESTIMATE)

| Session | Phases | Estimate | Highest risk |
|---|---|---|---|
| A | A0–A7 plus the hour-5 checkpoint | ~10 h | A2 isolation wiring; A3 → D9 may raise the unit count, and with it the formal cost |
| D12 | independent review (human or another model) | owner | — |
| B | rehearsal + OD-3 + package | ~6–7 h | OD-3 refusals; the rehearsal exposing reveal/replay gaps |

**Honest consequence of G1:** if D9 picks more units, the formal campaign may cost many times the old 3.67 h
ESTIMATE. That is the price of a result that can actually show something. A3 and A6 give the number before anything
is approved.
