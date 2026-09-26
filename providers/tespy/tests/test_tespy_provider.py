"""Proof C (part): real TESPy thermal-fluid network execution mapped to Forge records."""

from __future__ import annotations

import pytest

from engcore.materials import FluidIdentity
from engcore.providers import ProviderRefusal, ProviderRegistry
from engcore.scientific.units.quantity import Quantity
from forge_tespy import ChainProblem, HeatExchangerSpec, TESPyProvider, descriptor

REG = ProviderRegistry()
descriptor.register(REG)
OK = REG.status("tespy").available
pytestmark = pytest.mark.skipif(not OK, reason="TESPy unavailable")


def chain(q_w=5000.0):
    return ChainProblem("coolant-loop", FluidIdentity("water"), Quantity(0.05, "kg/s"), Quantity(2, "bar"), Quantity(20, "degC"),
                        (HeatExchangerSpec("cold_plate", Quantity(q_w, "W"), 1.0),))


def test_proof_c_tespy_chain_converges_and_satisfies_its_energy_balance():
    rec = TESPyProvider(REG).solve(chain())
    assert rec.succeeded, rec.reason
    h1, h2 = rec.scalars["c1.enthalpy"].magnitude, rec.scalars["c2.enthalpy"].magnitude
    assert (h2 - h1) * 0.05 == pytest.approx(5000.0, rel=1e-9)  # the imposed heat is what the stream carries
    assert rec.scalars["c2.temperature"].magnitude == pytest.approx(273.15 + 43.92, abs=0.05)
    conns = chain().connections()
    assert [(c.source_instance_id, c.target_instance_id) for c in conns] == [("inlet", "cold_plate"), ("cold_plate", "outlet")]
    assert TESPyProvider(REG).solve(chain(4000.0)).identity.digest != rec.identity.digest
    with pytest.raises(ProviderRefusal, match="no declared TESPy mapping"):
        ChainProblem("x", FluidIdentity("unobtainium"), Quantity(1, "kg/s"), Quantity(1, "bar"), Quantity(300, "K"), chain().exchangers)


def test_impossible_network_fails_closed():
    boil = ChainProblem("boiler", FluidIdentity("water"), Quantity(1e-4, "kg/s"), Quantity(1, "bar"), Quantity(20, "degC"),
                        (HeatExchangerSpec("burner", Quantity(1e9, "W"), 1.0),))
    rec = TESPyProvider(REG).solve(boil)
    assert not rec.succeeded and not rec.scalars
