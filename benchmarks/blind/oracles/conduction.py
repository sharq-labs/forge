"""Independent oracle for 1-D conduction realization applicability.

The question this domain poses is not "what is the temperature" but "is this
scheme applicable to this discretization". Two realizations of one diffusion
model are declared: backward Euler, which is A-stable and declares no
restriction, and FTCS, which is conditionally stable.

**Two oracles, and the second one is the interesting one.**

``evaluate`` forms the von Neumann criterion in closed form: the amplification
factor of the highest representable mode under FTCS is ``g = 1 - 4r`` with
``r = alpha dt / dx^2``, so ``|g| > 1`` once ``r > 1/2``.

``march_amplification`` is the independent numerical oracle: it seeds the grid
with the sawtooth ``(-1)^i`` -- exactly the highest mode -- actually marches
FTCS, and measures the growth. It shares no line of reasoning with the closed
form; it is the criterion's own prediction put to an experiment. Where the two
disagree the case is UNRESOLVED before the freeze and is not scored.

**The backward-Euler cases are CONTRACT_ONLY on purpose.** An A-stable scheme
has no stability restriction, so its declared applicability domain holds no
conditions -- and an empty domain assesses to UNKNOWN, because absence of
declared limits is not evidence of unlimited applicability. That is a claim
about the record's semantics rather than about diffusion, and the truth class
says so rather than dressing it up as physics.

Source: von Neumann stability analysis of the FTCS diffusion stencil; e.g.
Press et al., *Numerical Recipes*, 3rd ed., Sec. 20.2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .electrothermal import ConditionValue, OracleUnresolved
from .units import to_si

__all__ = ["ORACLE_ID", "ORACLE_VERSION", "SECOND_ORACLE_ID",
           "FTCS_STABILITY_LIMIT", "ConductionTruth", "evaluate",
           "march_amplification"]

ORACLE_ID = "blind.oracle.conduction1d.vonneumann"
SECOND_ORACLE_ID = "blind.oracle.conduction1d.ftcs_march"
ORACLE_VERSION = "1.0.0"

#: r <= 1/2. Not a convention: it is where |1 - 4r| reaches 1.
FTCS_STABILITY_LIMIT = 0.5

DIFFUSION_MODEL_ID = "thermal.conduction1d.linear_diffusion"
EXPLICIT_REALIZATION = "thermal.conduction1d.explicit_forward_euler"
IMPLICIT_REALIZATION = "thermal.conduction1d.implicit_backward_euler"

BOUNDS: dict[str, tuple[float | None, float | None, bool, bool]] = {
    "alpha": (0.0, None, True, True),
    "fourier_number": (None, FTCS_STABILITY_LIMIT, True, True),
}

CONDITION_DOMAIN = {"alpha": "conduction", "fourier_number": "conduction"}


@dataclass(frozen=True)
class ConductionTruth:
    verdict: str
    conditions: tuple[ConditionValue, ...]
    state: dict

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
        return "conduction"

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return ()


def _fourier(payload: dict) -> tuple[float, float, float, float]:
    length = to_si(payload["length"], "m")
    alpha = to_si(payload["diffusivity"], "m2/s")
    end_time = to_si(payload["end_time"], "s")
    n_cells = int(payload["n_cells"])
    n_steps = int(payload["n_steps"])
    if n_cells < 2 or n_cells % 2 != 0:
        raise OracleUnresolved(
            "outside_supported_model",
            f"n_cells must be even and at least 2, got {n_cells}; the midpoint "
            f"QoI is read as a nodal value")
    if n_steps < 1:
        raise OracleUnresolved("outside_supported_model",
                               f"n_steps must be at least 1, got {n_steps}")
    if length <= 0.0 or end_time <= 0.0:
        raise OracleUnresolved("invalid_sampled_state",
                               "length and end_time must be strictly positive")
    dx = length / n_cells
    dt = end_time / n_steps
    return alpha, dx, dt, alpha * dt / (dx * dx)


def evaluate(payload: dict) -> ConductionTruth:
    """Independent truth for one slab-and-scheme case."""
    alpha, dx, dt, fourier = _fourier(payload)
    realization = payload.get("realization", EXPLICIT_REALIZATION)

    def classify(name: str, value: float | None, model_id: str) -> ConditionValue:
        if value is None:
            return ConditionValue(name, model_id, None, "unknown", None, None,
                                  "not_supplied")
        minimum, maximum, min_incl, max_incl = BOUNDS[name]
        ok = True
        margin = position = None
        if minimum is not None:
            ok = ok and (value >= minimum if min_incl else value > minimum)
            margin = value - minimum
            position = value / minimum if minimum else value
        if maximum is not None:
            ok = ok and (value <= maximum if max_incl else value < maximum)
            upper = maximum - value
            margin = upper if margin is None else min(margin, upper)
            upper_position = value / maximum if maximum else value
            position = (upper_position if position is None
                        else max(position, upper_position))
        return ConditionValue(name, model_id, value,
                              "satisfied" if ok else "violated", margin, position)

    conditions = [classify("alpha", alpha, DIFFUSION_MODEL_ID)]
    if realization == EXPLICIT_REALIZATION:
        conditions.append(classify("fourier_number", fourier, realization))
        if any(c.status == "violated" for c in conditions):
            verdict = "NOT_SUPPORTED"
        elif any(c.status == "unknown" for c in conditions):
            verdict = "INSUFFICIENT_EVIDENCE"
        else:
            verdict = "SUPPORTED"
    else:
        # An A-stable scheme declares no conditions, and an EMPTY validity
        # domain assesses to UNKNOWN rather than to IN_DOMAIN. Absence of
        # declared limits is not evidence of unlimited applicability -- a
        # statement about the record, not about backward Euler, which really is
        # unconditionally stable.
        #
        # It is emitted as a CONDITION rather than only as a verdict, and that
        # is not bookkeeping. A consumer that derives the verdict from the
        # condition set -- which is what makes counterfactual repair exact --
        # saw an empty set of findings here and called the case SUPPORTED, so
        # 12 cases carried the opposite of their own truth. A gap that is not
        # in the condition set is a gap the reason channel cannot report.
        conditions.append(ConditionValue(
            "realization_applicability", realization, None, "unknown",
            None, None, "empty_validity_domain"))
        verdict = "INSUFFICIENT_EVIDENCE"
    return ConductionTruth(
        verdict=verdict, conditions=tuple(conditions),
        state={"fourier_number": fourier, "dx_m": dx, "dt_s": dt,
               "alpha_m2_s": alpha, "realization": realization,
               "amplification_factor": 1.0 - 4.0 * fourier})


def march_amplification(payload: dict, *, probe_steps: int = 200) -> dict:
    """SECOND ORACLE. March FTCS on the highest mode and measure the growth.

    Seeds the interior with the EXACT highest discrete eigenmode under
    homogeneous Dirichlet ends, ``v_i = sin(m pi i / n)`` with ``m = n - 1``,
    marches the explicit stencil, and measures the growth per step.

    **Why the exact mode and not the sawtooth.** The sawtooth ``(-1)^i`` is the
    highest mode of the INFINITE grid, and on a finite one with Dirichlet ends
    it is not an eigenvector, so marching it mixes modes and under-reports the
    growth. A first version of this oracle did that and disagreed with the
    closed form by 4% at ``r = 0.51`` -- not a defect in either, an artefact of
    seeding the wrong vector, and exactly the kind of thing a second oracle is
    supposed to have removed before it is trusted to convict anything.

    **The finite grid is slightly more forgiving than the bound, and that is
    the safe direction.** The discrete amplification is
    ``g = 1 - 4r sin^2(m pi / 2n)``, and ``sin^2(...) < 1`` for finite ``n``, so
    the true stability limit is a little ABOVE ``r = 1/2``. The declared bound
    is therefore conservative rather than wrong, and this function reports both
    numbers so a reader can see which is which. The only outcome that would
    falsify the bound is growth at ``r <= 1/2``, and that is reported
    separately as ``falsifies_bound``.

    Deliberately not the case's own ``n_steps``: this measures amplification
    per step, which is a property of ``r`` and the grid alone.
    """
    alpha, dx, dt, fourier = _fourier(payload)
    n_cells = int(payload["n_cells"])
    mode = n_cells - 1
    u = [0.0] * (n_cells + 1)
    for i in range(1, n_cells):
        u[i] = math.sin(mode * math.pi * i / n_cells)
    start = max(abs(x) for x in u)
    discrete_factor = abs(1.0 - 4.0 * fourier
                          * math.sin(mode * math.pi / (2.0 * n_cells)) ** 2)
    # How far the seeded mode may be allowed to decay before the measurement
    # stops being about it.
    #
    # `sin()` cannot represent the eigenvector exactly, so the seed carries
    # about 1e-16 of every OTHER mode, and the slowest of those decays far more
    # gently than the fastest. Once the seeded mode has fallen below that
    # contamination the geometric mean measures the contamination instead --
    # which is why this oracle reported a 0.62 gap at r = 0.2 while agreeing to
    # 1e-15 near the bound, where the highest mode decays slowly enough to
    # survive 200 steps.
    #
    # Marching only until the mode has decayed by 1e-10 keeps it six orders
    # above the contamination floor throughout.
    if 0.0 < discrete_factor < 1.0:
        affordable = int(-10.0 / math.log10(discrete_factor))
        steps = max(1, min(probe_steps, affordable))
    else:
        steps = min(probe_steps, 400)
    for _ in range(steps):
        updated = list(u)
        for i in range(1, n_cells):
            updated[i] = u[i] + fourier * (u[i + 1] - 2.0 * u[i] + u[i - 1])
        updated[0] = updated[n_cells] = 0.0
        u = updated
        peak = max(abs(x) for x in u)
        if not math.isfinite(peak) or peak > 1e100:
            return {"status": "amplified", "grew": True,
                    "fourier_number": fourier,
                    "asymptotic_factor": abs(1.0 - 4.0 * fourier),
                    "discrete_factor": discrete_factor,
                    "falsifies_bound": 0.0 <= fourier <= FTCS_STABILITY_LIMIT}
    end = max(abs(x) for x in u)
    measured = (end / start) ** (1.0 / steps) if start > 0.0 and end > 0.0 else 0.0
    grew = end > start * (1.0 + 1e-9)
    return {
        "status": "marched",
        "grew": grew,
        "fourier_number": fourier,
        "measured_factor": measured,
        "discrete_factor": discrete_factor,
        "asymptotic_factor": abs(1.0 - 4.0 * fourier),
        "steps_taken": steps,
        # The only way the declared bound is WRONG rather than conservative.
        # `0.0 <=` is not decoration. r = alpha dt / dx^2 is NEGATIVE when the
        # declared diffusivity is, and |1 - 4r| > 1 for every r < 0 -- so a
        # backwards-diffusing slab grows, trivially and correctly, and reading
        # that as a counterexample to the stability bound would convict a
        # theorem with a case it was never stated over. The von Neumann
        # criterion is a statement about a diffusion problem, and a negative
        # diffusivity is not one; `alpha > 0` is the condition that catches it.
        "falsifies_bound": grew and 0.0 <= fourier <= FTCS_STABILITY_LIMIT,
        # How far measurement and the discrete closed form disagree. A
        # material gap here means one of the two oracles is broken, and the
        # case is UNRESOLVED before the freeze rather than scored.
        "oracle_gap": abs(measured - discrete_factor),
    }
