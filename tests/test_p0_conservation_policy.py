"""Adversarial numerical conservation checks; synthetic inputs, no validation."""
from dataclasses import replace
from fractions import Fraction
import math
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

from engcore.domains.thermal_models import conduction1d_transient_fv as model
from engcore.numerical.core import NumericalRefusal
from engcore.scientific.units.quantity import Quantity

_spec = importlib.util.spec_from_file_location("p0_m1c_fixture", Path(__file__).with_name("test_m1c_transient_fv.py"))
_fixture = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _fixture
_spec.loader.exec_module(_fixture)
SparseFVProvider, advance, flux, region, session = (
    _fixture.SparseFVProvider, _fixture.advance, _fixture.flux, _fixture.region, _fixture.session
)


CELLS = (4, 16, 32, 64, 128, 256, 512)


class UniformLeak(SparseFVProvider):
    """Unit total heat capacity: the offset injects the same physical energy."""

    def _execute(self, problem, method):
        record = super()._execute(problem, method)
        shifted = tuple(Quantity(q.magnitude + 1e-7, "K") for q in record.outputs["temperature"])
        return replace(record, outputs={"temperature": shifted})


@pytest.mark.parametrize("cells,datum,dt", [(n, 300.0, .1) for n in CELLS] + [(256, 3000.0, .01)])
def test_fixed_closed_system_leak_is_rejected_on_every_mesh(cells, datum, dt):
    nodes = tuple(np.linspace(0, 1, cells + 1))
    run = session(nodes=nodes, temperatures=(datum,) * len(nodes), provider=UniformLeak(),
                  residual_rtol=1e-8, conservation_rtol=1e-6)
    # The unit-length, unit-storage, unit-area slab has exactly 1 J/K in the
    # physical fixture. No mesh-dependent leak or acceptance threshold is used.
    with pytest.raises(NumericalRefusal, match="energy conservation"):
        advance(run, dt)
    with pytest.raises(NumericalRefusal, match="unusable"):
        advance(run, dt)


def _capacities(nodes, materials):
    """Geometric integration independent of the solver's capacity assembly."""
    edges = (nodes[0], *(0.5 * a + 0.5 * b for a, b in zip(nodes[:-1], nodes[1:])), nodes[-1])
    return tuple(math.fsum(max(0.0, min(b, hi) - max(a, lo)) * c * area
                           for lo, hi, c, area in materials)
                 for a, b in zip(edges[:-1], edges[1:]))


@pytest.mark.parametrize("cells", CELLS)
@pytest.mark.parametrize("kind", ("equilibrium", "redistribution", "source_and_flux", "heterogeneous"))
def test_independent_energy_accounting_on_each_mesh(cells, kind):
    nodes = tuple(np.linspace(0, 1, cells + 1))
    old = tuple(300.0 + (math.sin(math.pi * x) if kind == "redistribution" else 0.0) for x in nodes)
    if kind == "heterogeneous":
        regions = (region(0, 0.4, k=1, c=2, area=2), region(0.4, 1, k=10, c=3, area=1))
        materials, sources, left, right = ((0, .4, 2, 2), (.4, 1, 3, 1)), (3, -.75), flux(2), flux(-.5)
        external_power = 2 * 2 - .5 * 1 + 3 * 2 * .4 - .75 * 1 * .6
    else:
        regions, materials = (region(),), ((0, 1, 1, 1),)
        forcing = kind == "source_and_flux"
        sources, left, right = ((1.25,) if forcing else (0,)), flux(2 if forcing else 0), flux(-.5 if forcing else 0)
        external_power = 2.75 if forcing else 0.0
    run = session(nodes=nodes, regions=regions, temperatures=old)
    result = advance(run, .001, left=left, right=right, q=sources)
    new = run.adapter.read_state(result.temperature)
    capacities = _capacities(nodes, materials)
    assert run._capacity == pytest.approx(capacities, rel=1e-13, abs=1e-15)
    # Fraction measures the represented states without subtractive summation
    # error; the expected capacity/source total comes from geometry above.
    actual = sum((Fraction.from_float(c) * (Fraction.from_float(float(b)) - Fraction.from_float(float(a)))
                  for c, a, b in zip(capacities, old, new)), Fraction(0))
    assert float(actual) == pytest.approx(.001 * external_power, abs=1e-9)
    assert result.binding["conservation_admission_policy"] == "exact_represented_inputs_global/1"
    assert result.binding["conservation_arithmetic_floor_J"] == 0.0
    assert abs(Fraction(result.binding["conservation_exact_balance_J"])) <= Fraction(result.binding["conservation_exact_allowance_J"])


@pytest.mark.parametrize("dt", (.01, .005, .0025))
@pytest.mark.parametrize("datum", (300, 3000))
def test_timestep_and_datum_changes_preserve_global_policy(dt, datum):
    run = session(nodes=tuple(np.linspace(0, 1, 33)), temperatures=(datum,) * 33)
    result = advance(run, dt, left=flux(2), right=flux(-.5), q=(1.25,))
    assert result.binding["conservation_arithmetic_floor_J"] == 0.0
    # Exchange counts absolute external powers; the signed net is 2.75 W.
    external_exchange = math.fsum(abs(power) for power in (2.0, -.5, 1.25))
    assert result.binding["conservation_exchange_scale_J"] == pytest.approx(external_exchange * dt, rel=1e-7)


@pytest.mark.parametrize("factor", (math.inf, math.nan))
def test_nonfinite_local_allowance_cannot_disable_global_admission(monkeypatch, factor):
    run = session()
    monkeypatch.setattr(model, "_BALANCE_ROUNDOFF_FACTOR", factor)
    with pytest.raises(NumericalRefusal, match="non-finite"):
        advance(run)
    with pytest.raises(NumericalRefusal, match="unusable"):
        advance(run)


def test_overflowed_allowance_is_refused(monkeypatch):
    run = session(temperatures=(1e100,) * 4)
    monkeypatch.setattr(model, "_BALANCE_ROUNDOFF_FACTOR", 1e308)
    with np.errstate(over="ignore", invalid="ignore"):
        with pytest.raises(NumericalRefusal, match="non-finite"):
            advance(run)


@pytest.mark.parametrize("cells", (4, 128, 512))
def test_high_fourier_solver_drift_is_admitted_only_if_conservation_is_resolved(cells):
    nodes = tuple(np.linspace(0, 1, cells + 1))
    run = session(nodes=nodes)
    try:
        result = advance(run, 1e8)
    except NumericalRefusal:
        # An ill-conditioned solve is allowed to refuse; it may not publish a
        # successful step using conductance-inflated global allowance.
        with pytest.raises(NumericalRefusal, match="unusable"):
            advance(run)
    else:
        new = run.adapter.read_state(result.temperature)
        change = math.fsum(c * (t - 300) for c, t in zip(_capacities(nodes, ((0, 1, 1, 1),)), new))
        assert abs(change) <= 1e-9 + 1e-12 * math.fsum(abs(c * (t - 300)) for c, t in zip(run._capacity, new))
        assert result.binding["conservation_arithmetic_floor_J"] == 0.0
