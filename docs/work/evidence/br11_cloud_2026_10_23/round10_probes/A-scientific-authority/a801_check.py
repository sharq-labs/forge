"""Check a801 invariants on the HEAD output and diff the outcomes against older trees.
usage: a801_check.py head.jsonl [other.jsonl ...]"""
import json, sys
from collections import defaultdict
from engcore.scientific import Quantity
from engcore.mind.world.base import same_value
from engcore.scientific.units.quantity import base_unit


def load(p):
    return [json.loads(l) for l in open(p)]


head = load(sys.argv[1])
viol = defaultdict(list)
groups = defaultdict(set)
n_feas = 0
for r in head:
    if "feasible" not in r:
        continue
    s = Quantity(*r["s"])
    if r["feasible"]:
        n_feas += 1
        ex = Quantity(*r["ex"])
        # I1
        if not any(ex.magnitude == m for m in r["deciding_exec"]):
            viol["I1 executed not a deciding level"].append(r)
        # I2 / I3
        levels = [Quantity(*x) for x in r["all_levels"]]
        exl = [lv for lv in levels if same_value(lv, ex)]
        if not exl or not same_value(s, exl[0]):
            viol["I2 executed at a level the proposal is not"].append(r)
        else:
            base = base_unit(s.units)
            v = s.magnitude_in(base)
            dist = abs(v - exl[0].magnitude_in(base))
            for lv in levels:
                if not same_value(lv, exl[0]) and abs(v - lv.magnitude_in(base)) < dist:
                    viol["I3 a nearer other level exists"].append(r)
                    break
    if r["same"] and r["tag"].split("/")[1] in ("exact", "15g", "12g"):
        groups[(json.dumps(r["sig"], sort_keys=True), r["li"])].add((r["feasible"], tuple(r["codes"])))
print("cases", sum(1 for r in head if "feasible" in r), "feasible", n_feas,
      "bind_refused", sum(1 for r in head if "bind_refused" in r))
for k, v in viol.items():
    print(k, len(v))
    for r in v[:3]:
        print("   ", json.dumps(r)[:400])
split = {k: v for k, v in groups.items() if len(v) > 1}
print("levels whose honest spellings (exact/15g/12g, owner same_value) got >1 outcome:", len(split), "of", len(groups))
for k, v in list(split.items())[:6]:
    print("   ", k[0][:250], "li", k[1], sorted(v))

for other in sys.argv[2:]:
    o = load(other)
    assert len(o) == len(head)
    diff = defaultdict(list)
    for a, c in zip(head, o):
        assert a.get("sig") == c.get("sig") and a.get("tag") == c.get("tag") and a.get("s") == c.get("s"), (a, c)
        ka = "bind" if "bind_refused" in a else ("F" if a["feasible"] else "R")
        kc = "bind" if "bind_refused" in c else ("F" if c["feasible"] else "R")
        if ka != kc or (ka == "F" and a["ex"] != c["ex"]) or (ka == "R" and a["codes"] != c["codes"]):
            key = f"{other.split('_')[-1]}: then {kc} now {ka} same={a.get('same', c.get('same'))} kind={a['sig']['kind']}"
            if ka == kc == "F":
                key += " (executed differs)"
            diff[key].append((a, c))
    for k, v in sorted(diff.items()):
        print(k, len(v))
        for a, c in v[:3]:
            print("    now ", json.dumps({x: a.get(x) for x in ("sig", "li", "tag", "s", "same", "feasible", "codes", "ex", "bind_refused")})[:420])
            print("    then", json.dumps({x: c.get(x) for x in ("feasible", "codes", "ex", "bind_refused")})[:300])
