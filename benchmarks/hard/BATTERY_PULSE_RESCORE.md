# Battery record re-frozen after CAP-02 pulse screening

Machine-readable twin: `BATTERY_PULSE_RESCORE.json`. Record: `results_battery.json`, re-scored
2026-09-15 on the tracked path, the same way it was produced before (all 400 cases, no split
argument; the split in `split_battery.json` is not used by this record and was not touched).

## What changed: the code rule, not the answer key

The runtime now screens a declared battery pulse (audit CAP-02, domains stream):

* `f39b537` — `battery.cell.rint_ocv` gains `pulse_polarization_unmodelled_fraction` (polarization
  at the declared `pulse_duration`, a conservative screen: slewing leaves the claim UNKNOWN) and
  `pulse_terminal_voltage_ratio`; `battery.cell.constant_current_runtime` gains
  `pulse_cutoff_state_of_charge_shift` (a finding when the pulse reaches the voltage cutoff above
  the state of charge the runtime stops at).
* `f434d94` — golden trace B00006 updated for the same rule.

**Unchanged:** every case file, every `ground_truth` (0 `expected` labels moved), `case_set_digest`
`32a7bff3…`, `split_battery.json`, `index_battery.json`. No hold-out was opened beyond what scoring
this all-400 record already did before.

## Before / after (scored over the four battery models, as the scorer always has)

| Metric | before | after |
|---|---|---|
| Exact verdict match | 389/400 (97.2%) | **219/400 (54.8%)** |
| Catch rate | 219/219 (100.0%) | 219/219 (100.0%) |
| False accept | 0/219 (0.00%) | 0/219 (0.00%) |
| False reject | 11/181 (6.1%) | **181/181 (100.0%)** |
| Declared-catcher rate | 389/400 (97.2%) | 389/400 (97.2%) |
| UNKNOWN-verdict match | 54/54 | 54/54 |

Transitions (170 rows, all with expected `SUPPORTED`, all previously matching):

| before → after | rows | deciding condition(s) on the moved row |
|---|---|---|
| SUPPORTED → INSUFFICIENT_EVIDENCE | 157 | `pulse_polarization_unmodelled_fraction` (rint_ocv UNKNOWN) |
| SUPPORTED → NOT_SUPPORTED | 13 | `pulse_cutoff_state_of_charge_shift` (runtime OUTSIDE) + `pulse_polarization_unmodelled_fraction` |

Per model, over the moved rows: `rint_ocv` in_domain → unknown on all 170;
`constant_current_runtime` in_domain → outside_validated_domain on 13; `coulomb_counting` and
`peukert_capacity_derating` unchanged. Every sound case now fails for the same reason, which is why
false reject is 181/181; no unsound case moved.

## Why the truth and the runtime disagree

`generate_battery.py` does not model the declared pulse. Every case carries the template load pulse
**4 A for 10 s** against a polarization time constant of about **20 s**: f = 1 - exp(-0.5) = 0.39, so
min(f, 1-f) = 0.39 against the 0.05 convention — the pulse is mid-slew, and the Rint claim over that
duty is unestablished. In **13** cases (the `cutoff_consistency_margin` shapers whose state-of-charge
cutoff sits below z_cut(4 A) = 0.10 on the 3.0-4.2 V chord at 30 mΩ) the pulse also reaches the
voltage cutoff before the state of charge the runtime is computed to.

The runtime is taken as right on the physics it now checks; the generator's labels were drawn without
it. That is a truth defect of this benchmark version, not a runtime regression.

## Deferred

Correcting the generator (modelling the pulse, or drawing pulses the Rint screen admits) changes
payloads and therefore `case_set_digest` and the split binding. It is **deferred to a new battery
benchmark version**; this record is honest about the current version rather than adjusted to it.
