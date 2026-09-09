"""The challenge plan: which cases exist, how many, and where each is aimed.

**Frozen before generation, and before any truth is computed.** This module
contains no physics and no verdict. It is the design — per-domain counts, the
strata each family targets, and the conditions each family aims at — written
down first so that the composition of the corpus cannot become a function of
what Forge turned out to do with it.

Why the counts are here rather than passed on a command line: a count on a
command line is not a record. Phase 1C of the challenge asks for the per-domain
counts to be recorded *before* generation and never rebalanced afterwards, and
the only version of that promise anyone can check is one that is committed.

Positions, and why they are these numbers
-----------------------------------------

A family targets one condition and places it at a chosen ``position`` — the
condition's value as a fraction of the bound that would refuse it, so that
``position < 1`` is inside for a maximum bound and the generator solves the
declaration to land there. The ladder is::

    0.20  0.50  0.90   FAR_INSIDE / NEAR_INSIDE
    0.99  0.999        NEAR_INSIDE
    1.0                AT_BOUNDARY   (arithmetic-sensitive; see below)
    1.001 1.01         NEAR_OUTSIDE
    1.20  3.00         FAR_OUTSIDE

**Why 1e-3 is the closest resolvable approach and 1.0 is not scored.** The
oracle and the runtime are two independent implementations of the same fixed
point. Measured over the 1400 open development cases, they agree on the final
temperature to 3.8e-16 relative and on the steady-state temperature to 2.1e-9
relative — the latter set by the caller-declared coupling tolerance, not by
either implementation. A case placed closer to its bound than that has a truth
which is an artefact of arithmetic: it will be decided by whichever
implementation rounds which way, and calling either one wrong would be
measuring floating point rather than science.

So ``0.999`` and ``1.001`` sit 5e5 times the measured disagreement away from
the bound, which is as sharp as independent truth goes here. ``1.0`` is
generated anyway, tagged ``AT_BOUNDARY``, given
``truth_confidence_class = ARITHMETIC_SENSITIVE``, and **excluded from the
primary denominator** — it is reported as its own diagnostic, because a
challenge that quietly scored it would be manufacturing exactly the false
precision this round exists to remove. The evidence that this is a real effect
and not a hypothetical: ``U00611`` in the existing corpus computes
``working_voltage_utilization`` at ``1 + 1.2e-10`` and the two implementations
disagree about it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PLAN_VERSION",
    "RESOLUTION_FLOOR",
    "MEASURED_STATE_AGREEMENT",
    "Family",
    "ELECTROTHERMAL_FAMILIES",
    "BATTERY_FAMILIES",
    "KINETICS_FAMILIES",
    "CONDUCTION_FAMILIES",
    "PLANNED_COUNTS",
    "planned_total",
]

PLAN_VERSION = "blind-plan/1.0.0"

#: The closest a case may be placed to a bound and still carry decided truth,
#: as a relative distance. Five orders of magnitude above the measured
#: implementation disagreement below.
RESOLUTION_FLOOR = 1.0e-3

#: Measured, not assumed: the worst relative disagreement between this
#: challenge's oracle and the runtime over the 1400 open development cases.
#: `final_temperature` 3.77e-16, `steady_state_temperature` 2.05e-09.
MEASURED_STATE_AGREEMENT = {
    "final_temperature_relative": 3.77e-16,
    "steady_state_temperature_relative": 2.05e-09,
    "measured_over": "1400 open development cases, benchmarks/hard/cases_hard",
    "method": "independent oracle vs engcore.mcp.problem.run_electrothermal_case",
}

#: The position ladder, and the stratum each rung is aimed at. The stratum a
#: case ENDS UP in is measured from its truth, never assumed from this table --
#: a family that misses its target keeps its measured stratum and is counted as
#: a miss in the manifest.
POSITION_LADDER: tuple[tuple[float, str], ...] = (
    (0.20, "FAR_INSIDE"),
    (0.50, "FAR_INSIDE"),
    (0.90, "NEAR_INSIDE"),
    (0.99, "NEAR_INSIDE"),
    (0.999, "NEAR_INSIDE"),
    (1.0, "AT_BOUNDARY"),
    (1.001, "NEAR_OUTSIDE"),
    (1.01, "NEAR_OUTSIDE"),
    (1.20, "FAR_OUTSIDE"),
    (3.00, "FAR_OUTSIDE"),
)


@dataclass(frozen=True)
class Family:
    """One group of cases aimed at one thing.

    ``kind`` says what the family is FOR, and it is what stops a corpus that is
    all threshold-ladders: ``threshold`` walks a condition across its bound,
    ``missing`` withholds a declaration so the only finding is the gap,
    ``clean`` builds a design with every condition comfortably inside,
    ``representation`` re-expresses a clean design in different units, and
    ``malformed`` breaks the payload itself.
    """

    family_id: str
    system: str
    kind: str
    target: str | None
    count: int
    note: str = ""


# =====================================================================
# electro-thermal — the system boundary, four domains at once
# =====================================================================

#: Conditions the electro-thermal generator can place exactly, by solving the
#: declaration that puts them at a chosen position. Each gets a ten-rung
#: ladder, one case per rung.
_ET_LADDER_TARGETS = (
    "operating_temperature_utilization",
    "working_voltage_utilization",
    "dissipated_power_utilization",
    "source_current_utilization",
    "linearization_excursion_ratio",
    "reduced_debye_temperature",
    "melting_temperature_utilization",
    "biot_number",
    "conductance_excursion_ratio",
    "capacity_excursion_ratio",
    "radiation_to_convection_ratio",
    "convection_flow_range_utilization",
    "internal_fourier_number",
    "convection_conductance_agreement_ratio",
    "geometry_route_ratio",
)

#: Declarations that may be withheld, and the condition each starves. One case
#: each: the point of a missing-evidence case is that the gap is the ONLY
#: finding, so a ladder over it would be nine repetitions of one question.
_ET_WITHHOLD_TARGETS = (
    "linearization_band",
    "maximum_operating_temperature",
    "debye_temperature",
    "body_conductivity",
    "surface_emissivity",
    "melting_temperature",
    "conductance_excursion_bound",
    "capacity_excursion_bound",
    "fluid_conductivity",
    "fluid_prandtl_number",
    "fluid_kinematic_viscosity",
    "convection_length",
    "surface_area",
    "body_volume",
    "rated_power",
    "maximum_working_voltage",
    "maximum_current",
)

ELECTROTHERMAL_FAMILIES: tuple[Family, ...] = (
    *(Family(f"et.threshold.{name}", "electrothermal", "threshold", name,
             len(POSITION_LADDER),
             "one case per rung of the position ladder")
      for name in _ET_LADDER_TARGETS),
    *(Family(f"et.missing.{name}", "electrothermal", "missing", name, 1,
             "the withheld declaration is the only finding")
      for name in _ET_WITHHOLD_TARGETS),
    Family("et.clean", "electrothermal", "clean", None, 20,
           "every condition comfortably inside; the verdict must not refuse"),
    Family("et.representation", "electrothermal", "representation", None, 12,
           "a clean design re-declared in millivolt/kilohm/degC and multi-stage"),
    Family("et.malformed", "electrothermal", "malformed", None, 8,
           "the payload itself is broken: absent unit, wrong dimension, "
           "unknown field, non-finite magnitude"),
)


# =====================================================================
# battery — the second system boundary
# =====================================================================

_BATTERY_LADDER_TARGETS = (
    "continuous_c_rate_utilization",
    "soc_window_margin",
    "self_heating_rise_ratio",
    "discharge_temperature_position",
    "peukert_extrapolation_ratio",
    "internal_resistance_drift_ratio",
    "pulse_duration_utilization",
    "soc_step_resolution_ratio",
)

_BATTERY_WITHHOLD_TARGETS = (
    "continuous_discharge_c_rate",
    "usable_soc_minimum",
    "self_heating_rise_bound",
    "minimum_discharge_temperature",
    "peukert_exponent",
    "polarization_time_constant",
    "soc_step_resolution",
    "capacity_reference_temperature",
)

BATTERY_FAMILIES: tuple[Family, ...] = (
    *(Family(f"bat.threshold.{name}", "battery", "threshold", name,
             len(POSITION_LADDER), "position ladder")
      for name in _BATTERY_LADDER_TARGETS),
    *(Family(f"bat.missing.{name}", "battery", "missing", name, 1,
             "the withheld declaration is the only finding")
      for name in _BATTERY_WITHHOLD_TARGETS),
    Family("bat.clean", "battery", "clean", None, 14,
           "a duty every condition admits, marched to the end"),
    Family("bat.representation", "battery", "representation", None, 8,
           "milliampere / milliampere_hour / minute / degC spellings"),
    Family("bat.efficiency", "battery", "threshold", "coulombic_efficiency", 6,
           "the one HARD battery bound: charge conservation"),
    Family("bat.malformed", "battery", "malformed", None, 4,
           "the payload itself is broken"),
)


# =====================================================================
# kinetics — model contract only; there is no MCP case boundary
# =====================================================================

KINETICS_FAMILIES: tuple[Family, ...] = (
    Family("kin.ceiling", "kinetics_cstr", "threshold",
           "adiabatic_ceiling_temperature", 10,
           "the derived ceiling walked across the 1000 K scope bound"),
    Family("kin.envelope", "kinetics_cstr", "threshold", "temperature", 10,
           "the declared initial temperature walked across [250, 1000] K; "
           "the constructor refuses before the condition can fire, and that "
           "asymmetry is what this family tests"),
    Family("kin.missing", "kinetics_cstr", "missing", None, 8,
           "one declaration withheld; the ceiling becomes underivable"),
    Family("kin.clean", "kinetics_cstr", "clean", None, 12,
           "a reactor entirely inside the declared envelope"),
    Family("kin.endothermic", "kinetics_cstr", "clean", None, 6,
           "beta <= 0: the rise term must clamp at zero rather than lower "
           "the ceiling below the feed temperature"),
    Family("kin.positivity", "kinetics_cstr", "threshold", None, 8,
           "k0, activation energy, residence time and concentration at and "
           "below their physical floors"),
    Family("kin.representation", "kinetics_cstr", "representation", None, 6,
           "kilojoule/mole, mole/liter, minute, degC spellings"),
)


# =====================================================================
# conduction — model contract only: realization applicability
# =====================================================================

CONDUCTION_FAMILIES: tuple[Family, ...] = (
    Family("cond.ftcs", "conduction_1d", "threshold", "fourier_number", 20,
           "the von Neumann limit walked across r = 1/2, at several meshes"),
    Family("cond.implicit", "conduction_1d", "clean", None, 12,
           "backward Euler: an A-stable scheme declares no condition, and an "
           "EMPTY validity domain assesses to UNKNOWN — a claim about the "
           "record's semantics, not about diffusion"),
    Family("cond.alpha", "conduction_1d", "threshold", "alpha", 6,
           "the diffusivity floor: with no diffusivity nothing diffuses"),
    Family("cond.mesh", "conduction_1d", "clean", None, 14,
           "the same physical slab at several mesh and step counts, which "
           "moves r without moving the problem"),
    Family("cond.representation", "conduction_1d", "representation", None, 8,
           "millimeter / minute spellings of the same slab"),
)


ALL_FAMILIES: tuple[Family, ...] = (
    ELECTROTHERMAL_FAMILIES + BATTERY_FAMILIES
    + KINETICS_FAMILIES + CONDUCTION_FAMILIES
)

#: Per-system planned counts, recorded BEFORE generation. Phase 1C.
PLANNED_COUNTS: dict[str, int] = {}
for _family in ALL_FAMILIES:
    PLANNED_COUNTS[_family.system] = (
        PLANNED_COUNTS.get(_family.system, 0) + _family.count
    )


def planned_total() -> int:
    return sum(PLANNED_COUNTS.values())
