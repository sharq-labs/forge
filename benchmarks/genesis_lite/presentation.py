"""Task presentations: the same hidden universe shown four ways (Genesis §10.1 renamed/paraphrased variants, §10.2 traps).

A presentation is a pure NAME TRANSLATION between the escrow's card and what a proposer sees. It holds no hidden
information: it is built from the public card and a PER-RUN presentation key only, and the escrow, the scoring and the
answer key always use the original names.

* ``anonymous``   -- the escrow's own invented variable names.
* ``renamed``     -- every variable, the output and every base dimension renamed by a keyed permutation.
* ``paraphrased`` -- renamed, inputs reordered, and a differently worded task text (keyed choice of wording).
* ``trap``        -- anti-historical: the card uses the vocabulary of a familiar textbook law (e.g. metabolic rate vs
  body mass). The hidden law is the escrow's, whose effective exponents are off the textbook grid by construction, so
  the familiar answer is wrong there; every trap instance in which a law can earn credit is CHECKED against the
  revealed key (a world whose best-constant textbook law passes is invalid, never credited).

In EVERY presentation the universe id is replaced by a keyed pseudonym, so two runs over the same hidden world (another
presentation, seed or arm) never share an identifier a stateful proposer could merge observations by (review H1). The
presentation is assigned per CAMPAIGN, never per kind, and no card field names it.
"""

from __future__ import annotations

import hashlib
import hmac
import random
import re
from dataclasses import dataclass
from typing import Any, Mapping

PRESENTATIONS = ("anonymous", "renamed", "paraphrased", "trap")

#: allow-listed card keys; anything else is refused before a proposer sees the card
CARD_KEYS = frozenset({"universe_id", "level", "base_dimensions", "inputs", "observed_covariates", "covariate_units", "output",
                       "assessment_region", "query_budget", "query_cost", "answers", "task_text"})

_TEXTS = (
    "Find the relation between {out} and the settable inputs, or decide that the evidence does not support one.",
    "Using at most the query budget, determine how {out} depends on the inputs; a refusal is a valid answer.",
    "Characterise {out} as a function of the controllable quantities if the observations allow it.",
    "State how {out} responds to the inputs you can set, or say why that cannot be determined from the queries.",
)

#: anti-historical trap vocabularies: (output, historical input, textbook exponent, auxiliary inputs, covariate)
TRAP_TEMPLATES = (
    ("metabolic_rate", "body_mass", 0.75, ("ambient_temperature", "activity_level", "heart_rate"), "season_index"),
    ("orbital_period", "semi_major_axis", 1.5, ("central_mass", "eccentricity_factor", "inclination_factor"), "epoch_index"),
    ("drag_force", "flow_speed", 2.0, ("fluid_density", "frontal_area", "kinematic_viscosity"), "roughness_index"),
    ("swing_period", "pendulum_length", 0.5, ("bob_mass", "release_angle", "pivot_friction"), "draft_index"),
)


class PresentationRefused(RuntimeError):
    """A presented card failed the pre-proposal leak check: the benchmark run is invalid, not the proposer's fault."""


@dataclass(frozen=True)
class Presented:
    card: dict[str, Any]
    original_id: str
    to_original: Mapping[str, str]          # presented name -> escrow name
    to_presented: Mapping[str, str]         # escrow name -> presented name
    historical: tuple[str, float] | None    # trap only: (historical input as presented, textbook exponent)


def _rng(key: bytes, *parts: str) -> random.Random:
    return random.Random(hmac.new(key, "\n".join(parts).encode(), hashlib.sha256).hexdigest())


def pseudonym(key: bytes, universe_id: str) -> str:
    return "gl-" + hmac.new(key, f"universe\n{universe_id}".encode(), hashlib.sha256).hexdigest()[:16]


def _rename_units(unit: str, dims: Mapping[str, str]) -> str:
    return "*".join(re.sub(r"^[^^]+", lambda m: dims.get(m.group(0), m.group(0)), part) for part in unit.split("*")) if unit != "1" else unit


def present(card: Mapping[str, Any], presentation: str, key: bytes, stimulus_key: bytes | None = None) -> Presented:
    """``key`` is private to one run (the pseudonym); ``stimulus_key`` is shared by every arm on one world set, so that
    all arms see the same renaming, trap template and wording (v0.2, review D7). Without it the run key is used."""
    if presentation not in PRESENTATIONS:
        raise PresentationRefused(f"unknown presentation {presentation!r}")
    uid = str(card["universe_id"])
    inputs = [dict(x) for x in card["inputs"]]
    covs = list(card.get("observed_covariates", ()))
    out = card["output"]["name"]
    names = [x["name"] for x in inputs] + covs + [out]
    rng = _rng(key if stimulus_key is None else stimulus_key, presentation, uid)
    historical = None
    text = 0
    if presentation == "anonymous":
        rename = {n: n for n in names}
        dims = {d: d for d in card["base_dimensions"]}
    elif presentation in ("renamed", "paraphrased"):
        tokens = rng.sample(range(100, 1000), len(names))
        rename = {n: f"v{t}" for n, t in zip(names, tokens)}
        dims = {d: f"B{i + 1}" for i, d in enumerate(card["base_dimensions"])}
        text = 1 + rng.randrange(len(_TEXTS) - 1) if presentation == "paraphrased" else 0
    else:
        o, hist, exponent, aux, cov = TRAP_TEMPLATES[rng.randrange(len(TRAP_TEMPLATES))]
        order = [x["name"] for x in inputs]
        chosen = order[rng.randrange(len(order))]
        others = [n for n in order if n != chosen]
        rename = {chosen: hist, out: o, **{n: a for n, a in zip(others, aux)}}
        rename.update({c: f"{cov}_{i + 1}" if i else cov for i, c in enumerate(covs)})
        dims = {d: d for d in card["base_dimensions"]}
        historical = (hist, exponent)
    shown = {
        "universe_id": pseudonym(key, uid), "level": card["level"],
        "base_dimensions": [dims[d] for d in card["base_dimensions"]],
        "inputs": [{**x, "name": rename[x["name"]], "unit": _rename_units(x["unit"], dims)} for x in inputs],
        "observed_covariates": [rename[c] for c in covs],
        "covariate_units": {rename[c]: u for c, u in card.get("covariate_units", {}).items()},
        "output": {"name": rename[out], "unit": _rename_units(card["output"]["unit"], dims)},
        "assessment_region": {rename[n]: list(b) for n, b in card.get("assessment_region", {}).items()},
        "query_budget": card["query_budget"], "query_cost": card["query_cost"], "answers": list(card["answers"]),
        "task_text": _TEXTS[text].format(out=rename[out]),
    }
    if presentation == "paraphrased":
        rng.shuffle(shown["inputs"])
    check_card(shown)
    to_original = {v: k for k, v in rename.items()}
    return Presented(shown, uid, to_original, dict(rename), historical)


def check_card(card: Mapping[str, Any]) -> None:
    """Pre-proposal leak check: only reviewed keys reach a proposer (fail closed)."""
    extra = sorted(set(card) - CARD_KEYS)
    if extra:
        raise PresentationRefused(f"card keys outside the reviewed schema would reach the proposer: {extra}")


def to_original_law(law: Any, to_original: Mapping[str, str]) -> Any:
    """Rename every {"var": name} of a proposed law back to the escrow's names (unknown names are left as they are:
    admission refuses them)."""
    if isinstance(law, Mapping):
        if set(law) == {"var"} and isinstance(law["var"], str):
            return {"var": to_original.get(law["var"], law["var"])}
        return {k: to_original_law(v, to_original) for k, v in law.items()}
    if isinstance(law, list):
        return [to_original_law(v, to_original) for v in law]
    return law


class TranslatingClient:
    """What a proposer holds: ``observe`` in presented names and ids; the escrow sees the original ones. Refusal texts
    are translated too, so the escrow's own names never come back (review L2). In-process this is a convenience, not a
    boundary: the wrapped client remains reachable by introspection (SECURITY_BOUNDARY_NOT_PROVEN)."""

    def __init__(self, client: Any, presented: Presented) -> None:
        self.__client = client
        self.__p = presented
        self.calls = 0

    def _shown(self, text: str) -> str:
        p = self.__p
        text = text.replace(p.original_id, p.card["universe_id"])
        for original in sorted(p.to_presented, key=len, reverse=True):
            text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(original)}(?![A-Za-z0-9_])", p.to_presented[original], text)
        return text

    def observe(self, universe_id: str, settings: Mapping[str, float], query_id: str = "") -> dict[str, Any]:
        from engcore.blindfold.escrow import EscrowRefused

        self.calls += 1
        p = self.__p
        if universe_id != p.card["universe_id"]:            # this client serves exactly one universe, by its pseudonym
            raise EscrowRefused("unknown universe")
        target = p.original_id
        settable = {x["name"] for x in p.card["inputs"] if x.get("settable")}
        unknown = sorted(str(k) for k in settings if k not in settable)
        if unknown:
            # never forwarded: the escrow echoes setting names in its refusal text, and its client treats some refusal
            # texts as integrity failures, so a crafted name could turn a run the proposer is losing INVALID (review)
            raise EscrowRefused(f"cannot set {len(unknown)} name(s): not settable inputs of this universe")
        original = {p.to_original.get(k, k): v for k, v in settings.items()}
        try:
            resp = self.__client.observe(target, original, query_id=query_id)
        except EscrowRefused as exc:
            raise EscrowRefused(self._shown(str(exc))) from None
        obs = {p.to_presented.get(k, k): v for k, v in resp["observation"].items()}
        return {**{k: v for k, v in resp.items() if k in ("budget_remaining",)}, "observation": obs}
