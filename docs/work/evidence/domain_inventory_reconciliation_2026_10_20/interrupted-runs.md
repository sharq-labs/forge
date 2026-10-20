# Incomplete FAST executions — not gate results

The initial sequential candidate run (changed-gate.json/txt) and pristine-main run (main-fast.json/txt) were deliberately terminated after 1122.514s and 971.776s. Their pytest exit codes are 4294967295, despite the outer recording wrappers exiting0. They reached approximately76% and69%; partial logs contain failures/errors but no complete node summary. These are INCOMPLETE, not PASS and not a usable exact baseline comparison.

Reason: the reviewed candidate was superseded by the staged-identity/classification repair in a separate worktree. Final candidate gate reruns the entire FAST selection with4workers and --dist loadfile, without exclusions. Replaced baseline with the identical4worker/loadfile selection.

An initial parallel-baseline invocation accidentally omitted --dist loadfile:

`C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest -q -n 4 -m "not expensive" --basetemp=D:/tmp/domain-main-parallel/bt`

Cwd merge-main-control/wonderful-gould-1c576f, main31192784. Terminated that invocation and its recording wrapper shortly after launch. No final result/output was captured; NOT COMPLETED. Reissued as main-fast-loadfile with --dist loadfile, matching forge_check's exact scheduler. This is an invocation correction, not an ignored test outcome.

Only explicitly identified owned process trees were stopped. Required final FAST and matching pristine-main FAST remain running; all test selections retained.
