"""Guards for the scaling properties this round established. Counts, not clocks.

WHY THESE ARE NOT TIMING ASSERTIONS
-----------------------------------
The machine these were developed on is a mobile i7 on the Balanced power scheme,
and its measured round-to-round spread of the *median* is 8.6 % for
``normalize_unit`` and 10.5 % for a ``Quantity`` construction. A CI threshold
tighter than that is a false-alarm generator; one loose enough to survive it
would not catch a 2x regression on a micro-operation. **A wall-clock gate here
would describe the machine, not the code.**

So the guards below assert two things that are reproducible anywhere -- in CI,
under a debugger, on a busy laptop:

**Call counts.** "This path parses a unit string once, not four times" is a
statement about the algorithm. It is exactly the statement that identified every
defect this round fixed, and it does not move with the weather.

**Growth exponents.** Where a count is not available, the guard compares work at
two input sizes with a band wide enough that only a change of *exponent* can
trip it: a 10x input must not cost more than 25x. Linear passes at ~10x with
enormous margin; the quadratics this round removed were at 90-230x. The band is
deliberately loose, because its job is to catch O(n^2) coming back, not to
police a constant factor.

WHAT IS DELIBERATELY NOT GUARDED
--------------------------------
Absolute latency. No test here says "this must take under N milliseconds",
because that number is a property of the machine that ran it. The measured
baselines live in ``benchmarks/performance/results/`` with the machine record
attached, which is where a human compares them.
"""

from __future__ import annotations

import time

import pytest

from src.engcore.scientific.consensus import (
    ComponentKind,
    CrossSolverConsensus,
    SharedComponent,
    SolveRoute,
)
from src.engcore.scientific.models import definition as definition_module
from src.engcore.scientific.models.definition import (
    RangeCondition,
    UnknownCondition,
    UnknownReason,
    ValidityAssessment,
    ValidityStatus,
)
from src.engcore.scientific.results.provenance import ProvenanceRecord
from src.engcore.scientific.results.thresholds import VerificationThresholds
from src.engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationOutcome,
    ValidationReport,
)
from src.engcore.scientific.solvers.protocol import SolverIdentity
from src.engcore.scientific.units import quantity as quantity_module
from src.engcore.scientific.units.quantity import Quantity

BOUNDS = dict(
    minimum=Quantity(0.0, "dimensionless"),
    maximum=Quantity(1.0, "dimensionless"),
)

#: A 10x input may cost up to this multiple before the guard calls it a change
#: of exponent. Linear is ~10x; the quadratics removed this round were 90-230x.
GROWTH_BAND = 25.0


class _Counter:
    """Count calls to one module-level function, then put it back."""

    def __init__(self, module, name):
        self.module, self.name, self.count = module, name, 0
        self._original = getattr(module, name)

    def __enter__(self):
        original = self._original

        def counted(*args, **kwargs):
            self.count += 1
            return original(*args, **kwargs)

        setattr(self.module, self.name, counted)
        return self

    def __exit__(self, *exc):
        setattr(self.module, self.name, self._original)


def _elapsed(operation, *, repeats: int) -> float:
    """Best-of wall time. Best-of, not mean: the minimum is the run least
    disturbed by the scheduler, which is the right estimator for a ratio."""
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        operation()
        best = min(best, time.perf_counter() - start)
    return best


# ============================================== unit layer: exact call counts


def test_getting_a_number_out_of_a_quantity_parses_its_unit_once():
    """`magnitude_in` did FOUR unit parses to hand back a float it already had.

    Two came from `to` (`normalize_unit`, then `require_compatible` through
    `dimension_of`), and two more from constructing the returned `Quantity`.
    99.5 % of real calls ask for the unit the value already carries, so all four
    were spent to multiply by one.
    """
    quantity = Quantity(300.0, "kelvin")
    with _Counter(quantity_module, "normalize_unit") as normalize:
        quantity.magnitude_in("kelvin")
    assert normalize.count == 1, (
        f"magnitude_in parsed its unit {normalize.count} times; converting a "
        f"value into the unit it already carries needs exactly one parse to "
        f"validate the target and no conversion at all"
    )


def test_an_identity_conversion_does_not_reach_the_units_backend():
    """The short-circuit must actually short-circuit.

    Counted at `registry()`, which every backend operation goes through. A
    regression that reinstated the round trip would show here as a non-zero
    count long before it showed as a slow benchmark.
    """
    quantity = Quantity(300.0, "kelvin")
    with _Counter(quantity_module, "registry") as backend:
        quantity.to("kelvin")
        quantity.magnitude_in("kelvin")
    assert backend.count == 0, (
        f"an identity conversion reached the units backend {backend.count} "
        f"times; it should be a string comparison"
    )

    # ...and a REAL conversion still does, or the short-circuit is too greedy.
    with _Counter(quantity_module, "registry") as backend:
        quantity.to("millikelvin")
    assert backend.count > 0


def test_a_repeated_unit_string_is_canonicalised_once():
    """The memo, asserted as a count rather than as a duration."""
    quantity_module.clear_unit_caches()
    before = quantity_module.unit_cache_stats()["misses"]
    for _ in range(500):
        quantity_module.normalize_unit("watt/meter/kelvin")
    after = quantity_module.unit_cache_stats()["misses"]
    assert after - before == 1, (
        f"500 canonicalisations of one unit string cost {after - before} "
        f"parses; the registry cannot change, so it should cost one"
    )


def test_the_memo_stays_bounded_under_pressure():
    """A bound that is not enforced is a comment."""
    stats = quantity_module.unit_cache_stats()
    assert stats["currsize"] <= stats["maxsize"]


# ==================================== dependency ordering: work per condition


@pytest.mark.parametrize("size", [50, 200])
def test_ordering_a_chain_reads_each_conditions_requirements_a_bounded_number_of_times(size):
    """The quadratic, guarded where it actually lived.

    The previous implementation rescanned every pending condition on every
    layer, so a CHAIN -- which resolves one condition per layer -- read the
    requirement list O(n^2) times. Flat and fan graphs resolved in a single
    layer and never showed it.

    A constant multiple of n is the invariant; the exact constant is an
    implementation detail and is not pinned.
    """
    conditions = tuple(
        RangeCondition(
            name=f"c{i:05d}",
            requires=(f"c{i - 1:05d}",) if i else (),
            **BOUNDS,
        )
        for i in range(size)
    )
    with _Counter(definition_module, "_required_names") as reads:
        definition_module._dependency_order(conditions)
    assert reads.count <= 4 * size, (
        f"ordering a {size}-deep chain read requirements {reads.count} times "
        f"({reads.count / size:.1f} per condition). The rescan-per-layer form "
        f"cost about {size // 2} per condition"
    )


def test_ordering_still_refuses_a_cycle_and_a_missing_prerequisite():
    """A faster sort that stopped refusing would be a correctness regression."""
    cyclic = (
        RangeCondition(name="a", requires=("b",), **BOUNDS),
        RangeCondition(name="b", requires=("a",), **BOUNDS),
    )
    with pytest.raises(definition_module.ModelValidityError, match="cycle"):
        definition_module._dependency_order(cyclic)

    dangling = (RangeCondition(name="a", requires=("ghost",), **BOUNDS),)
    with pytest.raises(definition_module.ModelValidityError, match="not a condition"):
        definition_module._dependency_order(dangling)


def test_declaration_order_within_a_layer_is_preserved():
    """The ordering contract the faster algorithm had to reproduce exactly."""
    conditions = tuple(
        RangeCondition(name=f"c{i}", **BOUNDS) for i in range(6)
    )
    ordered = definition_module._dependency_order(conditions)
    assert [c.name for c in ordered] == [c.name for c in conditions]


# ============================================ growth exponents, loosely banded


def _growth(build, small: int, large: int, *, repeats: int = 5) -> float:
    small_time = _elapsed(lambda: build(small), repeats=repeats)
    large_time = _elapsed(lambda: build(large), repeats=repeats)
    return large_time / max(small_time, 1e-9)


def test_validation_report_construction_grows_linearly_with_its_checks():
    """Was O(n^2) through `names.count(name)`: 684 ms at 10,000 checks."""

    def build(size):
        checks = tuple(
            ValidationCheck(
                name=f"check_{i:06d}",
                outcome=ValidationOutcome.PASS,
                detail="d",
            )
            for i in range(size)
        )
        return ValidationReport(checks=checks)

    growth = _growth(build, 200, 2_000)
    assert growth < GROWTH_BAND, (
        f"10x the checks cost {growth:.1f}x the time; a linear duplicate scan "
        f"is ~10x and the `.count()` form this replaced was ~90x"
    )


def test_validity_assessment_construction_grows_linearly_with_its_unknowns():
    """Was O(n^2) twice over -- the duplicate scan AND the coverage check."""

    def build(size):
        names = tuple(f"c{i:06d}" for i in range(size))
        reasons = tuple(
            UnknownCondition(name=n, reason=UnknownReason.NOT_SUPPLIED)
            for n in names
        )
        return ValidityAssessment(
            status=ValidityStatus.UNKNOWN, unknown=names, unknown_reasons=reasons
        )

    growth = _growth(build, 200, 2_000)
    assert growth < GROWTH_BAND, (
        f"10x the unknown conditions cost {growth:.1f}x the time; this path "
        f"was ~170x before the set was hoisted out of the comprehension"
    )


def test_consensus_completeness_grows_linearly_with_required_outputs():
    """Was O(routes x Q^2) through membership against a tuple."""
    thresholds = VerificationThresholds(
        gate_id="guard", version="1", values={"rel_tol": 1e-9}, basis="fixture"
    )
    routes = tuple(
        SolveRoute(
            route_id=f"r{i}",
            solver=SolverIdentity(f"s{i}", "1"),
            components=frozenset(
                {SharedComponent(kind=ComponentKind.IMPLEMENTATION, name=f"i{i}")}
            ),
        )
        for i in range(2)
    )

    def build(size):
        names = tuple(f"q_{j:06d}" for j in range(size))
        values = {f"r{i}": {n: 1.0 for n in names} for i in range(2)}
        consensus = CrossSolverConsensus.over(
            consensus_id="guard", routes=routes, values=values,
            thresholds=thresholds, tolerance_key="rel_tol",
            required_outputs=names,
        )
        return consensus.missing_outputs

    growth = _growth(build, 200, 2_000)
    assert growth < GROWTH_BAND, (
        f"10x the required outputs cost {growth:.1f}x the time; membership "
        f"against a tuple made this ~90x"
    )


def test_provenance_construction_grows_linearly_with_its_inputs():
    """Not a defect this round fixed -- a guard that it stays linear."""

    def build(size):
        inputs = {f"in_{i:06d}": Quantity(float(i), "kelvin") for i in range(size)}
        return ProvenanceRecord(run_id="guard", inputs=inputs)

    growth = _growth(build, 200, 2_000)
    assert growth < GROWTH_BAND, f"10x the inputs cost {growth:.1f}x the time"
