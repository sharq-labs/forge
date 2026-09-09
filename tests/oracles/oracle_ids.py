"""The register every oracle test declares itself against.

An oracle test that did not say where its expected value came from would be
indistinguishable from a regression test after one reading, which is the
confusion this whole directory exists to prevent. So each test carries an
``ORACLE_ID``, each id is described here once, and a test naming an id that is
not here fails.

``independent`` is the field to read. It is False for entries that share a
governing equation with the thing they check, and those entries are kept
because a same-equation cross-check still catches transcription errors,
sign errors and unit errors -- it just cannot catch a wrong equation, and
saying so is the point.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Oracle:
    oracle_id: str
    oracle_class: str
    statement: str
    source: str
    #: Independent of Forge's implementation AND of the benchmark generator?
    independent: bool
    #: Runs as code, as opposed to being a citation a human must check?
    executable: bool
    limitations: str


_ORACLES = (
    Oracle(
        "ORA-DIM-GROUPS",
        "INDEPENDENT_ANALYTIC",
        "Bi = hL/k, Fo = alpha*t/L^2 = (t/tau)/Bi, tau = C/(hA), "
        "Ra = g*beta*dT*L^3/(nu*alpha_f) = g*beta*dT*L^3*Pr/nu^2, Re = vL/nu "
        "are dimensionless as defined, and equal an independent evaluation.",
        "Standard definitions; Incropera, DeWitt, Bergman & Lavine, "
        "Fundamentals of Heat and Mass Transfer, 6th ed. (2007), Ch. 5 and 9.",
        independent=True,
        executable=True,
        limitations=(
            "Verifies the DEFINITIONS as implemented, and the dimensional "
            "identity. Says nothing about whether the bounds placed on these "
            "groups are the right bounds."
        ),
    ),
    Oracle(
        "ORA-RAD-LINEARIZATION",
        "INDEPENDENT_ANALYTIC",
        "The linearized radiation coefficient h_r must equal the derivative of "
        "the exact Stefan-Boltzmann exchange with respect to surface "
        "temperature, evaluated between the two temperatures: "
        "h_r = eps*sigma*(Ts^2+Tsur^2)(Ts+Tsur), which is what makes "
        "q_rad = h_r (Ts - Tsur) exact rather than approximate.",
        "Derived here by central finite difference of "
        "eps*sigma*(Ts^4 - Tsur^4) and by exact algebraic factorisation. "
        "Stefan-Boltzmann constant from CODATA 2018: 5.670374419e-8 W/m^2/K^4.",
        independent=True,
        executable=True,
        limitations=(
            "Assumes a grey diffuse surface with view factor 1 to large "
            "surroundings, which is the configuration Forge declares."
        ),
    ),
    Oracle(
        "ORA-FREE-CONVECTION-CROSS",
        "INDEPENDENT_REFERENCE_DATA",
        "Churchill-Chu (1975) and McAdams (1954) are two independently "
        "published correlations for laminar free convection from a vertical "
        "isothermal plate. Over their common range they must agree to within "
        "the scatter the literature reports for such correlations.",
        "Churchill & Chu, Int. J. Heat Mass Transfer 18(11) 1323-1329 (1975); "
        "McAdams, Heat Transmission, 3rd ed. (1954), Nu = 0.59 Ra^(1/4) for "
        "1e4 <= Ra <= 1e9.",
        independent=True,
        executable=True,
        limitations=(
            "Two correlations of the same configuration are not fully "
            "independent of each other -- both are fits to overlapping "
            "experimental corpora. Agreement bounds a transcription error, "
            "not the physics."
        ),
    ),
    Oracle(
        "ORA-LUMPED-ODE",
        "INDEPENDENT_ANALYTIC",
        "The first-order lumped closed form T(t) = T_inf + (T0 - T_inf) "
        "exp(-t/tau) must agree with a numerical integration of the ODE "
        "C dT/dt = Q - hA (T - T_amb) it claims to solve.",
        "Classical fourth-order Runge-Kutta, implemented here, with the step "
        "refined until Richardson extrapolation shows the discretisation error "
        "below the comparison tolerance.",
        independent=True,
        executable=True,
        limitations=(
            "Algorithmically independent -- a marching integrator against a "
            "closed form -- but both describe the SAME governing balance. It "
            "verifies the solution of the equation, not the choice of equation."
        ),
    ),
    Oracle(
        "ORA-NGSPICE-DC",
        "INDEPENDENT_EXECUTABLE",
        "Node voltages, branch current and resistor dissipation of a DC "
        "resistive circuit must match a general-purpose circuit simulator "
        "given the same netlist.",
        "ngspice (U.C. Berkeley CAD Group), invoked as a subprocess. The "
        "netlist is written by this suite, not by Forge's adapter, and the "
        "output is parsed here.",
        independent=True,
        executable=True,
        limitations=(
            "Skipped where ngspice is absent. Covers linear resistive DC only "
            "-- the regime Forge's dc domain implements."
        ),
    ),
    Oracle(
        "ORA-TCR-LIMITS",
        "INDEPENDENT_ANALYTIC",
        "R(T) = R_ref (1 + alpha (T - T_ref)) must reduce to R_ref at "
        "T = T_ref for every alpha, be exactly linear in T, be independent of "
        "temperature when alpha = 0, and be symmetric under a simultaneous "
        "sign flip of alpha and (T - T_ref).",
        "Limiting-case and algebraic-identity analysis performed here.",
        independent=True,
        executable=True,
        limitations=(
            "Verifies the linear form's own algebra. Whether a linear TCR "
            "describes a given conductor over a given range is what the "
            "linearization band condition is for, and is not checked here."
        ),
    ),
    Oracle(
        "ORA-PEUKERT",
        "LITERATURE_REFERENCE",
        "Peukert's law: the available capacity falls with discharge rate as "
        "C_eff = C_ref (I_ref/I)^(k-1), equivalently the runtime satisfies "
        "t = H (C/(I H))^k. k = 1 must recover rate-independent capacity "
        "exactly.",
        "Peukert, W. (1897), Elektrotechnische Zeitschrift 18, 287-288; "
        "standard modern statement e.g. Linden & Reddy, Handbook of Batteries, "
        "3rd ed. (2002), Ch. 3.",
        independent=True,
        executable=True,
        limitations=(
            "Peukert is an empirical fit, valid over a limited rate range and "
            "at a fixed temperature. The oracle checks the algebra and the "
            "k = 1 limit, not the fit's applicability to any real cell."
        ),
    ),
    Oracle(
        "ORA-DIMENSIONAL",
        "INDEPENDENT_ANALYTIC",
        "Every scientific quantity Forge derives must carry the dimensions its "
        "defining equation implies, checked against dimensions assembled here "
        "from SI base units rather than from Forge's unit registry.",
        "SI base dimensions, composed independently in this suite.",
        independent=True,
        executable=True,
        limitations=(
            "A dimensionally correct formula can still be the wrong formula; "
            "this is a necessary condition, not a sufficient one."
        ),
    ),
    Oracle(
        "ORA-CONDUCTION-ANALYTIC",
        "INDEPENDENT_ANALYTIC",
        "du/dt = alpha d2u/dx2 with zero Dirichlet ends and u(x,0) = "
        "sin(pi x/L) has the closed solution u = sin(pi x/L) "
        "exp(-alpha pi^2 t/L^2). The initial condition IS the fundamental "
        "eigenmode, so there is no series and no truncation.",
        "Separation of variables, performed here. Standard result; e.g. "
        "Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007), Ch. 5.",
        independent=True,
        executable=True,
        limitations=(
            "Verifies the discretisation by convergence, not to round-off -- "
            "a discrete scheme is not supposed to equal the continuum."
        ),
    ),
    Oracle(
        "ORA-CONDUCTION-DISCRETE",
        "INDEPENDENT_ANALYTIC",
        "Backward Euler on the fundamental eigenmode has the closed-form "
        "amplification (1 + r mu_1)^-N with mu_1 = 4 sin^2(pi dx/(2L)) the "
        "second-difference eigenvalue, so the discrete answer is exact and "
        "needs no matrix.",
        "Eigenanalysis of the standard second-difference operator, performed "
        "here. No matrix is assembled and nothing is inverted.",
        independent=True,
        executable=True,
        limitations=(
            "Checks assembly and linear solve, NOT whether backward Euler is "
            "the right scheme for the problem."
        ),
    ),
    Oracle(
        "ORA-CSTR-STEADY",
        "INDEPENDENT_ANALYTIC",
        "At steady state the non-isothermal first-order CSTR satisfies "
        "C = a Cf/(a + k(T)) and a(Tf - T) + beta k(T) C - gamma(T - Tc) = 0, "
        "which reduces to one nonlinear equation in T solvable by bisection.",
        "Mass and energy balances written out here and solved with a bracketed "
        "bisection -- a different algorithm from the ODE march Forge runs. "
        "Standard model; e.g. Seborg, Edgar, Mellichamp & Doyle, Process "
        "Dynamics and Control, 3rd ed. (2011), Ch. 2.",
        independent=True,
        executable=True,
        limitations=(
            "Shares the governing balances with Forge, so it verifies the "
            "SOLUTION and not the choice of model. The CSTR admits multiple "
            "steady states; the oracle brackets the one the march reaches."
        ),
    ),
    Oracle(
        "ORA-CSTR-RK4",
        "INDEPENDENT_ANALYTIC",
        "The CSTR trajectory from a given initial state must agree with a "
        "classical Runge-Kutta march of the same two balances.",
        "RK4 implemented here; Forge integrates with SciPy. Algorithmically "
        "independent, tolerance set by Richardson refinement.",
        independent=True,
        executable=True,
        limitations="Same governing balances; verifies integration, not model.",
    ),
    Oracle(
        "ORA-BATTERY-COULOMB",
        "LITERATURE_REFERENCE",
        "Coulomb counting SoC(t) = SoC_0 - I t/(eta Q), with the discharge "
        "lasting steps * step_duration; C-rate = I/Q_nom; terminal voltage "
        "V = OCV(z) - I R_int for the Rint model.",
        "Plett, Battery Management Systems Volume I: Battery Modeling, Artech "
        "House (2015), Ch. 2-3.",
        independent=True,
        executable=True,
        limitations=(
            "The Rint model is an approximation with no diffusion or "
            "polarisation dynamics; the oracle checks its algebra and the "
            "contract, not its fidelity to a real cell."
        ),
    ),
)

ORACLE_REGISTER = {oracle.oracle_id: oracle for oracle in _ORACLES}


def oracle(oracle_id: str) -> Oracle:
    """Look an oracle up, refusing an id the register does not carry."""
    try:
        return ORACLE_REGISTER[oracle_id]
    except KeyError:
        raise AssertionError(
            f"{oracle_id!r} is not in ORACLE_REGISTER. An oracle test must "
            f"declare where its expected value came from; add the entry "
            f"before the test."
        ) from None
