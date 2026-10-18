"""R-03: FDA-03 -- MaterialPropertySet.resolve interpolating across two conflicting sources at one position.

Illustrative fixture values only (not reference data), built in memory; nothing is read from the repository's data.
Two sources disagree at 300 K (10 vs 20 W/(m*K)); one datum at 400 K (30). Linear rule along temperature.
"""
import hashlib, json

import engcore
from engcore.materials import (ApplicabilityRange, CompositionEntry, InterpolationRule, MaterialIdentity,
                               MaterialPropertySet, MaterialState, PropertyApplicability, PropertyDatum)
from engcore.materials.coverage import material_coverage_report
from engcore.scenarios import NamedQuantity
from engcore.scientific.knowledge.claim import KnowledgeClaim, KnowledgeKind
from engcore.scientific.knowledge.snapshot import KnowledgeSnapshot
from engcore.scientific.knowledge.source import KnowledgeSource, KnowledgeSourceClass
from engcore.scientific.units.quantity import Quantity

print("engcore:", engcore.__file__)
KU = "W/(m*K)"
MAT = MaterialIdentity("audit_alloy", specification="AUDIT-FIXTURE", grade="X1", condition="annealed",
                       composition=(CompositionEntry("Al", NamedQuantity("Al", Quantity(0.97, "dimensionless"))),))


def source(sid, rows):
    payload = json.dumps(rows, sort_keys=True).encode()
    return KnowledgeSource(sid, "audit fixture (illustrative values, not reference data)", hashlib.sha256(payload).hexdigest(),
                           "1", f"audit::{sid}", KnowledgeSourceClass.OTHER)


def build(rows, set_id):
    """rows: (claim_id, source_id, temperature_K, value)"""
    sources = {sid: source(sid, [r for r in rows if r[1] == sid]) for sid in sorted({r[1] for r in rows})}
    claims, data = [], []
    for claim_id, sid, t, v in rows:
        app = PropertyApplicability(MAT.digest, "thermal_conductivity",
                                    (ApplicabilityRange("temperature", Quantity(t, "K"), Quantity(t, "K")),), "solid")
        claim = KnowledgeClaim(claim_id, KnowledgeKind.MATERIAL_PROPERTY, MAT.subject_key, "thermal_conductivity",
                               Quantity(v, KU), "", None, sources[sid].source_id, sources[sid].document_digest, app.digest)
        claims.append(claim)
        data.append((claim, app))
    snap = KnowledgeSnapshot(f"{set_id}-snapshot", tuple(sources.values()), tuple(claims))
    return MaterialPropertySet(set_id, MAT, snap, tuple(PropertyDatum(c, a, "compiled", None) for c, a in data),
                               (InterpolationRule("thermal_conductivity", "temperature", "linear"),))


def state(t):
    return MaterialState(MAT, (NamedQuantity("temperature", Quantity(t, "K")),), "solid")


def show(label, props, t):
    r = props.resolve("thermal_conductivity", state(t))
    used = [d.claim.claim_id for d in props.data if d.claim.digest in r.claim_digests]
    val = None if r.value is None else r.value.value.magnitude
    print(f"{label}: T={t} status={r.status} derivation={r.derivation.value} value={val} used_claims={used} "
          f"sources={[s.source_id for s in r.sources]} reason={r.reason!r}")
    return r


S1 = build([("a-300", "src-A", 300, 10.0), ("b-300", "src-B", 300, 20.0), ("c-400", "src-A", 400, 30.0)], "s1")
S2 = build([("b-300", "src-A", 300, 10.0), ("a-300", "src-B", 300, 20.0), ("c-400", "src-A", 400, 30.0)], "s2")
r1 = show("TRIGGER ids a<b ", S1, 350)
r2 = show("TRIGGER ids swap", S2, 350)
r3 = show("EXACT 300 K     ", S1, 300)
cov = material_coverage_report(S1, state(350), ["thermal_conductivity"], requirement_source="audit.r03")
entry = cov.entries[0].to_dict()
print(f"COVERAGE at 350 K: status={entry['status']} conflicted={entry['conflicted']} value={entry['value'] and entry['value']['value']}")

# negative control: no coincident data; renaming the claim must not change the answer
N1 = build([("a-300", "src-A", 300, 10.0), ("c-400", "src-A", 400, 30.0)], "n1")
N2 = build([("z-300", "src-A", 300, 10.0), ("c-400", "src-A", 400, 30.0)], "n2")
n1 = show("CONTROL a-300   ", N1, 350)
n2 = show("CONTROL z-300   ", N2, 350)

v1 = r1.value and r1.value.value.magnitude
v2 = r2.value and r2.value.value.magnitude
reproduced = (r1.status == "known" and r2.status == "known" and v1 != v2 and r3.status == "unknown"
              and not entry["conflicted"])
control_ok = n1.value.value.magnitude == n2.value.value.magnitude == 20.0
print("VERDICT FDA-03:", "REPRODUCED" if reproduced else "NOT_REPRODUCED/CHECK")
print("CONTROL_OK:", control_ok)
