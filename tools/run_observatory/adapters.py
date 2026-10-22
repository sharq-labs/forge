"""Adapters: how a kind of command is read. v1 ships GENERIC_COMMAND and PYTEST.

An adapter may add arguments that only make the command *report* (pytest's ``--junitxml``), may map
an exit code onto a run status, and may supply trusted counters from a structured report. It may
never infer counts from free log text, and it never changes what the command computes.

Extension point for solver / provider / replay adapters (v2): subclass :class:`GenericCommand`,
override ``prepare`` / ``classify`` / ``counters``, and register the instance in ``ADAPTERS``.
Domain identities a replay adapter knows (output or trace identity) go into the child's report
file (``FORGE_RUN_REPORT_FILE``) or the ``--output-identity`` / ``--trace-identity`` options; the
observatory compares them, it never decides what replay equivalence means.
"""

from __future__ import annotations

from pathlib import Path
import signal
import sys
from typing import Sequence

#: Windows' exit status for a process ended by a console control event (Ctrl+C / Ctrl+Break).
STATUS_CONTROL_C_EXIT = 0xC000013A


class GenericCommand:
    name = "GENERIC_COMMAND"

    def prepare(self, argv: Sequence[str], artifacts_dir: Path) -> tuple[list[str], dict]:
        """Arguments appended to the child's command line, and context for ``classify``."""
        return [], {}

    def classify(self, returncode: int | None, *, interrupted: bool, context: dict) -> dict:
        result = {"status": "RUN_FAIL", "exit_code": returncode, "raw_returncode": returncode,
                  "terminated_by_signal": None, "adapter_outcomes": None, "notes": []}
        if returncode is not None and returncode < 0:
            result["exit_code"] = 128 - returncode
            try:
                result["terminated_by_signal"] = signal.Signals(-returncode).name
            except ValueError:
                result["terminated_by_signal"] = f"SIG{-returncode}"
        if interrupted:
            result["status"] = "RUN_INTERRUPTED"
        elif returncode is not None and returncode < 0:
            result["status"] = "RUN_ERROR"
        elif sys.platform == "win32" and returncode == STATUS_CONTROL_C_EXIT:
            result["status"] = "RUN_INTERRUPTED"
            result["notes"].append("child ended by a console control event (STATUS_CONTROL_C_EXIT)")
        elif returncode == 0:
            result["status"] = "RUN_PASS"
        return result

    def counters(self, result: dict) -> dict[str, int]:
        return {}


class Pytest(GenericCommand):
    """pytest: exit codes per pytest's contract, outcomes from its own JUnit XML report."""

    name = "PYTEST"
    _EXIT = {0: "RUN_PASS", 1: "RUN_FAIL", 2: "RUN_INTERRUPTED", 3: "RUN_ERROR", 4: "RUN_ERROR", 5: "RUN_FAIL"}

    def prepare(self, argv: Sequence[str], artifacts_dir: Path) -> tuple[list[str], dict]:
        for i, arg in enumerate(argv):
            for flag in ("--junitxml", "--junit-xml"):
                if arg == flag and i + 1 < len(argv):
                    return [], {"junit": argv[i + 1], "injected": False}
                if arg.startswith(flag + "="):
                    return [], {"junit": arg.split("=", 1)[1], "injected": False}
        report = artifacts_dir / "junit.xml"
        return [f"--junitxml={report}"], {"junit": str(report), "injected": True}

    def classify(self, returncode: int | None, *, interrupted: bool, context: dict) -> dict:
        result = super().classify(returncode, interrupted=interrupted, context=context)
        if interrupted or returncode is None or returncode < 0:
            pass
        elif returncode in self._EXIT:
            result["status"] = self._EXIT[returncode]
            if returncode == 5:
                result["notes"].append("pytest exit 5: no tests were collected")
        elif returncode != STATUS_CONTROL_C_EXIT:
            result["status"] = "RUN_ERROR"
        result["adapter_outcomes"] = self._outcomes(context)
        if result["adapter_outcomes"] is None:
            result["notes"].append("no JUnit report was produced; outcome counts are not available")
        return result

    @staticmethod
    def _outcomes(context: dict) -> dict | None:
        import xml.etree.ElementTree as ET  # only pytest runs pay for it

        try:
            root = ET.parse(context["junit"]).getroot()
        except (OSError, ET.ParseError, KeyError):
            return None
        counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0}
        failures = []
        for case in root.iter("testcase"):
            nodeid = f"{case.get('classname', '')}::{case.get('name', '')}"
            skipped = case.find("skipped")
            if case.find("failure") is not None:
                counts["failed"] += 1
                failures.append(nodeid)
            elif case.find("error") is not None:
                counts["errors"] += 1
                failures.append(nodeid)
            elif skipped is not None:
                counts["xfailed" if skipped.get("type") == "pytest.xfail" else "skipped"] += 1
            else:
                counts["passed"] += 1
        support = {k: "SUPPORTED" for k in counts}
        support["xpassed"] = "UNSUPPORTED"  # JUnit XML records a non-strict xpass as a plain pass
        return {**counts, "xpassed": None, "total": sum(counts.values()), "failure_set": sorted(failures),
                "support": support, "source": "JUNIT_XML", "report": context["junit"]}

    def counters(self, result: dict) -> dict[str, int]:
        outcomes = result.get("adapter_outcomes")
        return {"tests": outcomes["total"]} if outcomes else {}


ADAPTERS = {"generic": GenericCommand(), "pytest": Pytest()}
_ALIASES = {"GENERIC_COMMAND": "generic", "PYTEST": "pytest"}


def get(name: str) -> GenericCommand:
    key = _ALIASES.get(name, name).lower()
    if key not in ADAPTERS:
        raise ValueError(f"unknown adapter {name!r}; available: {', '.join(sorted(ADAPTERS))}")
    return ADAPTERS[key]
