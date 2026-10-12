"""Discovery providers own ALGORITHMS; FORGE owns AUTHORITY.

The runners in ``providers/discovery`` execute inside each provider's own environment (PySINDy, BoTorch, Dakota) and
return JSON.  This module runs them (a subprocess with JSON in and out, the runner source digested), records a
:class:`ProviderRun`, and translates the output into the canonical planner/hypothesis records -- and nothing more:

* PySINDy -> :class:`~engcore.sria.decision.Hypothesis` records of kind EQUATION, status PROPOSED, proposer ALGORITHM,
  coefficients as FITTED parameters (source: the run digest), units DERIVED from the declared variable and time units
  (never defaulted).  A fit's R^2 is the provider's number in the proposal note, not evidence.
* BoTorch -> :class:`~engcore.sria.decision.external.ExternalSuggestion` (family OPTIMIZE): the acquisition value is
  BoTorch's own number, never FORGE's utility.
* Dakota -> the raw provider output, labelled untrusted: a sampling study's moments are not a FORGE uncertainty record.

Executing a provider is not qualifying it.  :data:`PROVIDER_STATUS` states what was attempted in this tree.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..sria.decision import (
    Hypothesis, HypothesisKind, HypothesisParameter, HypothesisPrediction, ParameterProvenance, ProposalProvenance, ProposerKind,
)
from ..sria.decision.actions import ActionFamily
from ..sria.decision.external import ExternalSuggestion

PROVIDER_RUN_SCHEMA = "engcore.claims.discovery_provider_run/1"
RUNNERS = Path(__file__).resolve().parents[3] / "providers" / "discovery"

#: what was attempted for each discovery provider in this tree (executing is not qualifying)
PROVIDER_STATUS: Mapping[str, str] = {
    "pysindy": "EXECUTED_IN_PROVIDER_ENV (conda-forge pysindy 2.1.0; sparse regression proposals only)",
    "botorch": "EXECUTED_IN_PROVIDER_ENV (conda-forge botorch 0.17.2; acquisition suggestions only)",
    "ax": "NOT_INSTALLED (BoTorch is used directly; no Ax service layer)",
    "dakota": "EXECUTED_IN_PROVIDER_ENV (conda-forge dakota 6.16; raw sampling output, no UQ authority)",
    "pysr": "NOT_INSTALLED (needs Julia registry packages; not attempted under the no-provider-breadth decision)",
}


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ProviderRefused(ValueError):
    pass


@dataclass(frozen=True)
class ProviderRun:
    provider: str
    provider_version: str
    runner_digest: str
    request_digest: str
    output: Mapping[str, Any] = field(hash=False)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROVIDER_RUN_SCHEMA, "provider": self.provider, "provider_version": self.provider_version,
                "runner_digest": self.runner_digest, "request_digest": self.request_digest, "output": dict(self.output),
                "authority": "none: provider output is a proposal source, not evidence"}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def run_provider(command: Sequence[str], runner: str, request: Mapping[str, Any], *, timeout: float = 600.0) -> ProviderRun:
    """Run ``runner`` (a file in ``providers/discovery``) with ``command`` (the provider environment's interpreter,
    e.g. ``[micromamba, "run", "-n", "discovery", "python", "-I"]``), JSON in, JSON out."""
    path = RUNNERS / runner
    if not path.is_file() or path.parent != RUNNERS:
        raise ProviderRefused(f"unknown runner {runner!r}")
    # The bounded boundary: output spilled to files, the process tree killed on timeout, so a
    # runner started through a wrapper (micromamba run ...) cannot outlive its timeout.
    from ..providers.process import run_bounded
    from ..providers.records import ProviderRefusal

    try:
        code, timed_out, stdout, stderr = run_bounded([*command, str(path)], timeout_s=timeout,
                                                      input_bytes=json.dumps(dict(request)).encode("utf-8"))
    except ProviderRefusal as exc:
        raise ProviderRefused(f"{runner} could not run: {exc}") from exc
    if timed_out:
        raise ProviderRefused(f"{runner} did not finish within {timeout}s; its process tree was terminated")
    if code != 0:
        raise ProviderRefused(f"{runner} failed ({code}): {stderr.decode('utf-8', 'replace').strip()[-400:]}")
    try:
        out = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProviderRefused(f"{runner} wrote no JSON result: {exc}") from exc
    if not isinstance(out, dict):
        raise ProviderRefused(f"{runner} wrote {type(out).__name__}, not a JSON object")
    return ProviderRun(str(out.get("provider", "")), str(out.get("provider_version", "")), hashlib.sha256(path.read_bytes()).hexdigest(),
                       _digest(dict(request)), out)


# ---------------------------------------------------------------------------- PySINDy -> PROPOSED equations


_TERM = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*)(?:\^(\d+))?$")


def _term(term: str, units: Mapping[str, str]) -> tuple[dict | None, str]:
    """A SINDy polynomial library term ('1', 'u', 'u^2', 'u v') as a law-grammar monomial and its unit string."""
    if term == "1":
        return None, "1"
    factors, unit_parts = [], []
    for part in term.split():
        m = _TERM.match(part)
        if m is None or m.group(1) not in units:
            raise ProviderRefused(f"cannot read library term {term!r} over the declared variables")
        name, power = m.group(1), int(m.group(2) or 1)
        factors.append({"var": name} if power == 1 else {"pow": [{"var": name}, {"const": float(power)}]})
        unit_parts.append(f"({units[name]})^{power}" if power != 1 else f"({units[name]})")
    return (factors[0] if len(factors) == 1 else {"mul": factors}), "*".join(unit_parts)


def sindy_hypotheses(run: ProviderRun, *, units: Mapping[str, str], time_unit: str, prefix: str,
                     condition_ref: str) -> tuple[Hypothesis, ...]:
    """One PROPOSED EQUATION hypothesis per fitted target.  Units come from the caller's declaration -- a missing unit is
    refused, never defaulted."""
    if run.provider != "pysindy":
        raise ProviderRefused("not a PySINDy run")
    out = run.output
    names = [t[1:-3] for t in out["targets"]]                        # "du/dt" -> "u"
    if not str(time_unit).strip() or any(not str(units.get(n, "")).strip() for n in names):
        raise ProviderRefused("every state variable and the time variable declare their units; a unit is never defaulted")
    hyps = []
    for target, name, row in zip(out["targets"], names, out["coefficients"]):
        terms, params = [], []
        for i, (term, coef) in enumerate(zip(out["terms"], row)):
            if coef == 0.0 or not math.isfinite(coef):
                continue
            mono, term_unit = _term(term, units)
            pname = f"c{i}"
            terms.append({"const": float(coef)} if mono is None else {"mul": [{"const": float(coef)}, mono]})
            params.append(HypothesisParameter(pname, f"({units[name]})/({time_unit})/({term_unit})", float(coef),
                                              ParameterProvenance.FITTED, f"provider_run:{run.digest}"))
        if not terms:
            continue
        expr = terms[0] if len(terms) == 1 else {"add": terms}
        statement = f"{target} = " + " + ".join(f"{p.value:.6g}*{t}" for p, t in zip(params, [x for x, c in zip(out["terms"], row) if c]))
        hyps.append(Hypothesis(
            hypothesis_id=f"{prefix}:{name}", model_ref=f"sindy:{run.digest[:16]}:{name}", kind=HypothesisKind.EQUATION,
            statement=statement, statement_payload={"expression": expr, "target": target},
            predictions=(HypothesisPrediction(target, f"({units[name]})/({time_unit})", condition_ref),), parameters=tuple(params),
            proposal=ProposalProvenance(ProposerKind.ALGORITHM, f"pysindy@{run.provider_version}", run.digest,
                                        note=f"provider training R^2 {out.get('training_score_r2')!r} (the provider's number, not evidence)")))
    return tuple(hyps)


# ---------------------------------------------------------------------------- BoTorch -> an external suggestion


def botorch_suggestion(run: ProviderRun, *, names: Sequence[str], target_ref: str) -> ExternalSuggestion:
    if run.provider != "botorch":
        raise ProviderRefused("not a BoTorch run")
    point = list(run.output["point"])
    if len(point) != len(names):
        raise ProviderRefused("the suggestion's dimension does not match the declared variable names")
    return ExternalSuggestion(ProposerKind.ALGORITHM, "botorch", run.provider_version, ActionFamily.OPTIMIZE, target_ref,
                              dict(zip(names, point)), f"{run.output.get('acquisition')} maximiser (provider run {run.digest[:12]})",
                              float(run.output["acquisition_value"]))


# ---------------------------------------------------------------------------- Dakota -> raw output, no authority


def dakota_output(run: ProviderRun) -> dict[str, Any]:
    if run.provider != "dakota":
        raise ProviderRefused("not a Dakota run")
    return {"provider_run": run.digest, "untrusted_provider_output": dict(run.output),
            "note": "Dakota's sample statistics; not a FORGE uncertainty record and not evidence"}


__all__ = ["PROVIDER_STATUS", "ProviderRefused", "ProviderRun", "botorch_suggestion", "dakota_output", "run_provider",
           "sindy_hypotheses"]
