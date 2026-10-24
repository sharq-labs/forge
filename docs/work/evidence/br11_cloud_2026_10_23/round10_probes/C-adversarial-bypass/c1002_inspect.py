from benchmarks.mind_gen2_authority_v1 import fixtures as ax
import json
o = ax.owned("battery")
for k, l in o.ledgers.items():
    d = l.to_dict()
    print(k, json.dumps({kk: d[kk] for kk in d if kk != "charges"})[:600], "charges", len(d.get("charges", [])))
for k, e in o.experiments.items():
    print("exp", k, e.to_dict().get("budget"), e.to_dict().get("accounting"))
SIM = ax.base("battery")["simulate_pulse"]
print("SIM", SIM)
spec = o.world.action("simulate_pulse")
print(spec.estimated_cost, spec.estimated_duration)
