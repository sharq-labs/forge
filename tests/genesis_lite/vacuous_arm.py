"""The FDA-05 attack as a proposer: on every card, an in-box fit L and the public box edges, nothing else.

A = L (1 + K s), B = L / (1 + K s), s = sum over inputs of (x / hi)^M + (lo / x)^M. Inside the box s <= 2 n, so A and B
agree within K s; outside it they diverge without limit, so they bracket any finite truth. Under the v0.2 pair rule such
a pair can earn ``indistinguishable_hit`` while carrying no knowledge of the extrapolation. Importable by name
(``tests.genesis_lite.vacuous_arm:vacuous_pair``).
"""

from __future__ import annotations

import random
from typing import Any, Mapping

from benchmarks.genesis_lite import arms as v02_arms
from engcore.blindfold.expression import add, c, mul, pw, v

K, M = 1e-4, 60.0


def vacuous_pair(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    uid, out = card["universe_id"], card["output"]["name"]
    rows, _replicate = v02_arms._gather(card, client, random.Random(seed), "lhs", "vac")
    names = [x["name"] for x in card["inputs"] if x["settable"]]
    fit = v02_arms._fit(rows, names, out)
    if fit is None:
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "no fit"}
    law = v02_arms._law(fit[0], names)
    terms = []
    for x in card["inputs"]:
        if x["settable"]:
            lo, hi = x["range"]
            terms += [pw(mul(v(x["name"]), c(1.0 / hi)), M), pw(mul(v(x["name"]), c(1.0 / lo)), -M)]
    grow = add(c(1.0), mul(c(K), add(*terms)))
    return {"universe_id": uid, "answer": "indistinguishable", "laws": [mul(law, grow), mul(law, pw(grow, -1.0))],
            "rationale": "vacuous pair: in-box fit spread by the public box edges"}
