"""Rival structural hypotheses, as canonical :class:`engcore.sria.decision.Hypothesis` records (M-2 input side).

A structure states that the logarithm of the observable is linear in the logarithms of a chosen set of variables
(``linear``), optionally plus the squares of the log of some settable inputs (``quadratic``: curvature that no power
law has).  The empty structure is the NULL hypothesis: the observable does not depend on any variable.

The structure is the CLAIM; its coefficients are fitted to evidence and are never part of the claim (a falsifier
judges the structure, so refitting does not mint new content).  Every structure is a hypothesis of the canonical
record type, proposed by a named algorithm or by an external proposer (a language model included), and starts
PROPOSED: its scientific status changes only through sealed falsifier verdicts (``engcore.claims.falsification``).

The PRIOR over structures is a declared design choice (:data:`PRIOR_SPEC`), never a proposer's confidence: a
beta-binomial(1, 1) multiplicity prior over the number of SETTABLE inputs used (Scott & Berger 2010), an independent
prior inclusion of :data:`COVARIATE_PRIOR_INCLUSION` for each passive covariate, and :data:`CURVATURE_PRIOR_MASS` of
the mass on the curved family.  (A beta-binomial over inputs and covariates together gives a structure that uses
every variable several times the prior of one that omits a single irrelevant covariate, which manufactures
association with that covariate whenever the true dependence uses every input -- found on development worlds.)  It is
part of the Mind's identity.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ...sria.decision import (
    Hypothesis, HypothesisKind, HypothesisPrediction, ProposalProvenance, ProposerKind,
)
from .problem import ExperimentalProblem

MODEL_REF = "forge.mind.minimal.loglinear/1"
ENUMERATOR_ID = "forge.mind.minimal.structure_enumerator"
ENUMERATOR_VERSION = "1"
CURVATURE_PRIOR_MASS = 0.2
COVARIATE_PRIOR_INCLUSION = 0.5
PRIOR_SPEC = {"family": "beta_binomial_1_1_over_settable_inputs", "covariate_prior_inclusion": COVARIATE_PRIOR_INCLUSION,
              "curvature_prior_mass": CURVATURE_PRIOR_MASS,
              "curvature_form": "squares of the log of every settable input in the structure"}


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class StructureRefused(ValueError):
    """A structure that names variables the problem does not have, or squares a passive covariate."""


@dataclass(frozen=True)
class Structure:
    linear: tuple[str, ...]
    quadratic: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "linear", tuple(sorted(set(self.linear))))
        object.__setattr__(self, "quadratic", tuple(sorted(set(self.quadratic))))
        if set(self.quadratic) - set(self.linear):
            raise StructureRefused("a curvature term needs its variable's linear term")

    @property
    def is_null(self) -> bool:
        return not self.linear

    @property
    def n_features(self) -> int:
        return len(self.linear) + len(self.quadratic)

    def check(self, problem: ExperimentalProblem) -> "Structure":
        settable = {x.name for x in problem.inputs}
        allowed = settable | set(problem.covariates)
        if set(self.linear) - allowed:
            raise StructureRefused(f"the structure names variables not in the problem: {sorted(set(self.linear) - allowed)}")
        if set(self.quadratic) - settable:
            raise StructureRefused("curvature is entertained for settable inputs only")
        return self

    def canonical_key(self, problem: ExperimentalProblem) -> str:
        """Name-free identity: settable inputs by canonical index, covariates by sorted index."""
        index = {x.name: f"x{i}" for i, x in enumerate(problem.canonical_inputs())}
        index.update({c: f"u{i}" for i, c in enumerate(problem.covariates)})
        lin = sorted(index[n] for n in self.linear)
        quad = sorted(index[n] for n in self.quadratic)
        return f"L[{','.join(lin)}]Q[{','.join(quad)}]"

    def hypothesis_id(self, problem: ExperimentalProblem) -> str:
        return f"mind:{self.canonical_key(problem)}"

    def to_dict(self) -> dict[str, Any]:
        return {"linear": list(self.linear), "quadratic": list(self.quadratic)}


def enumerate_structures(problem: ExperimentalProblem) -> list[Structure]:
    """Every linear subset of the variables, plus one curved variant per subset with a settable input."""
    variables = [x.name for x in problem.canonical_inputs()] + list(problem.covariates)
    settable = {x.name for x in problem.inputs}
    out: list[Structure] = []
    for k in range(len(variables) + 1):
        for subset in itertools.combinations(variables, k):
            out.append(Structure(subset))
            curved = tuple(n for n in subset if n in settable)
            if curved:
                out.append(Structure(subset, curved))
    return out


def log_prior(structure: Structure, problem: ExperimentalProblem) -> float:
    """The declared prior (unnormalised log): beta-binomial(1,1) over the settable inputs used, an independent inclusion
    prior per passive covariate, curvature mass split."""
    settable = {x.name for x in problem.inputs}
    m = len(settable)
    k = len(set(structure.linear) & settable)
    base = -math.log(m + 1) - math.log(math.comb(m, k))
    for cov in problem.covariates:
        base += math.log(COVARIATE_PRIOR_INCLUSION if cov in structure.linear else 1 - COVARIATE_PRIOR_INCLUSION)
    if structure.quadratic:
        return base + math.log(CURVATURE_PRIOR_MASS)
    return base + math.log(1 - CURVATURE_PRIOR_MASS)


def hypothesis_for(structure: Structure, problem: ExperimentalProblem, *,
                   proposer: ProposalProvenance | None = None) -> Hypothesis:
    """The canonical hypothesis record of a structure (status PROPOSED; coefficients are never part of the claim)."""
    structure.check(problem)
    key = structure.canonical_key(problem)
    if structure.is_null:
        statement = f"ln({problem.observable}) does not depend on any variable of the problem"
    else:
        terms = [f"ln({n})" for n in structure.linear] + [f"ln({n})^2" for n in structure.quadratic]
        statement = f"ln({problem.observable}) is linear in {', '.join(terms)} inside the settable box"
    return Hypothesis(
        hypothesis_id=structure.hypothesis_id(problem), model_ref=MODEL_REF,
        description="structural rival in the Minimal Mind's competition",
        kind=HypothesisKind.NULL if structure.is_null else HypothesisKind.EQUATION,
        statement=statement,
        statement_payload={"observable": problem.observable, "structure": structure.to_dict(), "canonical": key},
        structure_digest=_digest({"model_ref": MODEL_REF, "canonical": key}),
        predictions=(HypothesisPrediction(observable=problem.observable, unit=problem.observable_unit or "1",
                                          condition_ref="settable_box", description="hypothesis-conditioned posterior "
                                          "predictive of the observable at each admissible setting"),),
        complexity=structure.n_features,
        proposal=proposer or ProposalProvenance(ProposerKind.ALGORITHM, f"{ENUMERATOR_ID}@{ENUMERATOR_VERSION}"),
    )


#: keys an external structure proposal may not carry: what a proposer may never decide (sria.decision.external's list
#: plus every belief-shaped number a proposer could try to smuggle into the competition)
_FORBIDDEN_PROPOSAL_KEYS = frozenset({"status", "verdict", "verdicts", "evidence", "evidence_level", "validation",
                                      "validated", "applicable", "applicability", "admitted", "supported", "support",
                                      "uncertainty", "novel", "novelty", "qualified", "weight", "prior", "posterior",
                                      "probability", "confidence", "score", "credit", "threshold", "stop", "outcome"})


def structure_from_proposal(proposal: Mapping[str, Any], problem: ExperimentalProblem) -> Structure:
    """An external (e.g. language-model) structure proposal: variable names only.  Refused when it tries to carry
    authority or a number the competition would read as belief."""
    keys = {str(k).lower() for k in proposal}
    bad = sorted(keys & _FORBIDDEN_PROPOSAL_KEYS)
    if bad:
        raise StructureRefused(f"a structure proposal carries {bad}: a proposer names variables, it never sets status, "
                               "belief, uncertainty, thresholds or outcomes")
    extra = sorted(keys - {"linear", "quadratic", "rationale"})
    if extra:
        raise StructureRefused(f"unknown structure proposal keys {extra}")
    linear = proposal.get("linear", ())
    quadratic = proposal.get("quadratic", ())
    if not isinstance(linear, (list, tuple)) or not isinstance(quadratic, (list, tuple)):
        raise StructureRefused("linear and quadratic are lists of variable names")
    return Structure(tuple(str(n) for n in linear), tuple(str(n) for n in quadratic)).check(problem)


def structures_for(problem: ExperimentalProblem, extra: Iterable[Structure] = ()) -> list[Structure]:
    seen, out = set(), []
    for s in [*enumerate_structures(problem), *extra]:
        key = s.canonical_key(problem)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


__all__ = ["COVARIATE_PRIOR_INCLUSION", "CURVATURE_PRIOR_MASS", "ENUMERATOR_ID", "MODEL_REF", "PRIOR_SPEC", "Structure", "StructureRefused",
           "enumerate_structures", "hypothesis_for", "log_prior", "structure_from_proposal", "structures_for"]
