"""F10 f04: round 9's _named_records decides 'older revision' with str.isdigit() and int().  A world's declaration
binding revision is any non-empty str (AuthorityBinding validates only type and text), so a submitted world can carry
'²' (isdigit() is True, int() raises ValueError) or '٠' (Arabic-Indic zero: int() = 0).  What does admission do?"""
import copy

import engcore
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import ExecutionDesk, FeasibleActionSpace, ScientificWorld, WorldRefused
from engcore.mind.world.authority import BindingStatus

print("engcore from", engcore.__file__)
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
calls = []
gateway = ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True).gateway()
base = o.world.to_dict()
for rev in ("²", "٠", "0", "1x", "1" * 5000):
    payload = copy.deepcopy(base)
    payload["declaration"]["revision"] = rev
    payload["declaration"]["record_digest"] = "ab" * 32           # not the declaration in force
    payload.pop("content_digest", None); payload.pop("revision_id", None)
    try:
        w = ScientificWorld.from_dict(payload)
    except WorldRefused as exc:
        print(f"revision {rev!r}: world refused at from_dict: {str(exc)[:100]}")
        continue
    try:
        r = gateway.admit(FeasibleActionSpace.build(w), o.propose("simulate_pulse", *SIM, world=w))
        unnamed = sorted({c.status.value for c in r.verification.checks if "not read" in str((c.detail or {}).get("why", ""))})
        print(f"revision {rev!r}: admit returned {r.status.value}, admitted={r.admitted is not None}; unnamed-binding labels {unnamed}")
    except Exception as exc:  # noqa: BLE001
        print(f"revision {rev[:12]!r}{'...' if len(rev) > 12 else ''}: admit RAISED {type(exc).__name__}: {str(exc)[:100]}")
print("executor calls", len(calls))
