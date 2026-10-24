"""R11-C c1105: Q6/Q7 regression sweep through the public Mind-facing API at aad2f69 (no round-10 change was meant to
touch these; this pins that nothing regressed).
 1. suggestions_only desk: a raw (human-provenance) proposal is refused at admit; an admitted action minted elsewhere
    for a raw proposal is refused at dispatch.
 2. LM ExternalSuggestion intake (MindWorldPort(suggestions_only=True) + proposed_action_from_suggestion): admitted and
    dispatched once; a suggestion edited after intake, or a proposal whose source is another suggestion, is refused.
 3. In-place edits (object.__setattr__) of AdmittedAction.configuration / .proposal / .world, DispatchAuthorization
    .settings / .configuration (handed to the executor's guarded __call__), AdmissionResult.live, FeasibilityDecision
    .status, and dataclasses.replace of AdmittedAction / DispatchAuthorization / AdmissionResult(live=True)."""
import dataclasses

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import (
    DispatchRefused, ExecutionDesk, FeasibleActionSpace, IntakeRefusal, MindWorldPort, WorldRefused, admit,
    project_world, proposed_action_from_suggestion,
)
from engcore.mind.world.admission import AdmissionResult, authorize_dispatch
from engcore.scientific import Quantity
from engcore.sria.decision.external import ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposerKind

SIM = ax.base("battery")["simulate_pulse"]


def attempt(label, fn):
    try:
        out = fn()
        print(f"  {label:70s}: ACCEPTED -> {str(out)[:60]}")
    except (WorldRefused, DispatchRefused, TypeError, ValueError, AttributeError) as exc:
        print(f"  {label:70s}: refused ({type(exc).__name__}: {str(exc)[:70]})")


o = ax.owned("battery")
auth = o.authorities()
calls = []
desk_open = ExecutionDesk(auth, lambda a: calls.append(a) or "ran", accept_synthetic=True)
gw_only = ExecutionDesk(auth, lambda a: calls.append(a) or "ran", accept_synthetic=True, suggestions_only=True).gateway()
gw_open = desk_open.gateway()
world = project_world(o.declaration, auth)
space = FeasibleActionSpace.build(world)
raw = o.propose("simulate_pulse", *SIM, world=world)
print("1. suggestions_only")
attempt("admit a raw proposal on the suggestions_only gateway", lambda: gw_only.admit(space, raw))
r_open = gw_open.admit(space, raw)
assert r_open.admitted is not None
attempt("dispatch an action admitted elsewhere for a raw proposal", lambda: gw_only.dispatch(r_open.admitted))

print("2. LM intake")
port = MindWorldPort(space, suggestions_only=True)
spec = port.world.action("simulate_pulse")
assignments, observe = SIM


def suggestion(assign):
    return ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", spec.family, "simulate_pulse",
                              {"assignments": [{"variable": k, "value": v.to_dict()} for k, v in assign.items()],
                               "observe": list(observe)}, "lm", extra={"world_revision": port.world.revision_id})


s = suggestion(assignments)
p = proposed_action_from_suggestion(s, world=port.world)
assert not isinstance(p, IntakeRefusal), p
r = port.request_admission(p, gw_only)
print("  LM suggestion admission:", r.status.value, r.codes())
attempt("port.execute the LM-admitted action", lambda: port.execute(r.admitted, gw_only))
other = dict(assignments)
other["I"] = Quantity(2.5, "ampere")
s2 = suggestion(other)
attempt("proposal whose assignments differ from its source suggestion",
        lambda: dataclasses.replace(p, assignments=tuple(sorted(other.items()))))
attempt("proposal re-sourced to another suggestion", lambda: dataclasses.replace(p, source=s2))
p_edit = proposed_action_from_suggestion(s, world=port.world)
object.__setattr__(p_edit, "assignments", tuple(sorted(other.items())))
attempt("proposal assignments edited in place after intake: admit", lambda: gw_only.admit(space, p_edit).status)

print("3. edits in place / replace")
n0 = len(calls)
a = r.admitted
for field, value in (("configuration", tuple((n, Quantity(9.0, "ampere") if n == "I" else v)
                                              for n, v in a.configuration)),
                     ("proposal", p_edit), ("synthetic", False), ("execution", a.execution)):
    b = dataclasses.replace.__wrapped__(a) if hasattr(dataclasses.replace, "__wrapped__") else None
    clone = object.__new__(type(a))
    for f in dataclasses.fields(a):
        object.__setattr__(clone, f.name, getattr(a, f.name))
    object.__setattr__(clone, field, value)
    attempt(f"dispatch AdmittedAction with .{field} edited in place", lambda: gw_only.dispatch(clone))
attempt("dataclasses.replace(AdmittedAction)", lambda: dataclasses.replace(a, synthetic=False))
auth_ok = authorize_dispatch(a, auth, accept_synthetic=True, suggestions_only=True)
for field, value in (("settings", {**dict(auth_ok.settings), "I": 9.0}),
                     ("configuration", ()), ("observe", ())):
    clone = object.__new__(type(auth_ok))
    for f in dataclasses.fields(auth_ok):
        object.__setattr__(clone, f.name, getattr(auth_ok, f.name))
    object.__setattr__(clone, field, value)
    attempt(f"guarded executor handed DispatchAuthorization with .{field} edited",
            lambda: desk_open._executor(clone))
attempt("dataclasses.replace(DispatchAuthorization)", lambda: dataclasses.replace(auth_ok, synthetic=False))
attempt("AdmissionResult(..., live=True) built by a caller",
        lambda: dataclasses.replace(r, live=True))
dec = r.decision
attempt("FeasibilityDecision with a status its reasons do not give",
        lambda: dataclasses.replace(dec, status=type(dec.status)("INFEASIBLE_PROTOCOL")))
print(f"executor ran {len(calls) - n0} times in section 3 (expected 0)")
print("addendum")
p_rep = dataclasses.replace(p, assignments=tuple(sorted(other.items())))
def _adm():
    return gw_only.admit(space, p_rep).status
attempt("admit the proposal whose assignments differ from its source suggestion", _adm)
