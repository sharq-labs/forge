"""The independent physics. Ground truth is computed here and never asked of engcore.

Why this file exists at all
---------------------------
A benchmark whose labels come from the tool under test measures nothing. Every
number this module produces is computed from the equations named in
``docs/domains/applicability-conditions.md`` and their cited sources, restated
here rather than imported, so that a change inside ``src/engcore`` cannot move
a label.

It is also *not* a copy of ``benchmarks/hard/generate_hard.py``. That file is
frozen and off limits; the formulas below were written against the same cited
literature (Incropera, DeWitt, Bergman & Lavine, 6th ed.; Churchill & Chu 1975)
and agree with it where they overlap, which is the point of two independent
statements of one physics.

The one semantic fact that had to be read from the source
---------------------------------------------------------
Which temperature the conditions are evaluated at is a property of the runtime,
not of the physics, and it cannot be derived from a textbook. Reading it out of
``src`` is reading a specification, not asking for an answer:

* the coupled fixed point transports ``final_temperature`` -- the body
  temperature at ``t = duration`` -- so the converged electrical operating point
  is ``R(T_final)`` (``engcore/domains/thermal_models/lumped.py``,
  ``TEMPERATURE_METRIC``);
* the applicability conditions are then formed from the *steady* temperature
  implied by that converged heat input, ``T_amb + Q/hA``, and the peak is
  ``max(T_0, T_ss)`` (``derived_lumped_quantities`` in
  ``engcore/domains/thermal_models/context.py``).

:func:`solve` returns both temperatures, and :func:`assess` is deliberately
written so that a case whose label depends on which of the two is used is
reported as ``ambiguous``. Every seed case in this benchmark is built to be
unambiguous under both readings; :func:`assess_robust` enforces that. A design
that sits close enough to a bound for the distinction to matter is not a design
this benchmark is willing to label.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants. Restated from their sources, never imported from engcore.
# ---------------------------------------------------------------------------

#: BIPM, *The International System of Units (SI)*, 9th ed. (2019), Sec. 2.3.1.
SIGMA = 5.670374419e-8

#: Incropera et al., 6th ed., Sec. 5.1, Eq. 5.10.
BIOT_LIMIT = 0.1
#: Incropera et al., 6th ed., Sec. 5.5.2 (one-term approximation).
FOURIER_MIN = 0.2
#: The neglected-mechanism convention; Incropera et al., Sec. 1.2.3, Eq. 1.9.
RADIATION_SHARE_LIMIT = 0.1
#: Definitional: a declared budget in use is a fraction of itself.
EXCURSION_LIMIT = 1.0
PHASE_CHANGE_LIMIT = 1.0
LINEARIZATION_LIMIT = 1.0
#: Ashcroft & Mermin, Ch. 26: linear ideal resistivity above ~theta_D/3.
DEBYE_FLOOR = 1.0 / 3.0
#: The declared range of the repository's own linear TCR form. A limit of the
#: *model*, narrower than any material's category temperature, and the trap
#: that mislabelled 61 cases of the frozen benchmark before it was written down.
TCR_MIN_TEMPERATURE = 200.0
TCR_MAX_TEMPERATURE = 450.0
#: Churchill & Chu (1975) laminar vertical plate, Ra_L <= 1e9.
RAYLEIGH_MAX = 1.0e9
#: Flat plate transition, Incropera et al. Sec. 7.1; Eq. 7.30 needs Pr >= 0.6.
REYNOLDS_MAX = 5.0e5
PRANDTL_MIN = 0.6
#: A convention, not a cited threshold. Recorded as one in the domain docs.
CONVECTION_AGREEMENT_FACTOR = 2.0
#: The sphere's shape factor; the bound is inclusive on purpose.
GEOMETRY_AGREEMENT_FACTOR = 3.0

G_STANDARD = 9.80665

#: Dry air near 300 K, used only where a case declares air explicitly.
#: Incropera et al., 6th ed., Table A.4.
AIR_KINEMATIC_VISCOSITY = 1.589e-5
AIR_PRANDTL = 0.707
AIR_CONDUCTIVITY = 0.0263


# ---------------------------------------------------------------------------
# The electro-thermal fixed point
# ---------------------------------------------------------------------------


@dataclass
class Solution:
    """The converged operating point, in both readings of "the temperature"."""

    t_final: float          # body temperature at t = duration
    t_steady: float         # T_amb + Q/hA at the converged heat input
    resistance: float       # R(T_final) -- the circuit the run actually solved
    current: float
    power: float
    tau: float
    converged: bool


def _march(t_amb: float, t_init: float, power: float, ha: float,
           cap: float, duration: float) -> float:
    """One lumped body over one interval at constant heat input.

    C dT/dt = Q - hA (T - T_amb), integrated exactly:
        T(t) = T_amb + Q/hA + (T_0 - T_amb - Q/hA) exp(-t hA / C)
    """
    tau = cap / ha
    steady = t_amb + power / ha
    return steady + (t_init - steady) * math.exp(-duration / tau)


def solve(*, source_voltage: float, reference_resistance: float,
          temperature_coefficient: float, reference_temperature: float,
          ambient_conductance: float, ambient_temperature: float,
          initial_temperature: float, heat_capacity: float,
          duration: float, max_iterations: int = 400,
          tolerance: float = 1e-9) -> Solution | None:
    """Fixed point on the torn temperature edge.

    The iterate is the *end-of-interval* body temperature, which is the metric
    the coupling transports. Returns ``None`` when the loop diverges or the
    resistance goes non-positive -- a temperature coefficient steep enough to
    zero the resistance is not a run, it is a broken declaration.
    """
    t = initial_temperature
    for _ in range(max_iterations):
        r = reference_resistance * (
            1.0 + temperature_coefficient * (t - reference_temperature)
        )
        if r <= 0.0:
            return None
        power = source_voltage * source_voltage / r
        nxt = _march(ambient_temperature, initial_temperature, power,
                     ambient_conductance, heat_capacity, duration)
        if not math.isfinite(nxt) or abs(nxt) > 1e7:
            return None
        if abs(nxt - t) < tolerance:
            t = nxt
            break
        t = nxt
    else:
        return None

    r = reference_resistance * (
        1.0 + temperature_coefficient * (t - reference_temperature)
    )
    if r <= 0.0:
        return None
    power = source_voltage * source_voltage / r
    return Solution(
        t_final=t,
        t_steady=ambient_temperature + power / ambient_conductance,
        resistance=r,
        current=source_voltage / r,
        power=power,
        tau=heat_capacity / ambient_conductance,
        converged=True,
    )


# ---------------------------------------------------------------------------
# The dimensionless groups
# ---------------------------------------------------------------------------


def characteristic_length(declared, volume, surface_area):
    if declared is not None:
        return declared
    if volume is not None and surface_area:
        return volume / surface_area
    return None


def biot(ha, surface_area, length, conductivity):
    if None in (ha, surface_area, length, conductivity) or 0 in (
        surface_area, conductivity
    ):
        return None
    return (ha / surface_area) * length / conductivity


def fourier(duration, tau, bi):
    """Fo = (t/tau)/Bi.

    Incropera et al., Sec. 5.2, Eq. 5.12 gives Bi*Fo = t/tau. Writing ``t/tau``
    and calling it Fo is the error the frozen benchmark records having made in
    103 cases; it is restated here so this file cannot repeat it.
    """
    if bi is None or bi <= 0 or tau <= 0:
        return None
    return (duration / tau) / bi


def radiation_share(emissivity, surface_area, ha, peak, ambient):
    """h_r/h with h_r = eps*sigma*(Ts+Tsur)(Ts^2+Tsur^2), at the peak surface."""
    if None in (emissivity, surface_area, ha) or surface_area <= 0:
        return None
    h_r = emissivity * SIGMA * (peak + ambient) * (peak * peak + ambient * ambient)
    h = ha / surface_area
    if h <= 0:
        return None
    return h_r / h


def churchill_chu(ra, pr):
    """Nu = 0.68 + 0.670 Ra^(1/4) / [1 + (0.492/Pr)^(9/16)]^(4/9)."""
    return 0.68 + 0.670 * ra ** 0.25 / (
        1.0 + (0.492 / pr) ** (9.0 / 16.0)
    ) ** (4.0 / 9.0)


def flat_plate(re, pr):
    """Nu = 0.664 Re^(1/2) Pr^(1/3)."""
    return 0.664 * re ** 0.5 * pr ** (1.0 / 3.0)


def convection(decl: dict, *, excursion: float, ha: float,
               surface_area: float) -> dict | None:
    """The three convection conditions, from whichever route is declared.

    The route is chosen by which declaration is present -- an expansion
    coefficient for free convection, a velocity for forced -- exactly as the
    domain does, and never by any categorical ``convection_regime`` string.
    Declaring both is mixed convection and is refused here as it is there.
    """
    k_f = decl.get("fluid_conductivity")
    nu_visc = decl.get("fluid_kinematic_viscosity")
    pr = decl.get("fluid_prandtl_number")
    length = decl.get("convection_length")
    beta = decl.get("fluid_expansion_coefficient")
    velocity = decl.get("fluid_velocity")
    if None in (k_f, nu_visc, pr, length):
        return None
    if (beta is None) == (velocity is None):
        return None                       # neither route, or both -- no verdict
    if beta is not None:
        ra = (G_STANDARD * beta * abs(excursion) * length ** 3) / (
            nu_visc * nu_visc
        ) * pr
        nu_number = churchill_chu(ra, pr)
        flow = ra / RAYLEIGH_MAX
        prop = 0.0                        # Churchill-Chu states no Pr restriction
        re = None
    else:
        re = velocity * length / nu_visc
        nu_number = flat_plate(re, pr)
        flow = re / REYNOLDS_MAX
        prop = PRANDTL_MIN / pr
        ra = None
    if nu_number <= 0:
        return None
    h_correlated = nu_number * k_f / length
    h_declared = ha / surface_area
    if h_correlated <= 0:
        return None
    return {
        "rayleigh": ra,
        "reynolds": re,
        "flow_utilization": flow,
        "property_utilization": prop,
        "agreement": h_declared / h_correlated,
    }


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

#: Which condition, when it fails, means which failure class. A model that does
#: not apply and a limit that is exceeded are different findings and the
#: labelling template keeps them apart.
CONDITION_CLASS = {
    "biot_number": "model_inapplicable",
    "internal_fourier_number": "model_inapplicable",
    "radiation_to_convection_ratio": "model_inapplicable",
    "conductance_excursion_ratio": "model_inapplicable",
    "capacity_excursion_ratio": "model_inapplicable",
    "linearization_excursion_ratio": "model_inapplicable",
    "reduced_debye_temperature": "model_inapplicable",
    "tcr_form_declared_range": "model_inapplicable",
    "geometry_route_ratio": "inconsistent_inputs",
    "convection_flow_range_utilization": "model_inapplicable",
    "convection_property_range_utilization": "model_inapplicable",
    "convection_conductance_agreement_ratio": "inconsistent_inputs",
    "operating_temperature_utilization": "limit_exceeded",
    "melting_temperature_utilization": "limit_exceeded",
    "dissipated_power_utilization": "limit_exceeded",
    "working_voltage_utilization": "limit_exceeded",
    "source_current_utilization": "limit_exceeded",
}


@dataclass
class Assessment:
    """Every condition this module could form, and what it says."""

    violated: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    satisfied: dict[str, float] = field(default_factory=dict)
    solution: Solution | None = None

    @property
    def verdict(self) -> str:
        if self.solution is None:
            return "NO_SOLUTION"
        if self.violated:
            return "NOT_SUPPORTED"
        if self.unknown:
            return "INSUFFICIENT_EVIDENCE"
        return "SUPPORTED"

    @property
    def failure_class(self) -> str | None:
        """The class of the *leading* violation.

        Applicability leads: a limit read off a model that does not apply is
        not a meaningful reading, so ``model_inapplicable`` outranks
        ``limit_exceeded`` when both are present. Same precedence the frozen
        benchmark states for its compound defects.
        """
        order = ("model_inapplicable", "inconsistent_inputs", "limit_exceeded")
        classes = {CONDITION_CLASS.get(c) for c in self.violated}
        for cls in order:
            if cls in classes:
                return cls
        return None


def assess(case: dict, *, temperature: str = "steady") -> Assessment:
    """Every condition, at one reading of "the operating temperature".

    ``temperature="steady"`` forms the conditions from ``T_amb + Q/hA`` as the
    domain does. ``temperature="final"`` forms them from the marched endpoint.
    They differ, and :func:`assess_robust` refuses to label any case where the
    difference changes the answer.
    """
    a = Assessment()
    sol = solve(
        source_voltage=case["source_voltage"],
        reference_resistance=case["reference_resistance"],
        temperature_coefficient=case["temperature_coefficient"],
        reference_temperature=case["reference_temperature"],
        ambient_conductance=case["ambient_conductance"],
        ambient_temperature=case["ambient_temperature"],
        initial_temperature=case["initial_temperature"],
        heat_capacity=case["heat_capacity"],
        duration=case["duration"],
    )
    a.solution = sol
    if sol is None:
        return a

    t_amb = case["ambient_temperature"]
    t_init = case["initial_temperature"]
    t_op = sol.t_steady if temperature == "steady" else sol.t_final
    peak = max(t_init, t_op)
    excursion = max(abs(t_init - t_amb), abs(t_op - t_amb))

    def check(name: str, value, ok: bool | None):
        if value is None or ok is None:
            a.unknown.append(name)
        elif ok:
            a.satisfied[name] = value
        else:
            a.violated.append(name)

    lc = characteristic_length(
        case.get("characteristic_length"), case.get("body_volume"),
        case.get("surface_area"),
    )
    bi = biot(case["ambient_conductance"], case.get("surface_area"), lc,
              case.get("body_conductivity"))
    check("biot_number", bi, None if bi is None else bi <= BIOT_LIMIT)

    fo = fourier(case["duration"], sol.tau, bi)
    check("internal_fourier_number", fo, None if fo is None else fo >= FOURIER_MIN)

    rs = radiation_share(case.get("surface_emissivity"), case.get("surface_area"),
                         case["ambient_conductance"], peak, t_amb)
    check("radiation_to_convection_ratio", rs,
          None if rs is None else rs <= RADIATION_SHARE_LIMIT)

    cb = case.get("conductance_excursion_bound")
    check("conductance_excursion_ratio", None if cb is None else excursion / cb,
          None if cb is None else excursion <= cb * EXCURSION_LIMIT)

    kb = case.get("capacity_excursion_bound")
    swing = abs(t_op - t_init)
    check("capacity_excursion_ratio", None if kb is None else swing / kb,
          None if kb is None else swing <= kb * EXCURSION_LIMIT)

    melt = case.get("melting_temperature")
    check("melting_temperature_utilization", None if melt is None else peak / melt,
          None if melt is None else peak <= melt * PHASE_CHANGE_LIMIT)

    band = case.get("linearization_band")
    dev = max(abs(t_op - case["reference_temperature"]),
              abs(t_amb - case["reference_temperature"]))
    check("linearization_excursion_ratio", None if band is None else dev / band,
          None if band is None else dev <= band * LINEARIZATION_LIMIT)

    tmax = case.get("maximum_operating_temperature")
    check("operating_temperature_utilization", None if tmax is None else t_op / tmax,
          None if tmax is None else t_op <= tmax * 1.0)

    debye = case.get("debye_temperature")
    coldest = min(t_amb, t_op, t_init)
    check("reduced_debye_temperature", None if debye is None else coldest / debye,
          None if debye is None else coldest / debye >= DEBYE_FLOOR)

    # The linear TCR form's own declared range. Not a material limit.
    check("tcr_form_declared_range", t_op,
          TCR_MIN_TEMPERATURE <= t_op <= TCR_MAX_TEMPERATURE)

    # Two routes to one length. Inclusive on both edges: a body whose V/A_s is
    # exactly L_c/3 is the sphere the factor was derived from.
    if (case.get("characteristic_length") is not None
            and case.get("body_volume") is not None
            and case.get("surface_area")):
        implied = case["body_volume"] / case["surface_area"]
        ratio = case["characteristic_length"] / implied if implied else None
        check("geometry_route_ratio", ratio,
              None if ratio is None
              else (1.0 / GEOMETRY_AGREEMENT_FACTOR
                    <= ratio <= GEOMETRY_AGREEMENT_FACTOR))

    derating = case.get("derating_factor") or 1.0
    rated_p = case.get("rated_power")
    check("dissipated_power_utilization",
          None if rated_p is None else sol.power / (rated_p * derating),
          None if rated_p is None else sol.power <= rated_p * derating)

    vmax = case.get("maximum_working_voltage")
    check("working_voltage_utilization",
          None if vmax is None else case["source_voltage"] / (vmax * derating),
          None if vmax is None else case["source_voltage"] <= vmax * derating)

    s_derating = case.get("source_derating_factor") or 1.0
    imax = case.get("maximum_current")
    check("source_current_utilization",
          None if imax is None else sol.current / (imax * s_derating),
          None if imax is None else sol.current <= imax * s_derating)

    conv = convection(case, excursion=excursion,
                      ha=case["ambient_conductance"],
                      surface_area=case.get("surface_area") or 0.0)
    if conv is None:
        a.unknown.extend([
            "convection_flow_range_utilization",
            "convection_property_range_utilization",
            "convection_conductance_agreement_ratio",
        ])
    else:
        check("convection_flow_range_utilization", conv["flow_utilization"],
              conv["flow_utilization"] <= 1.0)
        check("convection_property_range_utilization", conv["property_utilization"],
              conv["property_utilization"] <= 1.0)
        check("convection_conductance_agreement_ratio", conv["agreement"],
              1.0 / CONVECTION_AGREEMENT_FACTOR <= conv["agreement"]
              <= CONVECTION_AGREEMENT_FACTOR)
    return a


def assess_robust(case: dict) -> tuple[Assessment, bool]:
    """Assess under both readings of the operating temperature.

    Returns ``(assessment, stable)``. ``stable`` is False when the two readings
    disagree about the verdict or about which conditions are violated -- the
    case sits close enough to a bound that the answer depends on a choice this
    module cannot make from the physics alone. Such a case is not labelled.
    """
    a = assess(case, temperature="steady")
    b = assess(case, temperature="final")
    stable = (a.verdict == b.verdict
              and set(a.violated) == set(b.violated)
              and set(a.unknown) == set(b.unknown))
    return a, stable
