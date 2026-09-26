# Flagship D - Chemical / Thermal-Fluid System

Statement labels: **FACT** a checkable statement about the run artifacts - **REFERENCE DATA** taken from an external source with provenance - **ASSUMPTION** declared, not evidenced - **MODEL OUTPUT** a provider's computed value - **CORROBORATION** independent solvers agreeing (never validation) - **VALIDATION** comparison with a reference or measurement, stated with its scope (a numerical benchmark is not an experiment).

`request d685c1dea0e61f55  plan 3569744110d25b78  result 103fb147d26b1811`

## 1. Engineering question

[FACT] A stoichiometric methane/air stream is burned and its exhaust cooled by a water jacket. What are the flame temperature and exhaust composition, how much heat must the loop remove, what does the water do, and do the chemistry and thermal-fluid providers agree on the energy balance?

## 2. System definition

[FACT] One BIG 12 request. `adiabatic_equilibrium` (Cantera HP from 300 K, 1 atm), `cooled_equilibrium` (TP at 400 K), `heat_duty` = m_mix (h_reactants - h_cooled), `coolant_loop` (TESPy water, 0.3 kg/s from 293.15 K at 2 bar, heat input = the duty), `energy_balance`, three `kinetic_*` adiabatic constant-pressure reactors from 1400 K at different integrator settings, `equilibrium_limit`, `integrator_study`, `heat_of_combustion`. The reactor-to-jacket interface is a declared connection carrying an ENERGY BALANCE, not a new physical model: the water loop is handed the heat the chemistry says must be removed.

## 3. Assumptions

[ASSUMPTION] Ideal gas, equilibrium products at the exhaust outlet, no heat loss to the environment, every watt of the duty enters the water, reactant flow 0.01 kg/s, exhaust outlet 400 K, kinetic start 1400 K. All declared illustrative values.

## 4. Inputs and sources

[REFERENCE DATA] Mechanism: GRI-Mech 3.0 (`gri30.yaml` shipped with Cantera), bound as exact bytes by sha256 into every Cantera execution identity. [FACT] Its validity range is the mechanism authors' statement; the GRI-Mech page fetched for this work lists the experimental targets it was optimised against but no single temperature range, so Forge asserts none. [REFERENCE DATA] NIST Chemistry WebBook (SRD 69) gas-phase formation enthalpies (Chase 1998 / CODATA / Manion 2002) for the Hess's-law check, source page digest b739cd368e99e241..

## 5. Providers and models

[FACT] Providers executed: cantera 3.2.0, tespy 0.11.2. Cantera: `equilibrate('HP'/'TP')` and `IdealGasConstPressureReactor` (CVODES); adapter extended (additively) with mass and molar enthalpy, elemental mass fractions before/after, and the mechanism's thermodynamic data range. TESPy: water `SimpleHeatExchanger` chain.

## 6. Applicability

[FACT] Runtime checks: equilibrium temperatures against the species thermodynamic data range stored in the mechanism bytes ([300, 3000] K), the water loop against a declared liquid range [274.0, 380.0] K. [FACT] The mechanism's KINETIC validity range is NOT established by Forge, so the kinetic reactor is a demonstration of execution and consistency only.

## 7. Execution

[FACT] SUCCEEDED; 9 recorded provider executions; total node wall time 4.6 s (operational).

## 8. Results

[MODEL OUTPUT] Adiabatic flame temperature 2225.5 K; mole fractions CO2 0.0854, H2O 0.1835, CO 8.9879e-03, NO 1.8882e-03; at 400 K the equilibrium CO falls to 1.3e-25. Heat to remove 26483.0 watt (2.6483 MJ/kg of reactants); cooling water 293.15 K -> 314.27 K (+21.12 K). Kinetic reactor from 1400 K: ignition delay 3.450 ms (discrete maximum of dT/dt), end temperature 2697.883 K, fuel remaining 1.57e-14.

## 9. Verification

[FACT] Verification pyramid position:

- **L1 reached** - units, material-record digests, provider bindings and identities checked by BIG 12 preflight; deferred to the solved state: ['adiabatic_equilibrium:thermo_range', 'coolant_loop:water_liquid_range', 'cooled_equilibrium:thermo_range', 'equilibrium_limit:thermo_range', 'heat_of_combustion:thermo_range']
- **L2 reached** - elemental mass conserved through both equilibrations (a genuine conservation check: the solver could violate it); the heat the chemistry says must be removed equals the heat the water absorbs - an INTERFACE consistency (TESPy is handed that duty as its heat input, so closure cannot fail unless the solver or a unit is wrong). Criteria pre-registered
- **L3 reached** - heating value of methane vs Hess's law with evaluated NIST data: MET; the kinetic reactor converges to the equilibrium it must approach (thermodynamic consistency of mechanism and integrator): MET
- **L4 attempted not reached** - three integrator tolerances / output resolutions. The predeclared ignition criterion compares a discrete sample time whose spacing (0.05-0.25 ms) is itself 1.4-7.2 % of the ignition delay, so a converged solution need not satisfy a criterion tighter than that; the outcome is reported as it came out, with a post hoc refined reading beside it
- **L5 not available** - no second, independent chemistry provider exists in the ecosystem; the two chemistry solvers would share the mechanism and thermodynamic data
- **L6 not available** - no published numerical benchmark for this system was integrated
- **L7 not available** - no measured data (ignition delays, flame temperature, exhaust composition) were integrated; GRI-Mech 3.0 was optimised against experiments by its AUTHORS, which is their claim, not a Forge result

## 10. Cross-provider results

[FACT] Cantera and TESPy agree on the energy balance: the heat Cantera says must be removed and the heat TESPy's water absorbs (m dh) differ by -3.6e-12 W (1.4e-16 of the duty). This is a consistency check of an interface that is defined by that balance; it is NOT independent corroboration of the chemistry (there is no second chemistry provider).

## 11. Reference comparison

[REFERENCE DATA] Hess's law with evaluated NIST-JANAF / CODATA data gives a lower heating value of methane of 802.310 kJ/mol (Chase 1998) and 802.562 kJ/mol (CODATA with Manion 2002). [MODEL OUTPUT] Cantera with GRI-Mech 3.0 thermodynamics, evaluated at 300 K (the mechanism's lowest stored temperature; the reference is at 298.15 K, below it), gives 802.539 kJ/mol (the 1.85 K offset is bounded by 0.018 kJ/mol from the same thermodynamic data): lhv_hess_law MET (0.229 kJ/mol against 0.5). The reference is an ANALYTIC relation evaluated with critically evaluated data - a DATA-CONSISTENCY check of the mechanism's thermodynamics (it checks the data the model carries, classified apart from an implementation limit), not an experiment on this system; it applies near 298.15 K, 1 atm, gas-phase products only. [VALIDATION] None.

## 12. Uncertainty

[FACT] Known input uncertainty: none. UNKNOWN (never zero): reactant composition, temperature, pressure (declared); flows and outlet temperature (declared); GRI-Mech 3.0 rate and thermodynamic parameters (the mechanism authors' values; uncertainty not propagated); water properties (CoolProp via TESPy, uncertainty not propagated). Model discrepancy: NOT QUANTIFIED: equilibrium and 0-D adiabatic reactor idealisations, ideal gas, no heat loss, water assumed to absorb every watt of the duty (unknown, not zero)

## 13. Constraint and conservation checks

[FACT] `b_tflame` (max_flame_temperature) **SATISFIED** (margin 74.48 kelvin); `b_twater` (max_water_outlet) **SATISFIED** (margin 38.88 kelvin). [MODEL OUTPUT] Elemental mass balance through equilibration (max relative change of C, H, O, N): adiabatic 1.8e-11, cooled 3.4e-16 (criterion 1e-09); heat duty balance 3.6e-12 watt (tolerance 1e-06 of the duty). The kinetic reactor ends at 2697.8832 K, the HP equilibrium of the same state is 2697.8832 K (relative gap 3.4e-12).

## 14. Negative control

[FACT] A composition containing a species the mechanism does not define: `adiabatic_equilibrium` FAILED - ProviderRefusal: species ['XY9'] are not defined by the mechanism; the duty, loop and balance are BLOCKED. An exhaust outlet colder than the mechanism's thermodynamic data (100 K): `cooled_equilibrium` REFUSED - the solved state left applicability (thermo_range: exhaust outlet temperature 100.0 K against the species thermodynamic data range [300, 3000] K); the step is not committed; downstream BLOCKED.

## 15. Scientific status

[FACT] Credibility verdict (existing authority): **insufficient_evidence**. Verification ladder (from the run): L1 reached; L2 reached; L3 reached; L4 attempted not reached; L5 not available; L6 not available; L7 not available; reference level: none. This flagship demonstrates chemistry-to-thermal-fluid execution, conservation and consistency checks. It validates nothing about combustion.

## 16. Known limitations

[FACT] Equilibrium and 0-D adiabatic idealisations; one mechanism; no transport, no heat loss, no flow; illustrative flows and temperatures; the kinetic validity range is not established; the discrete ignition-time criterion was declared before its sampling-resolution limit was understood (reported NOT MET, with a post hoc refined reading); no experimental validation (ignition delays, flame temperature, exhaust composition were not integrated).

## 17. Reproduction command

```bash
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c 'cd /mnt/d/forge-b13 && FORGE_PY_ENV=sci source tools/wsl_env.sh && python -m forge_flagships chemistry --out /mnt/d/ftmp/chemistry'
```
Tests: `python -m pytest flagships/tests/test_flagship_chemistry.py` in the `sci` environment.

## Engineering summary (generated from the run)

```text
SYSTEM
  Jacketed stoichiometric methane/air reactor with a water cooling loop (nominal)
EXECUTION
  SUCCEEDED
KEY OUTPUTS
  Adiabatic flame temperature: 2225.52 kelvin   [uncertainty UNKNOWN (not quantified)]
  CO2 mole fraction (adiabatic equilibrium): 0.0853642 dimensionless   [uncertainty UNKNOWN (not quantified)]
  H2O mole fraction (adiabatic equilibrium): 0.183467 dimensionless   [uncertainty UNKNOWN (not quantified)]
  CO mole fraction (adiabatic equilibrium): 0.00898794 dimensionless   [uncertainty UNKNOWN (not quantified)]
  NO mole fraction (adiabatic equilibrium): 0.00188821 dimensionless   [uncertainty UNKNOWN (not quantified)]
  Heat to remove from the exhaust: 26483 watt   [uncertainty UNKNOWN (not quantified)]
  Cooling water outlet temperature: 314.268 kelvin   [uncertainty UNKNOWN (not quantified)]
  Cooling water temperature rise: 21.1182 kelvin   [uncertainty UNKNOWN (not quantified)]
  Energy-balance residual (Cantera vs TESPy): -3.63798e-12 watt   [uncertainty UNKNOWN (not quantified)]
  Kinetic ignition delay (finest setting, discrete): 0.00345 second   [uncertainty UNKNOWN (not quantified)]
  Kinetic end temperature: 2697.88 kelvin   [uncertainty UNKNOWN (not quantified)]
  Equilibrium temperature of the same state: 2697.88 kelvin   [uncertainty UNKNOWN (not quantified)]
  Fuel remaining after 50 ms: 1.57427e-14 dimensionless   [uncertainty UNKNOWN (not quantified)]
  Lower heating value of methane: 802.539 kilojoule / mole   [uncertainty UNKNOWN (not quantified)]
CONSTRAINTS
  b_tflame (max_flame_temperature): SATISFIED  (margin 74.48 kelvin)
  b_twater (max_water_outlet): SATISFIED  (margin 38.88 kelvin)
CONSERVATION
  heat_duty: closed residual 3.638e-12 watt (tolerance 2.648e-02)
VERIFICATION
  L1 reached: units, material-record digests, provider bindings and identities checked by BIG 12 preflight; deferred to the solved state: ['adiabatic_equilibrium:thermo_range', 'coolant_loop:water_liquid_range', 'cooled_equilibrium:thermo_range', 'equilibrium_limit:thermo_range', 'heat_of_combustion:thermo_range']
  L2 reached: elemental mass conserved through both equilibrations (a genuine conservation check: the solver could violate it); the heat the chemistry says must be removed equals the heat the water absorbs - an INTERFACE consistency (TESPy is handed that duty as its heat input, so closure cannot fail unless the solver or a unit is wrong). Criteria pre-registered
  L3 reached: heating value of methane vs Hess's law with evaluated NIST data: MET; the kinetic reactor converges to the equilibrium it must approach (thermodynamic consistency of mechanism and integrator): MET
  L4 attempted not reached: three integrator tolerances / output resolutions. The predeclared ignition criterion compares a discrete sample time whose spacing (0.05-0.25 ms) is itself 1.4-7.2 % of the ignition delay, so a converged solution need not satisfy a criterion tighter than that; the outcome is reported as it came out, with a post hoc refined reading beside it
  L5 not available: no second, independent chemistry provider exists in the ecosystem; the two chemistry solvers would share the mechanism and thermodynamic data
  L6 not available: no published numerical benchmark for this system was integrated
  L7 not available: no measured data (ignition delays, flame temperature, exhaust composition) were integrated; GRI-Mech 3.0 was optimised against experiments by its AUTHORS, which is their claim, not a Forge result
REFERENCE COMPARISONS
  reference_data_consistency_check_not_validation: lhv_hess_law MET (0.2292 kilojoule / mole; tolerance 0.5 kilojoule / mole)
UNCERTAINTY
  known input uncertainty: none stated
  UNKNOWN input uncertainty: reactant composition, temperature, pressure (declared), flows and outlet temperature (declared), GRI-Mech 3.0 rate and thermodynamic parameters (the mechanism authors' values; uncertainty not propagated), water properties (CoolProp via TESPy, uncertainty not propagated)
  model discrepancy: NOT QUANTIFIED: equilibrium and 0-D adiabatic reactor idealisations, ideal gas, no heat loss, water assumed to absorb every watt of the duty (unknown, not zero)
  model applicability: equilibrium temperatures were checked against the species thermodynamic data range stored in the mechanism and the water loop against a declared liquid range; the mechanism's KINETIC validity range is the authors' statement and is NOT established by Forge (the kinetic reactor is therefore a demonstration of execution and consistency only)
  benchmark applicability: the NIST-JANAF based Hess's-law value is an analytic reference built from evaluated data; the reference applies near 298.15 K, 1 atm and to gas-phase products only, and the comparison is evaluated at 300 K (the mechanism's lowest stored temperature; the offset is bounded in the record)
SCIENTIFIC STATUS
  insufficient_evidence - derived by the existing credibility authority; the runtime supplies no validity record and no validation check, and this summary adds none
TRACE
  complete
```
