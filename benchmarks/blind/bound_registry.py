"""What KIND of statement each bound is. Transcribed, not imported.

Every threshold the blind challenge can place a case against, and the class of
claim that threshold makes. The classification is taken from
``docs/assurance/SCIENTIFIC_BOUND_REGISTER.md`` — the repository's own audit of
its 64 conditions — and is written out here as data rather than imported,
because this module is part of the truth layer and the truth layer may not
reach into ``engcore``.

**Why a truth record needs this at all.** A challenge that reported one
accuracy figure over every case would be averaging two different kinds of
statement. ``biot_number <= 0.1`` is an approximation criterion with a citation;
``radiation_to_convection_ratio <= 0.1`` is a 10 %-neglect allowance with no
located source. Agreement on the second says the runtime implements a
convention correctly, and says nothing whatever about physics. Reporting them
apart is the difference between measuring science and measuring compliance.

The classes
-----------

``DEFINITIONAL``
    A utilisation or margin bounded at 0 or 1. ``u = value / limit_the_caller_
    declared``, so ``u <= 1`` *is* "at or under the declared limit". The number
    needs no source; the scientific content is in the caller's declaration,
    which Forge does not supply and does not vouch for.

``POSITIVITY``
    ``x > 0`` / ``x >= 0``: the physical domain of the quantity.

``SOURCED_SCIENTIFIC``
    A substantive threshold with a primary citation or an analytic derivation.

``INTERNAL_POLICY``
    A substantive threshold that is a declared convention. The truth is what
    the declaration says, and the declaration is a policy. **Never reported as
    a scientific result.**

``SOFT`` marks the thresholds the register records as approximation criteria
rather than transitions — nothing changes in the world at the number. A case
placed near a soft bound is tagged ``SOFT_BOUND_NEAR`` rather than being given
an exact-boundary truth it cannot support.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "BOUND_REGISTRY_VERSION",
    "Bound",
    "BOUNDS",
    "bound_for",
    "class_of",
    "is_policy",
    "is_soft",
]

BOUND_REGISTRY_VERSION = "blind-bound-registry/1.0.0"

DEFINITIONAL = "DEFINITIONAL"
POSITIVITY = "POSITIVITY"
SOURCED_SCIENTIFIC = "SOURCED_SCIENTIFIC"
INTERNAL_POLICY = "INTERNAL_POLICY"


@dataclass(frozen=True)
class Bound:
    bound_id: str
    condition: str
    domain: str
    bound_class: str
    soft: bool
    source: str


_BOUNDS: tuple[Bound, ...] = (
    # ---- the eleven substantive thresholds, register section 2 ----------
    Bound("B-BIOT", "biot_number", "conduction", SOURCED_SCIENTIFIC, True,
          "Incropera, DeWitt, Bergman & Lavine 6th ed. (2007) sec. 5.1 — "
          "lumped-capacitance approximation criterion Bi <= 0.1."),
    Bound("B-FOURIER", "internal_fourier_number", "conduction",
          SOURCED_SCIENTIFIC, True,
          "Incropera 6th ed. sec. 5.5 — one-term series validity Fo >= 0.2."),
    Bound("B-GEOM", "geometry_route_ratio", "conduction", SOURCED_SCIENTIFIC,
          False,
          "Analytically derived: the two standard characteristic-length "
          "conventions (conduction path vs V/A_s) span exactly 1 to 3 across "
          "plane wall, long cylinder and sphere; the sphere sets the bound."),
    Bound("B-CONV-AGREE", "convection_conductance_agreement_ratio", "thermal",
          SOURCED_SCIENTIFIC, True,
          "Incropera sec. 9.6.3 — the two horizontal-plate orientations give "
          "0.54 vs 0.27 Ra^(1/4), a factor of two. A scope bound."),
    Bound("B-RAD", "radiation_to_convection_ratio", "thermal", INTERNAL_POLICY,
          True,
          "NO SOURCE LOCATED. h_r/h <= 0.1 is a 10 %-neglect allowance. The "
          "quantity is verified (ORA-RAD-LINEARIZATION); the threshold is not."),
    Bound("B-DEBYE", "reduced_debye_temperature", "materials", INTERNAL_POLICY,
          True,
          "The Bloch-Grueneisen linear regime is standard; the FRACTION is "
          "not — the literature quotes theta_D/2, /3 and /5."),
    Bound("B-DEBYE-CEIL", "ceiling_reduced_debye_temperature", "materials",
          INTERNAL_POLICY, True,
          "The same 1/3 fraction as B-DEBYE, applied at the declared ceiling."),
    Bound("B-DEBYE-REF", "reference_reduced_debye_temperature", "materials",
          SOURCED_SCIENTIFIC, True,
          "Kittel 8th ed. Ch. 5 Tab. 1 — beryllium theta_D = 1440 K refuses a "
          "1/3 floor at a conventional 293.15 K reference, so 1/5 is "
          "empirically characterised against one material."),
    Bound("B-POL", "polarization_unmodelled_fraction", "battery",
          INTERNAL_POLICY, True,
          "NO SOURCE LOCATED. A 5 % neglect allowance."),
    Bound("B-ETA", "coulombic_efficiency", "battery", SOURCED_SCIENTIFIC,
          False,
          "Charge conservation: a cell cannot return more charge than it "
          "accepted. Hard bound."),
    Bound("B-TCR-RANGE", "temperature", "materials", INTERNAL_POLICY, False,
          "[200, 450] K — repository scope for the linear TCR form."),
    Bound("B-ELEC-LEN", "lumped_electrical_length", "electrical",
          SOURCED_SCIENTIFIC, True,
          "The electrically-small criterion L < lambda/10. LATENT: a DC model "
          "has f = 0, so the ratio is exactly zero and the bound never binds."),

    # ---- kinetics: the same scope bound under a different model ---------
    Bound("B-CSTR-RANGE", "cstr:temperature", "kinetics", INTERNAL_POLICY,
          False, "[250, 1000] K — repository scope for the CSTR."),
    Bound("B-CSTR-CEIL", "adiabatic_ceiling_temperature", "kinetics",
          INTERNAL_POLICY, False,
          "The same [250, 1000] K scope ceiling, evaluated at the hottest "
          "state the declaration permits. The DERIVATION of the ceiling is "
          "analytic (the Z = T + beta C invariant); the 1000 K it is compared "
          "against is the policy."),

    # ---- conduction realization ----------------------------------------
    Bound("B-FTCS", "fourier_number", "conduction", SOURCED_SCIENTIFIC, False,
          "von Neumann stability of FTCS: the amplification factor of the "
          "highest representable mode is 1 - 4r, so |g| > 1 once r > 1/2. "
          "Every correct implementation of the scheme has this bound."),

    # ---- contract semantics, not a threshold ----------------------------
    Bound("B-EMPTY-DOMAIN", "realization_applicability", "conduction",
          "CONTRACT", False,
          "Not a bound at all. An A-stable scheme declares no applicability "
          "condition, and an EMPTY validity domain assesses to UNKNOWN rather "
          "than to valid: absence of declared limits is not evidence of "
          "unlimited applicability. A claim about the record's semantics."),

    # ---- definitional utilisations and margins --------------------------
    *(Bound(f"B-DEF-{name}", name, domain, DEFINITIONAL, False,
            "Definitional: value divided by a limit the CALLER declared, "
            "bounded at 1. The number is a tautology given the definition; "
            "the scientific content is the caller's declared limit, which "
            "Forge does not supply and does not vouch for.")
      for name, domain in (
          ("source_current_utilization", "electrical"),
          ("dissipated_power_utilization", "electrical"),
          ("working_voltage_utilization", "electrical"),
          ("compliance_voltage_utilization", "electrical"),
          ("source_regulation_utilization", "electrical"),
          ("element_hot_spot_utilization", "electrical"),
          ("linearization_excursion_ratio", "materials"),
          ("operating_temperature_utilization", "materials"),
          ("reference_temperature_utilization", "materials"),
          ("conductance_excursion_ratio", "thermal"),
          ("capacity_excursion_ratio", "thermal"),
          ("melting_temperature_utilization", "thermal"),
          ("convection_flow_range_utilization", "thermal"),
          ("convection_property_range_utilization", "thermal"),
          ("continuous_c_rate_utilization", "battery"),
          ("pulse_c_rate_utilization", "battery"),
          ("pulse_duration_utilization", "battery"),
          ("soc_window_margin", "battery"),
          ("soc_step_resolution_ratio", "battery"),
          ("capacity_temperature_drift_ratio", "battery"),
          ("internal_resistance_drift_ratio", "battery"),
          ("self_heating_rise_ratio", "battery"),
          ("discharge_temperature_position", "battery"),
          ("cutoff_consistency_margin", "battery"),
          ("peukert_extrapolation_ratio", "battery"),
          ("peukert_capacity_ratio", "battery"),
          ("peukert_temperature_drift_ratio", "battery"),
      )),

    # ---- positivity / physical domain -----------------------------------
    *(Bound(f"B-POS-{name}", name, domain, POSITIVITY, False,
            "Physical domain of the quantity. A negative value is not one the "
            "quantity can take.")
      for name, domain in (
          ("resistance", "electrical"),
          ("reference_resistance", "materials"),
          ("linear_resistance_ratio", "materials"),
          ("heat_capacity", "thermal"),
          ("ambient_conductance", "thermal"),
          ("nominal_capacity", "battery"),
          ("internal_resistance", "battery"),
          ("terminal_voltage_ratio", "battery"),
          ("alpha", "conduction"),
          ("k0", "kinetics"),
          ("activation_energy", "kinetics"),
          ("residence_time", "kinetics"),
          ("concentration", "kinetics"),
      )),
)

BOUNDS: dict[str, Bound] = {bound.condition: bound for bound in _BOUNDS}

#: Every bound, by its register id, for a truth record that wants to name one.
BY_ID: dict[str, Bound] = {bound.bound_id: bound for bound in _BOUNDS}


def bound_for(condition: str, *, system: str = "") -> Bound | None:
    """The bound a condition is placed against.

    ``temperature`` is declared by both the material models and the CSTR with
    different ranges and different classes, so the caller says which system it
    is asking about. Everything else is unambiguous.
    """
    if condition == "temperature" and system == "kinetics_cstr":
        return BOUNDS["cstr:temperature"]
    return BOUNDS.get(condition)


def class_of(condition: str, *, system: str = "") -> str:
    bound = bound_for(condition, system=system)
    return bound.bound_class if bound is not None else "UNREGISTERED"


def is_policy(condition: str, *, system: str = "") -> bool:
    return class_of(condition, system=system) == INTERNAL_POLICY


def is_soft(condition: str, *, system: str = "") -> bool:
    bound = bound_for(condition, system=system)
    return bool(bound is not None and bound.soft)
