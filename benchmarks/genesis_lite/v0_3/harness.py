"""Genesis-lite v0.3 DRAFT harness: one campaign, one arm, one presentation, bound to the committed v0.3 identity.

The v0.2 harness (``benchmarks.genesis_lite.harness``) is pinned by v0.2 and stays as it is: it scores with the v0.2
evaluator and checks the v0.2 identity. This harness re-uses v0.2's campaign procedure (``harness._run``: present,
observe, seal, reveal, re-score, audit, verify traps) by re-binding that one function to a namespace in which exactly
these names differ:

* ``independent``: the v0.3 evaluator (bounded pair rule), called with the BOUND w and the preregistered w;
* ``CONFIG``: the v0.3 evaluator configuration, whose digest seals w at campaign creation;
* ``EscrowService``: the escrow that applies the same bound (``engcore.blindfold.pair_bound``, the certified FDA-05
  escrow half; OD-3). Without it this harness REFUSES: it never falls back to the v0.2 escrow or evaluator.

Differences from v0.2 beyond that:

* **FDA-18**: one FRESH proposer process per CARD, not per campaign, each with its own empty working and temporary
  directory. A proposer can no longer carry process memory or temp files from one card to the next. Files written
  elsewhere, or a detached helper process, under the same OS account remain possible (measured by the
  ``cross_card_state`` and ``persistence`` attacks); closing those needs the OD-20 deployment.
* **Formal lockdown** (review 2026-10-20 finding 2): a formal run accepts no card hook, no extra import path and no
  caller-chosen arm spec. It runs a registered v0.3 arm or the candidate the identity names, and records each arm's
  code digest.
* **FDA-22**: every universe records ``law_form`` (power / exp / two_term / regime) from the revealed key, so the
  kind-conditional form prior can be measured per world (declared as a structural tell in the v0.3 preregistration).
* Every record carries the harness, the bound and the environment-manifest digest it was produced under.

:func:`bind` is the only way to obtain a :class:`Binding`. It refuses any document that is not the committed v0.3
preregistration rebuilt by this code, a credit table, w or environment that differs from the preregistered one, and a
FORMAL binding of a non-FROZEN identity.
"""

from __future__ import annotations

import functools
import json
import os
import pathlib
import queue
import subprocess
import sys
import tempfile
import threading
import types
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from engcore.blindfold.roles import DEFAULT_CREDIT

from .. import harness as _v02h
from . import arms as v03_arms
from . import environment
from . import evaluator as v03e
from . import preregistration as v03p

try:                                       # the certified escrow half of FDA-05 (OD-3); absent until Batch A lands
    from engcore.blindfold import pair_bound as escrow_bound
except ImportError:                        # pragma: no cover - exercised on a tree without the escrow half
    escrow_bound = None

HARNESS_ID = "forge.genesis_lite.harness.v0_3"
#: the code a registered v0.3 arm runs (v0.2 arms.py, re-bound by v0.3 arms.py)
ARM_CODE = ("benchmarks/genesis_lite/arms.py", "benchmarks/genesis_lite/v0_3/arms.py")
CONFIG_ID, CONFIG_VERSION = "forge.genesis_lite.v0_3", "1"
TIERS = ("formal", "development")
ODR = v03p.ODR


class HarnessRefused(RuntimeError):
    """The v0.3 harness cannot run as preregistered."""


@dataclass(frozen=True)
class Binding:
    prereg_sha256: str
    status: str
    tier: str
    pair_bound: v03e.PairBound
    config: Any
    credit_digest: str
    environment_manifest_sha256: str
    preregistered_pair_bound: Mapping[str, Any] | None = None     # None only in development while w is still open
    candidate: Mapping[str, Any] | None = None


def bind(doc_bytes: bytes, *, tier: str, manifest: Mapping[str, Any] | None = None,
         pair_bound: v03e.PairBound | None = None, development_bound: v03e.PairBound | None = None) -> Binding:
    """Bind a run to the committed v0.3 preregistration. ``pair_bound`` is the caller's expectation (refused if it
    differs). ``development_bound`` is accepted ONLY in the development tier, and only while the preregistered w is
    still the owner's open decision. Development records can never enter a lift decision (analysis requires tier
    'formal')."""
    if tier not in TIERS:
        raise HarnessRefused(f"unknown tier {tier!r}")
    if tier == "formal" and manifest is not None:
        raise HarnessRefused("a formal binding measures its environment itself; a caller's manifest is not evidence")
    problems = v03p.committed_doc_problems(doc_bytes)
    if problems:
        raise HarnessRefused("; ".join(problems))
    doc = json.loads(doc_bytes)
    if tier == "formal" and doc.get("status") != "FROZEN":
        raise HarnessRefused(f"a formal run needs a FROZEN identity; this one is {doc.get('status')!r}")
    credit = v03e.credit_digest(v03e.CREDIT)
    if not credit == doc["evaluator"]["credit_digest"] == v03e.credit_digest(DEFAULT_CREDIT):
        raise HarnessRefused("the credit table is not the preregistered one (evaluator, escrow and preregistration differ)")
    recorded = doc["evaluator"]["pair_bound"]
    if recorded == ODR:
        if tier != "development" or development_bound is None:
            raise HarnessRefused("w is still OWNER_DECISION_REQUIRED (ODC-05b): only a development run with an explicit "
                                 "development bound is possible, and it can never be formal evidence")
        bound = v03e._checked(development_bound)
    else:
        bound = v03e._checked(v03e.PairBound(**recorded))
        if development_bound is not None and development_bound.to_dict() != recorded:
            raise HarnessRefused("a development bound may not differ from the preregistered w")
    if pair_bound is not None and v03e._checked(pair_bound).to_dict() != bound.to_dict():
        raise HarnessRefused(f"w {pair_bound.to_dict()} is not the bound one {bound.to_dict()}")
    measured = environment.manifest_digest(manifest if manifest is not None else environment.build_manifest())
    frozen_env = doc["formal"]["environment_manifest_sha256"]
    if frozen_env == ODR:
        if tier == "formal":
            raise HarnessRefused("the environment manifest is not preregistered")
    elif frozen_env != measured:
        raise HarnessRefused("the environment manifest differs from the preregistered one")
    candidate = None
    if tier == "formal":
        from . import formal  # noqa: PLC0415 - formal imports this module lazily

        try:
            candidate = formal.candidate_of(doc)
        except formal.FormalRefused as exc:
            raise HarnessRefused(str(exc)) from exc
        problems = formal.candidate_code_problems(candidate)
        if problems:
            raise HarnessRefused("; ".join(problems))
    if escrow_bound is None:
        raise HarnessRefused("the escrow half of FDA-05 (engcore.blindfold.pair_bound) is not in this tree: the escrow "
                             "would score pairs with the unbounded v0.2 rule (BLOCKED_BY_OD3); no fallback")
    config = escrow_bound.BoundedEvaluatorConfig(CONFIG_ID, CONFIG_VERSION,
                                                 pair_bound=escrow_bound.PairBound(bound.form, float(bound.value)))
    return Binding(v03p.sha256(doc_bytes), str(doc.get("status")), tier, bound, config, credit, measured,
                   None if recorded == ODR else dict(recorded), candidate)


class _Evaluator:
    """The v0.3 evaluator as the v0.2 procedure calls it (``independent.*``), with w bound; it keeps the revealed key."""

    def __init__(self, binding: Binding) -> None:
        self._binding = binding
        self.key: Mapping[str, Any] | None = None
        self.CREDIT, self.CREDIT_DIGEST, self.credit_digest = v03e.CREDIT, v03e.CREDIT_DIGEST, v03e.credit_digest
        from ..evaluator import score as v02_score  # noqa: PLC0415 - the unchanged audit helpers

        self.score, self.region_tell = v02_score, v02_score.region_tell
        self.audit_presented_cards, self.in_monomial_family = v02_score.audit_presented_cards, v02_score.in_monomial_family

    def evaluate_campaign(self, proposals, key, escrow, *, expected_credit_digest):  # noqa: ANN001
        self.key = key
        bound = self._binding.pair_bound
        # the expectation comes from the preregistration; only a development run with an open w checks against itself
        expected = self._binding.preregistered_pair_bound or bound.to_dict()
        return v03e.evaluate_campaign(proposals, key, escrow, expected_credit_digest=expected_credit_digest, bound=bound,
                                      expected_pair_bound=expected)


def _bound_run(binding: Binding, evaluator: _Evaluator) -> Callable[..., None]:
    namespace = dict(vars(_v02h))
    namespace.update(independent=evaluator, CONFIG=binding.config,
                     EscrowService=functools.partial(escrow_bound.PairBoundedEscrowService, config=binding.config))
    src = _v02h._run
    return types.FunctionType(src.__code__, namespace, src.__name__, src.__defaults__, src.__closure__)


class CardProposerHost(_v02h.ProposerHost):
    """v0.2's isolated proposer process, started for ONE card, with its own empty working AND temporary directory
    (TEMP, TMP and TMPDIR point into it), so temp files do not survive into the next card's process."""

    def __init__(self, extra_paths: tuple[str, ...] = (), timeout: float = 600.0) -> None:  # noqa: D107
        self._dir = tempfile.TemporaryDirectory(prefix="gl-card-")
        env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR") if k in os.environ}
        env.update(TEMP=self._dir.name, TMP=self._dir.name, TMPDIR=self._dir.name)
        paths = [str(_v02h._ROOT), str(_v02h._ROOT / "src"), *extra_paths]
        self._proc = subprocess.Popen([sys.executable, "-I", str(_v02h._HOST), *paths], cwd=self._dir.name, env=env,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self._lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._timeout = timeout
        hello = self._recv()
        expected = str((_v02h._ROOT / "src" / "engcore" / "__init__.py").resolve())
        if hello.get("op") != "hello" or str(pathlib.Path(hello.get("engcore", "")).resolve()) != expected:
            self.close()
            raise RuntimeError(f"the proposer process did not import this tree's engcore: {hello}")


def fresh_process_per_card(spec: str, extra_paths: tuple[str, ...] = ()) -> Callable[..., dict[str, Any]]:
    """FDA-18: an arm callable that starts a new isolated proposer process for every card and ends it after the card."""
    starts: list[float] = []

    def arm(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
        import time  # noqa: PLC0415

        t0 = time.perf_counter()
        host = CardProposerHost(extra_paths)
        starts.append(time.perf_counter() - t0)
        try:
            return host.propose(spec, card, seed, client)
        finally:
            host.close()

    arm.host_starts = starts  # type: ignore[attr-defined]
    return arm


def law_form(entry: Mapping[str, Any]) -> str | None:
    """The generator form of a revealed universe's law (for INDISTINGUISHABLE: of its non-rival member)."""
    laws = [x for x in (entry.get("law"), entry.get("alternative_law")) if x is not None]
    if not laws:
        return None
    if entry.get("kind") == "indistinguishable":
        laws = [min(laws, key=lambda x: len(json.dumps(x, sort_keys=True)))]
    text = json.dumps(laws[0], sort_keys=True)
    if '"piecewise"' in text:
        return "regime"
    if '"exp"' in text:
        return "exp"
    if '"add"' in text:
        return "two_term"
    return "power"


def run_one(arm_name: str, *, binding: Binding, master_seed: bytes, campaign_id: str, presentation: str, seed: int = 0,
            isolation: str = "proposer_process", arm_spec: str | None = None, extra_paths: tuple[str, ...] = (),
            card_hook: Callable[[dict], dict] | None = None) -> _v02h.RunRecord:
    if not isinstance(binding, Binding):
        raise HarnessRefused("a v0.3 run needs a Binding from harness.bind()")
    if isolation not in _v02h.ISOLATIONS:
        raise HarnessRefused(f"unknown isolation {isolation!r}")
    candidate = binding.candidate
    if binding.tier == "formal":
        if isolation != "proposer_process":
            raise HarnessRefused("a formal run isolates the proposer in its own process")
        if card_hook is not None or extra_paths or arm_spec is not None:
            raise HarnessRefused("a formal run takes no card hook, extra path or caller-chosen arm spec")
        if arm_name not in v03_arms.ARMS and not (candidate and arm_name == candidate["name"]):
            raise HarnessRefused(f"{arm_name!r} is neither a registered v0.3 arm nor the identity's candidate")
    if candidate and arm_name == candidate["name"]:
        spec, code = candidate["spec"], dict(candidate["code_sha256"])
    else:
        spec = arm_spec or f"benchmarks.genesis_lite.v0_3.arms:{arm_name}"
        code = {rel: v03p._sha(v03p.v02.ROOT / rel) for rel in ARM_CODE}
    rec = _v02h.RunRecord(arm_name, seed, campaign_id, presentation, isolation=isolation)
    rec.prereg_sha256 = binding.prereg_sha256
    if isolation == "proposer_process":
        arm = fresh_process_per_card(spec, extra_paths)
    else:
        arm = v03_arms.ARMS[arm_name][0]
    evaluator = _Evaluator(binding)
    try:
        _bound_run(binding, evaluator)(rec, arm, master_seed, campaign_id, presentation, seed, False, card_hook,
                                       binding.config)
    except Exception as exc:  # noqa: BLE001 - every failure is a recorded benchmark-invalid run, never a lost record
        rec.invalid(f"run aborted: {type(exc).__name__}: {str(exc)[:300]}")
    entries = {e["universe_id"]: e for e in (evaluator.key or {}).get("universes", [])}
    for u in rec.universes:
        u["law_form"] = law_form(entries[u["universe_id"]]) if u.get("universe_id") in entries else None
    starts = getattr(arm, "host_starts", [])
    rec.host_start_seconds = float(sum(starts))
    rec.__dict__.update(harness=HARNESS_ID, tier_bound=binding.tier, pair_bound=binding.pair_bound.to_dict(),
                        environment_manifest_sha256=binding.environment_manifest_sha256,
                        proposer_processes=len(starts), arm_spec=spec, arm_code_sha256=code)
    return rec
