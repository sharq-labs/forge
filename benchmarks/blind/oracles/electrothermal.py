"""Independent oracle for the electro-thermal system. No Forge code is reached.

**What this is.** A second implementation, from the literature definitions, of
every quantity the electro-thermal validity conditions are stated over, plus the
fixed point those quantities are evaluated at. It is written to decide a case's
truth *before* Forge is run on it, so it may not import, call, or otherwise
consult ``engcore``. ``tests/test_blind_challenge_guards.py`` enforces that by
AST audit; the enforcement is the point, since an oracle that quietly reached
the runtime would agree with it for the wrong reason.

**What it is NOT.** It is not a copy of Forge's implementation. Every formula
below was written from the cited source, and every one is evaluated on plain
floats in SI, so the two implementations share no unit library, no quantity
type, no context assembly and no iteration driver.

**The contract this oracle implements** — what the conditions mean, which state
coordinate each is read at — was taken from the model records themselves, and
that is deliberate rather than a leak. A second implementer given a spec
implements the spec; an oracle that *guessed* which temperature
``melting_temperature_utilization`` is read at would not be testing whether
Forge computes the right number, it would be testing whether two authors
guessed alike. The contract is the shared input to both implementations. The
*arithmetic* is what is independent, and the arithmetic is where a defect
lives.

Sources, once, for the whole module:

* Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat and Mass
  Transfer*, 6th ed. (2007) — Sec. 1.2.3 (Eq. 1.9, linearized radiation),
  Sec. 5.1 (Eqs. 5.2, 5.6, 5.7, 5.10, lumped capacity and Biot),
  Sec. 5.2 (Eq. 5.12, Fourier), Sec. 5.3 (Eq. 5.25, steady state with
  generation), Sec. 6.5 (Nusselt), Sec. 7.2 (Eq. 7.30, flat plate),
  Sec. 9.2/9.6.1 (Grashof, Rayleigh).
* Churchill & Chu (1975), *Int. J. Heat Mass Transfer* 18, 1323 — the laminar
  vertical-plate equation and its Ra <= 1e9 range.
* Ashcroft & Mermin, *Solid State Physics* (1976), Ch. 26, Eq. 26.55 —
  Bloch-Grueneisen regimes behind the reduced-Debye conditions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .units import to_si

__all__ = [
    "ORACLE_ID",
    "ORACLE_VERSION",
    "STEFAN_BOLTZMANN",
    "OracleUnresolved",
    "ConditionValue",
    "ElectroThermalTruth",
    "evaluate",
]

ORACLE_ID = "blind.oracle.electrothermal.analytic"
ORACLE_VERSION = "1.0.0"

#: CODATA 2018. Written out rather than imported, so a wrong constant in either
#: implementation is a disagreement rather than a shared assumption.
STEFAN_BOLTZMANN = 5.670374419e-8  # W m^-2 K^-4
STANDARD_GRAVITY = 9.80665  # m s^-2

# Declared bounds, transcribed from the model records. `bound_id` names each one
# so a truth record can say which bound decided it, and
# `tests/test_blind_challenge_guards.py::test_oracle_bounds_match_the_model_records`
# re-reads the records and fails if any of these drifts. That test is the only
# place the oracle layer and engcore are allowed to meet, and it runs AFTER the
# freeze as a check on the freeze, never as an input to it.
BOUNDS: dict[str, tuple[float | None, float | None, bool, bool]] = {
    # name: (minimum, maximum, minimum_inclusive, maximum_inclusive)
    "source_current_utilization": (None, 1.0, True, True),
    "lumped_electrical_length": (None, 0.1, True, True),
    "resistance": (0.0, None, False, True),
    "dissipated_power_utilization": (None, 1.0, True, True),
    "working_voltage_utilization": (None, 1.0, True, True),
    "temperature": (200.0, 450.0, True, True),
    "reference_resistance": (0.0, None, False, True),
    "linearization_excursion_ratio": (None, 1.0, True, True),
    "operating_temperature_utilization": (None, 1.0, True, True),
    "reduced_debye_temperature": (1.0 / 3.0, None, True, True),
    "reference_temperature_utilization": (None, 1.0, True, True),
    "reference_reduced_debye_temperature": (0.2, None, True, True),
    "ceiling_reduced_debye_temperature": (1.0 / 3.0, None, True, True),
    "linear_resistance_ratio": (0.0, None, False, True),
    "heat_capacity": (0.0, None, False, True),
    "ambient_conductance": (0.0, None, False, True),
    "biot_number": (None, 0.1, True, True),
    "internal_fourier_number": (0.2, None, True, True),
    "conductance_excursion_ratio": (None, 1.0, True, True),
    "capacity_excursion_ratio": (None, 1.0, True, True),
    "radiation_to_convection_ratio": (None, 0.1, True, True),
    "convection_flow_range_utilization": (None, 1.0, True, True),
    "convection_property_range_utilization": (None, 1.0, True, True),
    "convection_conductance_agreement_ratio": (0.5, 2.0, True, True),
    "geometry_route_ratio": (1.0 / 3.0, 3.0, True, True),
    "melting_temperature_utilization": (None, 1.0, True, True),
}

#: Conditions whose bound SCREENS rather than certifies against: a value
#: outside is an evidence gap, not a finding. Transcribed from the model
#: records' own `conservative_screen` flag, which is the declaring record's
#: statement and not something an oracle may infer -- a bound that certifies
#: against and one that merely screens are both two numbers and a name.
#: Exactly one condition in the current tree declares it.
CONSERVATIVE_SCREENS: frozenset[str] = frozenset({"internal_fourier_number"})

#: Which model owns which condition. The truth record reports reasons per model,
#: because that is the granularity a Forge report carries and a comparison that
#: flattened them could not tell a violated resistor bound from a violated
#: material bound of the same name.
CONDITION_OWNER: dict[str, str] = {
    "source_current_utilization": "electrical.dc.ideal_voltage_source",
    "lumped_electrical_length": "electrical.dc.kcl",
    "resistance": "electrical.dc.resistor_ohm",
    "dissipated_power_utilization": "electrical.dc.resistor_ohm",
    "working_voltage_utilization": "electrical.dc.resistor_ohm",
    "linearization_excursion_ratio": "electrical.material.rated_linear_tcr_resistance",
    "operating_temperature_utilization": "electrical.material.rated_linear_tcr_resistance",
    "reduced_debye_temperature": "electrical.material.rated_linear_tcr_resistance",
    "reference_temperature_utilization": "electrical.material.rated_linear_tcr_resistance",
    "reference_reduced_debye_temperature": "electrical.material.rated_linear_tcr_resistance",
    "ceiling_reduced_debye_temperature": "electrical.material.rated_linear_tcr_resistance",
    "linear_resistance_ratio": "electrical.material.rated_linear_tcr_resistance",
    "heat_capacity": "thermal.lumped.first_order_capacity",
    "ambient_conductance": "thermal.lumped.first_order_capacity",
    "biot_number": "thermal.lumped.first_order_capacity",
    "internal_fourier_number": "thermal.lumped.first_order_capacity",
    "conductance_excursion_ratio": "thermal.lumped.first_order_capacity",
    "capacity_excursion_ratio": "thermal.lumped.first_order_capacity",
    "radiation_to_convection_ratio": "thermal.lumped.first_order_capacity",
    "convection_flow_range_utilization": "thermal.lumped.first_order_capacity",
    "convection_property_range_utilization": "thermal.lumped.first_order_capacity",
    "convection_conductance_agreement_ratio": "thermal.lumped.first_order_capacity",
    "geometry_route_ratio": "thermal.lumped.first_order_capacity",
    "melting_temperature_utilization": "thermal.lumped.first_order_capacity",
    # `temperature` and `reference_resistance` are declared by BOTH material
    # models, so they are resolved per-model at assembly rather than here.
}

#: Which domain a condition belongs to, for the per-domain scorecard. The
#: electro-thermal boundary exercises four domains at once, so a case is
#: attributed by the domain of the condition that DECIDES it — see
#: `ElectroThermalTruth.primary_domain`.
CONDITION_DOMAIN: dict[str, str] = {
    "source_current_utilization": "electrical",
    "lumped_electrical_length": "electrical",
    "resistance": "electrical",
    "dissipated_power_utilization": "electrical",
    "working_voltage_utilization": "electrical",
    "temperature": "materials",
    "reference_resistance": "materials",
    "linearization_excursion_ratio": "materials",
    "operating_temperature_utilization": "materials",
    "reduced_debye_temperature": "materials",
    "reference_temperature_utilization": "materials",
    "reference_reduced_debye_temperature": "materials",
    "ceiling_reduced_debye_temperature": "materials",
    "linear_resistance_ratio": "materials",
    "heat_capacity": "thermal",
    "ambient_conductance": "thermal",
    "conductance_excursion_ratio": "thermal",
    "capacity_excursion_ratio": "thermal",
    "radiation_to_convection_ratio": "thermal",
    "convection_flow_range_utilization": "thermal",
    "convection_property_range_utilization": "thermal",
    "convection_conductance_agreement_ratio": "thermal",
    "melting_temperature_utilization": "thermal",
    # The two lumped-criterion screens are conduction claims: each asks whether
    # an internal temperature FIELD may be replaced by one number.
    "biot_number": "conduction",
    "internal_fourier_number": "conduction",
    "geometry_route_ratio": "conduction",
}


class OracleUnresolved(Exception):
    """The oracle declines to state a truth for this candidate.

    Raised only for the documented pre-freeze rejection reasons: a sampled
    state that is not physical, a fixed point that does not converge, or an
    input the oracle's own contract does not cover. It is never raised because
    a case looks hard.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class ConditionValue:
    """One condition, its computed value, and where it sits against its bound."""

    name: str
    model_id: str
    value: float | None          # None => not derivable => UNKNOWN
    status: str                  # "satisfied" | "violated" | "unknown"
    margin: float | None         # signed distance to the nearest active bound
    relative_position: float | None   # value / bound, for stratification
    unknown_reason: str | None = None


@dataclass(frozen=True)
class CheckValue:
    """One validation check: a claim about the DECLARATION, not about a model.

    Kept in its own channel because it reaches the verdict by its own route --
    a FAIL is NOT_SUPPORTED just as a violated condition is -- and because a
    comparison that folded it into the condition set could not tell a
    self-contradictory declaration from a design that exceeded a bound. They
    recommend different repairs.
    """

    name: str
    outcome: str            # "pass" | "fail"
    detail: str = ""


@dataclass(frozen=True)
class ElectroThermalTruth:
    verdict: str
    conditions: tuple[ConditionValue, ...]
    stage_states: tuple[dict, ...]
    checks: tuple[CheckValue, ...] = ()
    converged: bool = True
    iterations: int = 0
    current_a: float = 0.0
    notes: tuple[str, ...] = field(default=())

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.checks if c.outcome == "fail")

    @property
    def satisfied(self) -> tuple[str, ...]:
        return tuple(f"{c.model_id}::{c.name}" for c in self.conditions
                     if c.status == "satisfied")

    @property
    def violated(self) -> tuple[str, ...]:
        return tuple(f"{c.model_id}::{c.name}" for c in self.conditions
                     if c.status == "violated")

    @property
    def unknown(self) -> tuple[str, ...]:
        return tuple(f"{c.model_id}::{c.name}" for c in self.conditions
                     if c.status == "unknown")

    @property
    def primary_domain(self) -> str:
        """The domain of the condition that decides the verdict.

        A violated condition decides; among several, the one whose bound is
        exceeded by the largest relative margin, which is a deterministic rule
        rather than a judgement. With no violation, an unknown decides. With
        neither, the case is SUPPORTED and is attributed to `thermal` only if
        nothing else applies — see `_deciding` for the tie-break, which is
        frozen with the challenge.
        """
        deciding = _deciding(self.conditions)
        if deciding is None:
            return "none"
        return CONDITION_DOMAIN.get(deciding.name, "unknown")


def _deciding(conditions: tuple[ConditionValue, ...]) -> ConditionValue | None:
    """The single condition that carries the verdict, by a frozen rule.

    Violations outrank unknowns, exactly as ``derive_verdict`` orders them.
    Within a class, the largest relative excess wins; ties break on the
    condition name so the answer never depends on evaluation order.
    """
    violated = [c for c in conditions if c.status == "violated"]
    if violated:
        return max(violated, key=lambda c: (abs(c.relative_position or 0.0), c.name))
    unknown = [c for c in conditions if c.status == "unknown"]
    if unknown:
        return min(unknown, key=lambda c: c.name)
    return None


def _classify(name: str, value: float | None, *, model_id: str,
              unknown_reason: str | None = None) -> ConditionValue:
    """Place one computed value against its declared bound.

    Endpoints are inclusive/exclusive exactly as the record declares them, and
    the comparison is exact: no tolerance is applied here. A case that needs to
    sit *at* a boundary is placed there by the generator and is tagged
    AT_BOUNDARY, and the whole point of that tag is that its truth is decided
    by an exact comparison both implementations must agree on.
    """
    if value is None:
        return ConditionValue(name, model_id, None, "unknown", None, None,
                              unknown_reason or "not_supplied")
    if not math.isfinite(value):
        return ConditionValue(name, model_id, value, "violated", None, None)
    minimum, maximum, min_incl, max_incl = BOUNDS[name]
    ok = True
    margin: float | None = None
    position: float | None = None
    if minimum is not None:
        ok = ok and (value >= minimum if min_incl else value > minimum)
        margin = value - minimum
        position = value / minimum if minimum != 0.0 else value
    if maximum is not None:
        ok = ok and (value <= maximum if max_incl else value < maximum)
        upper_margin = maximum - value
        margin = upper_margin if margin is None else min(margin, upper_margin)
        upper_position = value / maximum if maximum != 0.0 else value
        position = upper_position if position is None else max(position, upper_position)
    if not ok and name in CONSERVATIVE_SCREENS:
        # Outside a screen the value was read and the bound declined to
        # certify it. That is a gap, not a finding, and it may never become a
        # claim: the condition still costs the domain its clean status.
        return ConditionValue(name, model_id, value, "unknown", margin,
                              position, "conservative_screen")
    return ConditionValue(name, model_id, value,
                          "satisfied" if ok else "violated", margin, position)


# ---------------------------------------------------------------------------
# The physics. Everything below is written from the sources named in the module
# docstring and evaluated on floats in SI.
# ---------------------------------------------------------------------------


def _resistance(r_ref: float, alpha: float, t_ref: float, t: float) -> float:
    """R(T) = R_ref [1 + alpha (T - T_ref)] — the linear TCR form itself."""
    return r_ref * (1.0 + alpha * (t - t_ref))


def _solve_fixed_point(stages: list[dict], source_v: float, seed_t: float,
                       tolerance: float, max_iterations: int
                       ) -> tuple[list[float], float, bool, int]:
    """Series circuit of self-heating resistors, marched to its fixed point.

    The loop is ``T -> R(T) -> I -> P -> T(duration)`` repeated until the
    largest body temperature moves by less than ``tolerance``.

    **The coupled state is the temperature at the END of the interval, not the
    asymptote**, and the distinction is not cosmetic. The lumped balance
    integrates exactly to

        T(t) = T_ss + (T_0 - T_ss) exp(-t / tau),    T_ss = T_amb + Q / hA

    (Incropera 6th ed., Sec. 5.3, Eq. 5.25), and a run with a short horizon
    stops well short of ``T_ss``. It is ``T(duration)`` that the resistance is
    evaluated at and that the material conditions are asked about, because that
    is the state the run actually reached.

    The *applicability* groups are a different question and use the asymptote
    on purpose -- they ask how far the body could travel under this operating
    point, and a horizon shorter than the answer does not make a
    constant-property assumption safer, it only defers the excursion. Both
    temperatures are therefore computed, and each condition is asked at the one
    its own contract names.

    An earlier form of this oracle used the asymptote for both. It disagreed
    with the runtime on 83 of the 2000 calibration cases, every one of them a
    case whose horizon was short, and the runtime was right. The bug is
    recorded here rather than silently corrected because it is the exact
    mistake this two-temperature structure exists to prevent.

    Divergence is a real outcome, not an error: with a large enough positive
    ``alpha`` the loop gain exceeds one and the design runs away. That is a
    finding about the design, and it is returned as ``converged=False`` for the
    caller to classify rather than raised.
    """
    temperatures = [seed_t for _ in stages]
    current = 0.0
    for iteration in range(1, max_iterations + 1):
        resistances = [
            _resistance(s["r_ref"], s["alpha"], s["t_ref"], t)
            for s, t in zip(stages, temperatures)
        ]
        if any(r <= 0.0 or not math.isfinite(r) for r in resistances):
            # A LINEAR TCR FORM CROSSES ZERO. Past the crossing the expression
            # does not describe a worse conductor, it describes a negative one.
            # That is a finding about the design -- the model has left its own
            # domain -- and it is returned as a state to be assessed rather
            # than as an oracle failure, because `linear_resistance_ratio` is
            # precisely the condition that exists to catch it.
            return temperatures, current, False, iteration
        total = sum(resistances)
        if total <= 0.0 or not math.isfinite(total):
            return temperatures, float("nan"), False, iteration
        current = source_v / total
        updated = []
        for stage, resistance in zip(stages, resistances):
            power = current * current * resistance
            asymptote = stage["t_amb"] + power / stage["g"]
            tau = stage["capacity"] / stage["g"]
            decay = math.exp(-stage["duration"] / tau)
            updated.append(asymptote + (stage["t_0"] - asymptote) * decay)
        movement = max(abs(a - b) for a, b in zip(updated, temperatures))
        temperatures = updated
        if not all(math.isfinite(t) for t in temperatures):
            return temperatures, current, False, iteration
        if movement <= tolerance:
            return temperatures, current, True, iteration
    return temperatures, current, False, max_iterations


def _churchill_chu(rayleigh: float, prandtl: float) -> float:
    """Nu_L = 0.68 + 0.670 Ra^(1/4) / [1 + (0.492/Pr)^(9/16)]^(4/9)."""
    denominator = (1.0 + (0.492 / prandtl) ** (9.0 / 16.0)) ** (4.0 / 9.0)
    return 0.68 + 0.670 * rayleigh**0.25 / denominator


def _flat_plate(reynolds: float, prandtl: float) -> float:
    """Nu_L = 0.664 Re^(1/2) Pr^(1/3), laminar parallel flow over a plate."""
    return 0.664 * math.sqrt(reynolds) * prandtl ** (1.0 / 3.0)


def _get(section: dict, key: str, dimension: str) -> float | None:
    """A declared quantity, or ``None`` when it was not declared.

    ``None`` is never a zero and never a typical value: a condition that needs
    an absent input is UNKNOWN, which is the whole reason the missing-evidence
    cases in this challenge can have a truth at all.
    """
    raw = section.get(key)
    if raw is None:
        return None
    return to_si(raw, dimension)


def evaluate(payload: dict) -> ElectroThermalTruth:
    """Independent truth for one electro-thermal case.

    Returns every condition with its value and its position against its bound,
    plus the verdict those conditions imply under the documented precedence:
    any violation is NOT_SUPPORTED, else any unknown is INSUFFICIENT_EVIDENCE,
    else SUPPORTED.
    """
    source_v = to_si(payload["source_voltage"], "V")
    coupling = payload.get("coupling", {})
    seed_t = to_si(coupling.get("seed_temperature", "300 kelvin"), "K")
    tolerance = to_si(coupling.get("tolerance", "1e-06 kelvin"), "K")
    max_iterations = int(coupling.get("max_iterations", 200))

    raw_stages = payload["stages"]
    stages: list[dict] = []
    for entry in raw_stages:
        conductor = entry["conductor"]
        body = entry["body"]
        applicability = body.get("applicability", {})
        stages.append({
            "component_id": entry["component_id"],
            "r_ref": to_si(conductor["reference_resistance"], "ohm"),
            "alpha": to_si(conductor["temperature_coefficient"], "1/K"),
            "t_ref": to_si(conductor["reference_temperature"], "K"),
            "limits": conductor.get("limits", {}),
            "ratings": conductor.get("ratings", {}),
            "g": to_si(body["ambient_conductance"], "W/K"),
            "capacity": to_si(body["heat_capacity"], "J/K"),
            "t_amb": to_si(body["ambient_temperature"], "K"),
            "t_0": to_si(body["initial_temperature"], "K"),
            "duration": to_si(body["duration"], "s"),
            "app": applicability,
        })

    for stage in stages:
        if stage["g"] <= 0.0:
            raise OracleUnresolved(
                "invalid_sampled_state",
                f"{stage['component_id']} declares a non-positive ambient "
                f"conductance; the steady state is not defined")
        if stage["capacity"] <= 0.0:
            raise OracleUnresolved(
                "invalid_sampled_state",
                f"{stage['component_id']} declares a non-positive heat capacity")

    temperatures, current, converged, iterations = _solve_fixed_point(
        stages, source_v, seed_t, tolerance, max_iterations)

    conditions: list[ConditionValue] = []
    checks: list[CheckValue] = []
    add = conditions.append

    if not converged:
        # Two different things reach here and they are not the same finding.
        #
        # A loop that ran away until a resistance crossed zero HAS a decidable
        # truth: the linear form left its own domain, `linear_resistance_ratio`
        # is violated, and the verdict is NOT_SUPPORTED. Refusing that case
        # would throw away one of the sharpest tests in the corpus.
        #
        # A loop that merely failed to settle within its budget has no
        # operating point, so no condition about an operating point can be
        # stated, and the oracle declines rather than inventing a state. The
        # generator counts every such refusal before the freeze.
        crossed = [
            stage["component_id"] for stage, temperature in zip(stages, temperatures)
            if _resistance(stage["r_ref"], stage["alpha"], stage["t_ref"],
                           temperature) <= 0.0
        ]
        if not crossed:
            raise OracleUnresolved(
                "oracle_non_convergence",
                f"the electro-thermal fixed point did not settle within "
                f"{max_iterations} iterations (last current {current!r} A)")
        ratios = tuple(
            1.0 + stage["alpha"] * (temperature - stage["t_ref"])
            for stage, temperature in zip(stages, temperatures)
        )
        runaway = tuple(
            _classify("linear_resistance_ratio", ratio,
                      model_id="electrical.material.rated_linear_tcr_resistance")
            for ratio in ratios
        )
        return ElectroThermalTruth(
            verdict="NOT_SUPPORTED", conditions=runaway, stage_states=(),
            converged=False, iterations=iterations, current_a=current,
            notes=(f"thermal runaway: resistance crossed zero on "
                   f"{', '.join(crossed)}",))

    total_r = sum(_resistance(s["r_ref"], s["alpha"], s["t_ref"], t)
                  for s, t in zip(stages, temperatures))

    # ---- source ---------------------------------------------------------
    source_ratings = payload.get("source_ratings", {})
    i_max = _get(source_ratings, "maximum_current", "A")
    add(_classify("source_current_utilization",
                  None if i_max is None else current / i_max,
                  model_id="electrical.dc.ideal_voltage_source"))
    # DC carries no frequency, so the electrical length of the network is zero
    # and this condition is satisfied by construction. Stated rather than
    # skipped: a condition that is always satisfied still has to appear in the
    # reason set, or a comparison would score its absence as a missing reason.
    add(_classify("lumped_electrical_length", 0.0,
                  model_id="electrical.dc.kcl"))

    stage_states: list[dict] = []
    for stage, temperature in zip(stages, temperatures):
        resistance = _resistance(stage["r_ref"], stage["alpha"], stage["t_ref"],
                                 temperature)
        power = current * current * resistance
        drop = current * resistance
        # ---- resistor ---------------------------------------------------
        add(_classify("resistance", resistance,
                      model_id="electrical.dc.resistor_ohm"))
        rated_power = _get(stage["ratings"], "rated_power", "W")
        add(_classify("dissipated_power_utilization",
                      None if rated_power is None else power / rated_power,
                      model_id="electrical.dc.resistor_ohm"))
        v_max = _get(stage["ratings"], "maximum_working_voltage", "V")
        add(_classify("working_voltage_utilization",
                      None if v_max is None else drop / v_max,
                      model_id="electrical.dc.resistor_ohm"))

        # ---- material, unrated and rated --------------------------------
        # Read at the state the run reached, except the two conditions the
        # contract reads elsewhere: the Debye floor at the coldest instant and
        # the linearization band at the furthest excursion from the reference.
        coldest = min(stage["t_0"], temperature)
        furthest = max((stage["t_0"], temperature),
                       key=lambda value: abs(value - stage["t_ref"]))
        for model_id in ("electrical.material.linear_tcr_resistance",
                         "electrical.material.rated_linear_tcr_resistance"):
            add(_classify("temperature", temperature, model_id=model_id))
            add(_classify("reference_resistance", stage["r_ref"],
                          model_id=model_id))
        rated = "electrical.material.rated_linear_tcr_resistance"
        limits = stage["limits"]
        band = _get(limits, "linearization_band", "K")
        add(_classify("linearization_excursion_ratio",
                      None if band is None else abs(furthest - stage["t_ref"]) / band,
                      model_id=rated))
        t_max = _get(limits, "maximum_operating_temperature", "K")
        add(_classify("operating_temperature_utilization",
                      None if t_max is None else temperature / t_max,
                      model_id=rated))
        theta_d = _get(limits, "debye_temperature", "K")
        add(_classify("reduced_debye_temperature",
                      None if theta_d is None else coldest / theta_d,
                      model_id=rated))
        add(_classify("reference_temperature_utilization",
                      None if t_max is None else stage["t_ref"] / t_max,
                      model_id=rated))
        add(_classify("reference_reduced_debye_temperature",
                      None if theta_d is None else stage["t_ref"] / theta_d,
                      model_id=rated))
        add(_classify("ceiling_reduced_debye_temperature",
                      None if (t_max is None or theta_d is None)
                      else t_max / theta_d, model_id=rated))
        add(_classify("linear_resistance_ratio",
                      1.0 + stage["alpha"] * (temperature - stage["t_ref"]),
                      model_id=rated))

        # ---- thermal ----------------------------------------------------
        thermal = "thermal.lumped.first_order_capacity"
        app = stage["app"]
        add(_classify("heat_capacity", stage["capacity"], model_id=thermal))
        add(_classify("ambient_conductance", stage["g"], model_id=thermal))

        area = _get(app, "surface_area", "m2")
        volume = _get(app, "body_volume", "m3")
        declared_length = _get(app, "characteristic_length", "m")
        conductivity = _get(app, "body_conductivity", "W/m/K")
        # L_c = V/A_s unless the caller declares one; h = (hA)/A_s.
        length = declared_length if declared_length is not None else (
            None if (volume is None or area is None or area <= 0.0)
            else volume / area)
        coefficient = None if (area is None or area <= 0.0) else stage["g"] / area
        add(_classify("biot_number",
                      None if (coefficient is None or length is None
                               or conductivity is None or conductivity <= 0.0)
                      else coefficient * length / conductivity,
                      model_id=thermal))

        # Fo = (t/tau)/Bi, with tau = C/(hA). Formed through the identity so it
        # needs no separate diffusivity, exactly as the contract states.
        tau = stage["capacity"] / stage["g"]
        horizon = stage["duration"] / tau
        biot_value = next(c.value for c in reversed(conditions)
                          if c.name == "biot_number")
        add(_classify("internal_fourier_number",
                      None if (biot_value is None or biot_value <= 0.0)
                      else horizon / biot_value, model_id=thermal))

        steady = stage["t_amb"] + power / stage["g"]
        peak = max(stage["t_0"], steady)
        excursion = max(abs(stage["t_0"] - stage["t_amb"]),
                        abs(steady - stage["t_amb"]))
        g_bound = _get(app, "conductance_excursion_bound", "K")
        add(_classify("conductance_excursion_ratio",
                      None if (g_bound is None or g_bound <= 0.0)
                      else excursion / g_bound, model_id=thermal))
        c_bound = _get(app, "capacity_excursion_bound", "K")
        add(_classify("capacity_excursion_ratio",
                      None if (c_bound is None or c_bound <= 0.0)
                      else abs(steady - stage["t_0"]) / c_bound,
                      model_id=thermal))

        emissivity = _get(app, "surface_emissivity", "1")
        h_r = (None if emissivity is None else
               STEFAN_BOLTZMANN * emissivity * (peak + stage["t_amb"])
               * (peak * peak + stage["t_amb"] * stage["t_amb"]))
        add(_classify("radiation_to_convection_ratio",
                      None if (h_r is None or coefficient is None
                               or coefficient <= 0.0) else h_r / coefficient,
                      model_id=thermal))

        # Two routes to L_c; 1.0 when only one exists, which contradicts
        # nothing and is a true statement rather than a default.
        implied = (None if (volume is None or area is None or area <= 0.0)
                   else volume / area)
        if declared_length is None and implied is None:
            route_ratio = None
        elif declared_length is None or implied is None:
            route_ratio = 1.0
        else:
            route_ratio = declared_length / implied
        add(_classify("geometry_route_ratio", route_ratio, model_id=thermal))

        t_melt = _get(app, "melting_temperature", "K")
        add(_classify("melting_temperature_utilization",
                      None if (t_melt is None or t_melt <= 0.0)
                      else peak / t_melt, model_id=thermal))

        # ---- convection correlation -------------------------------------
        # The route is resolved on what was DECLARED, never on the regime
        # string: an expansion coefficient selects natural, a velocity selects
        # forced. A caller cannot assert their way past this.
        conv_length = _get(app, "convection_length", "m")
        viscosity = _get(app, "fluid_kinematic_viscosity", "m2/s")
        prandtl = _get(app, "fluid_prandtl_number", "1")
        beta = _get(app, "fluid_expansion_coefficient", "1/K")
        velocity = _get(app, "fluid_velocity", "m/s")
        fluid_k = _get(app, "fluid_conductivity", "W/m/K")

        rayleigh = None
        if (beta is not None and conv_length is not None
                and viscosity is not None and viscosity > 0.0
                and prandtl is not None):
            rayleigh = (STANDARD_GRAVITY * beta * excursion * conv_length**3
                        * prandtl / (viscosity * viscosity))
        reynolds = None
        if (velocity is not None and conv_length is not None
                and viscosity is not None and viscosity > 0.0):
            reynolds = velocity * conv_length / viscosity

        if rayleigh is not None:
            flow_range = rayleigh / 1.0e9
        elif reynolds is not None:
            flow_range = reynolds / 5.0e5
        else:
            flow_range = None
        add(_classify("convection_flow_range_utilization", flow_range,
                      model_id=thermal))

        if rayleigh is not None:
            # Churchill-Chu covers every Prandtl number by construction, so the
            # property range it leaves is empty and the utilization is zero.
            property_range = None if prandtl is None else 0.0
        elif reynolds is not None:
            property_range = (None if (prandtl is None or prandtl <= 0.0)
                              else 0.6 / prandtl)
        else:
            property_range = None
        add(_classify("convection_property_range_utilization", property_range,
                      model_id=thermal))

        nusselt = None
        if rayleigh is not None and prandtl is not None and rayleigh > 0.0:
            nusselt = _churchill_chu(rayleigh, prandtl)
        elif reynolds is not None and prandtl is not None and reynolds > 0.0:
            nusselt = _flat_plate(reynolds, prandtl)
        correlated = (None if (nusselt is None or fluid_k is None
                               or conv_length is None or conv_length <= 0.0)
                      else nusselt * fluid_k / conv_length)
        add(_classify("convection_conductance_agreement_ratio",
                      None if (correlated is None or correlated <= 0.0
                               or coefficient is None)
                      else coefficient / correlated, model_id=thermal))

        # ---- declared-limit consistency ---------------------------------
        # A part rated to operate at or above its own melting point is two
        # statements about one body that cannot both hold. Neither domain owns
        # this: the ceiling is a material limit and the melting point a
        # thermal one, and it is the caller who wrote both about one part.
        # Absent either limit there is nothing to compare and no check is
        # emitted -- an undeclared limit is never read as agreement.
        if t_max is not None and t_melt is not None:
            checks.append(CheckValue(
                "declared_limits_are_mutually_consistent",
                "pass" if t_melt > t_max else "fail",
                f"melting {t_melt:.6g} K vs ceiling {t_max:.6g} K "
                f"({stage['component_id']})"))

        stage_states.append({
            "component_id": stage["component_id"],
            "temperature_k": temperature,
            "resistance_ohm": resistance,
            "power_w": power,
            "voltage_drop_v": drop,
            "steady_k": steady,
            "peak_k": peak,
            "rayleigh": rayleigh,
            "reynolds": reynolds,
        })

    frozen = tuple(conditions)
    frozen_checks = tuple(checks)
    # The documented precedence, and the order matters: a finding outranks a
    # gap, because the two recommend opposite actions. A failed check is a
    # finding by the same argument -- gathering a missing declaration cannot
    # rescue a declaration that contradicts itself.
    if (any(c.status == "violated" for c in frozen)
            or any(c.outcome == "fail" for c in frozen_checks)):
        verdict = "NOT_SUPPORTED"
    elif any(c.status == "unknown" for c in frozen):
        verdict = "INSUFFICIENT_EVIDENCE"
    else:
        verdict = "SUPPORTED"
    return ElectroThermalTruth(
        verdict=verdict, conditions=frozen, stage_states=tuple(stage_states),
        checks=frozen_checks, converged=converged, iterations=iterations,
        current_a=current,
        notes=(f"series total resistance {total_r:.6g} ohm",))


# ---------------------------------------------------------------------------
# SECOND ORACLE. A different algorithm for the same coupled state.
# ---------------------------------------------------------------------------

SECOND_ORACLE_ID = "blind.oracle.electrothermal.rk4"


def march_stage_temperature(stage: dict, current: float, *, steps: int = 4000,
                            frozen_resistance: float | None = None) -> float:
    """Integrate ``C dT/dt = Q - hA (T - T_amb)`` with RK4.

    **Two different questions, and only one of them is an oracle.**

    With ``frozen_resistance`` given, this marches the SAME balance the closed
    form solves — heat held at ``I^2 R`` for the interval, exactly as the
    declared lumped model states it. That is a pure integration check: a
    different algorithm against the same equation, and the two must agree to
    round-off. This is the comparison that can convict an implementation.

    With it omitted, ``R(T)`` is re-evaluated at every stage of every step, so
    this marches the NONLINEAR balance instead. The gap to the closed form is
    then not an error in either — it is the linearisation error of the
    declared model itself, which is small exactly when the self-heating
    excursion is small compared with ``1/alpha``.

    Keeping these apart matters, and an earlier draft did not. Using the
    nonlinear march as the arbiter promoted 33 perfectly decidable cases to
    UNRESOLVED because two DIFFERENT MODELS disagreed by up to 1 %, which is a
    fact about the lumped approximation and not a reason to doubt anyone's
    arithmetic. The nonlinear gap is now reported as a model-fidelity note and
    decides nothing.

    ``current`` is held at the converged loop value, because this oracle is
    about the thermal integration and not about the circuit.
    """
    r_ref, alpha, t_ref = stage["r_ref"], stage["alpha"], stage["t_ref"]
    capacity, conductance = stage["capacity"], stage["g"]
    ambient, horizon = stage["t_amb"], stage["duration"]

    def derivative(temperature: float) -> float:
        resistance = (frozen_resistance if frozen_resistance is not None
                      else r_ref * (1.0 + alpha * (temperature - t_ref)))
        return (current * current * resistance
                - conductance * (temperature - ambient)) / capacity

    step = horizon / steps
    temperature = stage["t_0"]
    for _ in range(steps):
        k1 = derivative(temperature)
        k2 = derivative(temperature + 0.5 * step * k1)
        k3 = derivative(temperature + 0.5 * step * k2)
        k4 = derivative(temperature + step * k3)
        temperature += (step / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        if not math.isfinite(temperature):
            return float("nan")
    return temperature


def second_oracle(payload: dict, truth: "ElectroThermalTruth") -> dict:
    """Re-derive every stage temperature by RK4 and report the disagreement.

    Returns the per-stage relative gap and the worst of them. The caller
    decides what to do with it; this function never edits a truth.
    """
    if not truth.converged or not truth.stage_states:
        return {"status": "not_applicable",
                "why": "no converged operating point to re-derive"}
    stages = []
    for entry, state in zip(payload["stages"], truth.stage_states):
        conductor, body = entry["conductor"], entry["body"]
        stages.append({
            "r_ref": to_si(conductor["reference_resistance"], "ohm"),
            "alpha": to_si(conductor["temperature_coefficient"], "1/K"),
            "t_ref": to_si(conductor["reference_temperature"], "K"),
            "capacity": to_si(body["heat_capacity"], "J/K"),
            "g": to_si(body["ambient_conductance"], "W/K"),
            "t_amb": to_si(body["ambient_temperature"], "K"),
            "t_0": to_si(body["initial_temperature"], "K"),
            "duration": to_si(body["duration"], "s"),
        })
    gaps, nonlinear = [], []
    for stage, state in zip(stages, truth.stage_states):
        closed = state["temperature_k"]
        if closed == 0.0:
            gaps.append(float("inf"))
            continue
        marched = march_stage_temperature(
            stage, truth.current_a,
            frozen_resistance=state["resistance_ohm"])
        gaps.append(float("inf") if not math.isfinite(marched)
                    else abs(marched - closed) / abs(closed))
        free = march_stage_temperature(stage, truth.current_a)
        nonlinear.append(None if not math.isfinite(free)
                         else abs(free - closed) / abs(closed))
    return {
        "status": "compared",
        "oracle_a": ORACLE_ID,
        "oracle_b": SECOND_ORACLE_ID,
        "quantity": "stage final temperature",
        "per_stage_relative_gap": gaps,
        "worst_relative_gap": max(gaps) if gaps else 0.0,
        # Reported, never arbitrated on. See `march_stage_temperature`.
        "nonlinear_model_gap": nonlinear,
        "worst_nonlinear_model_gap": (max(g for g in nonlinear if g is not None)
                                      if any(g is not None for g in nonlinear)
                                      else None),
    }
