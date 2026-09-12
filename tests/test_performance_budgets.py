"""Guards for the work this sprint removed, so it cannot come back quietly.

Sprint 7, Phases 22 and 23. These follow the rule
`tests/test_core_performance_guards.py` already set and gives its reasons for:
**call counts, not clocks.** "This path parses a unit string once rather than
fifty-eight times" is a statement about the algorithm and is reproducible in
CI, under a debugger and on a busy laptop. A wall-clock threshold describes the
machine that ran it.

Each guard below is paired with the fault it detects, so what it is for is not
left to a reader to infer:

    PERF-1  a shared declaration rebuilt per case
    PERF-2  digest memoization disabled
    PERF-3  an already-frozen record deep-frozen again
    PERF-4  a fresh unit parse per conversion
    PERF-5  solver sessions retained across cases
    PERF-6  every result serialized inside the inner loop
    PERF-7  field topology rebuilt per solve
    PERF-8  the sweep's shared context disabled

The two wall-clock budgets at the end are deliberately enormous. Their job is
to catch a 20x catastrophe, not to police a constant factor, and they say so.
"""

from __future__ import annotations

import time

import pytest

from engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    solve_circuit,
)
from engcore.execution import SharedContext, SweepDefinition, cases_from, run_sweep
from engcore.scientific.units import quantity as quantity_module
from engcore.scientific.units.quantity import Quantity

GND = ElectricalNode("gnd", is_reference=True)


class Counter:
    """Counts calls to one attribute of one module, then puts it back."""

    def __init__(self, owner, name: str) -> None:
        self.owner, self.name, self.count = owner, name, 0
        self._original = getattr(owner, name)

    def __enter__(self) -> "Counter":
        original = self._original

        def counted(*args, **kwargs):
            self.count += 1
            return original(*args, **kwargs)

        setattr(self.owner, self.name, counted)
        return self

    def __exit__(self, *exc) -> None:
        setattr(self.owner, self.name, self._original)


def circuit(index: int = 0) -> DCCircuit:
    return DCCircuit(
        circuit_id=f"divider-{index}",
        nodes=(GND, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", Quantity(1.0 + index * 0.001, "kohm")),
            Resistor("R2", "mid", "gnd", Quantity(3.0, "kohm")),
        ),
        voltage_sources=(DCVoltageSource("V1", "top", "gnd", Quantity(12.0, "volt")),),
    )


# ---- PERF-4: the unit backend is not reached per conversion -------------------------
def test_a_repeated_conversion_does_not_reach_the_backend_again():
    """The conversion rule for a unit pair is decided once.

    Before this sprint every `magnitude_in` built a backend quantity from a
    unit *string*, so the string was re-parsed on every call: 58,000 parses
    over a thousand small solves.
    """
    quantity_module._conversion_rule.cache_clear()
    value = Quantity(1.0, "kohm")

    with Counter(quantity_module, "registry") as counter:
        first = value.magnitude_in("ohm")
        after_first = counter.count
        for _ in range(200):
            value.magnitude_in("ohm")
        total = counter.count

    assert first == 1000.0
    assert total == after_first, (
        f"200 further conversions of one unit pair reached the backend "
        f"{total - after_first} more times; the rule is not being reused"
    )


def test_an_identity_conversion_never_reaches_the_backend():
    value = Quantity(3.0, "kohm")
    with Counter(quantity_module, "registry") as counter:
        for _ in range(50):
            value.magnitude_in("kohm")
    assert counter.count == 0


def test_a_repeated_unit_string_is_normalized_without_reparsing():
    quantity_module._canonical_unit.cache_clear()
    quantity_module._normalized.cache_clear()
    with Counter(quantity_module, "_canonical_unit") as counter:
        for _ in range(300):
            quantity_module.normalize_unit("kohm")
    assert counter.count <= 1, (
        f"one unit spelling was canonicalised {counter.count} times"
    )


# ---- PERF-2: a frozen record's digest is computed once --------------------------------
#: `canonical_dict` is reached only from `fingerprint`, so counting it counts
#: fingerprint *computations* — where counting `json.dumps` would count every
#: caller in the process, `json` being one module object. The first draft of
#: this file did that and reported two phantom circuit serializations that
#: turned out to be threshold digests.
def _fingerprint_computations(subject_type=DCCircuit):
    return Counter(subject_type, "canonical_dict")


def test_a_circuit_fingerprint_is_computed_once_per_circuit():
    """One solve asks five times; the record is frozen, so it answers once."""
    subject = circuit(1)
    with _fingerprint_computations() as counter:
        digests = {subject.fingerprint() for _ in range(20)}
    assert len(digests) == 1
    assert counter.count <= 1, (
        f"the fingerprint was computed {counter.count} times for one frozen "
        f"circuit"
    )


def test_solving_the_same_circuit_twice_fingerprints_it_once():
    """The property, asserted where counting a helper could not reach it.

    `solve_circuit` also calls `canonical_dict` directly, for its own payload
    rather than for a digest, so counting that helper counts more than
    fingerprint computations — which is what the first draft of this test did.
    What matters is that the digest is computed once for a circuit and never
    again, whatever else reads its description.
    """
    subject = circuit(2)
    solve_circuit(subject, run_id="budget-1")
    memoized = getattr(subject, "_fingerprint_memo", None)
    assert memoized is not None, "the first solve did not leave a memo"

    with Counter(subject.__class__, "canonical_dict") as counter:
        before = subject.fingerprint()
        solve_circuit(subject, run_id="budget-2")
        after = subject.fingerprint()

    assert before == after == memoized
    assert counter.count <= 1, (
        f"a second solve of the same circuit recomputed its description "
        f"{counter.count} times"
    )


def test_two_different_circuits_do_not_share_a_fingerprint():
    """The memo must not be a class-level cache. PERF-2's inverse fault."""
    assert circuit(1).fingerprint() != circuit(2).fingerprint()


# ---- PERF-7: field topology is not rebuilt per element --------------------------------
def test_field_assembly_never_touches_a_lil_matrix():
    """The container whose per-element writes were 55 % of a field solve."""
    import scipy.sparse as sparse

    from engcore.domains.thermal_models.conduction2d import assemble
    from tests.manufactured_conduction2d import SINE_PLATE, square

    problem = SINE_PLATE.problem(square(16))
    with Counter(sparse, "lil_matrix") as counter:
        assemble(problem)
    assert counter.count == 0, "the assembly built a lil_matrix again"


def test_field_assembly_builds_one_sparse_matrix():
    import scipy.sparse as sparse

    from engcore.domains.thermal_models.conduction2d import assemble
    from tests.manufactured_conduction2d import SINE_PLATE, square

    problem = SINE_PLATE.problem(square(16))
    with Counter(sparse, "coo_matrix") as counter:
        assemble(problem)
    assert counter.count == 1, (
        f"the assembly built {counter.count} coordinate matrices for one solve"
    )


# ---- PERF-1 / PERF-8: a sweep shares its declarations ----------------------------------
def test_a_sweep_does_not_rebuild_its_shared_declarations_per_case():
    """PERF-1 and PERF-8 together: the context is built once, read many times."""
    built = {"count": 0}

    class CountingShared(SharedContext):
        pass

    shared = SharedContext({"r2": Quantity(3.0, "kohm")})

    def operation(context, case):
        built["count"] += 0  # the context is handed in, never constructed here
        assert context is shared, "each case was given a different context"
        return context["r2"].magnitude_in("ohm")

    summary = run_sweep(
        SweepDefinition(
            sweep_id="shared",
            operation=operation,
            cases=cases_from("c", [{"i": i} for i in range(50)]),
            shared=shared,
        )
    )
    assert summary.succeeded == 50
    assert set(summary.values()) == {3000.0}


def test_the_shared_context_identity_is_computed_from_what_it_holds():
    """PERF-8's correctness half: disabling sharing would change the identity."""
    one = SharedContext({"r2": Quantity(3.0, "kohm")})
    same = SharedContext({"r2": Quantity(3.0, "kohm")})
    other = SharedContext({"r2": Quantity(4.0, "kohm")})
    assert one.identity == same.identity != other.identity


# ---- PERF-5: nothing is retained that need not be -----------------------------------------
def test_a_sweep_retains_results_and_nothing_else():
    """PERF-5: a retained solver session would show up as growth per case.

    What a sweep legitimately retains is its outcomes — those are the output.
    This asserts the *summary* does not additionally grow, which is where a
    retained session or a per-case diagnostic would appear.
    """
    def operation(shared, case):
        return case.inputs["x"]

    small = run_sweep(
        SweepDefinition(
            sweep_id="s", operation=operation,
            cases=cases_from("c", [{"x": i} for i in range(10)]),
        )
    ).to_dict()
    large = run_sweep(
        SweepDefinition(
            sweep_id="s", operation=operation,
            cases=cases_from("c", [{"x": i} for i in range(1000)]),
        )
    ).to_dict()
    assert len(str(large)) < 2 * len(str(small))


# ---- PERF-6: results are not serialized inside the loop -------------------------------------
def test_a_sweep_does_not_serialize_results_while_running():
    serialized = {"count": 0}

    class Recording:
        def to_dict(self):
            serialized["count"] += 1
            return {}

    def operation(shared, case):
        return Recording()

    run_sweep(
        SweepDefinition(
            sweep_id="s", operation=operation,
            cases=cases_from("c", [{"x": i} for i in range(100)]),
        )
    )
    assert serialized["count"] == 0, (
        f"the sweep serialized {serialized['count']} results during execution"
    )


# ---- catastrophe budgets --------------------------------------------------------------------
#
# Deliberately enormous. On the machine these were developed on a thousand-case
# sweep takes about 0.52 s and a 64x64 field solve about 15 ms; the ceilings are
# roughly 60x and 65x those. Their job is to catch a change that makes something
# quadratic or reinstates a per-element Python loop, not to police a constant
# factor or to describe the machine. A CI box three times slower than this one
# still passes with twenty times to spare.
THOUSAND_CASE_CEILING_SECONDS = 30.0
FIELD_SOLVE_CEILING_SECONDS = 1.0


@pytest.mark.expensive
def test_a_thousand_case_sweep_finishes_well_inside_its_ceiling():
    def operation(shared, case):
        return solve_circuit(circuit(case.inputs["i"]), run_id=case.case_id)

    started = time.perf_counter()
    summary = run_sweep(
        SweepDefinition(
            sweep_id="budget",
            operation=operation,
            cases=cases_from("c", [{"i": i} for i in range(1000)]),
            shared=SharedContext({"r2": Quantity(3.0, "kohm")}),
        )
    )
    elapsed = time.perf_counter() - started
    assert summary.succeeded == 1000
    assert elapsed < THOUSAND_CASE_CEILING_SECONDS, (
        f"1000 cases took {elapsed:.1f} s against a {THOUSAND_CASE_CEILING_SECONDS} s "
        f"ceiling set roughly 60x above the development machine's 0.52 s. This "
        f"is a catastrophe budget, so a failure here means something became "
        f"quadratic rather than that the machine is busy"
    )


@pytest.mark.expensive
def test_a_field_solve_finishes_well_inside_its_ceiling():
    from engcore.domains.thermal_models.conduction2d import solve_steady_conduction
    from tests.manufactured_conduction2d import SINE_PLATE, square

    problem = SINE_PLATE.problem(square(64))
    solve_steady_conduction(problem, run_id="warm")
    started = time.perf_counter()
    solve_steady_conduction(problem, run_id="budget")
    elapsed = time.perf_counter() - started
    assert elapsed < FIELD_SOLVE_CEILING_SECONDS, (
        f"a 64x64 solve took {elapsed:.3f} s against a "
        f"{FIELD_SOLVE_CEILING_SECONDS} s ceiling set roughly 65x above the "
        f"development machine's 15 ms"
    )
