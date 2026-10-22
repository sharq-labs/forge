"""GEN2-BR1.1 authority mutations: one property of an authority-bound world payload changed at a time.

Shared by the adversarial test suite (``tests/mind/test_authority_mutations.py``) and the benchmark matrix
(``run_benchmark.py``).  Each mutation edits a world payload in place, exactly as a forger editing stored bytes would;
none of them goes through an owner.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable


def _hex(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _variable(payload: dict[str, Any], *, bound: bool = True) -> dict[str, Any]:
    for v in payload["variables"]:
        if (v.get("source") or {}).get("schema", "").endswith("authority_binding/1") == bound:
            return v
    raise AssertionError("no such variable")


def m_owner_id(p):
    _variable(p)["source"]["owner_id"] = _hex("another run")


def m_record_id(p):
    v = _variable(p)
    others = [x for x in p["variables"] if x is not v and (x.get("source") or {}).get("owner_kind") == "system_state"]
    v["source"]["record_id"] = others[0]["source"]["record_id"] if others else v["source"]["record_id"].replace(
        v["name"], v["name"] + "_other")


def m_record_digest(p):
    _variable(p)["source"]["record_digest"] = _hex("a state no run committed")


def m_revision(p):
    _variable(p)["source"]["revision"] = "7"


def m_value_only(p):
    v = _variable(p)
    v["value"]["magnitude"] = v["value"]["magnitude"] + 0.5


def m_value_and_projection(p):
    """A forger restates the value AND recomputes the binding's projection digest: same owner record, other value."""
    from engcore.mind.world.authority import projection_digest
    from engcore.scientific import Uncertainty
    from engcore.scientific.ir.values import decode_value
    v = _variable(p)
    v["value"]["magnitude"] = v["value"]["magnitude"] + 0.5
    if v["uncertainty"].get("lower"):
        v["uncertainty"]["lower"]["magnitude"] += 0.5
        v["uncertainty"]["upper"]["magnitude"] += 0.5
    v["source"]["projection"] = projection_digest({"value": decode_value(v["value"]).to_dict(),
                                                   "uncertainty": Uncertainty.from_dict(v["uncertainty"]).to_dict()})


def m_unit_text(p):
    v = _variable(p)
    v["value"]["units"] = "percent" if v["value"]["units"] == "dimensionless" else "milli" + v["value"]["units"]


def m_declared_unit(p):
    for d in p["roles"]["declarations"]:
        if d["name"] == _variable(p)["name"]:
            d["unit"] = "percent" if d["unit"] in ("dimensionless", "") else "milli" + d["unit"]


def m_domain(p):
    for v in p["variables"]:
        dom = v.get("domain")
        if dom and dom.get("upper"):
            dom["upper"]["magnitude"] = dom["upper"]["magnitude"] * 2 + 1
            return
    raise AssertionError("no ranged domain")


def m_protocol_level(p):
    for a in p["actions"]:
        for c in a["controls"]:
            dom = c["domain"]
            if dom.get("schema", "").endswith("discrete_levels/1"):
                dom["levels"].append({**dom["levels"][0], "magnitude": dom["levels"][0]["magnitude"] + 0.15})
                return
            if dom.get("upper"):
                dom["upper"]["magnitude"] = dom["upper"]["magnitude"] + 1
                return
    raise AssertionError("no control domain")


def m_provider_status(p):
    for s in p["providers"]:
        s["status"]["version"] = s["status"]["version"] + ".9"
        return
    raise AssertionError("no provider")


def m_provider_binding_digest(p):
    for s in p["providers"]:
        s["authority"]["record_digest"] = _hex("another provider build")
        return
    raise AssertionError("no provider")


def m_budget(p):
    for st in p["budget"]["statements"]:
        if st["kind"] == "ledger":
            st["payload"]["ledger"]["total_budget"] = st["payload"]["ledger"]["total_budget"] + 100
            return
        st["payload"]["accounting"]["remaining_observations"] += 100
        return
    raise AssertionError("no budget statement")


def m_budget_binding_revision(p):
    p["budget"]["statements"][0]["authority"]["revision"] = "999"


def m_applicability_identity(p):
    for a in p["applicability"]:
        a["authority"]["record_id"] = a["authority"]["record_id"].replace('"]', '.9"]')
        return
    raise AssertionError("no model")


def m_applicability_content(p):
    for a in p["applicability"]:
        cond = a["model"]["validity"]["conditions"][0]
        cond["maximum"]["magnitude"] = cond["maximum"]["magnitude"] * 10
        return
    raise AssertionError("no model")


def m_declaration_binding(p):
    p["declaration"]["revision"] = "2"


def m_unit_registry(p):
    p["unit_registry"]["record_digest"] = _hex("another unit registry")


def m_drop_binding(p):
    _variable(p)["source"] = {"schema": "forge.mind.world.record_ref/1", "kind": "synthetic_fixture",
                              "ref": "synthetic:laundered"}


MUTATIONS: dict[str, Callable[[dict[str, Any]], None]] = {
    "owner_id": m_owner_id, "record_id": m_record_id, "record_digest": m_record_digest, "revision": m_revision,
    "projected_value": m_value_only, "projected_value_and_binding": m_value_and_projection, "unit": m_unit_text,
    "declared_unit": m_declared_unit, "domain": m_domain, "protocol_level": m_protocol_level,
    "provider_status": m_provider_status, "provider_binding": m_provider_binding_digest, "budget": m_budget,
    "budget_binding": m_budget_binding_revision, "applicability_identity": m_applicability_identity,
    "applicability_content": m_applicability_content, "declaration_binding": m_declaration_binding,
    "unit_registry": m_unit_registry, "binding_replaced_by_a_copy": m_drop_binding,
}
#: Mutations a world without that kind of fact cannot carry.
NEEDS = {"provider_status": "providers", "provider_binding": "providers", "applicability_identity": "applicability",
         "applicability_content": "applicability", "budget": "budget", "budget_binding": "budget"}
