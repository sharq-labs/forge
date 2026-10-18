"""Genuine multi-timescale fixtures for the system-runtime tests (NOT a test module).

Every runtime here is a real BIG 10 ``MultiTimescaleRuntime`` over the heater/board reference system of
``tests/multiscale_reference.py`` (a real BIG 9 coupled fast system per resolved day), shortened to a two-day
chamber program with one-day macro windows so a run costs about a second. The system request is built on the
SAME scenario, timeline and environment records the runtime is bound to, unless a test deliberately supplies
another one. Nothing here is validation; the numbers are illustrative fixtures.
"""

from __future__ import annotations

from dataclasses import replace

from engcore.multiscale import MultiTimescaleRuntime
from engcore.scenarios import EnvironmentTimeline
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    AuthorityRegistry,
    ExecutionProfile,
    InitialStateSpec,
    MultiscaleAuthority,
    NodeKind,
    NodeOutputSpec,
    NodeSpec,
    OwnerState,
    RequestedObservable,
    RuntimeContext,
    SystemRunRequest,
)
from engcore.system_runtime._common import digest_of
from tests import multiscale_reference as R
from tests.system_runtime_fixtures import system

DAYS = 2
DAY = R.DAY
SLOW_OWNERS = {"thermal": "board_slow", "electrical": "heater_slow"}
WAIVER = "illustrative two-day chamber program; this node asserts no runtime applicability bound"


def environment(days: int = DAYS, *, daily_rise: float = 0.25, source_note: str | None = None, scenario_version: str = "1"):
    """``(EnvironmentTimeline, ScenarioSpecification)``.

    ``scenario_version`` changes only the scenario record (same horizon, same chamber history, so the timeline and the
    environment differ only through the scenario digest they are bound to); ``daily_rise`` changes the chamber history,
    hence the timeline, on the same scenario; ``source_note`` changes the environment's declared source, hence the
    environment, on the same timeline."""
    env, scn = R.build_environment(days, daily_rise=daily_rise)
    if scenario_version != "1":
        from engcore.scenarios import Timeline
        scn = replace(scn, version=scenario_version)
        tl = env.timeline
        timeline = Timeline.from_scenario(scn, timeline_id=tl.timeline_id, basis=tl.basis, histories=tl.histories,
                                          cycle_histories=tl.cycle_histories,
                                          extra_events=tuple(e for e in tl.events if not e.event_id.startswith("scheduled:")))
        env = EnvironmentTimeline(env.environment_id, timeline, env.registry, env.sources, env.channels, env.required)
    if source_note is not None:
        (src,) = env.sources
        env = EnvironmentTimeline(env.environment_id, env.timeline, env.registry, (replace(src, issuer=source_note),), env.channels, env.required)
    return env, scn


def runtime(env, *, run_id: str = "ms-identity", cls=MultiTimescaleRuntime):
    return cls(run_id=run_id, hierarchy=R.hierarchy(), policy=R.policy(default_days=1, near_threshold=False),
               fast_system=R.ReferenceHeaterSystem(env), environment=env, aggregations=R.aggregations(), lifecycle=R.lifecycle())


def until_day(env, day: int):
    from fractions import Fraction

    from engcore.scenarios import TimePoint
    return TimePoint(env.timeline.basis.basis_id, Fraction(day * DAY))


def moisture(record) -> Quantity:
    return Quantity(record.final_slow_state["thermal"]["moisture_content"].value.magnitude, "dimensionless")


def represented_days(record) -> Quantity:
    from fractions import Fraction
    return Quantity(float(Fraction(record.accounting["represented_seconds"])) / DAY, "day")


def authority(rt, *, authority_id: str = "ms-identity", staged_env=None, stages=None, extractors=None, slow_state_owners=None,
              initial_slow_state=None, **kwargs) -> MultiscaleAuthority:
    """A ``MultiscaleAuthority`` over ``rt``; ``staged_env`` adds the two stages a (day 1, fresh) and b (resume a to the end)."""
    if staged_env is not None and stages is None:
        stages = {"aging_a": {"until": until_day(staged_env, 1), "resume": False},
                  "aging_b": {"until": None, "resume": True, "from": "aging_a"}}
    return MultiscaleAuthority(authority_id, rt, initial_slow_state=R.initial_slow() if initial_slow_state is None else initial_slow_state,
                               extractors={"moisture": moisture, "represented_days": represented_days} if extractors is None else extractors,
                               slow_state_owners=SLOW_OWNERS if slow_state_owners is None else slow_state_owners, stages=stages, **kwargs)


def initial_state(moisture_content: float = 0.0, drift: float = 0.0) -> InitialStateSpec:
    slow = R.initial_slow(moisture_content, drift)
    return InitialStateSpec(Quantity(0, "s"), (OwnerState("board_slow", "slow", (slow["thermal"]["moisture_content"],)),
                                               OwnerState("heater_slow", "slow", (slow["electrical"]["resistance_drift"],))))


def outputs(names=("moisture", "represented_days")):
    units = {"moisture": "dimensionless", "represented_days": "day"}
    return tuple(NodeOutputSpec(n, units[n]) for n in names)


def node(auth, node_id: str = "aging", *, commits_state: bool = True, depends_on=(), output_names=("moisture", "represented_days")) -> NodeSpec:
    owners = tuple(sorted(SLOW_OWNERS.values()))
    common = {"commits_state": commits_state, "writes_owners": owners if commits_state else (), "reads_owners": () if commits_state else owners,
              "applicability_waiver": WAIVER if commits_state else "", "checkpointable": True,
              "configuration_digest": digest_of({"policy": "one-day macro windows", "hierarchy": "heater-board"})}
    return NodeSpec(node_id, NodeKind.MULTISCALE_EXECUTION, auth.ref, outputs(output_names), depends_on=tuple(depends_on), **common)


def request(env, scn, auth, *, staged: bool = False, with_environment: bool = True, initial: InitialStateSpec | None = None,
            nodes=None, request_id: str = "ms-identity", extra_authorities=()):
    """``(request, context)`` for one multiscale node (or the two stages a -> b) on ``scn`` / ``env``."""
    sysdef = system(with_constraint=False)
    if nodes is None:
        nodes = (node(auth, "aging_a"), node(auth, "aging_b", depends_on=("aging_a",))) if staged else (node(auth),)
    last = nodes[-1].node_id
    req = SystemRunRequest.build(
        request_id=request_id, system=sysdef, scenario=scn, timeline=env.timeline, environment=env if with_environment else None,
        initial_state=initial or initial_state(), nodes=tuple(nodes),
        **({} if with_environment else {"environment_absent_reason": "adversarial: the request states it uses no environment"}),
        observables=(RequestedObservable("moisture", last, "moisture", "dimensionless"),),
        profile=ExecutionProfile(("multiscale", "lifecycle"), "off", True, ("aging_a",) if staged else ()))
    context = RuntimeContext(AuthorityRegistry((auth, *extra_authorities)), system=sysdef, scenario=scn, timeline=env.timeline,
                             environment=env if with_environment else None)
    return req, context


class Counting(MultiTimescaleRuntime):
    """The genuine runtime, counting how often it actually executed."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.runs = self.resumes = 0

    def run(self, **kw):
        self.runs += 1
        return super().run(**kw)

    def resume(self, checkpoint, **kw):
        self.resumes += 1
        return super().resume(checkpoint, **kw)


def state_at(request, *, moisture_content: float = 0.0, drift: float = 0.0):
    """A genuine system state of ``request`` whose slow owners hold the given values."""
    from engcore.system_runtime import SystemState
    return SystemState.initial(initial_state(moisture_content, drift), request_digest=request.digest, system_digest=request.system.digest,
                               environment_digest="" if request.environment is None else request.environment.digest)


def slow_values(checkpoint_payload) -> tuple[float, float]:
    """``(moisture_content, resistance_drift)`` held by a serialized macro checkpoint."""
    from engcore.multiscale import MacroCheckpoint
    cp = MacroCheckpoint.deserialize(checkpoint_payload)
    return (float(cp.slow_state["thermal"]["moisture_content"].value.magnitude),
            float(cp.slow_state["electrical"]["resistance_drift"].value.magnitude))


def direct_call(request, context, node_id, *, state=None, request_digest=None, run_id="direct-run"):
    """The fields an authority reads from a ``NodeCall``, from the genuine compiled plan node and a genuine system state.

    For tests that drive an authority's ``execute`` directly (after admitting the node with ``preflight_findings``)."""
    from types import SimpleNamespace

    from engcore.system_runtime import compile_plan
    plan_node = next(n for n in compile_plan(request).nodes if n.node_id == node_id)
    return SimpleNamespace(node=plan_node, state=state if state is not None else state_at(request), context=context,
                           request_digest=request_digest or request.digest, run_id=run_id)


__all__ = [
    "DAY",
    "DAYS",
    "SLOW_OWNERS",
    "Counting",
    "R",
    "authority",
    "direct_call",
    "environment",
    "initial_state",
    "moisture",
    "node",
    "outputs",
    "replace",
    "represented_days",
    "request",
    "runtime",
    "slow_values",
    "state_at",
    "until_day",
]
