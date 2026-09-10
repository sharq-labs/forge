"""Build the v2 bound register from the captured contract surface.

Every bound the challenge relies on, with the class it is entitled to claim.
The class is this challenge's own judgement, argued from the literature the
condition cites or from the algebra, and it is deliberately *not* inherited
from how the repository describes itself: a bound the Core calls physics and
this register calls internal policy is exactly the disagreement worth
recording before any case is generated.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
BLIND = HERE.parent

# name -> (class, hard_or_soft, justification)
CLASSIFICATION: dict[str, tuple[str, str, str]] = {
    # -- follows from the algebra of the quantity itself -------------------
    "resistance": ("ANALYTICALLY_DERIVED", "hard", "R > 0 or the element is a short or an active device; not a tolerance."),
    "reference_resistance": ("ANALYTICALLY_DERIVED", "hard", "R_ref > 0; the relation is anchored on it."),
    "nominal_capacity": ("ANALYTICALLY_DERIVED", "hard", "Q_nom > 0; the charge balance divides by it."),
    "internal_resistance": ("ANALYTICALLY_DERIVED", "hard", "R_int > 0; zero is a lossless cell."),
    "heat_capacity": ("ANALYTICALLY_DERIVED", "hard", "C > 0 or the balance has no dynamics."),
    "ambient_conductance": ("ANALYTICALLY_DERIVED", "hard", "hA > 0 or tau = C/hA is not finite."),
    "alpha": ("ANALYTICALLY_DERIVED", "hard", "alpha > 0 or the diffusion operator changes type."),
    "k0": ("ANALYTICALLY_DERIVED", "hard", "Arrhenius prefactor strictly positive."),
    "k_const": ("ANALYTICALLY_DERIVED", "hard", "Rate constant strictly positive."),
    "residence_time": ("ANALYTICALLY_DERIVED", "hard", "tau = V/q > 0."),
    "activation_energy": ("ANALYTICALLY_DERIVED", "hard", "E >= 0; a negative barrier is not Arrhenius."),
    "concentration": ("ANALYTICALLY_DERIVED", "hard", "C_A >= 0 is a statement about states, not accuracy."),
    "coulombic_efficiency": ("ANALYTICALLY_DERIVED", "hard", "eta in (0,1]; above 1 the counter creates charge."),
    "linear_resistance_ratio": ("ANALYTICALLY_DERIVED", "hard", "1 + alpha (T - T_ref) > 0; past the zero the line describes a negative conductor."),
    "terminal_voltage_ratio": ("ANALYTICALLY_DERIVED", "hard", "V/OCV > 0; the straight line in I crosses zero and beyond it the circuit is not this circuit."),
    "cutoff_consistency_margin": ("ANALYTICALLY_DERIVED", "hard", "The two declared cutoffs must be mutually reachable; a negative margin is a contradiction in the declaration."),
    "soc_window_margin": ("ANALYTICALLY_DERIVED", "hard", "The trajectory must lie in the declared window; the normalisation makes the bound 0 exactly."),
    "peukert_capacity_ratio": ("ANALYTICALLY_DERIVED", "hard", "Q_eff/Q_nom <= 1: Peukert's law describes capacity lost to rate and is not evidence for capacity gained."),
    "adiabatic_ceiling_temperature": ("ANALYTICALLY_DERIVED", "hard", "Z = T + beta C_A is the reactor's exact invariant, so the ceiling is an upper bound and not an estimate; the threshold it is compared against is the model's own declared temperature band."),
    # -- printed in a cited source ----------------------------------------
    "biot_number": ("SOURCE_BACKED", "hard", "Bi <= 0.1: Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007), Sec. 5.1, Eq. 5.10."),
    "internal_fourier_number": ("SOURCE_BACKED", "soft", "Fo >= 0.2: the one-term approximation range, Incropera 6th ed. Sec. 5.5.2. Declared a conservative screen, so a short horizon refuses for want of evidence rather than as a finding."),
    "lumped_electrical_length": ("SOURCE_BACKED", "hard", "L/lambda <= 0.1 is the standard lumped-circuit criterion."),
    "reduced_debye_temperature": ("SOURCE_BACKED", "hard", "T/theta_D >= 1/3 for linear rho(T); Ashcroft & Mermin (1976) Ch. 26, Eq. 26.55; Kittel 8th ed. Ch. 6."),
    "ceiling_reduced_debye_temperature": ("SOURCE_BACKED", "hard", "The same 1/3, asked at the material's own ceiling."),
    "radiation_to_convection_ratio": ("SOURCE_BACKED", "hard", "h_r from the exact factorisation of eps sigma (T_s^4 - T_sur^4), Incropera 6th ed. Sec. 1.2.3, Eq. 1.9; the 0.1 share is the declared error budget for an omitted parallel mechanism."),
    "convection_flow_range_utilization": ("SOURCE_BACKED", "hard", "Ra <= 1e9 (Churchill & Chu 1975, Int. J. Heat Mass Transfer 18(11) 1323-1329) and Re <= 5e5 (Incropera 6th ed. Sec. 7.1); each is the range its own source prints with its equation."),
    "convection_property_range_utilization": ("SOURCE_BACKED", "hard", "Pr >= 0.6, printed with Eq. 7.30, Incropera 6th ed. Sec. 7.2."),
    # -- the record's own declared band ------------------------------------
    "temperature": ("CONTRACT_DECLARED", "hard", "The band the model declares it was validated over; a declaration about the record, not a law."),
    # -- definitional utilisations against a caller-declared rating --------
    "dissipated_power_utilization": ("ANALYTICALLY_DERIVED", "hard", "The bound of 1 is definitional: the quantity is a fraction of a declared rating. The rating itself is the caller's, and IEC 60115-1 Clause 2 is what makes the derating reading meaningful."),
    "working_voltage_utilization": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a declared rating; IEC 60115-1."),
    "source_current_utilization": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a declared rating."),
    "compliance_voltage_utilization": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a declared rating."),
    "source_regulation_utilization": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a declared regulation band."),
    "element_hot_spot_utilization": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a declared permissible element temperature."),
    "continuous_c_rate_utilization": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a declared continuous rating."),
    "pulse_c_rate_utilization": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a declared pulse rating."),
    "pulse_duration_utilization": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a declared rated pulse length."),
    "operating_temperature_utilization": ("ANALYTICALLY_DERIVED", "hard", "T/T_max <= 1 against a declared material limit."),
    "reference_temperature_utilization": ("ANALYTICALLY_DERIVED", "hard", "The same declared ceiling, asked at the reference; a declaration anchored above its own ceiling is self-contradictory."),
    "melting_temperature_utilization": ("ANALYTICALLY_DERIVED", "hard", "A balance with no latent-heat term does not describe a phase change."),
    "linearization_excursion_ratio": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a caller-declared band over which one alpha is supported."),
    "capacity_excursion_ratio": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a caller-declared constant-C budget."),
    "conductance_excursion_ratio": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a caller-declared constant-hA budget."),
    "soc_step_resolution_ratio": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a caller-declared step resolution."),
    "capacity_temperature_drift_ratio": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a caller-declared temperature span."),
    "internal_resistance_drift_ratio": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a caller-declared temperature span."),
    "peukert_temperature_drift_ratio": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a caller-declared temperature span."),
    "peukert_extrapolation_ratio": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a caller-declared fit width in decades."),
    "discharge_temperature_position": ("ANALYTICALLY_DERIVED", "hard", "Normalised position in a caller-declared rated range; 0 and 1 are its edges."),
    "self_heating_rise_ratio": ("ANALYTICALLY_DERIVED", "hard", "Definitional fraction of a caller-declared isothermal-cell budget."),
    # -- repository conventions, named as such -----------------------------
    "geometry_route_ratio": ("INTERNAL_POLICY", "hard", "A factor of 3 either way. Partly derivable -- the shape factor between L_c = V/A_s and a shape's own dimension is 1, 2 or 3 -- but the decision to admit the whole range as agreement is a convention, not a printed bound."),
    "convection_conductance_agreement_ratio": ("INTERNAL_POLICY", "hard", "A factor of 2 either way. The record itself says no source prints it for this comparison; this register agrees and classes it as policy."),
    "polarization_unmodelled_fraction": ("INTERNAL_POLICY", "hard", "min(f, 1-f) <= 0.05. The relaxation form is standard; the 5% budget for the omitted overpotential is a repository choice with no source attached."),
    "reference_reduced_debye_temperature": ("INTERNAL_POLICY", "hard", "T_ref/theta_D >= 1/5. Argued in the record from beryllium's 0.204 rather than printed anywhere as a criterion; a threshold chosen to admit a real datasheet is a policy choice, defensible and still a choice."),
}


def main() -> int:
    surface = json.loads((BLIND / "CONTRACT_SURFACE.json").read_text(encoding="utf-8"))
    bounds = []
    seen: dict[str, dict] = {}
    for model in surface["models"]:
        for condition in model["conditions"]:
            name = condition["name"]
            klass, hardness, justification = CLASSIFICATION.get(
                name, ("UNCLASSIFIED", "unknown", "no classification recorded")
            )
            entry = seen.setdefault(
                name,
                {
                    "id": f"V2B-{name}",
                    "name": name,
                    "class": klass,
                    "interpretation": hardness,
                    "justification": justification,
                    "conservative_screen": bool(condition.get("conservative_screen")),
                    "occurrences": [],
                },
            )
            entry["occurrences"].append(
                {
                    "model_id": model["model_id"],
                    "system": model["system"],
                    "condition_type": condition["condition_type"],
                    "minimum": condition.get("minimum"),
                    "minimum_inclusive": condition.get("minimum_inclusive"),
                    "maximum": condition.get("maximum"),
                    "maximum_inclusive": condition.get("maximum_inclusive"),
                }
            )
    bounds = [seen[k] for k in sorted(seen)]
    unclassified = [b["name"] for b in bounds if b["class"] == "UNCLASSIFIED"]
    payload = {
        "schema": "blind_v2_bound_register/1",
        "what_this_is": (
            "Every bound Blind Challenge v2 relies on, with the class this "
            "challenge is willing to defend for it. SOURCE_BACKED means a "
            "cited source prints the number. ANALYTICALLY_DERIVED means the "
            "bound follows from the algebra of the quantity, including the "
            "definitional bound of 1 on a fraction-of-a-declared-rating. "
            "CONTRACT_DECLARED means the record states a band and the band is "
            "a fact about the record. INTERNAL_POLICY means a repository "
            "convention with no source behind the number."
        ),
        "class_counts": {
            klass: sum(1 for b in bounds if b["class"] == klass)
            for klass in sorted({b["class"] for b in bounds})
        },
        "unclassified": unclassified,
        "bounds": bounds,
    }
    out = BLIND / "BOUND_REGISTER.json"
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    out.write_text(text, encoding="utf-8")
    print(f"bounds={len(bounds)} unclassified={unclassified}")
    print(json.dumps(payload["class_counts"], indent=2))
    print("sha256=", hashlib.sha256(text.encode()).hexdigest())
    return 1 if unclassified else 0


if __name__ == "__main__":
    raise SystemExit(main())
