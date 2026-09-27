# Flagship A - Battery + Cooling + Lifecycle

Statement labels: **FACT** a checkable statement about the run artifacts - **REFERENCE DATA** taken from an external source with provenance - **ASSUMPTION** declared, not evidenced - **MODEL OUTPUT** a provider's computed value - **CORROBORATION** independent solvers agreeing (never validation) - **VALIDATION** comparison with a reference or measurement, stated with its scope (a numerical benchmark is not an experiment).

`request 9158ed7ea3263b41  plan a41a0861327476b1  result 0967feab419839ae`

## 1. Engineering question

[FACT] How does a declared liquid-cooled cell module behave over a long operating period under a declared usage and environment profile, and how does the degradation accumulated over that period change its LATER electrical and thermal behaviour?

## 2. System definition

[FACT] One BIG 12 `SystemRunRequest` (request 9158ed7ea3263b41): a real PyBaMM cell coupled to a real TESPy water cold plate through the BIG 9 coupling runtime (100 identical cells in thermal parallel on one plate), run as

1. `day_fresh` - one 24 h operating day with a new cell (24 one-hour coupling windows);
2. `aging` - the SAME coupled day as a BIG 10 fast system inside a 56-day multi-timescale run (14-day macro steps, 4 resolved days, throughput/temperature fade from BIG 4); it commits the slow state `capacity_fade` and depends on `day_fresh` (the lifecycle run does not proceed from an inadmissible day);
3. `day_aged` - the same coupled day at day 56, the cell rebuilt from the COMMITTED fade;
4. `day_control` - the identical day-56 window with a NEW cell (isolates the effect of degradation from the effect of the drifting environment);
5. `shift` - aged - control (degradation) and control - fresh (environment drift).

Constraints: cell temperature <= 45 degC, minimum SOC >= 0.2, capacity fade <= 0.10 (all illustrative).

## 3. Assumptions

[ASSUMPTION] Usage: +2.5 A for one hour at 08:00 and -2.5 A at 14:00, per cell; the cell is recharged to SOC 0.8 every day. Coolant inlet = site air + 2 K (dry cooler), air = mean + 6 K sinusoid, +0.05 K/day drift. Cell-to-coolant thermal resistance 2.0 K/W per cell (an ASSUMED material record), module of 100 cells loaded identically, loop flow 0.02 kg/s at 2 bar. Fade law: ThroughputArrheniusFade k = 2e-4 /(A h), Ea = 30 kJ/mol (declared). Every value above is a declared illustrative fixture; none is measured.

## 4. Inputs and sources

[REFERENCE DATA] Cell parameters: the PyBaMM-bundled literature set `Chen2020` (provider data, content-digested, NOT Forge-sourced; its own source is the literature). [ASSUMPTION] Its negative / positive active-material volume fractions are multiplied by 0.9800 / 0.8539: factors IDENTIFIED (not measured) on one LG M50 discharge (cell02, C/10) by the pre-registered study big14-a-lgm50-dfn and carried here under that study's registered decision rule. [ASSUMPTION] Usage current, coolant inlet profile, contact resistance, multiplicity, fade constants: declared (see above). [FACT] The environment (BIG 3 channel `coolant_inlet`, source classified `design_assumption`) and usage (BIG 2 history `load`) are exact records hashed into the request.

## 5. Providers and models

[FACT] Providers executed: pybamm 26.8.0.0, tespy 0.11.2. Cell model: DFN with the heat of mixing (BIG 14 owner decision; earlier runs used SPM), isothermal at the coupled temperature, with heat computed by the model; coolant: TESPy `SimpleHeatExchanger` chain (water, CoolProp properties inside TESPy). Coupling: implicit, relaxation 0.8, tolerances 1e-6 W / 1e-6 K, 1 h windows (BIG 9). Long horizon: BIG 10 representative day, `DECLARED_INITIAL` fast state. The cell temperature is coolant mean temperature + cell heat x contact resistance (quasi-steady, declared).

## 6. Applicability

[FACT] Runtime checks on every solved day: SOC stays inside the declared window [0.15, 0.95] and cell temperature inside [273.15, 333.15] K; on the aging node the slow state stays inside the loss-of-active-material mapping range [0, 0.5). [ASSUMPTION] The windows are declared operating envelopes, not properties of the cell. The applicability of the Chen2020 parameters to these temperatures and this duty is UNKNOWN to Forge.

## 7. Execution

[FACT] Normal case: SUCCEEDED in 291 s of wall time; 1585 recorded provider executions (PyBaMM windows + every TESPy solve); 596f93ebebf9.. is the delegated BIG 10 run record; 1 committed slow-state change (final state digest fe05d0336d2c..). Wall times are operational, not evidence.

## 8. Results

[MODEL OUTPUT] Headline quantities (per cell unless stated; every uncertainty is UNKNOWN, none is quantified):

| quantity | normal | hot |
|---|---|---|
| Peak cell temperature, fresh day | 301.82 K | 321.66 K |
| Peak cell temperature, day 56, aged | 304.62 K | 324.5 K |
| Coolant temperature rise, fresh day (peak) | 0.41195 K | 0.3285 K |
| Module heat removed, fresh day | 68.964 hour * watt | 55.623 hour * watt |
| End-of-discharge voltage, fresh | 3.4009 volt | 3.43 volt |
| End-of-discharge voltage, aged | 3.3698 volt | 3.3559 volt |
| End-of-discharge voltage, new cell on day 56 (control) | 3.406 volt | 3.4327 volt |
| Voltage shift caused by DEGRADATION (aged - control) | -0.036166 volt | -0.076753 volt |
| Voltage shift caused by ENVIRONMENT drift (control - fresh) | 0.0051543 volt | 0.0027038 volt |
| Minimum SOC, aged day | 0.27263 dimensionless | 0.23692 dimensionless |
| Peak cell heat shift caused by degradation | 0.011676 watt | 0.02052 watt |
| Capacity fade after 56 days | 0.051893 dimensionless | 0.11202 dimensionless |

Histories (voltage, SOC, cell heat, cell / coolant-inlet / coolant-outlet temperature, module heat removed) are exported as `artifacts/day-*_history.csv` in the run bundle (dense PyBaMM points; temperatures are the window values).

## 9. Verification

[FACT] Verification pyramid position (a report vocabulary, not a validation grant):

- **L1 reached** - units, material-record digests, provider bindings and identities checked by BIG 12 preflight; deferred to the solved state: ['aging:fade_mapping_range', 'day_aged:cell_temperature_window', 'day_aged:soc_window', 'day_control:cell_temperature_window', 'day_control:soc_window', 'day_fresh:cell_temperature_window', 'day_fresh:soc_window']
- **L2 reached** - INTERFACE consistency, not an independent conservation law: TESPy is handed the cell heat as its heat duty, so closure of generated heat against m dh shows the solver honoured the duty (tolerance pre-registered). It would fail on a solver or unit error; it cannot detect a wrong heat model
- **L3 reached** - first-law coolant temperature rise vs Q/(m cp): verifies the heat -> enthalpy -> temperature implementation only
- **L4 attempted not reached** - the fresh-cell coupled day at three coupling-window sizes, each a separate BIG 12 request (evidence from OTHER requests than this run's). Criteria: finest-pair differences within 0.05 K / 2 mV / 2 % of peak heat (pre-registered, two-level version) AND monotonically decreasing successive differences (added after the review, with the third level; the two-level result had already met the tolerances). Only the coupling window is refined: the cell model's own solver tolerances and points-per-window are not varied
- **L5 not available** - no second, independent battery provider exists in the provider ecosystem; PyBaMM DFN vs SPM would be the same provider and compare_providers refuses that pair as non-independent
- **L6 not available** - no published numerical benchmark for this module/duty was integrated
- **L7 attempted not reached** - the CELL MODEL alone was compared with measured LG M50 lab discharges (big14-a-lgm50-dfn, pre-registered): NOT MET (C/2: voltage RMSE inside the criterion on all 3 cells; capacity inside the criterion on all 3 cells; surface-temperature rise missed on cell02, cell04), and in-sample (Chen2020 was tuned on those curves), so it is neither validation nor evidence about this module, cold plate or duty. The NASA PCoE Li-ion aging dataset (repository-pinned manifest) was also considered: the reference record Forge wrote for it (envelope authored here from the pack's description, not from the dataset's own metadata) states only the cell-format diameter (18 mm, from the '18650' name) as an envelope term and this flagship states no recorded cell format for the PyBaMM parameter set, so its applicability is UNKNOWN (condition 'cell_format_diameter' of the flagship is not stated); no comparison was made and none is claimed

## 10. Cross-provider results

[FACT] There is no independent battery provider in the ecosystem, so no cross-provider comparison exists (level 5 NOT AVAILABLE). PyBaMM DFN vs SPM would be the same provider and `compare_providers` refuses that pair as non-independent. [CORROBORATION] none is claimed.

## 11. Reference comparison

[VALIDATION] None for this module. [FACT] The CELL MODEL alone was compared with measured constant-current discharges of three LG M50 cells (Chen 2020 data, pre-registered study big14-a-lgm50-dfn): NOT MET (C/2: voltage RMSE inside the criterion on all 3 cells; capacity inside the criterion on all 3 cells; surface-temperature rise missed on cell02, cell04); C/2 voltage RMSE 13.6-16.9 mV and its peak surface-rise error -3.5 to -1.5 K. Those curves are the data Chen2020 was tuned on, so the comparison is in-sample consistency, not validation, and says nothing about this cold plate or duty (level 7 ATTEMPTED, NOT REACHED). [FACT] Analytic reference used: the first-law relation Q = m cp dT for the coolant (verifies the energy-balance implementation only; cp comes from the same CoolProp backend TESPy uses): first_law_delta_T MET (1.07e-07 against 0.005). [REFERENCE DATA] The NASA PCoE Li-ion aging dataset (repository-pinned manifest identity) was CONSIDERED: the reference record Forge wrote for it (envelope authored here from the pack's description, not from the dataset's own metadata) has one envelope term (cell format, 18 mm from the '18650' name) that this flagship cannot state for its PyBaMM parameter set, so its applicability is UNKNOWN and no comparison was made.

## 12. Uncertainty

[FACT] Known input uncertainty: none. UNKNOWN (never zero): coolant inlet profile (declared); cell current profile (declared); initial state of charge (declared); contact resistance (ASSUMED); cells-in-module multiplicity (declared); fade-law constants (declared); PyBaMM Chen2020 parameters (provider-bundled literature data); active-material balance factors (identified on one LG M50 curve, not measured). Model discrepancy: NOT QUANTIFIED for the DFN cell model, the quasi-steady thermal rule, the loss-of-active-material fade mapping or the representative-day approximation (unknown, not zero). Reported, not propagated: against LG M50 lab discharges at C/2 the cell model's voltage RMSE was 13.6-16.9 mV and its peak surface-rise error -3.5 to -1.5 K (big14-a-lgm50-dfn; in-sample, likely optimistic). The rise error belongs to the lab rig (its identified heat-transfer coefficient, a lumped model against a surface thermocouple) and says nothing about this flagship's cell temperature, which follows the declared contact-resistance rule; the charge half of the duty was never compared with data; applicability to this module and duty is UNKNOWN. Every reported output carries an UNKNOWN uncertainty record.

## 13. Constraint and conservation checks

[FACT] Normal case: `b_fade` (max_capacity_fade) **SATISFIED** (margin 0.04811 dimensionless); `b_soc_aged` (min_soc) **SATISFIED** (margin 0.07263 dimensionless); `b_soc_fresh` (min_soc) **SATISFIED** (margin 0.1 dimensionless); `b_tmax_aged` (max_cell_temperature) **SATISFIED** (margin 13.53 kelvin); `b_tmax_fresh` (max_cell_temperature) **SATISFIED** (margin 16.33 kelvin). Hot case: `b_fade` (max_capacity_fade) **VIOLATED** (margin -0.01202 dimensionless); `b_soc_aged` (min_soc) **SATISFIED** (margin 0.03692 dimensionless); `b_soc_fresh` (min_soc) **SATISFIED** (margin 0.1 dimensionless); `b_tmax_aged` (max_cell_temperature) **VIOLATED** (margin -6.347 kelvin); `b_tmax_fresh` (max_cell_temperature) **VIOLATED** (margin -3.509 kelvin). [MODEL OUTPUT] Heat balance (cell heat generated vs heat absorbed by the coolant, m dh), fresh / aged / control: module_heat_fresh residual 1.6e-11 hour * watt; module_heat_aged residual 3.5e-12 hour * watt; module_heat_control residual 3.0e-12 hour * watt (tolerance 1e-06 W h, pre-registered).

## 14. Negative control

[FACT] Overload (1.1 C discharge hour from 80 % SOC: more charge than the cell holds): `day_fresh` FAILED - ProviderRefusal: PyBaMM stopped early in [28800.0 second, 32400.0 second] (event); window refused; `aging` BLOCKED, `shift` BLOCKED; final fade is UNAVAILABLE (blocked); no state was committed; every constraint is UNAVAILABLE. Outside-window (the normal duty against a declared SOC window that the discharge leaves): `day_fresh` REFUSED (the solved state left applicability (soc_window: SOC range [0.3000, 0.8000] against the declared window [0.35, 0.95]); the step is not committed), aging BLOCKED, no state committed. The hot case above is the third: it succeeds and its constraints read VIOLATED.

## 15. Scientific status

[FACT] Credibility verdict (existing authority): **insufficient_evidence** for the normal case; per case: normal insufficient_evidence (run succeeded); hot insufficient_evidence (run succeeded); overload insufficient_evidence (run failed); outside_window insufficient_evidence (run failed). The runtime supplies no validity record and no validation check. Verification level reached: 3 of 4 (L1-L4); corroboration: none; reference level: none. Verification ladder (from the run): L1 reached; L2 reached; L3 reached; L4 attempted not reached; L5 not available; L6 not available; L7 attempted not reached; the coupling-window study: tolerances met = False, monotone decrease of successive differences met = True; no convergence is claimed and the cause was not investigated. This flagship demonstrates system execution, coupling, lifecycle propagation and numerical behaviour. It does not validate the battery model.

## 16. Known limitations

[FACT] Illustrative declared inputs; a single lumped cell type; the cell model's only measured comparison is in-sample (see Reference comparison); the cell's heat closes on its own energy identity (bulk open-circuit voltage) to 0.89 % at 300 K, 1.10 % at 313.15 K; the pre-registered 1 % check big14-a-cell-energy-check-dfn is NOT MET, and the heat of mixing is 36 % / 42 % of the cell heat; the reversible (entropic) heat is absent (Chen2020 has no entropic data); the fade law is a declared approximation with a loss-of-active-material mapping; 56 represented days from 4 resolved days (the representative-day approximation error was measured for the earlier SPM cell - fade under-read by 1.2-1.3 %, big14-a-representative-day - and is not re-measured for DFN); the cooling loop is a quasi-steady thermal rule; the cell current per module is uniform by assumption; SOC is a coulomb-counting definition. The aging temperature comes from the coupled day (cooling IS in the loop), which is more faithful than a lumped-air model but still unvalidated.

## 17. Reproduction command

```bash
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c 'cd /mnt/d/forge-b13 && FORGE_PY_ENV=battery source tools/wsl_env.sh && python -m forge_flagships battery normal --out /mnt/d/ftmp/battery_normal --extras'
```
Cases: `normal`, `hot`, `overload`, `outside_window`. Tests: `python -m pytest flagships/tests/test_flagship_battery.py` in the same environment.

## Engineering summary (generated from the run)

```text
SYSTEM
  Cell module with liquid cooling, 57-day declared profile (normal)
EXECUTION
  SUCCEEDED
KEY OUTPUTS
  Peak cell temperature, fresh day: 301.823 kelvin   [uncertainty UNKNOWN (not quantified)]
  Peak cell temperature, day 56 (aged): 304.623 kelvin   [uncertainty UNKNOWN (not quantified)]
  Coolant temperature rise, fresh day (peak): 0.411954 kelvin   [uncertainty UNKNOWN (not quantified)]
  Module heat removed, fresh day: 68.9635 hour * watt   [uncertainty UNKNOWN (not quantified)]
  End-of-discharge voltage, fresh day: 3.40085 volt   [uncertainty UNKNOWN (not quantified)]
  End-of-discharge voltage, aged cell: 3.36984 volt   [uncertainty UNKNOWN (not quantified)]
  Voltage shift caused by degradation: -0.0361664 volt   [uncertainty UNKNOWN (not quantified)]
  Voltage shift caused by environment drift: 0.00515429 volt   [uncertainty UNKNOWN (not quantified)]
  End SOC, fresh day: 0.8 dimensionless   [uncertainty UNKNOWN (not quantified)]
  Minimum SOC, aged day: 0.272634 dimensionless   [uncertainty UNKNOWN (not quantified)]
  Capacity fade after 56 days: 0.0518928 dimensionless   [uncertainty UNKNOWN (not quantified)]
  Peak cell heat shift caused by degradation: 0.011676 watt   [uncertainty UNKNOWN (not quantified)]
CONSTRAINTS
  b_fade (max_capacity_fade): SATISFIED  (margin 0.04811 dimensionless)
  b_soc_aged (min_soc): SATISFIED  (margin 0.07263 dimensionless)
  b_soc_fresh (min_soc): SATISFIED  (margin 0.1 dimensionless)
  b_tmax_aged (max_cell_temperature): SATISFIED  (margin 13.53 kelvin)
  b_tmax_fresh (max_cell_temperature): SATISFIED  (margin 16.33 kelvin)
CONSERVATION
  module_heat_fresh: closed residual 1.648e-11 hour * watt (tolerance 1.000e-06)
  module_heat_aged: closed residual 3.510e-12 hour * watt (tolerance 1.000e-06)
  module_heat_control: closed residual 3.013e-12 hour * watt (tolerance 1.000e-06)
VERIFICATION
  L1 reached: units, material-record digests, provider bindings and identities checked by BIG 12 preflight; deferred to the solved state: ['aging:fade_mapping_range', 'day_aged:cell_temperature_window', 'day_aged:soc_window', 'day_control:cell_temperature_window', 'day_control:soc_window', 'day_fresh:cell_temperature_window', 'day_fresh:soc_window']
  L2 reached: INTERFACE consistency, not an independent conservation law: TESPy is handed the cell heat as its heat duty, so closure of generated heat against m dh shows the solver honoured the duty (tolerance pre-registered). It would fail on a solver or unit error; it cannot detect a wrong heat model
  L3 reached: first-law coolant temperature rise vs Q/(m cp): verifies the heat -> enthalpy -> temperature implementation only
  L4 attempted not reached: the fresh-cell coupled day at three coupling-window sizes, each a separate BIG 12 request (evidence from OTHER requests than this run's). Criteria: finest-pair differences within 0.05 K / 2 mV / 2 % of peak heat (pre-registered, two-level version) AND monotonically decreasing successive differences (added after the review, with the third level; the two-level result had already met the tolerances). Only the coupling window is refined: the cell model's own solver tolerances and points-per-window are not varied
  L5 not available: no second, independent battery provider exists in the provider ecosystem; PyBaMM DFN vs SPM would be the same provider and compare_providers refuses that pair as non-independent
  L6 not available: no published numerical benchmark for this module/duty was integrated
  L7 attempted not reached: the CELL MODEL alone was compared with measured LG M50 lab discharges (big14-a-lgm50-dfn, pre-registered): NOT MET (C/2: voltage RMSE inside the criterion on all 3 cells; capacity inside the criterion on all 3 cells; surface-temperature rise missed on cell02, cell04), and in-sample (Chen2020 was tuned on those curves), so it is neither validation nor evidence about this module, cold plate or duty. The NASA PCoE Li-ion aging dataset (repository-pinned manifest) was also considered: the reference record Forge wrote for it (envelope authored here from the pack's description, not from the dataset's own metadata) states only the cell-format diameter (18 mm, from the '18650' name) as an envelope term and this flagship states no recorded cell format for the PyBaMM parameter set, so its applicability is UNKNOWN (condition 'cell_format_diameter' of the flagship is not stated); no comparison was made and none is claimed
REFERENCE COMPARISONS
  analytic_limit_comparison_verifies_implementation_only: first_law_delta_T MET (1.074e-07 dimensionless; tolerance 0.005 dimensionless)
UNCERTAINTY
  known input uncertainty: none stated
  UNKNOWN input uncertainty: coolant inlet profile (declared), cell current profile (declared), initial state of charge (declared), contact resistance (ASSUMED), cells-in-module multiplicity (declared), fade-law constants (declared), PyBaMM Chen2020 parameters (provider-bundled literature data), active-material balance factors (identified on one LG M50 curve, not measured)
  model discrepancy: NOT QUANTIFIED for the DFN cell model, the quasi-steady thermal rule, the loss-of-active-material fade mapping or the representative-day approximation (unknown, not zero). Reported, not propagated: against LG M50 lab discharges at C/2 the cell model's voltage RMSE was 13.6-16.9 mV and its peak surface-rise error -3.5 to -1.5 K (big14-a-lgm50-dfn; in-sample, likely optimistic). The rise error belongs to the lab rig (its identified heat-transfer coefficient, a lumped model against a surface thermocouple) and says nothing about this flagship's cell temperature, which follows the declared contact-resistance rule; the charge half of the duty was never compared with data; applicability to this module and duty is UNKNOWN
  model applicability: cell temperature window [273.15, 333.15] K and SOC window [0.15, 0.95] were checked on every solved day; the aging map range [0, 0.5) on the slow state. The applicability of the Chen2020 parameters to the temperatures and duty of this case is UNKNOWN to Forge
  benchmark applicability: no benchmark was used: the NASA PCoE Li-ion aging dataset (repository-pinned; 18650 cells) has a Forge-authored reference record with one envelope term (cell format) that this flagship cannot state for its parameter set, so its applicability is UNKNOWN and it is not compared
  material provenance: contact resistance record 831fcc041478.. (ASSUMED), PyBaMM parameter set Chen2020 (provider-bundled literature set)
SCIENTIFIC STATUS
  insufficient_evidence - derived by the existing credibility authority; the runtime supplies no validity record and no validation check, and this summary adds none
TRACE
  complete
NOTES
  case normal: 20 degC mean site air, 0.5 C discharge hour and 0.5 C charge hour
  all scenario inputs are declared illustrative fixtures, not measurements
```
