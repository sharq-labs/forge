"""The ONE frozen primitive library shared by every Genesis-lite arm (Genesis §10.1, §10.3).

Every arm -- baselines now, the Minimal Mind later -- proposes laws in the Blindfold law language and searches the same
structure family over the same variables the card lists. Nothing here is tailored to a hidden answer: the library is
written before any task instance exists and is frozen by digest in the preregistration.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

PRIMITIVE_LIBRARY = {
    "schema": "forge.genesis_lite.primitives/1",
    "law_language": "engcore.blindfold.expression",
    "operators": ["const", "var", "add", "mul", "pow", "exp", "log", "neg", "piecewise"],
    "limits": {"max_depth": 12, "max_nodes": 96},
    # what the structure-search baselines enumerate: a constant times a product of real-exponent powers of a SUBSET of
    # the observed variables (settable inputs and passive covariates alike), exponents fitted by least squares in log
    # space. Exponential, additive and piecewise forms are expressible in the language but not searched by v0 arms.
    "searched_family": "monomial_over_variable_subsets",
    "selection_rule": "smallest subset whose held-out log-MSE is within 5% of the best subset's",
    "variables": "exactly the names on the presented card",
}

_GRAMMAR = pathlib.Path(__file__).resolve().parents[2] / "src" / "engcore" / "blindfold" / "expression.py"


def library_digest() -> str:
    """Digest of the library declaration AND the grammar source it names (a grammar change is a new library)."""
    blob = json.dumps(PRIMITIVE_LIBRARY, sort_keys=True, separators=(",", ":")).encode() + b"\n" + _GRAMMAR.read_bytes()
    return hashlib.sha256(blob).hexdigest()
