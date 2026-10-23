# GEN2-BR1.1 cloud-session evidence, 2026-10-22/23

**UNCERTIFIED. Developer review and test evidence for an IN-PROGRESS repair, not a validation, certification or
closure result.** Index and resume instructions: [`../../BR11_LOCAL_RESUME_CHECKPOINT_2026_10_23.md`](../../BR11_LOCAL_RESUME_CHECKPOINT_2026_10_23.md).

## Provenance

| Item | Value |
|---|---|
| Session | Claude Code cloud session (claude.ai/code), container `/home/user/forge`, venv `/home/user/.forge-venv` |
| Environment | Linux 6.18 x86_64, 4 CPUs, CPython 3.13.16 |
| Branch | `research/mind-gen2-authority-binding-v1`, base `1202ea6c3d96f5c31d0b142a32438da75e020cae` |
| Last code SHA | `d5ef1e3` (round-11 fix); records `ec2c000`; gates record `a96baa6` (full SHAs in the checkpoint) |
| Copied from | the session scratchpad (`/tmp/claude-0/-home-user-forge/<session>/scratchpad/` and `/tmp/claude-0/-home-user/<session>/scratchpad/`), which the README §8/§9 and PROGRESS items 15-26 cite as `.../scratchpad/...` |
| Kept | evidence that is cited by the report or PROGRESS, cannot be regenerated cheaply (independent LLM review outputs, interrupted-review probes), or is needed to resume |
| Not kept | copied repository trees, pytest temp trees, `__pycache__`, the full FAST logs, agent transcripts, and the large JSON record dumps the round-10/11 replay probes write (their scripts are kept and regenerate them) |

Every probe here imports engcore. They are **not** a test suite: run one only from a checkout of the SHA it names, as
`cd <checkout> && PYTHONPATH=<checkout>/src:<checkout> python <probe>`. Many contain absolute cloud paths; adjust them.

## Layout

| Path | Content | Why kept |
|---|---|---|
| `brief/BRIEF.md` | the owner's GEN2-BR1.1 brief (sections 0-36: Q1-Q7, the completion gate, the final tables, the five conclusions) | the authoritative closure criteria of this task |
| `review_results/review_r{9,10,11}_result.json` | each review round's six lens outputs (findings, prior-closure checks, Q1-Q7 verdicts with code path/test/evidence), the skeptics' verdicts on every BLOCKER/MAJOR, and the critic | non-reproducible independent review output; the source of README §9's rows and dispositions |
| `round12_interrupted/` | the round-12 workflow script, its input (`r11_findings.txt`), the two started lenses' probes and outputs, and `ROUND12_STATUS.md` | the interrupted round: what ran, what did not, and the unverified leads to triage first |
| `round11_probes/`, `round10_probes/` | each lens's, skeptic's and critic's probe scripts and outputs (`*.py`, `*.txt` under 200 KB) | reproductions of the round-10/11 findings and of their closure, cited by README §9 and PROGRESS items 23, 25 |
| `mutation/` | the round-10/11 mutant scripts (`mutate_r10.py`, `mutate2_r10.py`, `mutate_r11.py`) and the pre-fix runs (`r10_on_c69e579*.txt`, `r11_on_aad2f69.txt`) | the "N fail on the pre-fix tree" and "each mutant caught" claims (README §5) |
| `performance/` | BR1's alternating harness (`br1_alternating5.py`) and the raw `d5ef1e3` run, the round-10 A/B (`ab_check_timing.py`, `ab_e573096_d89dd3b.txt`), the contention runs (`contention_*.txt`), B11-4's large-account A/B (`p24_ab.txt`) and the instrumented/headroom probes (`p24_count.py`, `p28b.py`) | README §8's paired figures, A/B and contention claims |
| `gates/` | the base's failing ids (`base_ids_sorted.txt`, 99), the latest gate run's ids and summary (`failing_ids_ec2c000.txt`, `summary_ec2c000.txt`), the affected expensive test list and ids, the two pre-existing guard failures' messages | the FAST/guard/expensive differential (PROGRESS items 5, 10, 26) and the base it is computed against |
| `EVIDENCE_MANIFEST.sha256` | SHA-256 of every other file here | integrity |
| `.gitattributes` | `* -text` | git never rewrites these bytes |

## Verify

From this directory: `sha256sum -c EVIDENCE_MANIFEST.sha256`.
