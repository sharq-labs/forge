"""Operator-side answer-key export (Genesis-lite reveal step).

Run ONLY by the escrow operator, and only AFTER every proposal of the campaign is sealed (scored once by the escrow).
It re-derives the campaign's hidden worlds from the escrow master seed exactly as ``EscrowService`` does
(``engcore.blindfold.escrow``: HMAC-SHA256 of the master seed over newline-joined parts; kinds sorted by value, then
shuffled by the ``shuffle`` seed; one ``generate_universe`` per position), and the noise-free interventional truths at
the hidden evaluation and in-box points with the escrow's own truth stream (``<cid>\\n<uid>\\ntruth``: evaluation points
first, then in-box points).

The key is DATA for the independent evaluator, which never imports ``engcore``. Re-deriving the escrow's private
derivation here is checked, not trusted: the key's universe ids must equal the campaign's cards, its kinds must equal
the kinds the escrow revealed at scoring, and the independent outcome must equal the escrow's adjudication for every
universe -- otherwise the run is KEY_MISMATCH / EVALUATOR_DISAGREEMENT.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
from typing import Any, Mapping, Sequence

from engcore.blindfold.universe import GENERATOR_TAG, UniverseKind, generate_universe, truth_at

KEY_SCHEMA = "forge.genesis_lite.answer_key/1"


def _seed(master: bytes, *parts: str) -> str:
    return hmac.new(master, "\n".join(parts).encode(), hashlib.sha256).hexdigest()


def export_answer_key(master_seed: bytes, campaign_id: str, mix: Mapping[str, int], card_ids: Sequence[str]) -> dict[str, Any]:
    kinds = [UniverseKind(k) for k, n in sorted(mix.items()) for _ in range(int(n))]
    kinds.sort(key=lambda k: k.value)
    random.Random(_seed(master_seed, campaign_id, "shuffle")).shuffle(kinds)
    universes = []
    for i, kind in enumerate(kinds):
        world = generate_universe(_seed(master_seed, campaign_id, "universe", str(i)), kind)
        rng = random.Random(_seed(master_seed, campaign_id, world.universe_id, "truth"))
        evaluation = [truth_at(world, p, rng) for p in world.evaluation_points]
        inbox = [truth_at(world, p, rng) for p in world.inbox_points]
        universes.append({
            "universe_id": world.universe_id, "kind": world.kind.value, "tolerance": world.tolerance,
            "noise_sigma": world.noise_sigma, "box": {x.name: [x.low, x.high] for x in world.inputs},
            "variables": sorted({x.name for x in world.inputs} | set(world.covariates)),
            "law": world.law, "alternative_law": world.alternative_law,
            "evaluation": [[dict(p), y] for p, y in evaluation], "inbox": [[dict(p), y] for p, y in inbox],
        })
    key = {"schema": KEY_SCHEMA, "generator": GENERATOR_TAG, "campaign_id": campaign_id,
           "mix": dict(sorted(mix.items())), "universes": universes}
    if [u["universe_id"] for u in universes] != list(card_ids):
        key["status"] = "KEY_MISMATCH"
    else:
        key["status"] = "DERIVED"
    return key


def key_digest(key: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(key, sort_keys=True, separators=(",", ":"), default=float).encode()).hexdigest()
