"""Deliberate leakage probes. Every one of them must be refused.

Phase 17 asks for five, and they are each a separate test below:

    a held-out observation accidentally included in calibration
    a posterior built from the held-out dataset
    a reused evidence identity (the two halves sharing a dataset id)
    the same observation duplicated under another label
    calibration and validation aliasing the same source

The fourth is the one a label-based check cannot see, and it is the reason this
module exists rather than a comparison of `dataset_id` strings.
"""

from __future__ import annotations

import pytest

from engcore.inference.grid import GaussianObservation, InferenceProblemError, ObservationSet
from engcore.inference.split import (
    DataLeakageError,
    ObservationSplit,
    observation_content_digest,
    require_split,
)
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity

TWIN = TwinReference(twin_id="conductor.copper.sample_a", version="1")
OTHER_TWIN = TwinReference(twin_id="conductor.copper.sample_b", version="1")


def observation(condition: str, value: float, sigma: float = 0.01) -> GaussianObservation:
    return GaussianObservation(
        condition_id=condition,
        observable_name="resistance",
        value=Quantity(value, "ohm"),
        sigma=Quantity(sigma, "ohm"),
        source_ref="bench/run-1",
    )


def source(n: int = 6) -> ObservationSet:
    return ObservationSet(
        observations=tuple(
            observation(f"T{i}", 1.0 + 0.05 * i) for i in range(n)
        ),
        dataset_id="tcr.bench.2026-09",
    )


def partition(**overrides):
    kwargs = dict(
        source=source(),
        held_out_condition_ids=("T4", "T5"),
        twin=TWIN,
        calibration_dataset_id="tcr.calibration",
        heldout_dataset_id="tcr.heldout",
    )
    kwargs.update(overrides)
    return ObservationSplit.partition(**kwargs)


# =====================================================================
# The happy path, so the refusals below mean something
# =====================================================================

def test_a_partition_produces_two_disjoint_halves():
    split = partition()
    assert split.calibration.keys == (
        "T0:resistance", "T1:resistance", "T2:resistance", "T3:resistance",
    )
    assert split.held_out.keys == ("T4:resistance", "T5:resistance")
    assert not set(split.calibration.keys) & set(split.held_out.keys)
    assert split.calibration_dataset_id == "tcr.calibration"
    assert split.heldout_dataset_id == "tcr.heldout"


def test_the_split_digest_covers_both_halves():
    a = partition()
    b = partition(held_out_condition_ids=("T3", "T5"))
    assert a.digest != b.digest


# =====================================================================
# PROBE 1 -- a held-out observation also present in calibration
# =====================================================================

def test_an_observation_in_both_halves_is_refused():
    shared = observation("T9", 2.0)
    with pytest.raises(DataLeakageError, match="appear in both"):
        ObservationSplit(
            calibration=ObservationSet((observation("T0", 1.0), shared), "cal"),
            held_out=ObservationSet((observation("T4", 1.2), shared), "heldout"),
            twin=TWIN,
            source_dataset_id="tcr.bench.2026-09",
        )


def test_partition_cannot_produce_that_state_at_all():
    """The constructor refuses it; the factory cannot reach it.

    Partitioning is by condition_id over one source, so an observation is on
    exactly one side by construction. Both guarantees are wanted: the factory
    makes the good path easy, the constructor makes the bad path impossible.
    """
    split = partition()
    assert not set(split.calibration.keys) & set(split.held_out.keys)


# =====================================================================
# PROBE 2 -- a posterior built from the held-out dataset
# =====================================================================

def test_a_posterior_conditioned_on_the_heldout_set_is_refused():
    split = partition()
    with pytest.raises(DataLeakageError, match="HELD-OUT set"):
        split.require_posterior_was_fitted_here("tcr.heldout")


def test_a_posterior_from_a_third_dataset_is_refused():
    split = partition()
    with pytest.raises(DataLeakageError, match="neither half"):
        split.require_posterior_was_fitted_here("some.other.study")


def test_the_calibration_posterior_is_accepted():
    partition().require_posterior_was_fitted_here("tcr.calibration")


# =====================================================================
# PROBE 3 -- a reused evidence identity
# =====================================================================

def test_two_halves_sharing_a_dataset_id_are_refused():
    with pytest.raises(DataLeakageError, match="share the dataset id"):
        ObservationSplit(
            calibration=ObservationSet((observation("T0", 1.0),), "same.id"),
            held_out=ObservationSet((observation("T4", 1.2),), "same.id"),
            twin=TWIN,
            source_dataset_id="tcr.bench.2026-09",
        )


def test_a_heldout_result_scored_against_the_wrong_dataset_is_refused():
    split = partition()
    with pytest.raises(DataLeakageError, match="cites"):
        split.require_scored_against_held_out("tcr.calibration")
    split.require_scored_against_held_out("tcr.heldout")


# =====================================================================
# PROBE 4 -- the same observation under another label
# =====================================================================

def test_the_same_reading_relabelled_into_the_other_half_is_refused():
    """The probe a dataset_id comparison cannot see.

    Different condition_id, so the keys differ and every key-based check is
    satisfied. Same observable, same value, same sigma -- the model is scored
    on a number it was fitted to.
    """
    reading = observation("T1", 1.05)
    relabelled = observation("T1_copy", 1.05)
    assert reading.key != relabelled.key
    assert observation_content_digest(reading) == observation_content_digest(relabelled)

    with pytest.raises(DataLeakageError, match="under different labels"):
        ObservationSplit(
            calibration=ObservationSet((observation("T0", 1.0), reading), "cal"),
            held_out=ObservationSet((relabelled,), "heldout"),
            twin=TWIN,
            source_dataset_id="tcr.bench.2026-09",
        )


def test_the_content_digest_ignores_the_label_and_the_source():
    """It is a digest of what the observation says, not of who said it."""
    a = GaussianObservation("T1", "resistance", Quantity(1.05, "ohm"),
                            Quantity(0.01, "ohm"), "bench/run-1")
    b = GaussianObservation("T2", "resistance", Quantity(1.05, "ohm"),
                            Quantity(0.01, "ohm"), "import/spreadsheet")
    assert observation_content_digest(a) == observation_content_digest(b)


def test_the_content_digest_is_unit_aware_rather_than_magnitude_aware():
    """0.01 ohm and 10 milliohm are one sigma, not two."""
    in_ohm = GaussianObservation("T1", "resistance", Quantity(1.05, "ohm"),
                                 Quantity(0.01, "ohm"), "s")
    in_milliohm = GaussianObservation("T2", "resistance", Quantity(1.05, "ohm"),
                                      Quantity(10.0, "milliohm"), "s")
    assert observation_content_digest(in_ohm) == observation_content_digest(in_milliohm)


def test_a_different_sigma_is_different_content():
    a = observation("T1", 1.05, sigma=0.01)
    b = observation("T2", 1.05, sigma=0.02)
    assert observation_content_digest(a) != observation_content_digest(b)


def test_declared_exact_replicates_are_allowed_through():
    """The escape hatch exists, and it is visible at the call site."""
    reading = observation("T1", 1.05)
    relabelled = observation("T1_copy", 1.05)
    split = ObservationSplit(
        calibration=ObservationSet((observation("T0", 1.0), reading), "cal"),
        held_out=ObservationSet((relabelled,), "heldout"),
        twin=TWIN,
        source_dataset_id="tcr.bench.2026-09",
        exact_replicates_allowed=True,
    )
    assert split.exact_replicates_allowed
    # and it is part of the digest, so a study cannot turn it on unnoticed
    assert split.digest != ObservationSplit(
        calibration=ObservationSet((observation("T0", 1.0), reading), "cal"),
        held_out=ObservationSet((observation("T9", 9.0),), "heldout"),
        twin=TWIN,
        source_dataset_id="tcr.bench.2026-09",
    ).digest


# =====================================================================
# PROBE 5 -- calibration and validation aliasing one source
# =====================================================================

def test_holding_out_every_condition_leaves_nothing_to_calibrate_on():
    with pytest.raises(InferenceProblemError, match="nothing to calibrate"):
        partition(held_out_condition_ids=tuple(f"T{i}" for i in range(6)))


def test_holding_out_nothing_is_refused():
    with pytest.raises(InferenceProblemError, match="at least one condition"):
        partition(held_out_condition_ids=())


def test_holding_out_a_condition_that_is_not_there_is_refused():
    with pytest.raises(InferenceProblemError, match="not present in"):
        partition(held_out_condition_ids=("T4", "T99"))


# =====================================================================
# Twin identity
# =====================================================================

def test_a_split_requires_a_twin():
    with pytest.raises(InferenceProblemError, match="TwinReference"):
        partition(twin="conductor.copper.sample_a")


def test_the_twin_is_part_of_the_split_digest():
    assert partition().digest != partition(twin=OTHER_TWIN).digest


# =====================================================================
# The type is the boundary
# =====================================================================

def test_two_observation_sets_side_by_side_are_not_a_split():
    with pytest.raises(InferenceProblemError, match="ObservationSplit"):
        require_split((source(), source()))


def test_a_split_passes_its_own_guard():
    split = partition()
    assert require_split(split) is split


def test_partitioning_is_by_condition_not_by_observable():
    """Splitting within one condition is unavailable, not merely discouraged.

    Fitting the voltage and holding out the current from the same run leaks
    through the physics even though no key is shared. The factory takes
    condition ids, so there is no argument that expresses that split.
    """
    multi = ObservationSet(
        observations=(
            GaussianObservation("T0", "resistance", Quantity(1.0, "ohm"),
                                Quantity(0.01, "ohm"), "s"),
            GaussianObservation("T0", "voltage", Quantity(0.5, "volt"),
                                Quantity(0.001, "volt"), "s"),
            GaussianObservation("T1", "resistance", Quantity(1.1, "ohm"),
                                Quantity(0.01, "ohm"), "s"),
            GaussianObservation("T1", "voltage", Quantity(0.6, "volt"),
                                Quantity(0.001, "volt"), "s"),
        ),
        dataset_id="multi",
    )
    split = ObservationSplit.partition(
        source=multi,
        held_out_condition_ids=("T1",),
        twin=TWIN,
        calibration_dataset_id="cal",
        heldout_dataset_id="heldout",
    )
    assert split.held_out.keys == ("T1:resistance", "T1:voltage")
    assert split.calibration.keys == ("T0:resistance", "T0:voltage")
