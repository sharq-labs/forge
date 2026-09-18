"""Repository-reviewed NAFEMS P18.T3 thermal benchmark evidence.

This module contains external benchmark DATA, not a solver and not a second
implementation of Forge's thermal physics.

Public reproductions of NAFEMS T3 report the target temperature as 36.6 degC
at x=0.08 m and t=32 s for the declared one-dimensional transient bar case.
The record stores the target as 309.75 K so the oracle comparison stays on an
absolute temperature scale.

The +/-0.05 K tolerance is a RECORDING-PRECISION envelope: the public target
is reported to one decimal degree Celsius. It is deliberately not described as
a NAFEMS acceptance criterion.

Sources reviewed for this declaration:
- NAFEMS P18.T3, The Standard NAFEMS Benchmarks, Rev. 3 (1990).
- Altair SimSolid verification case SS-V:3070 (public reproduction).
- MOOSE NAFEMS T3 verification example (public independent reproduction).

The evidence digest below is intentionally hard-coded. Changing a target,
condition, tolerance, kind or reference must change the digest and therefore
requires a reviewed change to the repository-owned trust registry.
"""

from __future__ import annotations

from ...scientific.oracles import OracleEvidenceSet, OracleKind, OracleObservation
from ...scientific.units.quantity import Quantity

ORACLE_ID = "nafems.p18.t3.transient_heat_1d"
ORACLE_VERSION = "1"
REFERENCE = (
    "NAFEMS P18.T3, The Standard NAFEMS Benchmarks, Rev. 3 (1990); "
    "public reproductions: Altair SimSolid SS-V:3070 and MOOSE nafems_t3_verif"
)

# Repository-reviewed content pin. Any scientific-content edit requires a new digest.
EVIDENCE_DIGEST = "eb6e2daf9a6ad6a957576fc9d3462175edf0525ebeea68bcd74778868d875328"

CONDITIONS = {
    "length": Quantity(0.1, "meter"),
    "width": Quantity(0.01, "meter"),
    "depth": Quantity(0.01, "meter"),
    "conductivity": Quantity(35.0, "watt/meter/kelvin"),
    "density": Quantity(7200.0, "kilogram/meter**3"),
    "specific_heat": Quantity(440.5, "joule/kilogram/kelvin"),
    "end_time": Quantity(32.0, "second"),
    "probe_position": Quantity(0.08, "meter"),
    "initial_temperature": Quantity(273.15, "kelvin"),
    "left_boundary_temperature": Quantity(273.15, "kelvin"),
    "right_boundary_offset": Quantity(273.15, "kelvin"),
    "right_boundary_amplitude": Quantity(100.0, "kelvin"),
    "right_boundary_sine_time_scale": Quantity(40.0, "second"),
    "lateral_heat_flux": Quantity(0.0, "watt/meter**2"),
    "internal_heat_generation": Quantity(0.0, "watt/meter**3"),
}

OBSERVATIONS = (
    OracleObservation(
        metric="temperature_at_probe",
        expected=Quantity(309.75, "kelvin"),
        absolute_tolerance=Quantity(0.05, "kelvin"),
        note=(
            "NAFEMS T3 target is publicly reproduced as 36.6 degC. "
            "Tolerance is +/-0.05 K from one-decimal reporting precision; "
            "it is not claimed to be a NAFEMS acceptance threshold."
        ),
        conditions=CONDITIONS,
    ),
)


def nafems_t3_evidence() -> OracleEvidenceSet:
    """Return the content-addressed T3 evidence set."""
    return OracleEvidenceSet.create(
        oracle_id=ORACLE_ID,
        version=ORACLE_VERSION,
        kind=OracleKind.BENCHMARK_DATASET,
        reference=REFERENCE,
        observations=OBSERVATIONS,
    )
