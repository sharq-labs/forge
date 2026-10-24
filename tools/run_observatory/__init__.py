"""FORGE Run Observatory -- an immutable, queryable ledger of what ran (BR-RUN-OBS-01).

Developer and performance infrastructure. One wrapper (``python -m tools.run_observatory run --
<command>``) executes any command and seals a receipt: which code, which workload, which machine,
how long, how much CPU, memory and I/O, and how it ended. Receipts live outside the repository in
a configurable run root and are indexed by SQLite.

A receipt is never scientific evidence and never certification. The observatory reads exit codes
and declared counters; it issues no scientific verdict, and nothing in FORGE reads a receipt to
decide one. The scientific authorities keep SUPPORTED / REFUSED / MODEL_ADEQUATE and the rest.
See ``docs/performance/run-observatory.md``.
"""

from __future__ import annotations

RECEIPT_SCHEMA = "forge.run_observatory.receipt/v1"
WORKLOAD_SCHEMA = "forge.run_observatory.workload/v1"
ENVIRONMENT_SCHEMA = "forge.run_observatory.environment/v1"
PENDING_SCHEMA = "forge.run_observatory.pending/v1"
LEDGER_SCHEMA_VERSION = 1

CLASSIFICATION = ("developer telemetry: not scientific evidence, not certification; "
                  "never read to decide a scientific result")

RUN_KINDS = ("TEST", "FAST", "SCIENTIFIC", "REPLAY", "BENCHMARK", "SOLVER", "PROVIDER", "DATA_PIPELINE",
             "CAMPAIGN", "FORMAL", "CERTIFICATION", "UTILITY")

RUN_STATUSES = ("RUN_PASS", "RUN_FAIL", "RUN_ERROR", "RUN_INTERRUPTED")
COMPARABILITY_CLASSES = ("EXACT_COMPARABLE", "CONFIG_VARIANT", "CODE_VARIANT", "ENVIRONMENT_VARIANT",
                         "WORKLOAD_VARIANT", "NOT_COMPARABLE")
PERFORMANCE_READINGS = ("PERFORMANCE_IMPROVED", "UNCHANGED", "PERFORMANCE_REGRESSION", "NOT_ENOUGH_REPEATS",
                        "NOT_COMPARABLE")
REPLAY_READINGS = ("REPLAY_EXACT", "REPLAY_MISMATCH", "NOT_CHECKED")
FAILURE_SET_READINGS = ("NO_NEW_FAILURES", "NEW_FAILURES", "NOT_CHECKED")

#: Whether a metric could be measured on this platform. A capability label for a number, not a
#: reading about anything the number describes -- the one place "SUPPORTED" appears here.
METRIC_SUPPORT = ("SUPPORTED", "PARTIAL", "UNSUPPORTED")

#: Verdicts owned by FORGE's scientific authorities. No observatory reading may ever be one of these.
FORBIDDEN_SCIENTIFIC_VERDICTS = frozenset({
    "SUPPORTED", "REFUSED", "CONTRADICTED", "MODEL_ADEQUATE", "MODEL_INADEQUATE", "DISCOVERY_CONFIRMED",
    "VALIDATED", "VERIFIED", "CERTIFIED",
})

REDACTED = "<REDACTED>"
