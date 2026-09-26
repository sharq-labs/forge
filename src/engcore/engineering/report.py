"""Flagship report rendering with a fixed, enforced section list and statement labels.

A report is prose over a run: it may not silently omit a section, and every claim class is labelled so a reader can tell what kind of
statement it is.  The labels are FACT (a checkable statement about the artifacts), REFERENCE DATA (from an external source with
provenance), ASSUMPTION (declared, not evidenced), MODEL OUTPUT (a provider's computed value), CORROBORATION (independent solvers
agreeing) and VALIDATION (a comparison with a reference or measurement, stated with its scope; a comparison with a NUMERICAL benchmark is labelled as such and is not experimental validation).  Nothing here computes a number: the
numbers are passed in from the run that produced them.
"""

from __future__ import annotations

from typing import Mapping

from ..scientific.errors import InvalidScientificProblem

REQUIRED_SECTIONS = (
    "Engineering question", "System definition", "Assumptions", "Inputs and sources", "Providers and models", "Applicability", "Execution", "Results",
    "Verification", "Cross-provider results", "Reference comparison", "Uncertainty", "Constraint and conservation checks", "Negative control",
    "Scientific status", "Known limitations", "Reproduction command",
)
LABELS = ("FACT", "REFERENCE DATA", "ASSUMPTION", "MODEL OUTPUT", "CORROBORATION", "VALIDATION")
LEGEND = ("Statement labels: **FACT** a checkable statement about the run artifacts - **REFERENCE DATA** taken from an external source with provenance - "
          "**ASSUMPTION** declared, not evidenced - **MODEL OUTPUT** a provider's computed value - **CORROBORATION** independent solvers agreeing "
          "(never validation) - **VALIDATION** comparison with a reference or measurement, stated with its scope (a numerical benchmark is not an experiment).")


def render_report(title: str, sections: Mapping[str, str], *, identity_line: str, summary_text: str) -> str:
    missing = [s for s in REQUIRED_SECTIONS if not str(sections.get(s, "")).strip()]
    if missing:
        raise InvalidScientificProblem(f"a flagship report states every section; missing or empty: {missing}")
    extra = sorted(set(sections) - set(REQUIRED_SECTIONS))
    if extra:
        raise InvalidScientificProblem(f"unknown report sections {extra}")
    for name, body in sections.items():
        if not any(f"[{label}]" in body for label in LABELS) and name not in ("Reproduction command",):
            raise InvalidScientificProblem(f"section {name!r} carries no labelled statement ({', '.join(LABELS)})")
    out = [f"# {title}", "", LEGEND, "", f"`{identity_line}`", ""]
    for i, name in enumerate(REQUIRED_SECTIONS, start=1):
        out += [f"## {i}. {name}", "", sections[name].strip(), ""]
    out += ["## Engineering summary (generated from the run)", "", "```text", summary_text.rstrip(), "```", ""]
    return "\n".join(out)
