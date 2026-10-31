"""EXC-4 (owner-approved 2026-10-30): a richer hypothesis language, Stage 2a -- development only.

Dimensional analysis from declared units (:mod:`.dimensions`), a bounded structure grammar ``scale x F(groups)`` over the
escrow expression operators (:mod:`.grammar`), deterministic constant fitting (:mod:`.fit`) and BIC scoring under a
declared prior with cross-validated selection and a multiplicity ledger (:mod:`.evidence`).

It is measured as a BASELINE arm (``benchmarks/genesis_lite/arms_grammar_v3.py``); it is not wired into the Minimal Mind
(:mod:`engcore.mind.minimal` is unchanged) and, like every proposer, it issues no verdict: the caller's gate and the
escrow judge what it selects.  No lift, novelty or maturity claim.
"""

from .dimensions import DimensionRefused, DimensionalBasis, InputDimension, analyse, parse_unit
from .evidence import STRATEGY_ID, STRATEGY_VERSION, ScoreRefused, Selection, select
from .fit import Fit, fit
from .grammar import MAX_DEPTH, MAX_NODES, MAX_STRUCTURES, SHAPES, Structure, enumerate_structures, log_f, to_expression

__all__ = ["DimensionRefused", "DimensionalBasis", "Fit", "InputDimension", "MAX_DEPTH", "MAX_NODES", "MAX_STRUCTURES",
           "SHAPES", "STRATEGY_ID", "STRATEGY_VERSION", "ScoreRefused", "Selection", "Structure", "analyse", "enumerate_structures", "fit",
           "log_f", "parse_unit", "select", "to_expression"]
