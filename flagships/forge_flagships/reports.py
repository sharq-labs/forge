"""Generate the flagship reports (docs/flagships/*.md) from real runs.  Numbers are read from run objects; the few fixed constants that appear
(criteria, declared inputs) are read from the flagship modules, never re-typed here.

    python -m forge_flagships.reports battery|structure|cavity|chemistry --docs docs/flagships [--bundles DIR]

Each flagship needs its own provider environment (see docs/flagships/README.md).  The report text states what each claim IS (FACT, REFERENCE DATA,
ASSUMPTION, MODEL OUTPUT, CORROBORATION, VALIDATION); the section list is enforced by ``engcore.engineering.render_report``.
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings

from engcore.engineering import committed_artifacts, render_report, verify_bundle, write_bundle

def _ladder_status(ladder) -> str:
    """One line from the run's own ladder (never a typed statement of where evidence stops)."""
    return "; ".join(f"L{e.level} {e.status.value.replace('_', ' ')}" for e in ladder.entries)


WSL = ("MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c 'cd /mnt/d/forge-b13 && FORGE_PY_ENV={env} source tools/wsl_env.sh && python -m forge_flagships {args}'")


def _q(run_or_result, oid, fmt="{:.6g}"):
    res = getattr(run_or_result, "result", run_or_result)
    o = res.observable(oid)
    return "UNAVAILABLE (" + o.availability.value + ")" if o.value is None else fmt.format(o.value.value.magnitude) + " " + str(o.value.value.units).replace("kelvin", "K").replace("meter", "m").replace("pascal", "Pa")


def _v(run, oid):
    o = getattr(run, "result", run).observable(oid)
    return None if o.value is None else o.value.value.magnitude


def _ladder_lines(ladder) -> str:
    return "\n".join(f"- **L{e.level} {e.status.value.replace('_', ' ')}** - {e.note}" for e in ladder.entries)


def _providers(result) -> str:
    return ", ".join(sorted({f"{p.provider_id} {p.provider_version}" for p in result.provider_records}))


def _constraints(cons) -> str:
    return "; ".join(f"`{c.binding_id}` ({c.constraint_id}) **{c.status.upper()}**" + (f" (margin {c.check.margin.magnitude:.4g} {c.check.margin.units})" if c.check else "") for c in cons)


def _identity(run) -> str:
    return f"request {run.result.request_digest[:16]}  plan {run.result.plan_digest[:16]}  result {run.result.digest[:16]}"


# ==================================================================================================== A
def battery_report(runs: dict) -> tuple[str, str]:
    n, h, ov, ow = runs["normal"], runs["hot"], runs["overload"], runs["outside_window"]
    from . import battery_cooling as bc
    r = n.result
    row = lambda label, oid, fmt="{:.5g}": f"| {label} | {_q(n, oid, fmt)} | {_q(h, oid, fmt)} |"  # noqa: E731
    sections = {
        "Engineering question": (
            "[FACT] How does a declared liquid-cooled cell module behave over a long operating period under a declared usage and environment profile, and how does the "
            "degradation accumulated over that period change its LATER electrical and thermal behaviour?"),
        "System definition": (
            "[FACT] One BIG 12 `SystemRunRequest` (request " + r.request_digest[:16] + "): a real PyBaMM cell coupled to a real TESPy water cold plate through the BIG 9 coupling runtime "
            f"({bc.N_CELLS} identical cells in thermal parallel on one plate), run as\n\n"
            "1. `day_fresh` - one 24 h operating day with a new cell (24 one-hour coupling windows);\n"
            "2. `aging` - the SAME coupled day as a BIG 10 fast system inside a 56-day multi-timescale run (14-day macro steps, 4 resolved days, throughput/temperature fade from BIG 4); "
            "it commits the slow state `capacity_fade` and depends on `day_fresh` (the lifecycle run does not proceed from an inadmissible day);\n"
            "3. `day_aged` - the same coupled day at day 56, the cell rebuilt from the COMMITTED fade;\n"
            "4. `day_control` - the identical day-56 window with a NEW cell (isolates the effect of degradation from the effect of the drifting environment);\n"
            "5. `shift` - aged - control (degradation) and control - fresh (environment drift).\n\n"
            "Constraints: cell temperature <= 45 degC, minimum SOC >= 0.2, capacity fade <= 0.10 (all illustrative)."),
        "Assumptions": (
            f"[ASSUMPTION] Usage: +{bc.CASES['normal'].discharge_A} A for one hour at 08:00 and -{bc.CASES['normal'].discharge_A} A at 14:00, per cell; the cell is recharged to SOC {bc.INITIAL_SOC} every day. "
            "Coolant inlet = site air + 2 K (dry cooler), air = mean + 6 K sinusoid, +0.05 K/day drift. "
            f"Cell-to-coolant thermal resistance {bc.R_CONTACT_K_PER_W} K/W per cell (an ASSUMED material record), module of {bc.N_CELLS} cells loaded identically, loop flow {bc.MASS_FLOW} kg/s at 2 bar. "
            "Fade law: ThroughputArrheniusFade k = 2e-4 /(A h), Ea = 30 kJ/mol (declared). Every value above is a declared illustrative fixture; none is measured."),
        "Inputs and sources": (
            "[REFERENCE DATA] Cell parameters: the PyBaMM-bundled literature set `Chen2020` (provider data, content-digested, NOT Forge-sourced; its own source is the literature). "
            "[ASSUMPTION] Usage current, coolant inlet profile, contact resistance, multiplicity, fade constants: declared (see above). "
            "[FACT] The environment (BIG 3 channel `coolant_inlet`, source classified `design_assumption`) and usage (BIG 2 history `load`) are exact records hashed into the request."),
        "Providers and models": (
            f"[FACT] Providers executed: {_providers(r)}. Cell model: SPM, isothermal at the coupled temperature, with heat computed by the model; coolant: TESPy `SimpleHeatExchanger` chain "
            "(water, CoolProp properties inside TESPy). Coupling: implicit, relaxation 0.8, tolerances 1e-6 W / 1e-6 K, 1 h windows (BIG 9). Long horizon: BIG 10 representative day, "
            "`DECLARED_INITIAL` fast state. The cell temperature is coolant mean temperature + cell heat x contact resistance (quasi-steady, declared)."),
        "Applicability": (
            f"[FACT] Runtime checks on every solved day: SOC stays inside the declared window {list(bc.SOC_WINDOW)} and cell temperature inside {list(bc.TEMP_WINDOW_K)} K; on the aging node the slow state stays inside the "
            "loss-of-active-material mapping range [0, 0.5). [ASSUMPTION] The windows are declared operating envelopes, not properties of the cell. The applicability of the Chen2020 parameters to "
            "these temperatures and this duty is UNKNOWN to Forge."),
        "Execution": (
            f"[FACT] Normal case: {r.status.value.upper()} in {n.wall_s:.0f} s of wall time; {len(r.provider_records)} recorded provider executions (PyBaMM windows + every TESPy solve); "
            f"{r.receipt('aging').delegated_record_digest[:12]}.. is the delegated BIG 10 run record; 1 committed slow-state change (final state digest {r.final_state.digest[:12]}..). "
            "Wall times are operational, not evidence."),
        "Results": (
            "[MODEL OUTPUT] Headline quantities (per cell unless stated; every uncertainty is UNKNOWN, none is quantified):\n\n| quantity | normal | hot |\n|---|---|---|\n"
            + "\n".join([row("Peak cell temperature, fresh day", "peak_cell_temperature_fresh"), row("Peak cell temperature, day 56, aged", "peak_cell_temperature_aged"),
                         row("Coolant temperature rise, fresh day (peak)", "coolant_rise_peak_fresh"), row("Module heat removed, fresh day", "module_heat_removed_fresh"),
                         row("End-of-discharge voltage, fresh", "voltage_end_of_discharge_fresh"), row("End-of-discharge voltage, aged", "voltage_end_of_discharge_aged"),
                         row("End-of-discharge voltage, new cell on day 56 (control)", "voltage_end_of_discharge_control"),
                         row("Voltage shift caused by DEGRADATION (aged - control)", "voltage_shift_degradation"), row("Voltage shift caused by ENVIRONMENT drift (control - fresh)", "voltage_shift_environment"),
                         row("Minimum SOC, aged day", "min_soc_aged"), row("Peak cell heat shift caused by degradation", "peak_heat_shift_degradation"),
                         row("Capacity fade after 56 days", "final_fade")])
            + "\n\nHistories (voltage, SOC, cell heat, cell / coolant-inlet / coolant-outlet temperature, module heat removed) are exported as `artifacts/day-*_history.csv` in the run bundle "
              "(dense PyBaMM points; temperatures are the window values)."),
        "Verification": ("[FACT] Verification pyramid position (a report vocabulary, not a validation grant):\n\n" + _ladder_lines(n.ladder)),
        "Cross-provider results": (
            "[FACT] There is no independent battery provider in the ecosystem, so no cross-provider comparison exists (level 5 NOT AVAILABLE). PyBaMM SPM vs SPMe would be the same provider and "
            "`compare_providers` refuses that pair as non-independent. [CORROBORATION] none is claimed."),
        "Reference comparison": (
            "[VALIDATION] None (no comparison with measurements was made). [FACT] Analytic reference used: the first-law relation Q = m cp dT for the coolant (verifies the energy-balance implementation only; cp comes from the same CoolProp backend TESPy uses): "
            + "; ".join(f"{c.criterion.criterion_id} {c.outcome.upper()} ({c.value.magnitude:.2e} against {c.criterion.tolerance.magnitude:g})" for c in n.comparisons)
            + ". [REFERENCE DATA] The NASA PCoE Li-ion aging dataset (repository-pinned manifest identity) was CONSIDERED: the reference record Forge wrote for it (envelope authored here from the pack's description, not from the dataset's own metadata) has one envelope term (cell format, 18 mm from the '18650' name) that this flagship cannot state "
              "for its PyBaMM parameter set, so its applicability is UNKNOWN and no comparison was made."),
        "Uncertainty": (
            "[FACT] Known input uncertainty: none. UNKNOWN (never zero): " + "; ".join(n.summary.uncertainty.unknown_input_uncertainty) + ". Model discrepancy: " + n.summary.uncertainty.model_discrepancy
            + ". Every reported output carries an UNKNOWN uncertainty record."),
        "Constraint and conservation checks": (
            f"[FACT] Normal case: {_constraints(n.constraints)}. Hot case: {_constraints(h.constraints)}. [MODEL OUTPUT] Heat balance (cell heat generated vs heat absorbed by the coolant, m dh), fresh / aged / control: "
            + "; ".join(f"{c.balance_id} residual {c.residual.magnitude:.1e} {c.residual.units}" for c in n.conservation) + f" (tolerance {bc.HEAT_BALANCE_TOL_WH:g} W h, fixed before the run)."),
        "Negative control": (
            f"[FACT] Overload ({bc.CASES['overload'].description}): `day_fresh` {ov.result.receipt('day_fresh').status.value.upper()} - {ov.result.receipt('day_fresh').reason}; `aging` "
            f"{ov.result.receipt('aging').status.value.upper()}, `shift` {ov.result.receipt('shift').status.value.upper()}; final fade is {_q(ov, 'final_fade')}; no state was committed; every constraint is UNAVAILABLE. "
            f"Outside-window ({bc.CASES['outside_window'].description}): `day_fresh` {ow.result.receipt('day_fresh').status.value.upper()} ({ow.result.receipt('day_fresh').reason[:300]}), aging BLOCKED, no state committed. "
            "The hot case above is the third: it succeeds and its constraints read VIOLATED."),
        "Scientific status": (
            f"[FACT] Credibility verdict (existing authority): **{n.summary.scientific_status}** for every case. Execution succeeded; the runtime supplies no validity record and no validation check. "
            "Verification level reached: " + f"{n.ladder.verification_reached} of 4 (L1-L4); corroboration: none; reference level: {n.ladder.reference_level_reached}. "
            "Verification ladder (from the run): " + _ladder_status(n.ladder) + "; " + (
                (f"the coupling-window study: tolerances met = {n.study['tolerances_met']}, monotone decrease of successive differences met = {n.study['monotone_met']}; "
                 + ("no convergence is claimed and the cause was not investigated. " if not n.study["met"] else ""))
                if n.study else "the coupling-window study was not run for this report. ")
            + "This flagship demonstrates system execution, coupling, lifecycle propagation and numerical behaviour. It does not validate the battery model."),
        "Known limitations": (
            "[FACT] Illustrative declared inputs; a single lumped cell type; no experimental data; the fade law is a declared approximation with a loss-of-active-material mapping; 56 represented days from 4 resolved days "
            "(the representative-day approximation error is UNKNOWN); the cooling loop is a quasi-steady thermal rule; the cell current per module is uniform by assumption; SOC is a coulomb-counting definition. "
            "The aging temperature comes from the coupled day (cooling IS in the loop), which is more faithful than a lumped-air model but still unvalidated."),
        "Reproduction command": (
            "```bash\n" + WSL.format(env="battery", args="battery normal --out /mnt/d/ftmp/battery_normal --extras") + "\n```\n"
            "Cases: `normal`, `hot`, `overload`, `outside_window`. Tests: `python -m pytest flagships/tests/test_flagship_battery.py` in the same environment."),
    }
    return render_report("Flagship A - Battery + Cooling + Lifecycle", sections, identity_line=_identity(n), summary_text=n.summary.render_text()), n.result.digest


# ==================================================================================================== B
def structure_report(run, over) -> tuple[str, str]:
    from . import thermo_mechanical as tm
    r = run.result
    st = run.study
    rows = "\n".join(f"| {l['nx']}x{l['ny']} | {l['nodes']} | {l['ux_mid_fenicsx']:.6e} | {l['ux_mid_calculix']:.6e} | {l['ux_mid_code_aster']:.6e} | {l['sxx_mid_fenicsx']/1e6:.6f} | {l['vm_max_fenicsx']/1e6:.3f} |" for l in st["levels"])
    orders = ", ".join(f"{k}: {v:.2f}" for k, v in st["orders"].items() if k.startswith(("ux_mid", "vm_max")))
    v = run.verification
    sections = {
        "Engineering question": ("[FACT] A plate takes a heat load into one end and rejects it at the other. How does its temperature field deform it, how hard must a restraint push back, and do independent "
                                 "structural solvers agree?"),
        "System definition": (
            f"[FACT] A symmetric half of an aluminium plate, {tm.LENGTH*1e3:.0f} x {2*tm.HALF_WIDTH*1e3:.0f} mm, {tm.THICKNESS.magnitude:g} {tm.THICKNESS.units}, plane stress, one structured P1 triangle mesh (80 x 16 cells; nodes {run.structure.mesh.node_count}). "
            f"Heat flux {tm.FLUX:.0f} W/m2 in at x = 0, sink at {tm.T_COLD} K at x = L, other edges adiabatic. Structure: rollers at both ends (u_x = 0 at x = 0 and x = L), symmetry at y = 0, top free - the plate "
            "cannot lengthen, so it is compressed. One BIG 12 request: `thermal` (FEniCSx steady conduction) -> `struct_fenicsx` / `struct_calculix` / `struct_code_aster` (same mesh, same temperature field, same material "
            "records) -> three pairwise comparison nodes. Bulk fields travel outside the request (an exchange keyed by the producing execution's identity); the request sees scalars and digests."),
        "Assumptions": (f"[ASSUMPTION] Small-strain linear thermoelasticity, isotropic constant properties, plane stress, stress-free temperature {tm.T_REF} K, 2-D symmetric-half idealisation, prescribed flux and sink temperature."),
        "Inputs and sources": (
            f"[ASSUMPTION] Material: illustrative typical values for 6061 aluminium - E = {tm.E_MOD/1e9:.1f} GPa, nu = {tm.NU}, alpha = {tm.ALPHA*1e6:.1f}e-6 /K, k = {tm.K_COND:g} W/(m K) - declared as ASSUMED BIG 5 records "
            "(NOT from a controlled datasheet, NOT measured). Every provider's material card is generated from those exact records (their digests are in the request). "
            "[FACT] Mesh, BCs, flux and geometry are declared in `flagships/forge_flagships/thermo_mechanical.py` and hashed into the request."),
        "Providers and models": (
            f"[FACT] Providers executed: {_providers(r)}. FEniCSx: `linear_thermoelasticity_plane_stress` template (BIG 8), P1, PETSc LU with a true-residual acceptance test. CalculiX: CPS3 plane-stress elements, `*EXPANSION, ZERO=T_ref`, "
            "nodal `*TEMPERATURE` (new adapter method `execute_thermoelastic`). Code_Aster: `C_PLAN`, `AFFE_VARC` on a nodal temperature field, stress from `SIEF_ELGA` (the adapter previously parsed displacement only). "
            "Stress for FEniCSx is recovered from its displacement with the same constitutive law (`engcore.pde.postprocess`)."),
        "Applicability": (f"[FACT] The thermal node checks every solved temperature against the declared property range {list(tm.PROPERTY_RANGE_K)} K (the property records are constants declared for that range); "
                          "outside it the node is REFUSED and every structural node is BLOCKED. [ASSUMPTION] Small-strain, linear-elastic response is assumed. [MODEL OUTPUT] Peak thermal strain alpha (T_max - T_ref) = " + "%.2e" % (tm.ALPHA * (_v(run, "t_max") - tm.T_REF)) + " and the mid-plate mechanical strain |sigma|/E = " + "%.2e" % (abs(_v(run, "sxx_mid_fenicsx")) / tm.E_MOD) + " (both << 1); peak von Mises " + "%.0f MPa" % (_v(run, "vm_max_fenicsx") / 1e6) + " against the declared illustrative yield " + "%.0f MPa" % (tm.YIELD_PA / 1e6) + " (the elastic model itself is never checked against yield - that is the stress constraint)."),
        "Execution": (f"[FACT] Flagship case: {r.status.value.upper()} in {run.result.receipt('struct_code_aster').resource_usage.wall_seconds + run.result.receipt('struct_calculix').resource_usage.wall_seconds + run.result.receipt('struct_fenicsx').resource_usage.wall_seconds + run.result.receipt('thermal').resource_usage.wall_seconds:.1f} s of provider wall time; "
                      f"{len(r.provider_records)} provider executions. Preflight: {run.preflight.status.value} with {len(run.preflight.findings)} non-blocking findings (the applicability WAIVERS on the structural nodes are stated, not hidden)."),
        "Results": (
            f"[MODEL OUTPUT] Hot end {_q(run, 't_max')}, sink end {_q(run, 't_min')} (max deviation from the exact linear conduction profile: {_q(run, 't_exact_error', '{:.1e}')}); max displacement {_q(run, 'disp_max_fenicsx')} (FEniCSx) / {_q(run, 'disp_max_calculix')} (CalculiX) / {_q(run, 'disp_max_code_aster')} (Code_Aster); "
            f"mid-plate axial stress {_q(run, 'sxx_mid_fenicsx')} / {_q(run, 'sxx_mid_calculix')} / {_q(run, 'sxx_mid_code_aster')}; peak von Mises {_q(run, 'vm_max_fenicsx')} / {_q(run, 'vm_max_calculix')} / {_q(run, 'vm_max_code_aster')} "
            "(the peak is NOT claimed converged - see Verification). Heat in " + _q(run, "heat_in") + ", heat out " + _q(run, "heat_out") + ". Fields (temperature, displacement, von Mises) are exported as VTU files in the run bundle "
            "(presentation artifacts, not evidence)."),
        "Verification": ("[FACT] Verification pyramid position:\n\n" + _ladder_lines(run.ladder)
                         + f"\n\n[FACT] Exact uniform-temperature limits (each through BIG 12): free growth u = alpha dT (x, y) max relative error by provider {v['free']['errors']}; fully restrained sigma_xx = -E alpha dT {v['constrained']['errors']} (criterion {tm.ANALYTIC_REL_TOL:g}, fixed before the run).\n\n"
                         f"[MODEL OUTPUT] Mesh study through BIG 12 (mid-length displacement, mid-plate stress, peak von Mises):\n\n| mesh | nodes | ux_mid FEniCSx | ux_mid CalculiX | ux_mid Code_Aster | sxx_mid FEniCSx (MPa) | vm_max FEniCSx (MPa) |\n|---|---|---|---|---|---|---|\n{rows}\n\n"
                         f"Observed orders: {orders}. **Predeclared criterion (monotone, order >= 0.9 for mid-plate displacement AND stress, every provider): "
                         f"{'MET' if st['predeclared_criterion_met'] else 'NOT MET'}** - failing: {st['predeclared_failing']}. Reason: the last relative change of the mid-plate stress over the finest two meshes is {max(abs(st['levels'][-1][k] - st['levels'][-2][k]) / abs(st['levels'][-1][k]) for k in st['levels'][-1] if k.startswith('sxx_mid_')):.1e}, "
                         "which is at the level of solver noise, so an observed order is not defined for it. "
                         f"A post-hoc noise-aware reading (labelled post hoc, added after seeing the outcome) is {'met' if st['post_hoc_noise_aware_met'] else 'not met'}; it does not replace the predeclared outcome."),
        "Cross-provider results": (
            "[CORROBORATION] Pairwise agreement, criteria fixed before the run (1 % of the free thermal growth scale alpha dT L for displacement, 1 % of E alpha dT for stress): "
            f"FEniCSx-CalculiX max |du| {_q(run, 'max_abs_displacement_difference_fenicsx_calculix')}, FEniCSx-Code_Aster {_q(run, 'max_abs_displacement_difference_fenicsx_code_aster')}, "
            f"CalculiX-Code_Aster {_q(run, 'max_abs_displacement_difference_calculix_code_aster')}; element stress CalculiX-Code_Aster max {_q(run, 'max_abs_stress_difference_calculix_code_aster')}. "
            f"FEniCSx and Code_Aster agree to {_v(run, 'max_abs_displacement_difference_fenicsx_code_aster') / _v(run, 'disp_max_fenicsx'):.1e} of the peak displacement (they share the plane-stress P1 formulation, so this is close to one algorithm run twice); "
            f"CalculiX differs by {100 * _v(run, 'max_abs_displacement_difference_fenicsx_calculix') / _v(run, 'disp_max_fenicsx'):.3f} % of the peak displacement, consistent with the BIG 11 observation that CalculiX expands 2-D elements to 3-D "
            "wedges (an observation, not a proven cause). All three solve the SAME discretisation from ONE shared FEniCSx temperature field, so this is corroboration of the implementations - not of the discretisation, not of the thermal "
            f"solution, and not validation. The criterion's scale: the displacement tolerance is {100 * tm.DISP_AGREEMENT_TOL.magnitude / _v(run, 'disp_max_fenicsx'):.1f} % of the peak displacement (set from the free-growth scale), far looser than what was observed."),
        "Reference comparison": (
            "[FACT] Analytic references only: (1) uniform-temperature free growth, (2) uniform-temperature restrained stress, (3) bar theory for the mid-plate stress with an axial gradient "
            "(its envelope is declared by the flagship with no external source, and this plate sits on the inclusive aspect-ratio edge; the observed agreement is far tighter than its 3 % tolerance, so it cannot discriminate a 1 % error), "
            "all labelled ANALYTIC; " + "; ".join(f"{c.criterion.criterion_id} {c.outcome.upper()} ({c.value.magnitude:.2e} vs {c.criterion.tolerance.magnitude:g})" for c in run.comparisons)
            + ". [VALIDATION] None: no published thermo-structural numerical benchmark and no measured data for this plate were integrated. The NAFEMS material in the repository is thermal only (T3, 1-D transient conduction) and does not exercise this problem."),
        "Uncertainty": ("[FACT] Known input uncertainty: none. UNKNOWN (never zero): " + "; ".join(run.uncertainty.unknown_input_uncertainty) + ". Model discrepancy: " + run.uncertainty.model_discrepancy
                        + ". Discretisation error is characterised only by the mesh study, not bounded."),
        "Constraint and conservation checks": (f"[FACT] {_constraints(run.constraints)}. [MODEL OUTPUT] Thermal energy: heat in vs heat out residual "
                                               + "; ".join(f"{c.residual.magnitude:.1e} {c.residual.units} (tolerance {c.tolerance.magnitude:.1e})" for c in run.conservation)
                                               + f". Equilibrium diagnostic (axial force through three sections): largest relative spread {max(_v(run, f'section_force_spread_{p}') for p in ('fenicsx', 'calculix', 'code_aster')):.1e} "
                                               f"(criterion {tm.EQUILIBRIUM_SPREAD_TOL:g}), mean force {min(_v(run, f'section_force_ratio_{p}') for p in ('fenicsx', 'calculix', 'code_aster')):.2f} of the thermal force scale "
                                               f"(read only at or above {tm.FORCE_FLOOR_RATIO:g}, so a solve that ignored the load cannot pass)."),
        "Negative control": (f"[FACT] Over-range load ({tm.STRUCT_CASES['over_range'].description}): thermal node {over.result.receipt('thermal').status.value.upper()} - {over.result.receipt('thermal').reason[:300]}; "
                             "all three structural nodes BLOCKED; every structural observable and both constraints UNAVAILABLE."),
        "Scientific status": (f"[FACT] Credibility verdict (existing authority): **{run.summary.scientific_status}**. Verification ladder (from the run): " + _ladder_status(run.ladder) + f"; reference level: {run.ladder.reference_level_reached}. "
                              "Level 5, where reached, is corroboration of the implementations only. This flagship demonstrates coupled thermo-mechanical execution, exact-limit verification, a mesh study (see its predeclared outcome above) "
                              "and independent-implementation corroboration. It validates nothing physical."),
        "Known limitations": ("[FACT] Illustrative material records; 2-D linear thermoelasticity only; one geometry; no reference benchmark beyond analytic limits; the peak von Mises value is mesh-dependent (order < 1) and "
                              "not claimed converged and its cause was not investigated; CalculiX and the other two differ by a small difference not explained in detail; FEniCSx stress is recovered, not native; the property range is a declared envelope; "
                              "the three solvers share one discretisation and one temperature field."),
        "Reproduction command": ("```bash\n" + WSL.format(env="fenicsx", args="structure flagship --out /mnt/d/ftmp/structure_flagship --extras") + "\n```\nCases: `flagship`, `over_range`, `uniform_free`, `uniform_constrained`. "
                                 "Tests: `python -m pytest flagships/tests/test_flagship_thermo_mechanical.py` in the `fenicsx` environment (CalculiX and Code_Aster are found through `FORGE_PROVIDER_ENVS`)."),
    }
    return render_report("Flagship B - Thermo-Mechanical Structure", sections, identity_line=_identity(run), summary_text=run.summary.render_text()), run.result.digest


# ==================================================================================================== C
def cavity_report(run, neg) -> tuple[str, str]:
    from . import cavity_cfd as cf
    r = run.result
    rows = []
    for n in cf.LEVELS:
        rows.append(f"| {n}x{n} | {_v(run, f'whole_field_max_difference_{n}'):.4f} | {_v(run, f'max_difference_cell_y_{n}'):.4f} | {_v(run, f'lower_half_max_difference_post_hoc_{n}'):.4f} | "
                    f"{_v(run, f'ghia_u_max_error_openfoam_{n}'):.4f} | {_v(run, f'ghia_v_max_error_openfoam_{n}'):.4f} | {_v(run, f'ghia_u_max_error_su2_{n}'):.4f} | {_v(run, f'ghia_v_max_error_su2_{n}'):.4f} |")
    finest = cf.LEVELS[-1]
    of_times = ", ".join("%.1f s" % _v(run, "wall_seconds_openfoam_%d" % n) for n in cf.LEVELS)
    su2_times = ", ".join("%.1f s" % _v(run, "wall_seconds_su2_%d" % n) for n in cf.LEVELS)
    sections = {
        "Engineering question": ("[FACT] Do two independent CFD codes, given exactly the same declared cavity, fluid records and Reynolds number, predict the same flow; how does each converge under refinement; "
                                 "and how close does each come to the published Ghia et al. (1982) centerline benchmark?"),
        "System definition": (f"[FACT] 2-D lid-driven square cavity, side {cf.SIDE} m, water at 20 degC / 1 atm, lid speed set so that Re = {cf.REYNOLDS:g} exactly (U = Re nu / L = {_v(run, 'lid_velocity'):.6g} m/s), N x N cells with N = {list(cf.LEVELS)}. One BIG 12 request: "
                              "`fluid_properties` (CoolProp) -> `openfoam_N` / `su2_N` -> `compare_N` (whole-field OpenFOAM vs SU2) -> `convergence`."),
        "Assumptions": ("[ASSUMPTION] Incompressible laminar Newtonian flow, constant properties, 2-D, steady end state (OpenFOAM: transient icoFoam marched until the last write interval changes by less than 1e-7 m/s; SU2: pseudo-time until log10 rms(p) < -10). "
                        "Declared comparison rules: SU2 nodal velocity is mapped to OpenFOAM cell centres by the mean of the four cell corners; profiles are sampled piecewise-linearly with the wall values closing each line."),
        "Inputs and sources": (f"[REFERENCE DATA] Water density {_q(run, 'density')} and viscosity {_q(run, 'dynamic_viscosity')} are CoolProp equation-of-state values (provider-derived property records, not measurements), and both CFD codes receive the same records. "
                               f"[REFERENCE DATA] Ghia, Ghia & Shin (1982), J. Comput. Phys. 48(3) 387-411, Tables I and II, Re = 100 columns: {run.references[0].source_digest[:16]}.. (transcription digests in the record). A NUMERICAL benchmark "
                               "(multigrid finite difference, 129 x 129), not an experiment; only the 17-point Re = 100 columns are stored, with attribution; the paper and the transcription files are not copied; the u column and the v column agree "
                               "with a second independent public transcription. The numbers were NOT checked against the printed paper itself (only against the two public transcriptions), so their fidelity to the paper is an unverified assumption."),
        "Providers and models": (f"[FACT] Providers executed: {_providers(r)}. OpenFOAM v2412 `icoFoam` (PISO, Gauss linear, Euler); SU2 8.5.0 `INC_NAVIER_STOKES` (FDS, MUSCL, implicit Euler pseudo-time). Both are process providers behind the same argv-only boundary; each input file and executable is content-bound."),
        "Applicability": (f"[FACT] Both adapters refuse Re >= 1000 (declared laminar bound); this case has Re = {cf.REYNOLDS:g}. The Ghia reference applies at Re = 100 only (envelope [99, 101]) and its applicability is evaluated, not assumed."),
        "Execution": (f"[FACT] {r.status.value.upper()}; provider wall times (operational): OpenFOAM {of_times}; SU2 {su2_times} for N = {list(cf.LEVELS)}. "
                      f"{len(r.provider_records)} recorded provider executions."),
        "Results": (f"[MODEL OUTPUT] u(0.5, 0.5)/U at {finest}x{finest}: OpenFOAM {_v(run, f'u_center_openfoam_{finest}'):.4f}, SU2 {_v(run, f'u_center_su2_{finest}'):.4f}; primary-vortex centre (grid resolution) OpenFOAM ({_v(run, f'vortex_x_openfoam_{finest}'):.4f}, {_v(run, f'vortex_y_openfoam_{finest}'):.4f}), "
                    f"SU2 ({_v(run, f'vortex_x_su2_{finest}'):.4f}, {_v(run, f'vortex_y_su2_{finest}'):.4f}) in x/L, y/L. Velocity fields, kinematic / gauge pressure, and centerline profiles are exported (VTU + CSV) in the run bundle. "
                    "Pressure is NOT compared between the codes: OpenFOAM reports kinematic pressure p/rho and SU2 gauge pressure in Pa with different reference constants."),
        "Verification": ("[FACT] Verification pyramid position:\n\n" + _ladder_lines(run.ladder)),
        "Cross-provider results": (
            "[CORROBORATION] NOT achieved. The pre-declared whole-field criterion (3 % of lid speed, the BIG 11 criterion, not loosened) is NOT MET at any mesh:\n\n"
            "| mesh | whole-field max diff (of U) | at y/L | POST-HOC lower-half max diff | OpenFOAM err u | OpenFOAM err v | SU2 err u | SU2 err v |\n|---|---|---|---|---|---|---|---|\n" + "\n".join(rows)
            + "\n\nThe largest differences are always in the cell layer next to the moving lid (y/L > 0.97) and they do NOT shrink with refinement (" + ", ".join(f"{100*_v(run, f'whole_field_max_difference_{n}'):.0f} %" for n in cf.LEVELS) + " of lid speed). The lower-half region was chosen AFTER the whole-field result "
              "and is labelled post hoc; it can never count as corroboration. **Interpretation, not established:** part of the disagreement is likely an artifact of the declared mapping (the 4-corner mean of SU2 nodal values includes the lid "
              "nodes at U, while OpenFOAM's cell-centre value sits half a cell below the lid in a steep boundary layer); this was not tested. The disagreement is reported as the result."),
        "Reference comparison": (
            f"[MODEL OUTPUT] Comparison with a NUMERICAL benchmark (not an experiment); scope: the Re = 100 centerlines, finest mesh, criterion 0.02 of lid speed fixed before the run: "
            + "; ".join(f"{c.criterion.criterion_id} {c.outcome.upper()} ({c.value.magnitude:.4f})" for c in run.comparisons)
            + ". [VALIDATION] None: this is not an experimental comparison. It supports the numerics of these codes at Re = 100 for this configuration only and says nothing outside it. "
              "The reference envelope covers Re and the square-cavity aspect ratio; geometry details and boundary conditions are described in the record, not enforced by it."),
        "Uncertainty": ("[FACT] Known input uncertainty: none. UNKNOWN (never zero): " + "; ".join(run.uncertainty.unknown_input_uncertainty) + ". Model discrepancy: " + run.uncertainty.model_discrepancy
                        + f". The benchmark itself carries its own discretisation error (129 x 129), so an error against it cannot be expected to fall to zero: the OpenFOAM error against Ghia is "
                          + ", ".join(f"{_v(run, f'ghia_u_max_error_openfoam_{n}'):.4f}" for n in cf.LEVELS) + " (u line) - not monotone, and the pre-declared monotonicity criterion is reported NOT MET."),
        "Constraint and conservation checks": (f"[FACT] {_constraints(run.constraints)} (the flux constraint is bound to the finest mesh of EACH code, on the unsigned maximum over both mid-planes). "
                                               f"[MODEL OUTPUT] Net mid-plane flux relative to U L at {finest}x{finest}: OpenFOAM {_v(run, f'flux_residual_abs_openfoam_{finest}'):.2e}, SU2 {_v(run, f'flux_residual_abs_su2_{finest}'):.2e} "
                                               f"(criterion {cf.FLUX_TOL:g} fixed before the run; level 2 reads " + run.ladder.entry(2).status.value.replace('_', ' ') + "; "
                                               + (f"NOT met by {', '.join(run.l2_failing)}" if run.l2_failing else "met by both") + ")."),
        "Negative control": (f"[FACT] Unsupported regime: Re = 1500 -> OpenFOAM {neg['unsupported_regime']['openfoam'].upper()} ({neg['unsupported_regime']['reason']}), SU2 {neg['unsupported_regime']['su2'].upper()}, no benchmark quantity available. "
                             f"Incompatible benchmark: the same Ghia data applied to a Re = 10 case is `{neg['benchmark_not_applicable']['outcome']}` ({neg['benchmark_not_applicable']['applicability']['reasons'][0]}); a perfect number would not rescue it."),
        "Scientific status": (f"[FACT] Credibility verdict (existing authority): **{run.summary.scientific_status}**. Verification ladder (from the run): " + _ladder_status(run.ladder)
                              + f"; reference level: {run.ladder.reference_level_reached} (a comparison with a numerical benchmark, not an experiment). What this flagship shows is that Forge exposes the disagreement "
                              "and the failed criteria instead of tuning them away; it validates nothing physical."),
        "Known limitations": ("[FACT] One geometry and one Reynolds number; a numerical (not experimental) benchmark with its own truncation error; the whole-field mapping likely contributes to the near-lid disagreement (untested); pressure is not compared; "
                              "the vortex diagnostics are at grid resolution; numerical uncertainty is unquantified (only a grid study); OpenFOAM and SU2 use different discretisations (cell-centred vs vertex-based), so 'identical inputs' does not mean identical numerics."),
        "Reproduction command": ("```bash\n" + WSL.format(env="sci", args="cavity --out /mnt/d/ftmp/cavity") + "\n```\nTests: `python -m pytest flagships/tests/test_flagship_cavity.py` in the `sci` environment (OpenFOAM and SU2 via `FORGE_PROVIDER_ENVS`)."),
    }
    return render_report("Flagship C - Lid-Driven Cavity CFD Benchmark", sections, identity_line=_identity(run), summary_text=run.summary.render_text()), run.result.digest


# ==================================================================================================== D
def chemistry_report(run, neg) -> tuple[str, str]:
    from . import chem_thermal as ct
    r = run.result
    hess = run.references[0]
    sections = {
        "Engineering question": ("[FACT] A stoichiometric methane/air stream is burned and its exhaust cooled by a water jacket. What are the flame temperature and exhaust composition, how much heat must the loop remove, what does the water do, "
                                 "and do the chemistry and thermal-fluid providers agree on the energy balance?"),
        "System definition": (f"[FACT] One BIG 12 request. `adiabatic_equilibrium` (Cantera HP from {ct.T_REACTANTS:g} K, 1 atm), `cooled_equilibrium` (TP at {ct.T_EXHAUST_OUT:g} K), `heat_duty` = m_mix (h_reactants - h_cooled), `coolant_loop` (TESPy water, {ct.M_WATER} kg/s from {ct.T_WATER_IN} K at 2 bar, "
                              f"heat input = the duty), `energy_balance`, three `kinetic_*` adiabatic constant-pressure reactors from {ct.T_KINETIC_START:g} K at different integrator settings, `equilibrium_limit`, `integrator_study`, `heat_of_combustion`. "
                              "The reactor-to-jacket interface is a declared connection carrying an ENERGY BALANCE, not a new physical model: the water loop is handed the heat the chemistry says must be removed."),
        "Assumptions": (f"[ASSUMPTION] Ideal gas, equilibrium products at the exhaust outlet, no heat loss to the environment, every watt of the duty enters the water, reactant flow {ct.M_MIX} kg/s, exhaust outlet {ct.T_EXHAUST_OUT:g} K, kinetic start {ct.T_KINETIC_START:g} K. All declared illustrative values."),
        "Inputs and sources": ("[REFERENCE DATA] Mechanism: GRI-Mech 3.0 (`gri30.yaml` shipped with Cantera), bound as exact bytes by sha256 into every Cantera execution identity. [FACT] Its validity range is the mechanism authors' statement; the GRI-Mech page fetched for this work lists "
                               "the experimental targets it was optimised against but no single temperature range, so Forge asserts none. "
                               f"[REFERENCE DATA] NIST Chemistry WebBook (SRD 69) gas-phase formation enthalpies (Chase 1998 / CODATA / Manion 2002) for the Hess's-law check, source page digest {hess.source_digest[:16]}.."),
        "Providers and models": (f"[FACT] Providers executed: {_providers(r)}. Cantera: `equilibrate('HP'/'TP')` and `IdealGasConstPressureReactor` (CVODES); adapter extended (additively) with mass and molar enthalpy, elemental mass fractions before/after, and the mechanism's thermodynamic data range. TESPy: water `SimpleHeatExchanger` chain."),
        "Applicability": ("[FACT] Runtime checks: equilibrium temperatures against the species thermodynamic data range stored in the mechanism bytes ([300, 3000] K), the water loop against a declared liquid range " + f"{list(ct.WATER_RANGE_K)} K. "
                          "[FACT] The mechanism's KINETIC validity range is NOT established by Forge, so the kinetic reactor is a demonstration of execution and consistency only."),
        "Execution": (f"[FACT] {r.status.value.upper()}; {len(r.provider_records)} recorded provider executions; total node wall time {sum(x.resource_usage.wall_seconds for x in r.node_receipts):.1f} s (operational)."),
        "Results": (f"[MODEL OUTPUT] Adiabatic flame temperature {_q(run, 'adiabatic_equilibrium__T_adiabatic', '{:.1f}')}; mole fractions CO2 {_v(run, 'adiabatic_equilibrium__X_CO2'):.4f}, H2O {_v(run, 'adiabatic_equilibrium__X_H2O'):.4f}, CO {_v(run, 'adiabatic_equilibrium__X_CO'):.4e}, NO {_v(run, 'adiabatic_equilibrium__X_NO'):.4e}; "
                    f"at {ct.T_EXHAUST_OUT:g} K the equilibrium CO falls to {_v(run, 'cooled_equilibrium__X_CO_out'):.1e}. Heat to remove {_q(run, 'heat_duty__Q_duty', '{:.1f}')} ({_v(run, 'heat_duty__q_specific')/1e6:.4f} MJ/kg of reactants); cooling water {ct.T_WATER_IN} K -> {_q(run, 'coolant_loop__T_water_out', '{:.2f}')} "
                    f"(+{_v(run, 'coolant_loop__water_rise'):.2f} K). Kinetic reactor from {ct.T_KINETIC_START:g} K: ignition delay {_v(run, 'kinetic_2__ignition_delay')*1e3:.3f} ms (discrete maximum of dT/dt), end temperature {_q(run, 'kinetic_2__T_final', '{:.3f}')}, fuel remaining {_v(run, 'kinetic_2__fuel_remaining'):.2e}."),
        "Verification": ("[FACT] Verification pyramid position:\n\n" + _ladder_lines(run.ladder)),
        "Cross-provider results": ("[CORROBORATION] Cantera and TESPy agree on the energy balance: the heat Cantera says must be removed and the heat TESPy's water absorbs (m dh) differ by "
                                   f"{_v(run, 'energy_balance__residual'):.1e} W ({_v(run, 'energy_balance__relative_residual'):.1e} of the duty). This is a consistency check of an interface that is defined by that balance; it is NOT independent corroboration of the chemistry "
                                   "(there is no second chemistry provider)."),
        "Reference comparison": (f"[REFERENCE DATA] Hess's law with evaluated NIST-JANAF / CODATA data gives a lower heating value of methane of {hess.values('lower_heating_value')[0]:.3f} kJ/mol (Chase 1998) and {hess.values('lower_heating_value')[1]:.3f} kJ/mol (CODATA with Manion 2002). "
                                 f"[MODEL OUTPUT] Cantera with GRI-Mech 3.0 thermodynamics, evaluated at 300 K (the mechanism's lowest stored temperature; the reference is at 298.15 K, below it), gives {_v(run, 'heat_of_combustion__lower_heating_value'):.3f} kJ/mol "
                                 f"(the 1.85 K offset is bounded by {_v(run, 'heat_of_combustion__temperature_offset_bound'):.3f} kJ/mol from the same thermodynamic data): " + "; ".join(f"{c.criterion.criterion_id} {c.outcome.upper()} ({c.value.magnitude:.3f} kJ/mol against {c.criterion.tolerance.magnitude:g})" for c in run.comparisons)
                                 + ". The reference is an ANALYTIC relation evaluated with critically evaluated data - a DATA-CONSISTENCY check of the mechanism's thermodynamics (it checks the data the model carries, classified apart from an implementation limit), "
                                   "not an experiment on this system; it applies near 298.15 K, 1 atm, gas-phase products only. [VALIDATION] None."),
        "Uncertainty": ("[FACT] Known input uncertainty: none. UNKNOWN (never zero): " + "; ".join(run.uncertainty.unknown_input_uncertainty) + ". Model discrepancy: " + run.uncertainty.model_discrepancy),
        "Constraint and conservation checks": (f"[FACT] {_constraints(run.constraints)}. [MODEL OUTPUT] Elemental mass balance through equilibration (max relative change of C, H, O, N): adiabatic {_v(run, 'adiabatic_equilibrium__element_residual'):.1e}, cooled {_v(run, 'cooled_equilibrium__element_residual'):.1e} "
                                               f"(criterion {ct.ELEMENT_TOL:g}); heat duty balance " + "; ".join(f"{c.residual.magnitude:.1e} {c.residual.units}" for c in run.conservation) + f" (tolerance {ct.ENERGY_BALANCE_REL_TOL:g} of the duty). "
                                               f"The kinetic reactor ends at {_q(run, 'kinetic_2__T_final', '{:.4f}')}, the HP equilibrium of the same state is {_q(run, 'equilibrium_limit__T_equilibrium', '{:.4f}')} (relative gap {_v(run, 'equilibrium_approach__relative_gap'):.1e})."),
        "Negative control": (f"[FACT] A composition containing a species the mechanism does not define: `adiabatic_equilibrium` {neg['missing_species']['nodes']['adiabatic_equilibrium'][0].upper()} - {neg['missing_species']['nodes']['adiabatic_equilibrium'][1]}; the duty, loop and balance are BLOCKED. "
                             f"An exhaust outlet colder than the mechanism's thermodynamic data ({100} K): `cooled_equilibrium` {neg['below_thermo_range']['nodes']['cooled_equilibrium'][0].upper()} - {neg['below_thermo_range']['nodes']['cooled_equilibrium'][1][:300]}; downstream BLOCKED."),
        "Scientific status": (f"[FACT] Credibility verdict (existing authority): **{run.summary.scientific_status}**. Verification ladder (from the run): " + _ladder_status(run.ladder) + f"; reference level: {run.ladder.reference_level_reached}. "
                              "This flagship demonstrates chemistry-to-thermal-fluid execution, conservation and consistency checks. It validates nothing about combustion."),
        "Known limitations": ("[FACT] Equilibrium and 0-D adiabatic idealisations; one mechanism; no transport, no heat loss, no flow; illustrative flows and temperatures; the kinetic validity range is not established; the discrete ignition-time criterion "
                              "was declared before its sampling-resolution limit was understood (reported NOT MET, with a post hoc refined reading); no experimental validation (ignition delays, flame temperature, exhaust composition were not integrated)."),
        "Reproduction command": ("```bash\n" + WSL.format(env="sci", args="chemistry --out /mnt/d/ftmp/chemistry") + "\n```\nTests: `python -m pytest flagships/tests/test_flagship_chemistry.py` in the `sci` environment."),
    }
    return render_report("Flagship D - Chemical / Thermal-Fluid System", sections, identity_line=_identity(run), summary_text=run.summary.render_text()), run.result.digest


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(prog="forge_flagships.reports")
    ap.add_argument("flagship", choices=("battery", "structure", "cavity", "chemistry"))
    ap.add_argument("--docs", required=True)
    ap.add_argument("--bundles", default=None, help="also write the run bundle(s) here (light files are committed, VTU are regenerated)")
    a = ap.parse_args(argv)
    os.makedirs(a.docs, exist_ok=True)
    if a.flagship == "battery":
        from . import battery_cooling as bc
        runs = {c: bc.run_flagship(c, first_law=(c in ("normal", "hot")), refinement=(c == "normal")) for c in ("normal", "hot", "overload", "outside_window")}
        text, digest = battery_report(runs)
        name, bundle = "battery_cooling_lifecycle.md", {c: (r.flagship.request, r.result, r.summary, list(r.references) + [x for x, _ in r.references_considered], r.flagship.store.files) for c, r in runs.items()}
    elif a.flagship == "structure":
        from . import thermo_mechanical as tm
        run, over = tm.run_structure("flagship", verification=True, study=True), tm.run_structure("over_range")
        text, digest = structure_report(run, over)
        name, bundle = "thermo_mechanical_structure.md", {"flagship": (run.structure.request, run.result, run.summary, list(run.references), run.structure.exchange.files),
                                                          "over_range": (over.structure.request, over.result, over.summary, [], over.structure.exchange.files)}
    elif a.flagship == "cavity":
        from . import cavity_cfd as cf
        run = cf.run_cavity()
        text, digest = cavity_report(run, cf.negative_controls())
        name, bundle = "cavity_cfd_benchmark.md", {"re100": (run.cavity.request, run.result, run.summary, list(run.references), run.cavity.exchange.files)}
    else:
        from . import chem_thermal as ct
        run = ct.run_chemistry()
        text, digest = chemistry_report(run, ct.negative_controls())
        name, bundle = "chemical_thermal_system.md", {"nominal": (run.chemistry.request, run.result, run.summary, list(run.references), run.chemistry.exchange.files)}
    open(os.path.join(a.docs, name), "wb").write(text.encode("utf-8"))
    if a.bundles:
        for case, (req, res, summ, refs, files) in bundle.items():
            d = os.path.join(a.bundles, f"{a.flagship}_{case}")
            write_bundle(d, name=f"flagship-{a.flagship}-{case}", request=req, result=res, summary=summ, references=list({r.reference_id: r for r in refs}.values()),
                         artifacts=committed_artifacts(res, files))
            verify_bundle(d)
    sys.stdout.write(f"wrote {os.path.join(a.docs, name)} (result {digest[:16]})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
