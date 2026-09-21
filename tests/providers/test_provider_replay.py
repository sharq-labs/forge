"""P20 #9: external replay actually re-executes the provider.

P11 states the distinction this file exists for:

    Replay: same provider version, same model, same parameters, same inputs,
    same provider configuration -> **execute again** -> compare canonical
    outputs.

The failure mode is a replay that loads a stored payload and compares it to
itself. That demonstrates a file is stable, which nobody doubted. So the test
here does not inspect the report's fields and conclude; it counts how many
times the provider was actually asked to run, using a provider that cannot lie
about it.
"""

from __future__ import annotations

import pytest

from engcore.providers import ExecutionOutcome, replay_provider_request
from engcore.providers import pybamm_provider as pp
from engcore.providers.contract import ProviderError

CELL = pp.CellUnderTest(
    cell_id="B0005",
    chemistry="LiCoO2/graphite",
    nominal_capacity_ah=1.86,
    ambient_temperature_k=297.0,
)
PROTOCOL = pp.CurrentProtocol(duration_s=900.0, constant_current_a=2.0)
AUTHORITY = pp.ParameterAuthority(
    authority_id="test.replay",
    source="forge_declared",
    parameter_set_name="ECM_Example",
    defining_provider_version="pybamm",
    chemistry="LiCoO2/graphite",
    nominal_capacity_ah=1.86,
    temperature_validity_k=(293.15, 313.15),
)


def _factory():
    import numpy as np
    import pybamm

    values = pybamm.ParameterValues("ECM_Example").copy()
    knots = np.linspace(0.0, 1.0, 11)

    def ocv(soc):
        return pybamm.Interpolant(
            knots, 3.0 + 1.2 * knots, soc, interpolator="linear", extrapolate=True
        )

    values.update(
        {
            "Cell capacity [A.h]": 1.86,
            "Nominal cell capacity [A.h]": 1.86,
            "Open-circuit voltage [V]": ocv,
            "R0 [Ohm]": 0.12,
            "R1 [Ohm]": 0.05,
            "C1 [F]": 1500.0,
            "Lower voltage cut-off [V]": 2.0,
            "Upper voltage cut-off [V]": 4.4,
            "Element-1 initial overpotential [V]": 0.0,
            "Entropic change [V/K]": 0.0,
            "Ambient temperature [K]": 297.0,
            "Initial temperature [K]": 297.0,
        },
        check_already_exists=False,
    )
    return values


class CountingProvider(pp.PyBaMMProvider):
    """A real provider that records how many times it was asked to execute."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.executions = 0

    def execute(self, request):
        self.executions += 1
        return super().execute(request)


def _request():
    return pp.build_request(
        model_key="thevenin_1rc",
        authority=AUTHORITY,
        cell=CELL,
        protocol=PROTOCOL,
        qois=("terminal_voltage", "time", "state_of_charge"),
        initial_state_of_charge=0.95,
    )


def test_external_replay_actually_re_executes_the_provider():
    pytest.importorskip("pybamm")
    provider = CountingProvider(
        authority=AUTHORITY, cell=CELL, protocol=PROTOCOL,
        parameter_values_factory=_factory,
    )
    request = _request()
    first = provider.execute(request)
    assert first.outcome is ExecutionOutcome.OK, first.receipt.detail
    assert provider.executions == 1

    report = replay_provider_request(provider, request, first, tolerance=0.0)

    assert provider.executions == 2, (
        "replay did not call the provider a second time, so it compared a "
        "stored payload to itself"
    )
    assert report.executed is True
    assert report.identity_matched is True
    assert report.reproduced is True
    assert report.tolerance == 0.0
    assert report.max_absolute_difference == 0.0, (
        "a deterministic provider re-run at zero tolerance is bit-identical or "
        "it is not deterministic; either way the number is the finding"
    )
    assert set(report.compared_qois) == set(request.qois)
    assert report.drift == ()


def test_replay_needs_something_to_reproduce():
    """A receipt with no payload has no numbers, and a replay of it is a no-op."""
    provider = pp.PyBaMMProvider(
        authority=pp.NAMED_AUTHORITIES["Chen2020"], cell=CELL, protocol=PROTOCOL
    )
    refused = provider.execute(
        pp.build_request(
            model_key="spme",
            authority=pp.NAMED_AUTHORITIES["Chen2020"],
            cell=CELL,
            protocol=PROTOCOL,
            qois=("terminal_voltage",),
            initial_state_of_charge=0.95,
        )
    )
    assert refused.result is None
    with pytest.raises(ProviderError, match="no numbers to reproduce"):
        replay_provider_request(provider, _request(), refused)


def test_a_replay_whose_provider_identity_moved_is_not_reproduced():
    """Drift is recorded, not hidden, and it defeats ``reproduced``.

    P11 is explicit: "If environment/provider drift prevents deterministic
    replay: record it explicitly. Do not hide it." Reproducing the same numbers
    under a *different* provider version demonstrates nothing about
    determinism, so identity is part of the verdict and the moved fields are
    named.
    """
    pytest.importorskip("pybamm")
    provider = CountingProvider(
        authority=AUTHORITY, cell=CELL, protocol=PROTOCOL,
        parameter_values_factory=_factory,
    )
    request = _request()
    first = provider.execute(request)
    assert first.outcome is ExecutionOutcome.OK

    class DriftedProvider(CountingProvider):
        def _identity(self, spec, solver_name, configuration):
            base = super()._identity(spec, solver_name, configuration)
            from dataclasses import replace

            return replace(base, provider_version=base.provider_version + "+drift")

    drifted = DriftedProvider(
        authority=AUTHORITY, cell=CELL, protocol=PROTOCOL,
        parameter_values_factory=_factory,
    )
    report = replay_provider_request(drifted, request, first, tolerance=0.0)

    assert drifted.executions == 1
    assert report.executed is True
    assert report.identity_matched is False
    assert report.reproduced is False, (
        "the same numbers under a different provider version were reported as "
        "reproduced"
    )
    assert any("provider_version" in line for line in report.drift), report.drift
    # And the numbers really were identical, which is what makes the point:
    # `reproduced` is False because of identity, not because of the values.
    assert report.max_absolute_difference == 0.0


def test_replay_of_a_provider_that_stops_delivering_is_recorded_as_such():
    """An unavailable provider on the second run is drift, not a reproduction."""
    pytest.importorskip("pybamm")
    provider = CountingProvider(
        authority=AUTHORITY, cell=CELL, protocol=PROTOCOL,
        parameter_values_factory=_factory,
    )
    request = _request()
    first = provider.execute(request)
    assert first.outcome is ExecutionOutcome.OK

    class GoneProvider(pp.PyBaMMProvider):
        def available(self) -> bool:
            return False

    report = replay_provider_request(
        GoneProvider(
            authority=AUTHORITY, cell=CELL, protocol=PROTOCOL,
            parameter_values_factory=_factory,
        ),
        request,
        first,
    )
    assert report.executed is False
    assert report.reproduced is False
    assert any("did not deliver" in line for line in report.drift)
